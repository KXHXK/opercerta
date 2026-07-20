import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    ApprovalSnapshotMismatch,
    DependencyUnavailable,
    EvidenceExpired,
    EvidenceUnavailable,
    InvalidTaskEvidence,
    InvalidTaskRecoveryPolicyEvidence,
    TaskNotFound,
    TaskRecoveryOutOfPolicy,
    WorkOrderStorageFailed,
    WorkOrderVerificationFailed,
)
from opercerta.domain.model_gateway import ModelGateway
from opercerta.domain.operation_state import ApprovalResume
from opercerta.domain.replenishment import ModelPlanExplanation, OperationError, OperationResult
from opercerta.domain.scenarios import ApprovalBinding
from opercerta.domain.task_recovery import (
    TaskEvidence,
    TaskRecoveryAssessment,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPlan,
    TaskRecoveryPolicyEvidence,
    TaskRecoveryWorkOrderPayload,
    assess_task_recovery,
    build_task_recovery_approval_binding,
    build_task_recovery_plan,
)
from opercerta.domain.work_orders import WorkOrderCommand, WorkOrderRecord, WorkOrderWriteResult
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.observability.tracing import NOOP_TRACING, Tracing, trace_async_node
from opercerta.workflow.replenishment_graph import ReplenishmentState

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class TaskGateway(Protocol):
    async def get_task(self, task_id: str) -> object: ...

    async def get_task_recovery_policy(self, task_id: str) -> object: ...

    async def create_work_order(
        self, command: WorkOrderCommand, *, plan_hash: str
    ) -> WorkOrderWriteResult: ...

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord: ...


TaskRecoveryGraph = CompiledStateGraph[
    ReplenishmentState, None, ReplenishmentState, ReplenishmentState
]


def build_task_recovery_graph(
    checkpointer: "AsyncPostgresSaver",
    operations: OperationRepository,
    evidence_repository: EvidenceRepository,
    gateway: TaskGateway,
    model_gateway: ModelGateway,
    clock: Callable[[], datetime],
    *,
    initial_gateway: TaskGateway | None = None,
    tracing: Tracing = NOOP_TRACING,
    approval_ttl_seconds: int = 300,
) -> TaskRecoveryGraph:
    if approval_ttl_seconds < 1:
        raise ValueError("approval_ttl_seconds must be positive")
    evidence_gateway = initial_gateway or gateway

    def operation_id(state: ReplenishmentState) -> UUID:
        return UUID(state["operation_id"])

    def request(state: ReplenishmentState) -> OperationRequest:
        return OperationRequest.model_validate(state["request"])

    def evidence(state: ReplenishmentState) -> TaskRecoveryEvidenceBundle:
        return TaskRecoveryEvidenceBundle.model_validate(state["evidence"])

    def assessment(state: ReplenishmentState) -> TaskRecoveryAssessment:
        return TaskRecoveryAssessment.model_validate(state["assessment"])

    def plan(state: ReplenishmentState) -> TaskRecoveryPlan:
        return TaskRecoveryPlan.model_validate(state["plan"])

    def binding(state: ReplenishmentState) -> ApprovalBinding:
        return ApprovalBinding.model_validate(state["approval_binding"])

    def approval(state: ReplenishmentState) -> ApprovalResume:
        return ApprovalResume.model_validate(state["approval"])

    def work_order(state: ReplenishmentState) -> WorkOrderRecord:
        return WorkOrderRecord.model_validate(state["work_order"])

    def error(state: ReplenishmentState) -> OperationError:
        return OperationError.model_validate(state["error"])

    def error_update(code: str) -> dict[str, object]:
        messages = {
            TaskNotFound.code: "Task was not found.",
            EvidenceUnavailable.code: "Task evidence is unavailable.",
            InvalidTaskEvidence.code: "Task evidence is invalid.",
            InvalidTaskRecoveryPolicyEvidence.code: "Task recovery policy is invalid.",
            EvidenceExpired.code: "Task evidence has expired.",
            TaskRecoveryOutOfPolicy.code: "Task retry count is outside recovery policy.",
            ApprovalSnapshotMismatch.code: "Approved task facts no longer match.",
            WorkOrderStorageFailed.code: "The recovery work order could not be stored.",
            WorkOrderVerificationFailed.code: "The recovery work order could not be verified.",
            DependencyUnavailable.code: "A required dependency is unavailable.",
        }
        value = OperationError(
            code=code,
            message=messages.get(code, "The task recovery operation could not be completed."),
        )
        return {"error": value.model_dump(mode="json")}

    def code_for(exception: Exception) -> str:
        stable = (
            TaskNotFound,
            EvidenceUnavailable,
            InvalidTaskEvidence,
            InvalidTaskRecoveryPolicyEvidence,
            EvidenceExpired,
            TaskRecoveryOutOfPolicy,
            ApprovalSnapshotMismatch,
            WorkOrderStorageFailed,
            WorkOrderVerificationFailed,
        )
        return exception.code if isinstance(exception, stable) else DependencyUnavailable.code

    async def parse_request(state: ReplenishmentState) -> dict[str, object]:
        try:
            parsed = request(state)
        except ValidationError:
            return error_update(DependencyUnavailable.code)
        if (
            parsed.requested_action not in {ActionType.QUERY, ActionType.CREATE_WORK_ORDER}
            or parsed.object_type is not ObjectType.TASK
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
        task_id = request(state).object_id
        if task_id is None:
            return error_update(DependencyUnavailable.code)
        try:
            raw_task, raw_policy = await asyncio.gather(
                evidence_gateway.get_task(task_id),
                evidence_gateway.get_task_recovery_policy(task_id),
            )
            try:
                task = TaskEvidence.model_validate(raw_task)
            except ValidationError:
                raise InvalidTaskEvidence from None
            try:
                policy = TaskRecoveryPolicyEvidence.model_validate(raw_policy)
            except ValidationError:
                raise InvalidTaskRecoveryPolicyEvidence from None
            bundle = TaskRecoveryEvidenceBundle(task=task, policy=policy)
            await evidence_repository.save_bundle(operation_id(state), bundle)
            await operations.record_evidence(operation_id(state), bundle)
        except Exception as exception:
            return error_update(code_for(exception))
        return {"evidence": bundle.model_dump(mode="json")}

    async def calculate_assessment(state: ReplenishmentState) -> dict[str, object]:
        try:
            value = assess_task_recovery(evidence(state), clock())
        except Exception as exception:
            return error_update(code_for(exception))
        return {"assessment": value.model_dump(mode="json")}

    def route_assessment(state: ReplenishmentState) -> str:
        if state["error"] is not None:
            return "failure"
        if request(state).requested_action is ActionType.QUERY:
            return "query"
        return "recover" if assessment(state).recovery_required else "normal"

    async def record_normal_plan(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_validated_plan(operation_id(state), assessment(state), None)
        return {}

    async def record_query_assessment(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_query_assessment(operation_id(state), assessment(state))
        return {}

    async def mark_reporting(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_reporting(operation_id(state))
        return {}

    async def complete_without_recovery(state: ReplenishmentState) -> dict[str, object]:
        is_query = request(state).requested_action is ActionType.QUERY
        result = OperationResult(
            outcome="query_completed" if is_query else "task_recovery_not_required",
            message=(
                "Evidence-backed task status returned without creating a work order."
                if is_query
                else "Task state is within the recovery policy."
            ),
        )
        await operations.complete_without_replenishment(operation_id(state), result)
        return {"result": result.model_dump(mode="json")}

    async def explain_plan(state: ReplenishmentState) -> dict[str, object]:
        try:
            explanation = await model_gateway.explain_plan(assessment(state))
        except Exception:
            return error_update(DependencyUnavailable.code)
        return {"plan": explanation.model_dump(mode="json")}

    async def build_plan(state: ReplenishmentState) -> dict[str, object]:
        try:
            value = build_task_recovery_plan(
                assessment(state),
                ModelPlanExplanation.model_validate(state["plan"]),
                evidence(state).policy,
            )
        except Exception as exception:
            return error_update(code_for(exception))
        return {"plan": value.model_dump(mode="json")}

    async def record_recovery_plan(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_validated_plan(operation_id(state), assessment(state), plan(state))
        value = build_task_recovery_approval_binding(evidence(state), plan(state))
        return {"approval_binding": value.model_dump(mode="json")}

    async def prepare_approval(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_awaiting_approval(
            operation_id(state), binding(state), clock() + timedelta(seconds=approval_ttl_seconds)
        )
        return {}

    async def request_approval(state: ReplenishmentState) -> dict[str, object]:
        detail = await operations.load_detail(operation_id(state))
        if detail.approval_expires_at is None:
            return error_update(DependencyUnavailable.code)
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "assessment": state["assessment"],
                "plan": state["plan"],
                "approval_binding": state["approval_binding"],
                "approval_expires_at": detail.approval_expires_at.isoformat(),
            }
        )
        try:
            value = ApprovalResume.model_validate(resumed)
        except ValidationError:
            return error_update(DependencyUnavailable.code)
        return {"approval": cast(dict[str, JsonValue], value.model_dump(mode="json"))}

    def route_approval(state: ReplenishmentState) -> str:
        return "failure" if state["error"] is not None else approval(state).decision.value

    async def mark_rejected(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_rejected(operation_id(state), approval(state).approval_id)
        return {}

    async def revalidate(state: ReplenishmentState) -> dict[str, object]:
        task_id = request(state).object_id
        if task_id is None:
            return error_update(DependencyUnavailable.code)
        original_plan, original_binding = plan(state), binding(state)
        try:
            refreshed = TaskRecoveryEvidenceBundle(
                task=TaskEvidence.model_validate(await gateway.get_task(task_id)),
                policy=TaskRecoveryPolicyEvidence.model_validate(
                    await gateway.get_task_recovery_policy(task_id)
                ),
            )
            await evidence_repository.save_refresh(operation_id(state), refreshed)
            refreshed_assessment = assess_task_recovery(refreshed, clock())
            if not refreshed_assessment.recovery_required:
                raise ApprovalSnapshotMismatch
            refreshed_plan = build_task_recovery_plan(
                refreshed_assessment,
                ModelPlanExplanation(
                    summary=original_plan.summary, rationale=original_plan.rationale
                ),
                refreshed.policy,
            )
            refreshed_binding = build_task_recovery_approval_binding(refreshed, refreshed_plan)
            if (
                refreshed_binding.rule_version,
                refreshed_binding.decision_facts_hash,
                refreshed_binding.plan_hash,
                refreshed_binding.parameters,
            ) != (
                original_binding.rule_version,
                original_binding.decision_facts_hash,
                original_binding.plan_hash,
                original_binding.parameters,
            ):
                raise ApprovalSnapshotMismatch
        except Exception as exception:
            if isinstance(
                exception,
                (
                    TaskNotFound,
                    EvidenceUnavailable,
                    InvalidTaskEvidence,
                    InvalidTaskRecoveryPolicyEvidence,
                    EvidenceExpired,
                    TaskRecoveryOutOfPolicy,
                ),
            ):
                return error_update(code_for(exception))
            return error_update(ApprovalSnapshotMismatch.code)
        return {}

    async def mark_executing(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_executing(operation_id(state), approval(state).approval_id)
        return {}

    async def execute(state: ReplenishmentState) -> dict[str, object]:
        approved = plan(state)
        payload = TaskRecoveryWorkOrderPayload(
            task_id=approved.task_id,
            blocker_code=approved.blocker_code,
            retry_count=approved.retry_count,
            recovery_action=approved.recovery_action,
            approved_plan_hash=approved.plan_hash,
        )
        try:
            result = await gateway.create_work_order(
                WorkOrderCommand(
                    operation_id=operation_id(state),
                    payload=cast(dict[str, JsonValue], payload.model_dump(mode="json")),
                ),
                plan_hash=approved.plan_hash,
            )
        except Exception as exception:
            return error_update(code_for(exception))
        return {
            "work_order": result.work_order.model_dump(mode="json"),
            "replayed": result.replayed,
        }

    async def mark_verifying(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_verifying(operation_id(state), work_order(state).id)
        return {}

    async def verify(state: ReplenishmentState) -> dict[str, object]:
        expected = work_order(state)
        try:
            stored = await gateway.get_work_order(expected.id)
        except Exception:
            return error_update(WorkOrderVerificationFailed.code)
        if (
            stored.id != expected.id
            or stored.operation_id != expected.operation_id
            or stored.payload != expected.payload
            or stored.payload_hash != expected.payload_hash
        ):
            return error_update(WorkOrderVerificationFailed.code)
        return {}

    async def complete(state: ReplenishmentState) -> dict[str, object]:
        stored = work_order(state)
        result = OperationResult(
            outcome="work_order_completed",
            message="The approved task recovery work order was created and verified.",
            work_order_id=stored.id,
        )
        await operations.mark_completed(operation_id(state), result, stored.id)
        return {"result": result.model_dump(mode="json")}

    async def fail(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_failed(operation_id(state), error(state))
        return {}

    builder = StateGraph(ReplenishmentState)
    nodes = {
        "parse_request": parse_request,
        "mark_gathering": mark_gathering,
        "gather_evidence": gather_evidence,
        "calculate_assessment": calculate_assessment,
        "record_normal_plan": record_normal_plan,
        "record_query_assessment": record_query_assessment,
        "mark_reporting": mark_reporting,
        "complete_without_recovery": complete_without_recovery,
        "explain_plan": explain_plan,
        "build_plan": build_plan,
        "record_recovery_plan": record_recovery_plan,
        "prepare_approval": prepare_approval,
        "request_approval": request_approval,
        "mark_rejected": mark_rejected,
        "revalidate": revalidate,
        "mark_executing": mark_executing,
        "execute": execute,
        "mark_verifying": mark_verifying,
        "verify": verify,
        "complete": complete,
        "fail": fail,
    }
    for name, node in nodes.items():
        builder.add_node(
            name,
            cast(
                Any,
                trace_async_node(
                    tracing,
                    scenario="task",
                    node=name,
                    function=node,
                ),
            ),
        )
    builder.add_edge(START, "parse_request")
    builder.add_conditional_edges(
        "parse_request", route_error, {"continue": "mark_gathering", "failure": "fail"}
    )
    builder.add_edge("mark_gathering", "gather_evidence")
    builder.add_conditional_edges(
        "gather_evidence",
        route_error,
        {"continue": "calculate_assessment", "failure": "fail"},
    )
    builder.add_conditional_edges(
        "calculate_assessment",
        route_assessment,
        {
            "query": "record_query_assessment",
            "normal": "record_normal_plan",
            "recover": "explain_plan",
            "failure": "fail",
        },
    )
    builder.add_edge("record_normal_plan", "mark_reporting")
    builder.add_edge("record_query_assessment", "mark_reporting")
    builder.add_edge("mark_reporting", "complete_without_recovery")
    builder.add_edge("complete_without_recovery", END)
    builder.add_edge("explain_plan", "build_plan")
    builder.add_conditional_edges(
        "build_plan", route_error, {"continue": "record_recovery_plan", "failure": "fail"}
    )
    builder.add_edge("record_recovery_plan", "prepare_approval")
    builder.add_edge("prepare_approval", "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_approval,
        {"approved": "revalidate", "rejected": "mark_rejected", "failure": "fail"},
    )
    builder.add_edge("mark_rejected", END)
    builder.add_conditional_edges(
        "revalidate", route_error, {"continue": "mark_executing", "failure": "fail"}
    )
    builder.add_edge("mark_executing", "execute")
    builder.add_conditional_edges(
        "execute", route_error, {"continue": "mark_verifying", "failure": "fail"}
    )
    builder.add_edge("mark_verifying", "verify")
    builder.add_conditional_edges(
        "verify", route_error, {"continue": "complete", "failure": "fail"}
    )
    builder.add_edge("complete", END)
    builder.add_edge("fail", END)
    return builder.compile(checkpointer=checkpointer)
