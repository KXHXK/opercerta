import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.domain.agent import AgentAnalysis, VerificationDecision
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    ApprovalSnapshotMismatch,
    DependencyUnavailable,
    EquipmentNotFound,
    EvidenceExpired,
    EvidenceUnavailable,
    InvalidEquipmentEvidence,
    InvalidMaintenancePolicyEvidence,
    WorkOrderStorageFailed,
    WorkOrderVerificationFailed,
)
from opercerta.domain.maintenance import (
    EquipmentEvidence,
    MaintenanceAssessment,
    MaintenanceEvidenceBundle,
    MaintenancePlan,
    MaintenancePolicyEvidence,
    RepairWorkOrderPayload,
    assess_maintenance,
    build_maintenance_approval_binding,
    build_maintenance_plan,
)
from opercerta.domain.model_gateway import AgentModelGateway, ModelGateway
from opercerta.domain.operation_state import ApprovalResume
from opercerta.domain.replenishment import (
    ModelPlanExplanation,
    OperationError,
    OperationResult,
)
from opercerta.domain.scenarios import ApprovalBinding
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
)
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.observability.tracing import NOOP_TRACING, Tracing, trace_async_node
from opercerta.workflow.agent_controlled_action_graph import (
    build_verification_context,
    choose_verification_route,
)
from opercerta.workflow.replenishment_graph import ReplenishmentState

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class MaintenanceGateway(Protocol):
    async def get_equipment(self, equipment_id: str) -> object: ...

    async def get_maintenance_policy(self, equipment_id: str) -> object: ...

    async def create_work_order(
        self,
        command: WorkOrderCommand,
        *,
        plan_hash: str,
    ) -> WorkOrderWriteResult: ...

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord: ...


EquipmentMaintenanceGraph = CompiledStateGraph[
    ReplenishmentState,
    None,
    ReplenishmentState,
    ReplenishmentState,
]


def build_equipment_maintenance_graph(
    checkpointer: "AsyncPostgresSaver",
    operations: OperationRepository,
    evidence_repository: EvidenceRepository,
    gateway: MaintenanceGateway,
    model_gateway: ModelGateway,
    clock: Callable[[], datetime],
    *,
    initial_gateway: MaintenanceGateway | None = None,
    tracing: Tracing = NOOP_TRACING,
    parallel_evidence_reads: bool = True,
    approval_ttl_seconds: int = 300,
    agent_model_gateway: AgentModelGateway | None = None,
) -> EquipmentMaintenanceGraph:
    if approval_ttl_seconds < 1:
        raise ValueError("approval_ttl_seconds must be positive")
    evidence_gateway = initial_gateway or gateway

    def operation_id(state: ReplenishmentState) -> UUID:
        try:
            return UUID(state["operation_id"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid graph operation ID") from None

    def request(state: ReplenishmentState) -> OperationRequest:
        return OperationRequest.model_validate(state["request"])

    def evidence(state: ReplenishmentState) -> MaintenanceEvidenceBundle:
        return MaintenanceEvidenceBundle.model_validate(state["evidence"])

    def assessment(state: ReplenishmentState) -> MaintenanceAssessment:
        return MaintenanceAssessment.model_validate(state["assessment"])

    def plan(state: ReplenishmentState) -> MaintenancePlan:
        return MaintenancePlan.model_validate(state["plan"])

    def approval_binding(state: ReplenishmentState) -> ApprovalBinding:
        return ApprovalBinding.model_validate(state["approval_binding"])

    def approval(state: ReplenishmentState) -> ApprovalResume:
        return ApprovalResume.model_validate(state["approval"])

    def work_order(state: ReplenishmentState) -> WorkOrderRecord:
        return WorkOrderRecord.model_validate(state["work_order"])

    def error(state: ReplenishmentState) -> OperationError:
        return OperationError.model_validate(state["error"])

    def error_update(code: str) -> dict[str, object]:
        messages = {
            EquipmentNotFound.code: "Equipment was not found.",
            EvidenceUnavailable.code: "Equipment evidence is unavailable.",
            InvalidEquipmentEvidence.code: "Equipment evidence is invalid.",
            InvalidMaintenancePolicyEvidence.code: "Maintenance policy evidence is invalid.",
            EvidenceExpired.code: "Equipment evidence has expired.",
            ApprovalSnapshotMismatch.code: "Approved equipment facts no longer match.",
            WorkOrderStorageFailed.code: "The repair work order could not be stored.",
            WorkOrderVerificationFailed.code: "The repair work order could not be verified.",
            DependencyUnavailable.code: "A required dependency is unavailable.",
        }
        value = OperationError(
            code=code,
            message=messages.get(code, "The maintenance operation could not be completed."),
        )
        return {"error": value.model_dump(mode="json")}

    def code_for(exception: Exception) -> str:
        if isinstance(
            exception,
            (
                EquipmentNotFound,
                EvidenceUnavailable,
                InvalidEquipmentEvidence,
                InvalidMaintenancePolicyEvidence,
                EvidenceExpired,
                ApprovalSnapshotMismatch,
                WorkOrderStorageFailed,
                WorkOrderVerificationFailed,
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
            parsed.requested_action not in {ActionType.QUERY, ActionType.CREATE_WORK_ORDER}
            or parsed.object_type is not ObjectType.EQUIPMENT
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
        equipment_id = request(state).object_id
        if equipment_id is None:
            return error_update(DependencyUnavailable.code)
        try:
            if parallel_evidence_reads:
                raw_equipment, raw_policy = await asyncio.gather(
                    evidence_gateway.get_equipment(equipment_id),
                    evidence_gateway.get_maintenance_policy(equipment_id),
                )
            else:
                raw_equipment = await evidence_gateway.get_equipment(equipment_id)
                raw_policy = await evidence_gateway.get_maintenance_policy(equipment_id)
            try:
                equipment = EquipmentEvidence.model_validate(raw_equipment)
            except ValidationError:
                raise InvalidEquipmentEvidence from None
            try:
                policy = MaintenancePolicyEvidence.model_validate(raw_policy)
            except ValidationError:
                raise InvalidMaintenancePolicyEvidence from None
            bundle = MaintenanceEvidenceBundle(equipment=equipment, policy=policy)
            await evidence_repository.save_bundle(operation_id(state), bundle)
            await operations.record_evidence(operation_id(state), bundle)
        except Exception as exception:
            return error_update(code_for(exception))
        return {"evidence": bundle.model_dump(mode="json")}

    async def calculate_assessment(state: ReplenishmentState) -> dict[str, object]:
        try:
            calculated = assess_maintenance(evidence(state), clock())
        except Exception as exception:
            return error_update(code_for(exception))
        return {"assessment": calculated.model_dump(mode="json")}

    def route_assessment(state: ReplenishmentState) -> str:
        if state["error"] is not None:
            return "failure"
        if request(state).requested_action is ActionType.QUERY:
            return "query"
        return "repair" if assessment(state).maintenance_required else "normal"

    async def record_normal_plan(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_validated_plan(operation_id(state), assessment(state), None)
        return {}

    async def record_query_assessment(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_query_assessment(operation_id(state), assessment(state))
        return {}

    async def mark_reporting(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_reporting(operation_id(state))
        return {}

    async def complete_without_maintenance(state: ReplenishmentState) -> dict[str, object]:
        is_query = request(state).requested_action is ActionType.QUERY
        result = OperationResult(
            outcome="query_completed" if is_query else "maintenance_not_required",
            message=(
                "Evidence-backed equipment status returned without creating a work order."
                if is_query
                else "Equipment state and heartbeat are within the maintenance policy."
            ),
        )
        await operations.complete_without_replenishment(operation_id(state), result)
        return {"result": result.model_dump(mode="json")}

    async def explain_plan(state: ReplenishmentState) -> dict[str, object]:
        try:
            if state.get("agent_analysis") is not None:
                agent_analysis = AgentAnalysis.model_validate(state["agent_analysis"])
                explanation = ModelPlanExplanation(
                    summary=agent_analysis.summary,
                    rationale=agent_analysis.recommendation,
                )
            else:
                explanation = await model_gateway.explain_plan(assessment(state))
        except Exception:
            return error_update(DependencyUnavailable.code)
        return {"plan": explanation.model_dump(mode="json")}

    async def build_and_validate_plan(state: ReplenishmentState) -> dict[str, object]:
        try:
            explanation = ModelPlanExplanation.model_validate(state["plan"])
            maintenance_plan = build_maintenance_plan(
                assessment(state),
                explanation,
                evidence(state).policy.rule_version,
            )
        except Exception as exception:
            return error_update(code_for(exception))
        return {"plan": maintenance_plan.model_dump(mode="json")}

    async def record_repair_plan(state: ReplenishmentState) -> dict[str, object]:
        await operations.record_validated_plan(operation_id(state), assessment(state), plan(state))
        binding = build_maintenance_approval_binding(evidence(state), plan(state))
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
        try:
            parsed = ApprovalResume.model_validate(resumed)
        except ValidationError:
            return error_update(DependencyUnavailable.code)
        return {"approval": cast(dict[str, JsonValue], parsed.model_dump(mode="json"))}

    def route_approval(state: ReplenishmentState) -> str:
        if state["error"] is not None:
            return "failure"
        return approval(state).decision.value

    async def mark_rejected(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_rejected(operation_id(state), approval(state).approval_id)
        return {}

    async def revalidate_evidence(state: ReplenishmentState) -> dict[str, object]:
        equipment_id = request(state).object_id
        if equipment_id is None:
            return error_update(DependencyUnavailable.code)
        original_plan = plan(state)
        original_binding = approval_binding(state)
        try:
            refreshed = MaintenanceEvidenceBundle(
                equipment=EquipmentEvidence.model_validate(
                    await gateway.get_equipment(equipment_id)
                ),
                policy=MaintenancePolicyEvidence.model_validate(
                    await gateway.get_maintenance_policy(equipment_id)
                ),
            )
            await evidence_repository.save_refresh(operation_id(state), refreshed)
            refreshed_assessment = assess_maintenance(refreshed, clock())
            if not refreshed_assessment.maintenance_required:
                if agent_model_gateway is None:
                    raise ApprovalSnapshotMismatch
                decision = await agent_model_gateway.verify(
                    build_verification_context(original_plan, evidence(state), refreshed)
                )
                return {
                    "verification": decision.model_dump(mode="json"),
                    "verification_route": "abort",
                }
            refreshed_plan = build_maintenance_plan(
                refreshed_assessment,
                ModelPlanExplanation(
                    summary=original_plan.summary,
                    rationale=original_plan.rationale,
                ),
                refreshed.policy.rule_version,
            )
            refreshed_binding = build_maintenance_approval_binding(refreshed, refreshed_plan)
            binding_matches = (
                refreshed_binding.rule_version,
                refreshed_binding.decision_facts_hash,
                refreshed_binding.plan_hash,
                refreshed_binding.parameters,
            ) != (
                original_binding.rule_version,
                original_binding.decision_facts_hash,
                original_binding.plan_hash,
                original_binding.parameters,
            )
            binding_matches = not binding_matches
            if agent_model_gateway is None and not binding_matches:
                raise ApprovalSnapshotMismatch
            if agent_model_gateway is None:
                return {}
            decision = await agent_model_gateway.verify(
                build_verification_context(original_plan, evidence(state), refreshed)
            )
            route = choose_verification_route(
                decision,
                original_plan,
                binding_matches=binding_matches,
            )
            update: dict[str, object] = {
                "verification": decision.model_dump(mode="json"),
                "verification_route": route,
            }
            if route == "reapproval":
                update.update(
                    {
                        "evidence": refreshed.model_dump(mode="json"),
                        "assessment": refreshed_assessment.model_dump(mode="json"),
                        "plan": refreshed_plan.model_dump(mode="json"),
                        "approval_binding": refreshed_binding.model_dump(mode="json"),
                    }
                )
            return update
        except Exception as exception:
            if isinstance(
                exception,
                (
                    EquipmentNotFound,
                    EvidenceUnavailable,
                    InvalidEquipmentEvidence,
                    InvalidMaintenancePolicyEvidence,
                    EvidenceExpired,
                ),
            ):
                return error_update(code_for(exception))
            return error_update(ApprovalSnapshotMismatch.code)
        return {}

    def route_verification(state: ReplenishmentState) -> str:
        if state["error"] is not None:
            return "failure"
        return state["verification_route"] or "proceed"

    async def mark_needs_reapproval(state: ReplenishmentState) -> dict[str, object]:
        decision = VerificationDecision.model_validate(state["verification"])
        await operations.mark_needs_reapproval(
            operation_id(state),
            approval(state).approval_id,
            evidence(state),
            assessment(state),
            plan(state),
            approval_binding(state),
            clock() + timedelta(seconds=approval_ttl_seconds),
            decision.reason,
        )
        return {"approval": None}

    async def request_reapproval(state: ReplenishmentState) -> dict[str, object]:
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "assessment": state["assessment"],
                "plan": state["plan"],
                "approval_binding": state["approval_binding"],
                "status": "needs_reapproval",
            }
        )
        try:
            parsed = ApprovalResume.model_validate(resumed)
        except ValidationError:
            return error_update(DependencyUnavailable.code)
        return {"approval": parsed.model_dump(mode="json")}

    async def mark_verifier_aborted(state: ReplenishmentState) -> dict[str, object]:
        decision = VerificationDecision.model_validate(state["verification"])
        await operations.mark_verifier_aborted(
            operation_id(state),
            approval(state).approval_id,
            decision.reason,
        )
        return {}

    async def mark_executing(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_executing(operation_id(state), approval(state).approval_id)
        return {}

    async def execute_work_order(state: ReplenishmentState) -> dict[str, object]:
        approved_plan = plan(state)
        payload = RepairWorkOrderPayload(
            equipment_id=approved_plan.equipment_id,
            alert_code=approved_plan.alert_code,
            priority=approved_plan.priority,
            approved_plan_hash=approved_plan.plan_hash,
        )
        command = WorkOrderCommand(
            operation_id=operation_id(state),
            payload=cast(dict[str, JsonValue], payload.model_dump(mode="json")),
        )
        try:
            write_result = await gateway.create_work_order(
                command,
                plan_hash=approved_plan.plan_hash,
            )
        except Exception as exception:
            return error_update(code_for(exception))
        return {
            "work_order": write_result.work_order.model_dump(mode="json"),
            "replayed": write_result.replayed,
        }

    async def mark_verifying(state: ReplenishmentState) -> dict[str, object]:
        await operations.mark_verifying(operation_id(state), work_order(state).id)
        return {}

    async def verify_work_order(state: ReplenishmentState) -> dict[str, object]:
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

    async def mark_completed(state: ReplenishmentState) -> dict[str, object]:
        stored = work_order(state)
        result = OperationResult(
            outcome="work_order_completed",
            message="The approved repair work order was created and verified.",
            work_order_id=stored.id,
        )
        await operations.mark_completed(operation_id(state), result, stored.id)
        return {"result": result.model_dump(mode="json")}

    async def mark_failed(state: ReplenishmentState) -> dict[str, object]:
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
        "complete_without_maintenance": complete_without_maintenance,
        "explain_plan": explain_plan,
        "build_and_validate_plan": build_and_validate_plan,
        "record_repair_plan": record_repair_plan,
        "prepare_approval": prepare_approval,
        "request_approval": request_approval,
        "mark_rejected": mark_rejected,
        "revalidate_evidence": revalidate_evidence,
        "mark_needs_reapproval": mark_needs_reapproval,
        "request_reapproval": request_reapproval,
        "mark_verifier_aborted": mark_verifier_aborted,
        "mark_executing": mark_executing,
        "execute_work_order": execute_work_order,
        "mark_verifying": mark_verifying,
        "verify_work_order": verify_work_order,
        "mark_completed": mark_completed,
        "mark_failed": mark_failed,
    }
    for name, node in nodes.items():
        builder.add_node(
            name,
            cast(
                Any,
                trace_async_node(
                    tracing,
                    scenario="equipment",
                    node=name,
                    function=node,
                ),
            ),
        )
    builder.add_edge(START, "parse_request")
    builder.add_conditional_edges(
        "parse_request", route_error, {"continue": "mark_gathering", "failure": "mark_failed"}
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
            "query": "record_query_assessment",
            "normal": "record_normal_plan",
            "repair": "explain_plan",
            "failure": "mark_failed",
        },
    )
    builder.add_edge("record_normal_plan", "mark_reporting")
    builder.add_edge("record_query_assessment", "mark_reporting")
    builder.add_edge("mark_reporting", "complete_without_maintenance")
    builder.add_edge("complete_without_maintenance", END)
    builder.add_edge("explain_plan", "build_and_validate_plan")
    builder.add_conditional_edges(
        "build_and_validate_plan",
        route_error,
        {"continue": "record_repair_plan", "failure": "mark_failed"},
    )
    builder.add_edge("record_repair_plan", "prepare_approval")
    builder.add_edge("prepare_approval", "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_approval,
        {
            "approved": "revalidate_evidence",
            "rejected": "mark_rejected",
            "failure": "mark_failed",
        },
    )
    builder.add_edge("mark_rejected", END)
    builder.add_conditional_edges(
        "revalidate_evidence",
        route_verification,
        {
            "proceed": "mark_executing",
            "abort": "mark_verifier_aborted",
            "reapproval": "mark_needs_reapproval",
            "failure": "mark_failed",
        },
    )
    builder.add_edge("mark_verifier_aborted", END)
    builder.add_edge("mark_needs_reapproval", "request_reapproval")
    builder.add_conditional_edges(
        "request_reapproval",
        route_approval,
        {
            "approved": "revalidate_evidence",
            "rejected": "mark_rejected",
            "failure": "mark_failed",
        },
    )
    builder.add_edge("mark_executing", "execute_work_order")
    builder.add_conditional_edges(
        "execute_work_order",
        route_error,
        {"continue": "mark_verifying", "failure": "mark_failed"},
    )
    builder.add_edge("mark_verifying", "verify_work_order")
    builder.add_conditional_edges(
        "verify_work_order",
        route_error,
        {"continue": "mark_completed", "failure": "mark_failed"},
    )
    builder.add_edge("mark_completed", END)
    builder.add_edge("mark_failed", END)
    return builder.compile(checkpointer=checkpointer)
