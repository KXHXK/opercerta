from scripts.verify_real_model import safe_failure_detail, summarize_explanation


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
