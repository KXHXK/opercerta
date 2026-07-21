import pytest
from pydantic import JsonValue

from opercerta.agent.tool_policy import ToolPolicy
from opercerta.domain.agent import GoalEncoding, ToolCallProposal
from opercerta.domain.errors import (
    DuplicateToolCall,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)


def goal(scenario: str = "inventory", object_id: str = "SKU-DEMO-001") -> GoalEncoding:
    return GoalEncoding(
        goal="create_work_order",
        scenario=scenario,
        object_id=object_id,
        required_evidence=("subject", "policy"),
        success_condition="approved_work_order_verified",
    )


def authorize_inventory(
    policy: ToolPolicy,
    *,
    sku: str = "SKU-DEMO-001",
    prior_calls: tuple[ToolCallProposal, ...] = (),
) -> ToolCallProposal:
    return policy.authorize(
        tool_call_id="call-001",
        tool_name="inventory.get_snapshot",
        arguments={"sku": sku},
        prior_calls=prior_calls,
    )


@pytest.mark.parametrize(
    ("scenario", "object_id", "expected"),
    [
        (
            "inventory",
            "SKU-DEMO-001",
            {"inventory.get_snapshot", "policy.list_constraints"},
        ),
        (
            "equipment",
            "EQ-PUMP-001",
            {"equipment.get_status", "policy.list_constraints"},
        ),
        (
            "task",
            "TASK-BLOCKED-001",
            {"task.get_status", "policy.list_constraints"},
        ),
    ],
)
def test_policy_exposes_only_scenario_read_tools(
    scenario: str,
    object_id: str,
    expected: set[str],
) -> None:
    policy = ToolPolicy(goal(scenario, object_id), max_tool_calls=4)

    assert {definition.name.value for definition in policy.definitions} == expected


@pytest.mark.parametrize(
    ("scenario", "object_id", "arguments"),
    [
        (
            "inventory",
            "SKU-DEMO-001",
            {"action": "replenish_inventory", "sku": "SKU-DEMO-001"},
        ),
        (
            "equipment",
            "EQ-PUMP-001",
            {"action": "repair_equipment", "equipment_id": "EQ-PUMP-001"},
        ),
        (
            "task",
            "TASK-BLOCKED-001",
            {"action": "recover_task", "task_id": "TASK-BLOCKED-001"},
        ),
    ],
)
def test_policy_authorizes_scenario_bound_policy_tool(
    scenario: str,
    object_id: str,
    arguments: dict[str, JsonValue],
) -> None:
    policy = ToolPolicy(goal(scenario, object_id), max_tool_calls=4)

    proposal = policy.authorize(
        tool_call_id="call-policy",
        tool_name="policy.list_constraints",
        arguments=arguments,
    )

    assert proposal.tool_name == "policy.list_constraints"
    assert proposal.arguments == arguments


@pytest.mark.parametrize("tool", ["work_order.create", "shell.exec", "sql.query"])
def test_policy_blocks_write_and_unknown_tools(tool: str) -> None:
    policy = ToolPolicy(goal(), max_tool_calls=4)

    with pytest.raises(ToolPolicyViolation, match="tool_policy_violation"):
        policy.authorize(
            tool_call_id="call-forbidden",
            tool_name=tool,
            arguments={"sku": "SKU-DEMO-001"},
        )


def test_policy_rejects_another_object_id() -> None:
    policy = ToolPolicy(goal(), max_tool_calls=4)

    with pytest.raises(ObjectBindingMismatch, match="object_binding_mismatch"):
        authorize_inventory(policy, sku="SKU-OTHER")


def test_policy_rejects_extra_arguments() -> None:
    policy = ToolPolicy(goal(), max_tool_calls=4)

    with pytest.raises(ToolPolicyViolation, match="tool_policy_violation"):
        policy.authorize(
            tool_call_id="call-extra",
            tool_name="inventory.get_snapshot",
            arguments={"sku": "SKU-DEMO-001", "include_secret": True},
        )


def test_policy_rejects_duplicate_call() -> None:
    policy = ToolPolicy(goal(), max_tool_calls=4)
    first = authorize_inventory(policy)

    with pytest.raises(DuplicateToolCall, match="duplicate_tool_call"):
        authorize_inventory(policy, prior_calls=(first,))


def test_policy_rejects_call_after_budget_is_exhausted() -> None:
    policy = ToolPolicy(goal(), max_tool_calls=1)
    first = authorize_inventory(policy)

    with pytest.raises(ToolBudgetExceeded, match="tool_budget_exceeded"):
        policy.authorize(
            tool_call_id="call-002",
            tool_name="policy.list_constraints",
            arguments={
                "action": "replenish_inventory",
                "sku": "SKU-DEMO-001",
            },
            prior_calls=(first,),
        )
