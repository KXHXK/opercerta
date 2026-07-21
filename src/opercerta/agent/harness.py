from opercerta.domain.agent import (
    AgentBudget,
    GoalEncoding,
    IntentEnvelope,
    InvestigationPlan,
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
