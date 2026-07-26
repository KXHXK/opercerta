from opercerta.domain.agent import (
    AgentBudget,
    AgentTurn,
    GoalEncoding,
    IntentEnvelope,
    InvestigationPlan,
    ToolDecision,
)


class AgentContractViolation(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AgentHarness:
    def __init__(self, budget: AgentBudget) -> None:
        self._budget = budget

    def validate_goal(
        self,
        intent: IntentEnvelope,
        candidate: GoalEncoding,
    ) -> GoalEncoding:
        trusted = (intent.goal, intent.scenario, intent.object_id)
        proposed = (candidate.goal, candidate.scenario, candidate.object_id)
        if proposed != trusted:
            raise AgentContractViolation("trusted_goal_mismatch")
        return candidate

    def validate_plan(
        self,
        goal: GoalEncoding,
        plan: InvestigationPlan,
    ) -> InvestigationPlan:
        if plan.goal != goal:
            raise AgentContractViolation("plan_goal_mismatch")
        if len(plan.steps) > self._budget.max_tool_calls:
            raise AgentContractViolation("tool_budget_exceeded")
        if plan.replan_count > self._budget.max_replans:
            raise AgentContractViolation("replan_budget_exceeded")
        return plan

    def validate_turn(
        self,
        turn: AgentTurn,
        *,
        model_call_count: int,
        prior_tool_call_count: int,
    ) -> AgentTurn:
        if type(model_call_count) is not int or model_call_count < 1:
            raise AgentContractViolation("invalid_model_call_count")
        if type(prior_tool_call_count) is not int or prior_tool_call_count < 0:
            raise AgentContractViolation("invalid_tool_call_count")
        if model_call_count > self._budget.max_model_calls:
            raise AgentContractViolation("model_budget_exceeded")
        if isinstance(turn.root, ToolDecision):
            total_tool_calls = prior_tool_call_count + len(turn.root.tool_calls)
            if total_tool_calls > self._budget.max_tool_calls:
                raise AgentContractViolation("tool_budget_exceeded")
        return turn
