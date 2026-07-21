from collections.abc import Sequence
from uuid import UUID

import pytest
from pydantic import BaseModel

from opercerta.domain.agent import (
    AgentAnalysis,
    AnalysisContext,
    FinalReport,
    GoalContext,
    GoalEncoding,
    InvestigationPlan,
    PlanningContext,
    PlanningMode,
    PlanningResult,
    ReadToolName,
    ReportingContext,
    VerificationContext,
    VerificationDecision,
)
from opercerta.domain.contracts import OperationRequest
from opercerta.workflow.agent_controlled_action_graph import (
    build_agent_investigation_graph,
    build_agent_investigation_initial_state,
)


class SyntheticEvidence(BaseModel):
    evidence_id: UUID
    kind: str
    object_id: str


class FakeReadGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[ReadToolName, dict[str, object]]] = []

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, object],
    ) -> BaseModel:
        self.calls.append((name, arguments))
        object_id = next(value for key, value in arguments.items() if key != "action")
        return SyntheticEvidence(
            evidence_id=UUID(int=len(self.calls)),
            kind=name.value,
            object_id=str(object_id),
        )


class ScriptedAgentModel:
    def __init__(self, plans: Sequence[InvestigationPlan]) -> None:
        self._plans = list(plans)
        self.planning_contexts: list[PlanningContext] = []
        self.analysis_contexts: list[AnalysisContext] = []

    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        return GoalEncoding(
            goal=context.intent.goal,
            scenario=context.intent.scenario,
            object_id=context.intent.object_id,
            required_evidence=("subject", "policy"),
            success_condition=(
                "query_reported"
                if context.intent.goal == "query"
                else "approved_work_order_verified"
            ),
        )

    async def plan(self, context: PlanningContext) -> PlanningResult:
        self.planning_contexts.append(context)
        return PlanningResult(
            mode=PlanningMode.NATIVE_TOOL_CALL,
            plan=self._plans.pop(0),
        )

    async def analyze(self, context: AnalysisContext) -> AgentAnalysis:
        self.analysis_contexts.append(context)
        return AgentAnalysis(
            summary="已核对业务对象与适用规则。",
            recommendation="进入确定性 Policy Guard。",
        )

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        del context
        raise AssertionError("pre-approval investigation must not verify")

    async def report(self, context: ReportingContext) -> FinalReport:
        del context
        raise AssertionError("reporting belongs to the outer workflow")


def goal_for(request: OperationRequest) -> GoalEncoding:
    scenario = request.object_type.value  # type: ignore[union-attr]
    return GoalEncoding(
        goal=request.requested_action,
        scenario=scenario,
        object_id=request.object_id,
        required_evidence=("subject", "policy"),
        success_condition="query_reported",
    )


def plan_for(
    goal: GoalEncoding,
    *tools: tuple[str, dict[str, object]],
    replan_count: int = 0,
) -> InvestigationPlan:
    return InvestigationPlan.model_validate(
        {
            "goal": goal.model_dump(mode="json"),
            "steps": [
                {"tool_name": name, "arguments": arguments, "purpose": "读取证据"}
                for name, arguments in tools
            ],
            "replan_count": replan_count,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id", "subject_tool", "subject_arguments", "policy_arguments"),
    [
        (
            "inventory",
            "SKU-LOW-001",
            "inventory.get_snapshot",
            {"sku": "SKU-LOW-001"},
            {"action": "replenish_inventory", "sku": "SKU-LOW-001"},
        ),
        (
            "equipment",
            "EQ-PUMP-001",
            "equipment.get_status",
            {"equipment_id": "EQ-PUMP-001"},
            {"action": "repair_equipment", "equipment_id": "EQ-PUMP-001"},
        ),
        (
            "task",
            "TASK-BLOCKED-001",
            "task.get_status",
            {"task_id": "TASK-BLOCKED-001"},
            {"action": "recover_task", "task_id": "TASK-BLOCKED-001"},
        ),
    ],
)
async def test_three_scenarios_share_agent_investigation_loop(
    object_type: str,
    object_id: str,
    subject_tool: str,
    subject_arguments: dict[str, object],
    policy_arguments: dict[str, object],
) -> None:
    request = OperationRequest(
        message="执行有限业务查询",
        requested_action="query",
        object_type=object_type,
        object_id=object_id,
    )
    goal = goal_for(request)
    model = ScriptedAgentModel(
        [
            plan_for(
                goal,
                (subject_tool, subject_arguments),
                ("policy.list_constraints", policy_arguments),
            )
        ]
    )
    gateway = FakeReadGateway()
    graph = build_agent_investigation_graph(model, gateway)

    result = await graph.ainvoke(build_agent_investigation_initial_state(request))

    assert result["status"] == "completed"
    assert len(result["observations"]) == 2
    assert result["analysis"]["recommendation"] == "进入确定性 Policy Guard。"
    assert {call[0].value for call in gateway.calls} == {
        subject_tool,
        "policy.list_constraints",
    }


@pytest.mark.asyncio
async def test_missing_policy_evidence_causes_one_bounded_replan() -> None:
    request = OperationRequest(
        message="查询库存",
        requested_action="query",
        object_type="inventory",
        object_id="SKU-LOW-001",
    )
    goal = goal_for(request)
    model = ScriptedAgentModel(
        [
            plan_for(
                goal,
                ("inventory.get_snapshot", {"sku": "SKU-LOW-001"}),
            ),
            plan_for(
                goal,
                (
                    "policy.list_constraints",
                    {"action": "replenish_inventory", "sku": "SKU-LOW-001"},
                ),
                replan_count=1,
            ),
        ]
    )
    gateway = FakeReadGateway()
    graph = build_agent_investigation_graph(model, gateway)

    result = await graph.ainvoke(build_agent_investigation_initial_state(request))

    assert result["status"] == "completed"
    assert result["replan_count"] == 1
    assert len(model.planning_contexts) == 2
    assert len(model.planning_contexts[1].prior_observations) == 1
    assert len(result["authorized_calls"]) == 2


@pytest.mark.asyncio
async def test_model_cannot_change_trusted_goal() -> None:
    request = OperationRequest(
        message="查询库存",
        requested_action="query",
        object_type="inventory",
        object_id="SKU-LOW-001",
    )

    class GoalDriftModel(ScriptedAgentModel):
        async def encode_goal(self, context: GoalContext) -> GoalEncoding:
            candidate = await super().encode_goal(context)
            return candidate.model_copy(update={"object_id": "SKU-OTHER"})

    gateway = FakeReadGateway()
    graph = build_agent_investigation_graph(GoalDriftModel([]), gateway)

    result = await graph.ainvoke(build_agent_investigation_initial_state(request))

    assert result["status"] == "failed"
    assert result["error_code"] == "trusted_goal_mismatch"
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_planner_object_drift_fails_before_mcp_call() -> None:
    request = OperationRequest(
        message="查询库存",
        requested_action="query",
        object_type="inventory",
        object_id="SKU-LOW-001",
    )
    goal = goal_for(request)
    model = ScriptedAgentModel(
        [
            plan_for(
                goal,
                ("inventory.get_snapshot", {"sku": "SKU-OTHER"}),
                (
                    "policy.list_constraints",
                    {"action": "replenish_inventory", "sku": "SKU-LOW-001"},
                ),
            )
        ]
    )
    gateway = FakeReadGateway()
    graph = build_agent_investigation_graph(model, gateway)

    result = await graph.ainvoke(build_agent_investigation_initial_state(request))

    assert result["status"] == "failed"
    assert result["error_code"] == "object_binding_mismatch"
    assert gateway.calls == []
