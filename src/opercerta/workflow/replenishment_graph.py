import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    DependencyUnavailable,
    EvidenceExpired,
    EvidenceUnavailable,
    InvalidInventoryEvidence,
    InvalidPolicyEvidence,
    InventoryNotFound,
    ReplenishmentQuantityOutOfPolicy,
)
from opercerta.domain.model_gateway import ModelGateway
from opercerta.domain.replenishment import (
    ApprovalBinding,
    EvidenceBundle,
    InventoryEvidence,
    ModelPlanExplanation,
    OperationError,
    OperationResult,
    PolicyEvidence,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    assess_replenishment,
    build_approval_binding,
    build_plan,
)
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class EvidenceGateway(Protocol):
    async def get_inventory(self, sku: str) -> object:
        raise NotImplementedError

    async def get_policy(self, sku: str) -> object:
        raise NotImplementedError


class ReplenishmentState(TypedDict):
    operation_id: str
    request: dict[str, JsonValue]
    evidence: dict[str, JsonValue] | None
    assessment: dict[str, JsonValue] | None
    plan: dict[str, JsonValue] | None
    approval_binding: dict[str, JsonValue] | None
    approval: dict[str, JsonValue] | None
    work_order: dict[str, JsonValue] | None
    result: dict[str, JsonValue] | None
    error: dict[str, JsonValue] | None
    replayed: bool


ReplenishmentGraph = CompiledStateGraph[
    ReplenishmentState,
    None,
    ReplenishmentState,
    ReplenishmentState,
]


def build_replenishment_initial_state(
    operation_id: UUID,
    request: OperationRequest,
) -> ReplenishmentState:
    return ReplenishmentState(
        operation_id=str(operation_id),
        request=cast(dict[str, JsonValue], request.model_dump(mode="json")),
        evidence=None,
        assessment=None,
        plan=None,
        approval_binding=None,
        approval=None,
        work_order=None,
        result=None,
        error=None,
        replayed=False,
    )


def build_replenishment_graph(
    checkpointer: "AsyncPostgresSaver",
    operations: ReplenishmentOperationRepository,
    evidence_repository: EvidenceRepository,
    gateway: EvidenceGateway,
    model_gateway: ModelGateway,
    clock: Callable[[], datetime],
    *,
    approval_ttl_seconds: int = 300,
) -> ReplenishmentGraph:
    if approval_ttl_seconds < 1:
        raise ValueError("approval_ttl_seconds must be positive")

    def operation_id(state: ReplenishmentState) -> UUID:
        try:
            return UUID(state["operation_id"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid graph operation ID") from None

    def request(state: ReplenishmentState) -> OperationRequest:
        return OperationRequest.model_validate(state["request"])

    def evidence(state: ReplenishmentState) -> EvidenceBundle:
        return EvidenceBundle.model_validate(state["evidence"])

    def assessment(state: ReplenishmentState) -> ReplenishmentAssessment:
        return ReplenishmentAssessment.model_validate(state["assessment"])

    def plan(state: ReplenishmentState) -> ReplenishmentPlan:
        return ReplenishmentPlan.model_validate(state["plan"])

    def approval_binding(state: ReplenishmentState) -> ApprovalBinding:
        return ApprovalBinding.model_validate(state["approval_binding"])

    def error(state: ReplenishmentState) -> OperationError:
        return OperationError.model_validate(state["error"])

    def error_update(code: str) -> dict[str, object]:
        messages = {
            InventoryNotFound.code: "Inventory item was not found.",
            EvidenceUnavailable.code: "Inventory evidence is unavailable.",
            InvalidInventoryEvidence.code: "Inventory evidence is invalid.",
            InvalidPolicyEvidence.code: "Replenishment policy evidence is invalid.",
            EvidenceExpired.code: "Inventory evidence has expired.",
            ReplenishmentQuantityOutOfPolicy.code: (
                "Recommended replenishment quantity is outside policy."
            ),
            DependencyUnavailable.code: "A required dependency is unavailable.",
        }
        operation_error = OperationError(
            code=code,
            message=messages.get(code, "The operation could not be completed."),
        )
        return {"error": operation_error.model_dump(mode="json")}

    def code_for(exception: Exception) -> str:
        if isinstance(
            exception,
            (
                InventoryNotFound,
                EvidenceUnavailable,
                InvalidInventoryEvidence,
                InvalidPolicyEvidence,
                EvidenceExpired,
                ReplenishmentQuantityOutOfPolicy,
            ),
        ):
            return exception.code
        return DependencyUnavailable.code

    async def parse_request(state: ReplenishmentState) -> dict[str, object]:
        try:
            parsed = request(state)
        except ValidationError:
            return error_update(DependencyUnavailable.code)
        if (
            parsed.requested_action is not ActionType.CREATE_WORK_ORDER
            or parsed.object_type is not ObjectType.INVENTORY
            or parsed.object_id is None
        ):
            return error_update(DependencyUnavailable.code)
        return {"request": parsed.model_dump(mode="json")}

    def route_error(state: ReplenishmentState) -> str:
        return "failure" if state["error"] is not None else "continue"

    async def mark_gathering(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_gathering_evidence(operation_id(state))
        return {}

    async def gather_evidence(state: ReplenishmentState) -> dict[str, object]:
        sku = request(state).object_id
        if sku is None:
            return error_update(DependencyUnavailable.code)
        try:
            raw_inventory, raw_policy = await asyncio.gather(
                gateway.get_inventory(sku),
                gateway.get_policy(sku),
            )
            try:
                inventory = InventoryEvidence.model_validate(raw_inventory)
            except ValidationError:
                raise InvalidInventoryEvidence from None
            try:
                policy = PolicyEvidence.model_validate(raw_policy)
            except ValidationError:
                raise InvalidPolicyEvidence from None
            bundle = EvidenceBundle(inventory=inventory, policy=policy)
            await evidence_repository.save_bundle(operation_id(state), bundle)
            await operations.record_evidence(operation_id(state), bundle)
        except Exception as exception:
            return error_update(code_for(exception))
        return {"evidence": bundle.model_dump(mode="json")}

    async def calculate_assessment(
        state: ReplenishmentState,
    ) -> dict[str, object]:
        try:
            calculated = assess_replenishment(evidence(state), clock())
        except Exception as exception:
            return error_update(code_for(exception))
        return {"assessment": calculated.model_dump(mode="json")}

    def route_assessment(state: ReplenishmentState) -> str:
        if state["error"] is not None:
            return "failure"
        return "low" if assessment(state).replenishment_required else "normal"

    async def record_normal_plan(
        state: ReplenishmentState,
    ) -> dict[str, object]:
        await operations.record_validated_plan(
            operation_id(state),
            assessment(state),
            None,
        )
        return {}

    async def mark_reporting(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_reporting(operation_id(state))
        return {}

    async def complete_without_replenishment(
        state: ReplenishmentState,
    ) -> dict[str, object]:
        result = OperationResult(
            outcome="replenishment_not_required",
            message="Inventory is at or above the approved reorder point.",
        )
        await operations.complete_without_replenishment(
            operation_id(state),
            result,
        )
        return {"result": result.model_dump(mode="json")}

    async def explain_plan(state: ReplenishmentState) -> dict[str, object]:
        try:
            explanation = await model_gateway.explain_plan(assessment(state))
        except Exception:
            return error_update(DependencyUnavailable.code)
        return {"plan": explanation.model_dump(mode="json")}

    async def build_and_validate_plan(
        state: ReplenishmentState,
    ) -> dict[str, object]:
        try:
            explanation = model_gateway_return(state)
            replenishment_plan = build_plan(
                assessment(state),
                explanation,
                evidence(state).policy.rule_version,
            )
        except Exception as exception:
            return error_update(code_for(exception))
        return {"plan": replenishment_plan.model_dump(mode="json")}

    def model_gateway_return(state: ReplenishmentState) -> ModelPlanExplanation:
        return ModelPlanExplanation.model_validate(state["plan"])

    async def record_low_plan(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_validated_plan(
            operation_id(state),
            assessment(state),
            plan(state),
        )
        binding = build_approval_binding(evidence(state), plan(state))
        return {"approval_binding": binding.model_dump(mode="json")}

    async def prepare_approval(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_awaiting_approval(
            operation_id(state),
            approval_binding(state),
            clock() + timedelta(seconds=approval_ttl_seconds),
        )
        return {}

    async def request_approval(state: ReplenishmentState) -> dict[str, object]:
        detail = await operations.load_detail(operation_id(state))
        expires_at = detail.approval_expires_at
        if expires_at is None:
            return error_update(DependencyUnavailable.code)
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "assessment": state["assessment"],
                "plan": state["plan"],
                "approval_binding": state["approval_binding"],
                "approval_expires_at": expires_at.isoformat(),
            }
        )
        return {"approval": cast(dict[str, JsonValue], resumed)}

    async def mark_failed(state: ReplenishmentState) -> dict[str, object]:
        operation_error = error(state)
        await operations.mark_failed(operation_id(state), operation_error)
        return {}

    builder = StateGraph(ReplenishmentState)
    builder.add_node("parse_request", parse_request)
    builder.add_node("mark_gathering", mark_gathering)
    builder.add_node("gather_evidence", gather_evidence)
    builder.add_node("calculate_assessment", calculate_assessment)
    builder.add_node("record_normal_plan", record_normal_plan)
    builder.add_node("mark_reporting", mark_reporting)
    builder.add_node(
        "complete_without_replenishment",
        complete_without_replenishment,
    )
    builder.add_node("explain_plan", explain_plan)
    builder.add_node("build_and_validate_plan", build_and_validate_plan)
    builder.add_node("record_low_plan", record_low_plan)
    builder.add_node("prepare_approval", prepare_approval)
    builder.add_node("request_approval", request_approval)
    builder.add_node("mark_failed", mark_failed)
    builder.add_edge(START, "parse_request")
    builder.add_conditional_edges(
        "parse_request",
        route_error,
        {"continue": "mark_gathering", "failure": "mark_failed"},
    )
    builder.add_edge("mark_gathering", "gather_evidence")
    builder.add_conditional_edges(
        "gather_evidence",
        route_error,
        {"continue": "calculate_assessment", "failure": "mark_failed"},
    )
    builder.add_conditional_edges(
        "calculate_assessment",
        route_assessment,
        {
            "normal": "record_normal_plan",
            "low": "explain_plan",
            "failure": "mark_failed",
        },
    )
    builder.add_edge("record_normal_plan", "mark_reporting")
    builder.add_edge("mark_reporting", "complete_without_replenishment")
    builder.add_edge("complete_without_replenishment", END)
    builder.add_edge("explain_plan", "build_and_validate_plan")
    builder.add_conditional_edges(
        "build_and_validate_plan",
        route_error,
        {"continue": "record_low_plan", "failure": "mark_failed"},
    )
    builder.add_edge("record_low_plan", "prepare_approval")
    builder.add_edge("prepare_approval", "request_approval")
    builder.add_edge("request_approval", END)
    builder.add_edge("mark_failed", END)
    return builder.compile(checkpointer=checkpointer)
