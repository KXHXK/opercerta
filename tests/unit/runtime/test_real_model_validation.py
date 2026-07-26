import json

import pytest

import scripts.verify_real_model as real_model_validation
from scripts.verify_real_model import (
    RepresentativeValidationError,
    build_real_report,
    run_representative_path,
    run_representative_scenario,
    safe_failure_detail,
    summarize_explanation,
)


def test_representative_path_can_limit_real_calls_to_query_only() -> None:
    result = run_representative_path(
        path="query",
        object_type="equipment",
        object_id="EQ-PUMP-001",
        expected_kind="repair",
        operator_headers={},
        approver_headers={},
        query_runner=lambda *_args: {"status": "completed"},
    )

    assert result == {
        "scenario": "equipment",
        "status": "passed",
        "operations_attempted": 1,
        "query": {"status": "completed"},
    }


def test_representative_path_can_limit_real_calls_to_one_approved_write() -> None:
    result = run_representative_path(
        path="approved_path",
        object_type="inventory",
        object_id="SKU-LOW-001",
        expected_kind="replenishment",
        operator_headers={},
        approver_headers={},
        approved_runner=lambda *_args: {"work_order_kind": "replenishment"},
    )

    assert result == {
        "scenario": "inventory",
        "status": "passed",
        "operations_attempted": 1,
        "approved_path": {"work_order_kind": "replenishment"},
    }


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


def test_representative_scenario_records_only_structured_safe_failure_detail() -> None:
    def failing_query(*_args: object) -> dict[str, object]:
        raise RepresentativeValidationError(
            stage="create_operation",
            http_status=503,
            error_code="dependency_unavailable",
        )

    result = run_representative_scenario(
        object_type="inventory",
        object_id="SKU-LOW-001",
        expected_kind="replenishment",
        operator_headers={},
        approver_headers={},
        query_runner=failing_query,
        approved_runner=lambda *_args: {},
    )

    assert result["failure_detail"] == {
        "stage": "create_operation",
        "http_status": 503,
        "error_code": "dependency_unavailable",
    }


def test_run_query_converts_create_failure_to_safe_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        real_model_validation,
        "request",
        lambda *_args, **_kwargs: (
            503,
            {
                "code": "dependency_unavailable",
                "message": "provider response and secret must not be persisted",
            },
        ),
    )

    with pytest.raises(RepresentativeValidationError) as captured:
        real_model_validation.run_query("inventory", "SKU-LOW-001", {})

    assert captured.value.detail == {
        "stage": "create_operation",
        "http_status": 503,
        "error_code": "dependency_unavailable",
    }
    assert "provider response" not in str(captured.value)
    assert "secret" not in str(captured.value)


def test_run_query_converts_terminal_failure_to_safe_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            (202, {"operation_id": "op-safe"}),
            (
                200,
                {
                    "status": "failed",
                    "error": {
                        "code": "dependency_unavailable",
                        "message": "provider response and secret must not be persisted",
                    },
                },
            ),
        ]
    )
    monkeypatch.setattr(
        real_model_validation,
        "request",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(RepresentativeValidationError) as captured:
        real_model_validation.run_query("inventory", "SKU-LOW-001", {})

    assert captured.value.detail == {
        "stage": "operation_terminal",
        "operation_status": "failed",
        "error_code": "dependency_unavailable",
    }


def test_run_query_identifies_agent_trace_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            (202, {"operation_id": "op-safe"}),
            (
                200,
                {
                    "status": "completed",
                    "result": {"outcome": "query_completed"},
                    "plan": None,
                    "approval_binding": None,
                    "approval": None,
                    "work_order": None,
                },
            ),
            (200, {"run": {"model_mode": "real"}, "events": []}),
        ]
    )
    monkeypatch.setattr(
        real_model_validation,
        "request",
        lambda *_args, **_kwargs: next(responses),
    )
    monkeypatch.setattr(
        real_model_validation, "assert_database_counts", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        real_model_validation,
        "assert_agent_trace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsafe trace")),
    )

    with pytest.raises(RepresentativeValidationError) as captured:
        real_model_validation.run_query("inventory", "SKU-LOW-001", {})

    assert captured.value.detail == {"stage": "agent_trace_contract"}
