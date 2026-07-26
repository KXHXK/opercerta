from uuid import uuid4

import pytest
from pydantic import ValidationError

from opercerta.domain.agent import (
    AgentAnalysis,
    AgentBudget,
    FinalReport,
    GoalEncoding,
    InvestigationPlan,
    KnowledgeCitation,
    ToolObservation,
    VerificationDecision,
)


def valid_goal() -> dict[str, object]:
    return {
        "goal": "create_work_order",
        "scenario": "inventory",
        "object_id": "SKU-DEMO-001",
        "required_evidence": ["subject", "policy"],
        "success_condition": "approved_work_order_verified",
        "uncertainties": [],
    }


def test_investigation_plan_rejects_write_tool() -> None:
    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(
            {
                "goal": valid_goal(),
                "steps": [
                    {
                        "tool_name": "work_order.create",
                        "arguments": {"sku": "SKU-DEMO-001"},
                        "purpose": "绕过审批直接创建工单",
                    }
                ],
                "replan_count": 0,
            }
        )


def test_investigation_plan_allows_only_one_replan() -> None:
    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate(
            {
                "goal": valid_goal(),
                "steps": [
                    {
                        "tool_name": "inventory.get_snapshot",
                        "arguments": {"sku": "SKU-DEMO-001"},
                        "purpose": "读取库存事实",
                    }
                ],
                "replan_count": 2,
            }
        )


def test_verifier_rejects_replacement_parameters() -> None:
    with pytest.raises(ValidationError):
        VerificationDecision.model_validate(
            {
                "decision": "proceed",
                "reason": "批准后事实仍与绑定一致",
                "replacement_parameters": {"quantity": 99},
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_model_calls", 0),
        ("max_tool_calls", 0),
        ("max_tool_calls", True),
        ("max_tool_calls", "4"),
        ("max_input_tokens", 0),
        ("timeout_seconds", 0),
    ],
)
def test_agent_budget_requires_strict_positive_limits(field: str, value: object) -> None:
    payload = {
        "max_model_calls": 4,
        "max_tool_calls": 4,
        "max_input_tokens": 4_000,
        "timeout_seconds": 30,
        "max_replans": 1,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        AgentBudget.model_validate(payload)


def test_agent_contracts_are_strict_and_json_serializable() -> None:
    goal = GoalEncoding.model_validate(valid_goal())
    observation = ToolObservation(
        tool_call_id="call-001",
        tool_name="inventory.get_snapshot",
        arguments_hash="a" * 64,
        status="ok",
        evidence_ref=uuid4(),
        safe_summary="库存事实已返回。",
        structured_payload={"available_quantity": 3},
    )
    citation = KnowledgeCitation(
        document_id=uuid4(),
        chunk_id=uuid4(),
        version="sop-v1",
        score=0.8,
        safe_snippet="库存低于补货点时应进入人工审批。",
    )
    analysis = AgentAnalysis(
        summary="库存事实低于规则阈值。",
        recommendation="建议形成受控补货计划。",
        uncertainties=(),
        citations=(citation,),
    )
    report = FinalReport(
        outcome="awaiting_approval",
        summary="计划等待人工审批。",
        evidence_refs=(observation.evidence_ref,),
        citations=(citation,),
    )

    assert goal.model_dump(mode="json")["scenario"] == "inventory"
    assert analysis.model_dump(mode="json")["citations"][0]["version"] == "sop-v1"
    assert report.model_dump(mode="json")["outcome"] == "awaiting_approval"

    with pytest.raises(ValidationError):
        ToolObservation.model_validate(
            {
                **observation.model_dump(mode="json"),
                "raw_authorization": "Bearer forbidden",
            }
        )
