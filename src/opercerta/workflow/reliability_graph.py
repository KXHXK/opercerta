from typing import TYPE_CHECKING, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.operation_state import ApprovalResume, OperationSnapshot, RecoveryView
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class ReliabilityState(TypedDict):
    operation_id: str
    snapshot: dict[str, JsonValue]
    approval: dict[str, JsonValue] | None
    work_order: dict[str, JsonValue] | None
    replayed: bool
    recovery_action: str | None


ReliabilityGraph = CompiledStateGraph[
    ReliabilityState,
    None,
    ReliabilityState,
    ReliabilityState,
]


def build_initial_state(view: RecoveryView) -> ReliabilityState:
    return ReliabilityState(
        operation_id=str(view.operation_id),
        snapshot=cast(
            dict[str, JsonValue],
            view.snapshot.model_dump(mode="json"),
        ),
        approval=None,
        work_order=None,
        replayed=False,
        recovery_action=None,
    )


def build_reliability_graph(
    checkpointer: "AsyncPostgresSaver",
    operation_states: OperationStateRepository,
    work_orders: WorkOrderRepository,
) -> ReliabilityGraph:
    def operation_id(state: ReliabilityState) -> UUID:
        try:
            return UUID(state["operation_id"])
        except (KeyError, TypeError, ValueError):
            raise RecoveryStateConflict(
                UUID(int=0),
                "invalid_graph_operation_id",
            ) from None

    def snapshot(state: ReliabilityState) -> OperationSnapshot:
        target = operation_id(state)
        try:
            return OperationSnapshot.model_validate(state["snapshot"])
        except (KeyError, ValidationError):
            raise RecoveryStateConflict(target, "invalid_graph_snapshot") from None

    def approval(state: ReliabilityState) -> ApprovalResume:
        target = operation_id(state)
        try:
            return ApprovalResume.model_validate(state["approval"])
        except (KeyError, ValidationError):
            raise RecoveryStateConflict(target, "invalid_graph_approval") from None

    async def prepare_approval(state: ReliabilityState) -> dict[str, object]:
        await operation_states.mark_awaiting_approval(operation_id(state))
        return {}

    def request_approval(state: ReliabilityState) -> dict[str, object]:
        frozen = snapshot(state)
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "risk": frozen.risk,
                "plan": frozen.plan,
            }
        )
        try:
            decision = ApprovalResume.model_validate(resumed)
        except ValidationError:
            raise RecoveryStateConflict(
                operation_id(state),
                "invalid_approval_resume",
            ) from None
        return {"approval": decision.model_dump(mode="json")}

    def route_decision(state: ReliabilityState) -> str:
        return approval(state).decision.value

    async def mark_executing(state: ReliabilityState) -> dict[str, object]:
        decision = approval(state)
        await operation_states.mark_executing(
            operation_id(state),
            decision.approval_id,
        )
        return {}

    async def execute_work_order(state: ReliabilityState) -> dict[str, object]:
        result = await work_orders.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id(state),
                payload=snapshot(state).work_order_payload,
            )
        )
        return {
            "work_order": {
                "work_order_id": str(result.work_order.id),
                "payload_hash": result.work_order.payload_hash,
            },
            "replayed": result.replayed,
        }

    def work_order_locator(state: ReliabilityState) -> tuple[UUID, str]:
        target = operation_id(state)
        value = state["work_order"]
        if not isinstance(value, dict) or set(value) != {
            "work_order_id",
            "payload_hash",
        }:
            raise RecoveryStateConflict(target, "invalid_graph_work_order")
        work_order_id = value["work_order_id"]
        payload_hash = value["payload_hash"]
        if not isinstance(work_order_id, str) or not isinstance(payload_hash, str):
            raise RecoveryStateConflict(target, "invalid_graph_work_order")
        try:
            return UUID(work_order_id), payload_hash
        except ValueError:
            raise RecoveryStateConflict(target, "invalid_graph_work_order") from None

    async def mark_verifying(state: ReliabilityState) -> dict[str, object]:
        work_order_id, _ = work_order_locator(state)
        await operation_states.mark_verifying(operation_id(state), work_order_id)
        return {}

    async def verify_work_order(state: ReliabilityState) -> dict[str, object]:
        target = operation_id(state)
        expected_id, expected_hash = work_order_locator(state)
        view = await operation_states.load_recovery_view(target)
        if view.work_order_id != expected_id or view.payload_hash != expected_hash:
            raise RecoveryStateConflict(
                target,
                "work_order_verification_mismatch",
            )
        return {}

    async def mark_completed(state: ReliabilityState) -> dict[str, object]:
        work_order_id, _ = work_order_locator(state)
        await operation_states.mark_completed(operation_id(state), work_order_id)
        return {}

    async def mark_rejected(state: ReliabilityState) -> dict[str, object]:
        decision = approval(state)
        await operation_states.mark_rejected(
            operation_id(state),
            decision.approval_id,
        )
        return {}

    builder = StateGraph(ReliabilityState)
    builder.add_node("prepare_approval", prepare_approval)
    builder.add_node("request_approval", request_approval)
    builder.add_node("mark_executing", mark_executing)
    builder.add_node("execute_work_order", execute_work_order)
    builder.add_node("mark_verifying", mark_verifying)
    builder.add_node("verify_work_order", verify_work_order)
    builder.add_node("mark_completed", mark_completed)
    builder.add_node("mark_rejected", mark_rejected)
    builder.add_edge(START, "prepare_approval")
    builder.add_edge("prepare_approval", "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_decision,
        {
            "approved": "mark_executing",
            "rejected": "mark_rejected",
        },
    )
    builder.add_edge("mark_executing", "execute_work_order")
    builder.add_edge("execute_work_order", "mark_verifying")
    builder.add_edge("mark_verifying", "verify_work_order")
    builder.add_edge("verify_work_order", "mark_completed")
    builder.add_edge("mark_completed", END)
    builder.add_edge("mark_rejected", END)
    return builder.compile(checkpointer=checkpointer)
