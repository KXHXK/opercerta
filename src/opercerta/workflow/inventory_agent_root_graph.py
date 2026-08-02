from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.agent.harness import AgentContractViolation, AgentHarness
from opercerta.agent.tool_executor import ReadToolGateway, ToolExecutor
from opercerta.agent.tool_policy import ToolPolicy
from opercerta.application.scenario_registry import (
    ScenarioAssessment,
    ScenarioEvidence,
    ScenarioPlan,
    ScenarioRegistry,
    build_default_scenario_registry,
)
from opercerta.application.scenario_runtime import (
    binding_facts,
    build_refresh_calls,
    build_scenario_approval_binding,
    no_action_outcome,
    parse_scenario_assessment,
    parse_scenario_evidence,
    parse_scenario_plan,
    required_fact_tools,
    scenario_work_order_payload,
)
from opercerta.domain.agent import (
    AgentAnalysis,
    AgentBudget,
    AgentDecisionContext,
    AgentToolCall,
    AgentTurn,
    EvidenceRequirement,
    FinalAnalysis,
    GoalContext,
    GoalEncoding,
    IntentEnvelope,
    ReadToolName,
    ToolCallProposal,
    ToolDecision,
    ToolObservation,
    VerificationDecision,
)
from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    DuplicateToolCall,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)
from opercerta.domain.model_gateway import AgentLoopModelGateway
from opercerta.domain.operation_state import ApprovalResume
from opercerta.domain.replenishment import (
    OperationError,
    OperationResult,
)
from opercerta.domain.scenarios import ApprovalBinding, ScenarioKind
from opercerta.domain.work_orders import WorkOrderCommand, WorkOrderRecord, WorkOrderWriteResult
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.model_gateway import ModelOutputInvalid
from opercerta.workflow.agent_controlled_action_graph import (
    build_verification_context,
    choose_verification_route,
)


class ControlledActionGateway(ReadToolGateway, Protocol):
    async def create_work_order(
        self,
        command: WorkOrderCommand,
        *,
        plan_hash: str,
    ) -> WorkOrderWriteResult: ...

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord: ...


InventoryActionGateway = ControlledActionGateway


class InventoryAgentRootState(TypedDict):
    operation_id: str
    request: dict[str, JsonValue]
    intent: dict[str, JsonValue]
    goal: dict[str, JsonValue] | None
    last_turn: dict[str, JsonValue] | None
    authorized_calls: list[dict[str, JsonValue]]
    observations: list[dict[str, JsonValue]]
    final_analysis: dict[str, JsonValue] | None
    agent_analysis: dict[str, JsonValue] | None
    evidence: dict[str, JsonValue] | None
    assessment: dict[str, JsonValue] | None
    decision_plan: dict[str, JsonValue] | None
    approval_binding: dict[str, JsonValue] | None
    approval: dict[str, JsonValue] | None
    refreshed_observations: list[dict[str, JsonValue]]
    verification: dict[str, JsonValue] | None
    verification_route: str | None
    work_order: dict[str, JsonValue] | None
    result: dict[str, JsonValue] | None
    replayed: bool
    model_call_count: int
    tool_call_count: int
    status: Literal[
        "running",
        "query_completed",
        "awaiting_approval",
        "needs_reapproval",
        "completed",
        "rejected",
        "aborted",
        "failed",
    ]
    error_code: str | None


InventoryAgentRootGraph = CompiledStateGraph[
    InventoryAgentRootState,
    None,
    InventoryAgentRootState,
    InventoryAgentRootState,
]
ControlledAgentRootState = InventoryAgentRootState
ControlledAgentRootGraph = InventoryAgentRootGraph

_TRIGGER_REASONS = {
    ScenarioKind.INVENTORY: ("inventory_query", "below_reorder_point"),
    ScenarioKind.EQUIPMENT: ("equipment_query", "equipment_alert"),
    ScenarioKind.TASK: ("task_query", "task_blocked"),
}
_EXPECTED_ACTIONS = {
    ScenarioKind.INVENTORY: ("report_inventory_status", "replenish_inventory"),
    ScenarioKind.EQUIPMENT: ("report_equipment_status", "repair_equipment"),
    ScenarioKind.TASK: ("report_task_status", "recover_task"),
}

_LOOP_ERRORS = (
    AgentContractViolation,
    DuplicateToolCall,
    ModelOutputInvalid,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)


def build_controlled_agent_root_initial_state(
    operation_id: UUID,
    request: OperationRequest,
) -> ControlledAgentRootState:
    if request.requested_action is None or request.object_type is None or request.object_id is None:
        raise ValueError("complete controlled action request is required")
    scenario = ScenarioKind(request.object_type.value)
    is_create = request.requested_action is ActionType.CREATE_WORK_ORDER
    intent = IntentEnvelope(
        goal=request.requested_action,
        scenario=scenario,
        object_id=request.object_id,
        trigger_reason=_TRIGGER_REASONS[scenario][int(is_create)],
        expected_action=_EXPECTED_ACTIONS[scenario][int(is_create)],
    )
    return InventoryAgentRootState(
        operation_id=str(operation_id),
        request=cast(dict[str, JsonValue], request.model_dump(mode="json")),
        intent=cast(dict[str, JsonValue], intent.model_dump(mode="json")),
        goal=None,
        last_turn=None,
        authorized_calls=[],
        observations=[],
        final_analysis=None,
        agent_analysis=None,
        evidence=None,
        assessment=None,
        decision_plan=None,
        approval_binding=None,
        approval=None,
        refreshed_observations=[],
        verification=None,
        verification_route=None,
        work_order=None,
        result=None,
        replayed=False,
        model_call_count=0,
        tool_call_count=0,
        status="running",
        error_code=None,
    )


def build_inventory_agent_root_initial_state(
    operation_id: UUID,
    request: OperationRequest,
) -> InventoryAgentRootState:
    if request.object_type is not ObjectType.INVENTORY:
        raise ValueError("inventory controlled action request is required")
    return build_controlled_agent_root_initial_state(operation_id, request)


def build_controlled_agent_root_graph(
    model: AgentLoopModelGateway,
    gateway: ReadToolGateway,
    *,
    clock: Callable[[], datetime],
    budget: AgentBudget | None = None,
    registry: ScenarioRegistry | None = None,
    checkpointer: object | None = None,
    enabled: bool = False,
    operations: ReplenishmentOperationRepository | None = None,
    action_gateway: ControlledActionGateway | None = None,
    refresh_gateway: ReadToolGateway | None = None,
    approval_ttl_seconds: int = 300,
    knowledge_enabled: bool = False,
    knowledge_required: bool = False,
) -> ControlledAgentRootGraph:
    if not enabled:
        raise RuntimeError("single_root_controlled_action_feature_disabled")
    runtime_values = (operations, action_gateway, refresh_gateway)
    if any(value is not None for value in runtime_values) and not all(
        value is not None for value in runtime_values
    ):
        raise ValueError("complete controlled action root runtime is required")
    if approval_ttl_seconds < 1:
        raise ValueError("approval_ttl_seconds must be positive")
    if knowledge_required and not knowledge_enabled:
        raise ValueError("required knowledge retrieval must be enabled")
    active_budget = budget or AgentBudget(
        # Goal encoding + up to four bounded tool turns + one final analysis.
        max_model_calls=6,
        max_tool_calls=4,
        max_input_tokens=4_000,
        timeout_seconds=30,
        max_replans=1,
    )
    harness = AgentHarness(active_budget)
    executor = ToolExecutor(gateway)
    scenario_registry = registry or build_default_scenario_registry()

    def trusted_intent(state: InventoryAgentRootState) -> IntentEnvelope:
        return IntentEnvelope.model_validate(state["intent"])

    def goal(state: InventoryAgentRootState) -> GoalEncoding:
        return GoalEncoding.model_validate(state["goal"])

    def observations(state: InventoryAgentRootState) -> list[ToolObservation]:
        return [ToolObservation.model_validate(item) for item in state["observations"]]

    def proposals(state: InventoryAgentRootState) -> list[ToolCallProposal]:
        return [ToolCallProposal.model_validate(item) for item in state["authorized_calls"]]

    def operation_id(state: InventoryAgentRootState) -> UUID:
        return UUID(state["operation_id"])

    def evidence(state: InventoryAgentRootState) -> ScenarioEvidence:
        return parse_scenario_evidence(goal(state).scenario, state["evidence"])

    def assessment(state: InventoryAgentRootState) -> ScenarioAssessment:
        return parse_scenario_assessment(goal(state).scenario, state["assessment"])

    def plan(state: InventoryAgentRootState) -> ScenarioPlan:
        return parse_scenario_plan(goal(state).scenario, state["decision_plan"])

    def approval(state: InventoryAgentRootState) -> ApprovalResume:
        return ApprovalResume.model_validate(state["approval"])

    def fail(code: str) -> dict[str, object]:
        return {"status": "failed", "error_code": code}

    async def encode_goal(state: InventoryAgentRootState) -> dict[str, object]:
        try:
            candidate = await model.encode_goal(GoalContext(intent=trusted_intent(state)))
            encoded = harness.validate_goal(trusted_intent(state), candidate)
            if (
                knowledge_required
                and EvidenceRequirement.KNOWLEDGE not in encoded.required_evidence
            ):
                encoded = encoded.model_copy(
                    update={
                        "required_evidence": (
                            *encoded.required_evidence,
                            EvidenceRequirement.KNOWLEDGE,
                        )
                    }
                )
        except _LOOP_ERRORS as error:
            return fail(str(error))
        return {
            "goal": encoded.model_dump(mode="json"),
            "model_call_count": 1,
        }

    async def begin_operation(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is not None:
            try:
                await operations.mark_gathering_evidence(operation_id(state))
            except Exception:
                return fail("dependency_unavailable")
        return {}

    async def model_decide(state: InventoryAgentRootState) -> dict[str, object]:
        next_model_count = state["model_call_count"] + 1
        if next_model_count > active_budget.max_model_calls:
            return fail("model_budget_exceeded")
        policy = ToolPolicy(
            goal(state),
            max_tool_calls=active_budget.max_tool_calls,
            include_knowledge=knowledge_enabled,
        )
        # A failed read is still a completed attempt. Re-offering the same strictly
        # bound call would create an identical proposal that the policy must reject
        # as a duplicate. The final-analysis contract reports the missing evidence
        # and lets the graph fail closed instead of spinning or retrying implicitly.
        observed_names = {item.tool_name for item in observations(state)}
        available_tools = tuple(
            definition for definition in policy.definitions if definition.name not in observed_names
        )
        try:
            turn = await model.decide(
                AgentDecisionContext(
                    goal=goal(state),
                    tools=available_tools,
                    observations=tuple(observations(state)),
                    model_call_count=state["model_call_count"],
                    tool_call_count=state["tool_call_count"],
                )
            )
            turn = harness.validate_turn(
                turn,
                model_call_count=next_model_count,
                prior_tool_call_count=state["tool_call_count"],
            )
        except _LOOP_ERRORS as error:
            return fail(str(error))
        return {
            "last_turn": cast(dict[str, JsonValue], turn.model_dump(mode="json")),
            "model_call_count": next_model_count,
        }

    def route_turn(state: InventoryAgentRootState) -> str:
        if state["status"] == "failed":
            return "failed"
        turn = AgentTurn.model_validate(state["last_turn"])
        return "tools" if isinstance(turn.root, ToolDecision) else "final"

    def authorize_tools(state: InventoryAgentRootState) -> dict[str, object]:
        turn = AgentTurn.model_validate(state["last_turn"])
        if not isinstance(turn.root, ToolDecision):
            return fail("agent_turn_route_invalid")
        policy = ToolPolicy(
            goal(state),
            max_tool_calls=active_budget.max_tool_calls,
            include_knowledge=knowledge_enabled,
        )
        authorized = proposals(state)
        try:
            for call in turn.root.tool_calls:
                authorized.append(_authorize_call(policy, call, authorized))
        except _LOOP_ERRORS as error:
            return fail(str(error))
        return {
            "authorized_calls": [item.model_dump(mode="json") for item in authorized],
            "tool_call_count": len(authorized),
        }

    async def execute_read_tools(state: InventoryAgentRootState) -> dict[str, object]:
        completed = {item.tool_call_id for item in observations(state)}
        updated = observations(state)
        for proposal in proposals(state):
            if proposal.tool_call_id not in completed:
                updated.append(await executor.execute(proposal))
        return {
            "observations": [item.model_dump(mode="json") for item in updated],
            "last_turn": None,
        }

    def validate_final_analysis(state: InventoryAgentRootState) -> dict[str, object]:
        turn = AgentTurn.model_validate(state["last_turn"])
        if not isinstance(turn.root, FinalAnalysis):
            return fail("agent_turn_route_invalid")
        successful = {item.tool_name: item for item in observations(state) if item.status == "ok"}
        required = required_fact_tools(goal(state).scenario)
        if knowledge_required:
            required = required | {ReadToolName.KNOWLEDGE_SEARCH}
        if not required <= set(successful) or turn.root.missing_evidence:
            return fail("required_evidence_incomplete")
        required_refs = {successful[name].tool_call_id for name in required}
        # Evidence identifiers are authoritative workflow facts, not a model
        # judgment. Bind them from validated observations so provider formatting
        # variation cannot drop or invent the lineage used by later controls.
        bound_final = turn.root.model_copy(update={"evidence_refs": tuple(sorted(required_refs))})
        analysis = AgentAnalysis(
            summary=bound_final.finding,
            recommendation=bound_final.explanation,
        )
        return {
            "final_analysis": bound_final.model_dump(mode="json"),
            "agent_analysis": analysis.model_dump(mode="json"),
        }

    def calculate_policy(state: InventoryAgentRootState) -> dict[str, object]:
        if state["status"] == "failed":
            return {}
        try:
            result = scenario_registry.evaluate_agent_result(
                goal(state),
                tuple(observations(state)),
                AgentAnalysis.model_validate(state["agent_analysis"]),
                clock(),
            )
        except (ValueError, RuntimeError) as error:
            return fail(getattr(error, "code", "policy_guard_failed"))
        controlled_request = OperationRequest.model_validate(state["request"])
        status = (
            "awaiting_approval"
            if controlled_request.requested_action is ActionType.CREATE_WORK_ORDER
            and result.plan is not None
            else "query_completed"
        )
        return {
            "evidence": result.evidence.model_dump(mode="json"),
            "assessment": result.assessment.model_dump(mode="json"),
            "decision_plan": (
                result.plan.model_dump(mode="json") if result.plan is not None else None
            ),
            "status": status,
        }

    async def persist_policy_result(state: InventoryAgentRootState) -> dict[str, object]:
        if state["status"] == "failed" or operations is None:
            return {}
        controlled_request = OperationRequest.model_validate(state["request"])
        bundle = evidence(state)
        calculated = assessment(state)
        try:
            await operations.record_evidence(operation_id(state), bundle)
            if state["status"] == "awaiting_approval":
                approved_plan = plan(state)
                await operations.record_validated_plan(
                    operation_id(state),
                    calculated,
                    approved_plan,
                )
                binding = build_scenario_approval_binding(bundle, approved_plan)
                await operations.mark_awaiting_approval(
                    operation_id(state),
                    binding,
                    clock() + timedelta(seconds=approval_ttl_seconds),
                )
                return {"approval_binding": binding.model_dump(mode="json")}
            if controlled_request.requested_action is ActionType.QUERY:
                await operations.record_query_assessment(operation_id(state), calculated)
            else:
                await operations.record_validated_plan(operation_id(state), calculated, None)
            await operations.mark_reporting(operation_id(state))
            operation_result = OperationResult(
                outcome=no_action_outcome(
                    goal(state).scenario,
                    query=controlled_request.requested_action is ActionType.QUERY,
                ),
                message="Evidence-backed controlled result completed without a work order.",
            )
            await operations.complete_without_replenishment(
                operation_id(state),
                operation_result,
            )
            return {
                "status": "completed",
                "result": operation_result.model_dump(mode="json"),
            }
        except Exception:
            return fail("dependency_unavailable")

    def route_policy(state: InventoryAgentRootState) -> str:
        if state["status"] == "failed":
            return "failed"
        if state["status"] == "awaiting_approval":
            return "approval"
        return "query"

    def approval_interrupt(state: InventoryAgentRootState) -> dict[str, Any]:
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "decision_plan": state["decision_plan"],
                "approval_binding": state["approval_binding"],
                "status": state["status"],
            }
        )
        try:
            parsed = ApprovalResume.model_validate(resumed)
        except ValidationError:
            return fail("approval_resume_invalid")
        return {"approval": parsed.model_dump(mode="json")}

    def route_approval(state: InventoryAgentRootState) -> str:
        if state["status"] == "failed":
            return "failed"
        return "approved" if approval(state).decision is ApprovalDecision.APPROVED else "rejected"

    async def mark_rejected(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is not None:
            try:
                await operations.mark_rejected(
                    operation_id(state),
                    approval(state).approval_id,
                )
            except Exception:
                return fail("dependency_unavailable")
        return {"status": "rejected"}

    async def refresh_and_verify(state: InventoryAgentRootState) -> dict[str, object]:
        active_refresh_gateway = refresh_gateway
        if active_refresh_gateway is None:
            return fail("controlled_root_runtime_missing")
        refresh_executor = ToolExecutor(active_refresh_gateway)
        refreshed = [
            await refresh_executor.execute(item) for item in build_refresh_calls(goal(state))
        ]
        if any(item.status == "error" for item in refreshed):
            return fail("evidence_unavailable")
        try:
            refreshed_result = scenario_registry.evaluate_agent_result(
                goal(state),
                tuple(refreshed),
                AgentAnalysis.model_validate(state["agent_analysis"]),
                clock(),
            )
            original_plan = plan(state)
            refreshed_plan = refreshed_result.plan
            verification = await model.verify(
                build_verification_context(
                    original_plan,
                    evidence(state),
                    refreshed_result.evidence,
                )
            )
            if refreshed_plan is None:
                route = "abort"
                refreshed_binding = None
            else:
                refreshed_binding = build_scenario_approval_binding(
                    refreshed_result.evidence,
                    refreshed_plan,
                )
                original_binding = ApprovalBinding.model_validate(state["approval_binding"])
                route = choose_verification_route(
                    verification,
                    original_plan,
                    binding_matches=binding_facts(refreshed_binding)
                    == binding_facts(original_binding),
                )
            update: dict[str, object] = {
                "refreshed_observations": [item.model_dump(mode="json") for item in refreshed],
                "verification": verification.model_dump(mode="json"),
                "verification_route": route,
            }
            if (
                route == "reapproval"
                and refreshed_plan is not None
                and refreshed_binding is not None
            ):
                update.update(
                    {
                        "evidence": refreshed_result.evidence.model_dump(mode="json"),
                        "assessment": refreshed_result.assessment.model_dump(mode="json"),
                        "decision_plan": refreshed_plan.model_dump(mode="json"),
                        "approval_binding": refreshed_binding.model_dump(mode="json"),
                    }
                )
            return update
        except Exception:
            return fail("approval_snapshot_mismatch")

    def route_verification(state: InventoryAgentRootState) -> str:
        if state["status"] == "failed":
            return "failed"
        return state["verification_route"] or "failed"

    async def mark_needs_reapproval(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is None:
            return fail("controlled_root_runtime_missing")
        try:
            verification = VerificationDecision.model_validate(state["verification"])
            await operations.mark_needs_reapproval(
                operation_id(state),
                approval(state).approval_id,
                evidence(state),
                assessment(state),
                plan(state),
                ApprovalBinding.model_validate(state["approval_binding"]),
                clock() + timedelta(seconds=approval_ttl_seconds),
                verification.reason,
            )
        except Exception:
            return fail("dependency_unavailable")
        return {
            "status": "needs_reapproval",
            "approval": None,
        }

    async def mark_verifier_aborted(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is None:
            return fail("controlled_root_runtime_missing")
        try:
            verification = VerificationDecision.model_validate(state["verification"])
            await operations.mark_verifier_aborted(
                operation_id(state),
                approval(state).approval_id,
                verification.reason,
            )
        except Exception:
            return fail("dependency_unavailable")
        return {"status": "aborted"}

    async def mark_executing(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is None:
            return fail("controlled_root_runtime_missing")
        try:
            await operations.mark_executing(
                operation_id(state),
                approval(state).approval_id,
            )
        except Exception:
            return fail("dependency_unavailable")
        return {}

    async def execute_work_order(state: InventoryAgentRootState) -> dict[str, object]:
        if action_gateway is None:
            return fail("controlled_root_runtime_missing")
        approved_plan = plan(state)
        try:
            write_result = await action_gateway.create_work_order(
                WorkOrderCommand(
                    operation_id=operation_id(state),
                    payload=scenario_work_order_payload(approved_plan),
                ),
                plan_hash=approved_plan.plan_hash,
            )
        except Exception:
            return fail("work_order_storage_failed")
        return {
            "work_order": write_result.work_order.model_dump(mode="json"),
            "replayed": write_result.replayed,
        }

    async def mark_verifying(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is None:
            return fail("controlled_root_runtime_missing")
        try:
            stored = WorkOrderRecord.model_validate(state["work_order"])
            await operations.mark_verifying(operation_id(state), stored.id)
        except Exception:
            return fail("dependency_unavailable")
        return {}

    async def verify_work_order(state: InventoryAgentRootState) -> dict[str, object]:
        if action_gateway is None:
            return fail("controlled_root_runtime_missing")
        expected = WorkOrderRecord.model_validate(state["work_order"])
        try:
            stored = await action_gateway.get_work_order(expected.id)
        except Exception:
            return fail("work_order_verification_failed")
        if (
            stored.id != expected.id
            or stored.operation_id != expected.operation_id
            or stored.payload != expected.payload
            or stored.payload_hash != expected.payload_hash
        ):
            return fail("work_order_verification_failed")
        return {}

    async def mark_completed(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is None:
            return fail("controlled_root_runtime_missing")
        stored = WorkOrderRecord.model_validate(state["work_order"])
        operation_result = OperationResult(
            outcome="work_order_completed",
            message="The approved controlled work order was created and verified.",
            work_order_id=stored.id,
        )
        try:
            await operations.mark_completed(
                operation_id(state),
                operation_result,
                stored.id,
            )
        except Exception:
            return fail("dependency_unavailable")
        return {
            "status": "completed",
            "result": operation_result.model_dump(mode="json"),
        }

    async def mark_failed(state: InventoryAgentRootState) -> dict[str, object]:
        if operations is not None:
            try:
                await operations.mark_failed(
                    operation_id(state),
                    OperationError(
                        code=state["error_code"] or "dependency_unavailable",
                        message="The controlled Agent operation failed safely.",
                    ),
                )
            except Exception:
                pass
        return {"status": "failed"}

    def route_failure(state: InventoryAgentRootState) -> str:
        return "failed" if state["status"] == "failed" else "continue"

    builder = StateGraph(InventoryAgentRootState)
    builder.add_node("encode_goal", encode_goal)
    builder.add_node("begin_operation", begin_operation)
    builder.add_node("model_decide", model_decide)
    builder.add_node("authorize_tools", authorize_tools)
    builder.add_node("execute_read_tools", execute_read_tools)
    builder.add_node("validate_final_analysis", validate_final_analysis)
    builder.add_node("calculate_policy", calculate_policy)
    builder.add_node("persist_policy_result", persist_policy_result)
    builder.add_node("approval_interrupt", approval_interrupt)
    builder.add_node("mark_rejected", mark_rejected)
    builder.add_node("refresh_and_verify", refresh_and_verify)
    builder.add_node("mark_needs_reapproval", mark_needs_reapproval)
    builder.add_node("mark_verifier_aborted", mark_verifier_aborted)
    builder.add_node("mark_executing", mark_executing)
    builder.add_node("execute_work_order", execute_work_order)
    builder.add_node("mark_verifying", mark_verifying)
    builder.add_node("verify_work_order", verify_work_order)
    builder.add_node("mark_completed", mark_completed)
    builder.add_node("mark_failed", mark_failed)
    builder.add_edge(START, "encode_goal")
    builder.add_conditional_edges(
        "encode_goal",
        route_failure,
        {"continue": "begin_operation", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "begin_operation",
        route_failure,
        {"continue": "model_decide", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "model_decide",
        route_turn,
        {
            "tools": "authorize_tools",
            "final": "validate_final_analysis",
            "failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "authorize_tools",
        route_failure,
        {"continue": "execute_read_tools", "failed": "mark_failed"},
    )
    builder.add_edge("execute_read_tools", "model_decide")
    builder.add_conditional_edges(
        "validate_final_analysis",
        route_failure,
        {"continue": "calculate_policy", "failed": "mark_failed"},
    )
    builder.add_edge("calculate_policy", "persist_policy_result")
    builder.add_conditional_edges(
        "persist_policy_result",
        route_policy,
        {"approval": "approval_interrupt", "query": END, "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "approval_interrupt",
        route_approval,
        {
            "approved": "refresh_and_verify",
            "rejected": "mark_rejected",
            "failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "refresh_and_verify",
        route_verification,
        {
            "proceed": "mark_executing",
            "abort": "mark_verifier_aborted",
            "reapproval": "mark_needs_reapproval",
            "failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "mark_needs_reapproval",
        route_failure,
        {"continue": "approval_interrupt", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "mark_executing",
        route_failure,
        {"continue": "execute_work_order", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "execute_work_order",
        route_failure,
        {"continue": "mark_verifying", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "mark_verifying",
        route_failure,
        {"continue": "verify_work_order", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "verify_work_order",
        route_failure,
        {"continue": "mark_completed", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "mark_rejected",
        route_failure,
        {"continue": END, "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "mark_verifier_aborted",
        route_failure,
        {"continue": END, "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "mark_completed",
        route_failure,
        {"continue": END, "failed": "mark_failed"},
    )
    builder.add_edge("mark_failed", END)
    return builder.compile(checkpointer=checkpointer)  # type: ignore[arg-type]


def build_inventory_agent_root_graph(
    model: AgentLoopModelGateway,
    gateway: ReadToolGateway,
    *,
    clock: Callable[[], datetime],
    budget: AgentBudget | None = None,
    registry: ScenarioRegistry | None = None,
    checkpointer: object | None = None,
    enabled: bool = False,
    operations: ReplenishmentOperationRepository | None = None,
    action_gateway: InventoryActionGateway | None = None,
    refresh_gateway: ReadToolGateway | None = None,
    approval_ttl_seconds: int = 300,
    knowledge_enabled: bool = False,
    knowledge_required: bool = False,
) -> InventoryAgentRootGraph:
    if not enabled:
        raise RuntimeError("single_root_inventory_feature_disabled")
    return build_controlled_agent_root_graph(
        model,
        gateway,
        clock=clock,
        budget=budget,
        registry=registry,
        checkpointer=checkpointer,
        enabled=True,
        operations=operations,
        action_gateway=action_gateway,
        refresh_gateway=refresh_gateway,
        approval_ttl_seconds=approval_ttl_seconds,
        knowledge_enabled=knowledge_enabled,
        knowledge_required=knowledge_required,
    )


def _authorize_call(
    policy: ToolPolicy,
    call: AgentToolCall,
    prior_calls: list[ToolCallProposal],
) -> ToolCallProposal:
    return policy.authorize(
        tool_call_id=call.tool_call_id,
        tool_name=call.tool_name.value,
        arguments=call.arguments,
        prior_calls=prior_calls,
    )
