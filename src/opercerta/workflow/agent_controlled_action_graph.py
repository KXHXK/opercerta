from collections.abc import Callable
from datetime import datetime
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import JsonValue

from opercerta.agent.harness import AgentContractViolation, AgentHarness
from opercerta.agent.tool_executor import ReadToolGateway, ToolExecutor
from opercerta.agent.tool_policy import ToolPolicy
from opercerta.application.scenario_registry import (
    ScenarioRegistry,
    build_default_scenario_registry,
)
from opercerta.domain.agent import (
    AgentAnalysis,
    AgentBudget,
    AnalysisContext,
    GoalContext,
    GoalEncoding,
    IntentEnvelope,
    PlanningContext,
    ReadToolName,
    ToolCallProposal,
    ToolObservation,
)
from opercerta.domain.contracts import ActionType, OperationRequest
from opercerta.domain.errors import (
    DuplicateToolCall,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)
from opercerta.domain.model_gateway import AgentModelGateway
from opercerta.domain.scenarios import ScenarioKind


class AgentInvestigationState(TypedDict):
    intent: dict[str, JsonValue]
    goal: dict[str, JsonValue] | None
    plan: dict[str, JsonValue] | None
    authorized_calls: list[dict[str, JsonValue]]
    observations: list[dict[str, JsonValue]]
    analysis: dict[str, JsonValue] | None
    evidence: dict[str, JsonValue] | None
    assessment: dict[str, JsonValue] | None
    decision_plan: dict[str, JsonValue] | None
    replan_count: int
    model_call_count: int
    status: Literal["running", "completed", "failed"]
    error_code: str | None


AgentInvestigationGraph = CompiledStateGraph[
    AgentInvestigationState,
    None,
    AgentInvestigationState,
    AgentInvestigationState,
]

_SUBJECT_TOOL = {
    ScenarioKind.INVENTORY: ReadToolName.INVENTORY_SNAPSHOT,
    ScenarioKind.EQUIPMENT: ReadToolName.EQUIPMENT_STATUS,
    ScenarioKind.TASK: ReadToolName.TASK_STATUS,
}
_CREATE_EXPECTED_ACTION = {
    ScenarioKind.INVENTORY: "replenish_inventory",
    ScenarioKind.EQUIPMENT: "repair_equipment",
    ScenarioKind.TASK: "recover_task",
}
_QUERY_EXPECTED_ACTION = {
    ScenarioKind.INVENTORY: "report_inventory_status",
    ScenarioKind.EQUIPMENT: "report_equipment_status",
    ScenarioKind.TASK: "report_task_status",
}
_CREATE_TRIGGER = {
    ScenarioKind.INVENTORY: "below_reorder_point",
    ScenarioKind.EQUIPMENT: "equipment_alert",
    ScenarioKind.TASK: "task_blocked",
}
_QUERY_TRIGGER = {
    ScenarioKind.INVENTORY: "inventory_query",
    ScenarioKind.EQUIPMENT: "equipment_query",
    ScenarioKind.TASK: "task_query",
}
_POLICY_ERRORS = (
    AgentContractViolation,
    DuplicateToolCall,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)


def build_agent_investigation_initial_state(
    request: OperationRequest,
) -> AgentInvestigationState:
    if request.requested_action is None or request.object_type is None or request.object_id is None:
        raise ValueError("complete controlled action request is required")
    scenario = ScenarioKind(request.object_type.value)
    is_create = request.requested_action is ActionType.CREATE_WORK_ORDER
    intent = IntentEnvelope(
        goal=request.requested_action,
        scenario=scenario,
        object_id=request.object_id,
        trigger_reason=(_CREATE_TRIGGER[scenario] if is_create else _QUERY_TRIGGER[scenario]),
        expected_action=(
            _CREATE_EXPECTED_ACTION[scenario] if is_create else _QUERY_EXPECTED_ACTION[scenario]
        ),
    )
    return AgentInvestigationState(
        intent=cast(dict[str, JsonValue], intent.model_dump(mode="json")),
        goal=None,
        plan=None,
        authorized_calls=[],
        observations=[],
        analysis=None,
        evidence=None,
        assessment=None,
        decision_plan=None,
        replan_count=0,
        model_call_count=0,
        status="running",
        error_code=None,
    )


def build_agent_investigation_graph(
    model: AgentModelGateway,
    gateway: ReadToolGateway,
    *,
    budget: AgentBudget | None = None,
    checkpointer: object | None = None,
    registry: ScenarioRegistry | None = None,
    clock: Callable[[], datetime] | None = None,
) -> AgentInvestigationGraph:
    active_budget = budget or AgentBudget(
        max_model_calls=4,
        max_tool_calls=4,
        max_input_tokens=4_000,
        timeout_seconds=30,
        max_replans=1,
    )
    harness = AgentHarness(active_budget)
    executor = ToolExecutor(gateway)
    scenario_registry = registry or build_default_scenario_registry()
    if clock is None:
        raise ValueError("agent investigation clock is required")

    def intent(state: AgentInvestigationState) -> IntentEnvelope:
        return IntentEnvelope.model_validate(state["intent"])

    def goal(state: AgentInvestigationState) -> GoalEncoding:
        return GoalEncoding.model_validate(state["goal"])

    def calls(state: AgentInvestigationState) -> list[ToolCallProposal]:
        return [ToolCallProposal.model_validate(value) for value in state["authorized_calls"]]

    def observations(state: AgentInvestigationState) -> list[ToolObservation]:
        return [ToolObservation.model_validate(value) for value in state["observations"]]

    def budget_failure(state: AgentInvestigationState) -> dict[str, object] | None:
        if state["model_call_count"] >= active_budget.max_model_calls:
            return {"status": "failed", "error_code": "model_budget_exceeded"}
        return None

    async def encode_goal(state: AgentInvestigationState) -> dict[str, object]:
        failure = budget_failure(state)
        if failure is not None:
            return failure
        trusted_intent = intent(state)
        try:
            candidate = await model.encode_goal(GoalContext(intent=trusted_intent))
            encoded = harness.validate_goal(trusted_intent, candidate)
        except _POLICY_ERRORS as error:
            return {"status": "failed", "error_code": str(error)}
        return {
            "goal": encoded.model_dump(mode="json"),
            "model_call_count": state["model_call_count"] + 1,
        }

    async def plan_investigation(state: AgentInvestigationState) -> dict[str, object]:
        failure = budget_failure(state)
        if failure is not None:
            return failure
        trusted_goal = goal(state)
        policy = ToolPolicy(trusted_goal, max_tool_calls=active_budget.max_tool_calls)
        try:
            result = await model.plan(
                PlanningContext(
                    goal=trusted_goal,
                    tools=policy.definitions,
                    replan_count=cast(Literal[0, 1], state["replan_count"]),
                    prior_observations=tuple(observations(state)),
                )
            )
            planned = harness.validate_plan(trusted_goal, result.plan)
            if planned.replan_count != state["replan_count"]:
                raise AgentContractViolation("replan_count_mismatch")
            authorized = calls(state)
            for index, step in enumerate(planned.steps):
                authorized.append(
                    policy.authorize(
                        tool_call_id=f"call-r{state['replan_count']}-s{index}",
                        tool_name=step.tool_name.value,
                        arguments=step.arguments,
                        prior_calls=authorized,
                    )
                )
        except _POLICY_ERRORS as error:
            return {"status": "failed", "error_code": str(error)}
        return {
            "plan": planned.model_dump(mode="json"),
            "authorized_calls": [
                cast(dict[str, JsonValue], proposal.model_dump(mode="json"))
                for proposal in authorized
            ],
            "model_call_count": state["model_call_count"] + 1,
        }

    async def execute_read_tools(state: AgentInvestigationState) -> dict[str, object]:
        completed_ids = {item.tool_call_id for item in observations(state)}
        updated = observations(state)
        for proposal in calls(state):
            if proposal.tool_call_id not in completed_ids:
                updated.append(await executor.execute(proposal))
        return {
            "observations": [
                cast(dict[str, JsonValue], item.model_dump(mode="json")) for item in updated
            ]
        }

    def route_evidence(state: AgentInvestigationState) -> str:
        if state["status"] == "failed":
            return "failed"
        trusted_goal = goal(state)
        successful = {item.tool_name for item in observations(state) if item.status == "ok"}
        required = {
            _SUBJECT_TOOL[trusted_goal.scenario],
            ReadToolName.POLICY_CONSTRAINTS,
        }
        if required <= successful:
            return "complete"
        if state["replan_count"] < active_budget.max_replans:
            return "replan"
        return "failed"

    def prepare_replan(state: AgentInvestigationState) -> dict[str, object]:
        return {"replan_count": state["replan_count"] + 1, "plan": None}

    async def analyze_observations(state: AgentInvestigationState) -> dict[str, object]:
        failure = budget_failure(state)
        if failure is not None:
            return failure
        analyzed = await model.analyze(
            AnalysisContext(
                goal=goal(state),
                observations=tuple(observations(state)),
            )
        )
        return {
            "analysis": cast(dict[str, JsonValue], analyzed.model_dump(mode="json")),
            "model_call_count": state["model_call_count"] + 1,
        }

    def calculate_policy_facts(state: AgentInvestigationState) -> dict[str, object]:
        analyzed = AgentAnalysis.model_validate(state["analysis"])
        try:
            result = scenario_registry.evaluate_agent_result(
                goal(state),
                tuple(observations(state)),
                analyzed,
                clock(),
            )
        except ValueError as error:
            code = getattr(error, "code", "policy_guard_failed")
            return {"status": "failed", "error_code": code}
        return {
            "evidence": cast(dict[str, JsonValue], result.evidence.model_dump(mode="json")),
            "assessment": cast(dict[str, JsonValue], result.assessment.model_dump(mode="json")),
            "decision_plan": (
                cast(dict[str, JsonValue], result.plan.model_dump(mode="json"))
                if result.plan is not None
                else None
            ),
            "status": "completed",
        }

    def mark_failed(state: AgentInvestigationState) -> dict[str, object]:
        return {
            "status": "failed",
            "error_code": state["error_code"] or "required_evidence_incomplete",
        }

    def route_status(state: AgentInvestigationState) -> str:
        return "failed" if state["status"] == "failed" else "continue"

    builder = StateGraph(AgentInvestigationState)
    builder.add_node("encode_goal", encode_goal)
    builder.add_node("plan_investigation", plan_investigation)
    builder.add_node("execute_read_tools", execute_read_tools)
    builder.add_node("prepare_replan", prepare_replan)
    builder.add_node("analyze_observations", analyze_observations)
    builder.add_node("calculate_policy_facts", calculate_policy_facts)
    builder.add_node("mark_failed", mark_failed)
    builder.add_edge(START, "encode_goal")
    builder.add_conditional_edges(
        "encode_goal",
        route_status,
        {"continue": "plan_investigation", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "plan_investigation",
        route_status,
        {"continue": "execute_read_tools", "failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "execute_read_tools",
        route_evidence,
        {
            "complete": "analyze_observations",
            "replan": "prepare_replan",
            "failed": "mark_failed",
        },
    )
    builder.add_edge("prepare_replan", "plan_investigation")
    builder.add_edge("analyze_observations", "calculate_policy_facts")
    builder.add_edge("calculate_policy_facts", END)
    builder.add_edge("mark_failed", END)
    return builder.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
