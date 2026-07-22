import json

from scripts.verify_real_model import (
    build_real_report,
    run_representative_scenario,
    safe_failure_detail,
    summarize_explanation,
)


def test_explanation_summary_records_lengths_without_model_text_or_authoritative_fields() -> None:
    summary = summarize_explanation(
        {
            "summary": "设备需要人工检查",
            "rationale": "告警和心跳事实符合规则",
            "priority": "urgent",
            "recommended_quantity": 999,
        }
    )

    assert summary == {
        "summary_characters": 8,
        "rationale_characters": 11,
    }


def test_safe_failure_detail_excludes_evidence_plan_and_model_text() -> None:
    result = safe_failure_detail(
        {
            "status": "failed",
            "error": {"code": "model_output_invalid", "message": "safe fixed message"},
            "audit_events": [
                {"event_type": "operation_created", "payload": {"secret": "no"}},
                {"event_type": "operation_failed", "payload": {"model_text": "no"}},
            ],
            "evidence": [{"secret": "no"}],
            "plan": {"summary": "no"},
        }
    )

    assert result == {
        "status": "failed",
        "error_code": "model_output_invalid",
        "audit_event_types": ["operation_created", "operation_failed"],
    }


def test_real_report_omits_usage_and_cost_when_provider_does_not_return_them() -> None:
    report = build_real_report(
        provider="moonshot-openai-compatible",
        model="kimi-k2.6",
        results=[{"scenario": "inventory"}],
    )

    serialized = json.dumps(report).lower()
    assert report["mode"] == "real"
    assert report["representative_operations"] == 1
    assert "token" not in serialized
    assert "cost" not in serialized


def test_representative_scenario_records_safe_failure_without_exception_text() -> None:
    def failing_query(*_args: object) -> dict[str, object]:
        raise AssertionError("provider response and secret must not be persisted")

    result = run_representative_scenario(
        object_type="inventory",
        object_id="SKU-LOW-001",
        expected_kind="replenishment",
        operator_headers={},
        approver_headers={},
        query_runner=failing_query,
        approved_runner=lambda *_args: {},
    )

    serialized = json.dumps(result)
    assert result == {
        "scenario": "inventory",
        "status": "failed",
        "failure_stage": "query",
        "error_type": "AssertionError",
        "operations_attempted": 1,
    }
    assert "provider response" not in serialized
    assert "secret" not in serialized
