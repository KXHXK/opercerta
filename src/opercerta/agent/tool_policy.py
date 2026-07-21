from collections.abc import Sequence

from pydantic import JsonValue, ValidationError

from opercerta.domain.agent import (
    GoalEncoding,
    ReadToolName,
    ToolCallProposal,
    ToolDefinition,
)
from opercerta.domain.errors import (
    DuplicateToolCall,
    ObjectBindingMismatch,
    ToolBudgetExceeded,
    ToolPolicyViolation,
)
from opercerta.domain.scenarios import ScenarioKind

_SUBJECT_TOOLS = {
    ScenarioKind.INVENTORY: ReadToolName.INVENTORY_SNAPSHOT,
    ScenarioKind.EQUIPMENT: ReadToolName.EQUIPMENT_STATUS,
    ScenarioKind.TASK: ReadToolName.TASK_STATUS,
}
_SUBJECT_KEYS = {
    ScenarioKind.INVENTORY: "sku",
    ScenarioKind.EQUIPMENT: "equipment_id",
    ScenarioKind.TASK: "task_id",
}
_ACTIONS = {
    ScenarioKind.INVENTORY: "replenish_inventory",
    ScenarioKind.EQUIPMENT: "repair_equipment",
    ScenarioKind.TASK: "recover_task",
}


class ToolPolicy:
    """Pure authorization policy; call history remains in recoverable graph state."""

    def __init__(self, goal: GoalEncoding, *, max_tool_calls: int) -> None:
        if type(max_tool_calls) is not int or max_tool_calls < 1:
            raise ValueError("max_tool_calls must be a positive integer")
        self._goal = goal
        self._max_tool_calls = max_tool_calls
        self._expected_arguments = self._build_expected_arguments(goal)
        self.definitions = self._build_definitions(goal)

    def authorize(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, JsonValue],
        prior_calls: Sequence[ToolCallProposal] = (),
    ) -> ToolCallProposal:
        if len(prior_calls) >= self._max_tool_calls:
            raise ToolBudgetExceeded
        try:
            read_name = ReadToolName(tool_name)
        except ValueError:
            raise ToolPolicyViolation from None
        expected = self._expected_arguments.get(read_name)
        if expected is None:
            raise ToolPolicyViolation

        subject_key = _SUBJECT_KEYS[self._goal.scenario]
        supplied_subject = arguments.get(subject_key)
        if supplied_subject is not None and supplied_subject != self._goal.object_id:
            raise ObjectBindingMismatch
        if arguments != expected:
            raise ToolPolicyViolation

        try:
            proposal = ToolCallProposal(
                tool_call_id=tool_call_id,
                tool_name=read_name,
                arguments=arguments,
            )
        except ValidationError:
            raise ToolPolicyViolation from None
        if any(
            previous.tool_call_id == proposal.tool_call_id
            or (
                previous.tool_name == proposal.tool_name
                and previous.arguments == proposal.arguments
            )
            for previous in prior_calls
        ):
            raise DuplicateToolCall
        return proposal

    @staticmethod
    def _build_expected_arguments(
        goal: GoalEncoding,
    ) -> dict[ReadToolName, dict[str, JsonValue]]:
        subject_key = _SUBJECT_KEYS[goal.scenario]
        subject_tool = _SUBJECT_TOOLS[goal.scenario]
        return {
            subject_tool: {subject_key: goal.object_id},
            ReadToolName.POLICY_CONSTRAINTS: {
                "action": _ACTIONS[goal.scenario],
                subject_key: goal.object_id,
            },
        }

    @classmethod
    def _build_definitions(cls, goal: GoalEncoding) -> tuple[ToolDefinition, ...]:
        expected = cls._build_expected_arguments(goal)
        subject_tool = _SUBJECT_TOOLS[goal.scenario]
        descriptions = {
            subject_tool: "读取当前业务对象的合成事实快照。",
            ReadToolName.POLICY_CONSTRAINTS: "读取当前业务对象适用的确定性规则约束。",
        }
        return tuple(
            ToolDefinition(
                name=name,
                description=descriptions[name],
                input_schema={
                    "type": "object",
                    "properties": {
                        key: {"const": value, "type": "string"} for key, value in arguments.items()
                    },
                    "required": list(arguments),
                    "additionalProperties": False,
                },
            )
            for name, arguments in expected.items()
        )
