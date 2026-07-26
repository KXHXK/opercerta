import pytest
from pydantic import ValidationError

from opercerta.domain.agent import (
    AgentDecisionContext,
    AgentTurn,
    FinalAnalysis,
    GoalEncoding,
    ToolDecision,
    ToolDefinition,
    ToolObservation,
)
from opercerta.domain.model_gateway import MockAgentModelGateway


def tool_decision_payload() -> dict[str, object]:
    return {
        "kind": "tool_calls",
        "tool_calls": [
            {
                "tool_call_id": "call-inventory-001",
                "tool_name": "inventory.get_snapshot",
                "arguments": {"sku": "SKU-DEMO-001"},
                "purpose": "读取当前库存事实。",
            }
        ],
    }


def final_analysis_payload() -> dict[str, object]:
    return {
        "kind": "final_analysis",
        "finding": "库存可用量低于补货点。",
        "evidence_refs": ["call-inventory-001", "call-policy-001"],
        "missing_evidence": [],
        "recommended_action": "request_approval",
        "confidence_band": "high",
        "explanation": "库存事实和确定性规则均支持进入人工审批。",
    }


def test_agent_turn_accepts_one_bounded_tool_decision() -> None:
    turn = AgentTurn.model_validate(tool_decision_payload())

    assert isinstance(turn.root, ToolDecision)
    assert turn.root.tool_calls[0].tool_name == "inventory.get_snapshot"
    assert turn.root.tool_calls[0].purpose == "读取当前库存事实。"


def test_agent_turn_accepts_final_analysis_instead_of_tool_calls() -> None:
    turn = AgentTurn.model_validate(final_analysis_payload())

    assert isinstance(turn.root, FinalAnalysis)
    assert turn.root.recommended_action == "request_approval"
    assert turn.root.evidence_refs == ("call-inventory-001", "call-policy-001")


def test_agent_turn_rejects_mixed_tool_and_final_payload() -> None:
    with pytest.raises(ValidationError):
        AgentTurn.model_validate(
            {
                **tool_decision_payload(),
                "finding": "不应与工具决策同时出现。",
                "recommended_action": "request_approval",
                "confidence_band": "high",
                "explanation": "混合回合会让运行时无法确定下一条边。",
            }
        )


def test_agent_turn_rejects_empty_or_oversized_tool_batches() -> None:
    with pytest.raises(ValidationError):
        AgentTurn.model_validate({"kind": "tool_calls", "tool_calls": []})

    call = tool_decision_payload()["tool_calls"]
    assert isinstance(call, list)
    with pytest.raises(ValidationError):
        AgentTurn.model_validate({"kind": "tool_calls", "tool_calls": call * 5})


@pytest.mark.parametrize(
    "forbidden_field",
    ["reasoning_content", "chain_of_thought", "full_prompt"],
)
def test_final_analysis_rejects_hidden_reasoning_fields(forbidden_field: str) -> None:
    with pytest.raises(ValidationError):
        AgentTurn.model_validate(
            {
                **final_analysis_payload(),
                forbidden_field: "不得保存或展示的内部推理。",
            }
        )


@pytest.mark.asyncio
async def test_mock_loop_model_requests_available_tools_then_finishes_from_observations() -> None:
    goal = GoalEncoding(
        goal="create_work_order",
        scenario="inventory",
        object_id="SKU-DEMO-001",
        required_evidence=("subject", "policy"),
        success_condition="approved_work_order_verified",
    )
    tools = (
        ToolDefinition(
            name="inventory.get_snapshot",
            description="读取库存事实。",
            input_schema={
                "type": "object",
                "properties": {"sku": {"const": "SKU-DEMO-001"}},
                "required": ["sku"],
            },
        ),
        ToolDefinition(
            name="policy.list_constraints",
            description="读取补货规则。",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"const": "replenish_inventory"},
                    "sku": {"const": "SKU-DEMO-001"},
                },
                "required": ["action", "sku"],
            },
        ),
    )
    model = MockAgentModelGateway()

    tool_turn = await model.decide(
        AgentDecisionContext(
            goal=goal,
            tools=tools,
            model_call_count=1,
            tool_call_count=0,
        )
    )
    assert isinstance(tool_turn.root, ToolDecision)
    assert [call.tool_name for call in tool_turn.root.tool_calls] == [
        "inventory.get_snapshot",
        "policy.list_constraints",
    ]

    observations = tuple(
        ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            arguments_hash="a" * 64,
            status="ok",
            evidence_ref=None,
            safe_summary="已验证只读事实。",
            structured_payload={},
        )
        for call in tool_turn.root.tool_calls
    )
    final_turn = await model.decide(
        AgentDecisionContext(
            goal=goal,
            tools=(),
            observations=observations,
            model_call_count=2,
            tool_call_count=2,
        )
    )
    assert isinstance(final_turn.root, FinalAnalysis)
    assert final_turn.root.evidence_refs == tuple(
        observation.tool_call_id for observation in observations
    )
