import pytest

from opercerta.agent.harness import AgentContractViolation, AgentHarness
from opercerta.domain.agent import (
    AgentBudget,
    AgentTurn,
    GoalEncoding,
    IntentEnvelope,
    InvestigationPlan,
)


def request() -> IntentEnvelope:
    return IntentEnvelope(
        goal="create_work_order",
        scenario="inventory",
        object_id="SKU-DEMO-001",
        trigger_reason="below_reorder_point",
        expected_action="replenish_inventory",
    )


def goal(**changes: object) -> GoalEncoding:
    payload: dict[str, object] = {
        "goal": "create_work_order",
        "scenario": "inventory",
        "object_id": "SKU-DEMO-001",
        "required_evidence": ["subject", "policy"],
        "success_condition": "approved_work_order_verified",
        "uncertainties": [],
    }
    payload.update(changes)
    return GoalEncoding.model_validate(payload)


def harness(*, max_tool_calls: int = 4) -> AgentHarness:
    return AgentHarness(
        AgentBudget(
            max_model_calls=4,
            max_tool_calls=max_tool_calls,
            max_input_tokens=4_000,
            timeout_seconds=30,
            max_replans=1,
        )
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scenario", "equipment"),
        ("object_id", "SKU-OTHER"),
        ("goal", "query"),
    ],
)
def test_harness_rejects_model_changes_to_trusted_goal(field: str, value: str) -> None:
    with pytest.raises(AgentContractViolation, match="trusted_goal_mismatch"):
        harness().validate_goal(request(), goal(**{field: value}))


def test_harness_rejects_plan_over_tool_budget() -> None:
    plan = InvestigationPlan.model_validate(
        {
            "goal": goal().model_dump(mode="json"),
            "steps": [
                {
                    "tool_name": "inventory.get_snapshot",
                    "arguments": {"sku": "SKU-DEMO-001"},
                    "purpose": "读取库存事实",
                },
                {
                    "tool_name": "policy.list_constraints",
                    "arguments": {
                        "action": "replenish_inventory",
                        "sku": "SKU-DEMO-001",
                    },
                    "purpose": "读取规则事实",
                },
            ],
            "replan_count": 0,
        }
    )

    with pytest.raises(AgentContractViolation, match="tool_budget_exceeded"):
        harness(max_tool_calls=1).validate_plan(goal(), plan)


def test_harness_accepts_bound_goal_and_plan() -> None:
    trusted_goal = goal()
    plan = InvestigationPlan.model_validate(
        {
            "goal": trusted_goal.model_dump(mode="json"),
            "steps": [
                {
                    "tool_name": "inventory.get_snapshot",
                    "arguments": {"sku": "SKU-DEMO-001"},
                    "purpose": "读取库存事实",
                }
            ],
            "replan_count": 0,
        }
    )

    assert harness().validate_goal(request(), trusted_goal) == trusted_goal
    assert harness().validate_plan(trusted_goal, plan) == plan


def tool_turn(call_count: int = 1) -> AgentTurn:
    return AgentTurn.model_validate(
        {
            "kind": "tool_calls",
            "tool_calls": [
                {
                    "tool_call_id": f"call-{index}",
                    "tool_name": "inventory.get_snapshot",
                    "arguments": {"sku": "SKU-DEMO-001"},
                    "purpose": "读取当前库存事实。",
                }
                for index in range(call_count)
            ],
        }
    )


def test_harness_rejects_turn_after_model_budget_is_exhausted() -> None:
    with pytest.raises(AgentContractViolation, match="model_budget_exceeded"):
        harness().validate_turn(
            tool_turn(),
            model_call_count=5,
            prior_tool_call_count=0,
        )


def test_harness_rejects_turn_that_exceeds_cumulative_tool_budget() -> None:
    with pytest.raises(AgentContractViolation, match="tool_budget_exceeded"):
        harness(max_tool_calls=2).validate_turn(
            tool_turn(call_count=2),
            model_call_count=2,
            prior_tool_call_count=1,
        )


def test_harness_accepts_turn_within_cumulative_budgets() -> None:
    turn = tool_turn()

    assert (
        harness(max_tool_calls=2).validate_turn(
            turn,
            model_call_count=2,
            prior_tool_call_count=1,
        )
        == turn
    )
