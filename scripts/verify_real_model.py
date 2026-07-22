"""Run a bounded real-model validation through the public release entrypoint."""

import argparse
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.verify_agent_compose import assert_agent_trace
from scripts.verify_compose import (
    assert_database_counts,
    demo_headers,
    request,
    submit_approval,
    wait_for_ready,
)

SCENARIOS = (
    ("inventory", "SKU-LOW-001", "replenishment"),
    ("equipment", "EQ-PUMP-001", "repair"),
    ("task", "TASK-BLOCKED-001", "task_recovery"),
)

SAFE_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class RepresentativeValidationError(AssertionError):
    """A validation failure containing only bounded, non-sensitive evidence."""

    def __init__(
        self,
        *,
        stage: str,
        http_status: int | None = None,
        error_code: str | None = None,
        operation_status: str | None = None,
    ) -> None:
        detail: dict[str, Any] = {"stage": stage}
        if http_status is not None:
            detail["http_status"] = http_status
        if error_code is not None and SAFE_SLUG.fullmatch(error_code):
            detail["error_code"] = error_code
        if operation_status is not None and SAFE_SLUG.fullmatch(operation_status):
            detail["operation_status"] = operation_status
        self.detail = detail
        super().__init__("representative_validation_failed")


def _safe_error_code(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    nested_error = payload.get("error")
    candidate = nested_error.get("code") if isinstance(nested_error, dict) else payload.get("code")
    return candidate if isinstance(candidate, str) and SAFE_SLUG.fullmatch(candidate) else None


def summarize_explanation(plan: dict[str, Any]) -> dict[str, int]:
    summary = plan.get("summary")
    rationale = plan.get("rationale")
    if not isinstance(summary, str) or not summary.strip():
        raise AssertionError("real model summary is missing")
    if not isinstance(rationale, str) or not rationale.strip():
        raise AssertionError("real model rationale is missing")
    return {
        "summary_characters": len(summary),
        "rationale_characters": len(rationale),
    }


def safe_failure_detail(detail: dict[str, Any]) -> dict[str, Any]:
    error = detail.get("error")
    error_code = error.get("code") if isinstance(error, dict) else None
    audit_events = detail.get("audit_events")
    event_types = (
        [event.get("event_type") for event in audit_events if isinstance(event, dict)]
        if isinstance(audit_events, list)
        else []
    )
    return {
        "status": detail.get("status"),
        "error_code": error_code,
        "audit_event_types": event_types,
    }


def assert_real_model_runtime() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "sh",
            "-c",
            'test "$OPERCERTA_MODEL_MODE" = real '
            '&& test -n "$OPERCERTA_MODEL_BASE_URL" '
            '&& test -n "$OPERCERTA_MODEL_NAME" '
            '&& test -n "$OPERCERTA_MODEL_API_KEY"',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError("API container is not configured for real model mode")


def _trace_summary(trace: dict[str, Any]) -> dict[str, object]:
    events = trace["events"]
    return {
        "event_types": sorted({event["event_type"] for event in events}),
        "citation_count": sum(len(event.get("citations", [])) for event in events),
        "model_mode": trace["run"]["model_mode"],
    }


def build_real_report(
    *,
    provider: str,
    model: str,
    results: list[dict[str, Any]],
) -> dict[str, object]:
    operations = sum(
        int(
            result.get(
                "operations_attempted",
                2 if "query" in result and "approved_path" in result else 1,
            )
        )
        for result in results
    )
    return {
        "executed_at": datetime.now(UTC).isoformat(),
        "provider": provider,
        "model": model,
        "mode": "real",
        "representative_operations": operations,
        "results": results,
    }


def run_representative_scenario(
    *,
    object_type: str,
    object_id: str,
    expected_kind: str,
    operator_headers: dict[str, str],
    approver_headers: dict[str, str],
    query_runner: Any = None,
    approved_runner: Any = None,
) -> dict[str, Any]:
    active_query_runner = query_runner or run_query
    active_approved_runner = approved_runner or run_approved_path
    try:
        query_result = active_query_runner(object_type, object_id, operator_headers)
    except Exception as error:
        failure: dict[str, Any] = {
            "scenario": object_type,
            "status": "failed",
            "failure_stage": "query",
            "error_type": type(error).__name__,
            "operations_attempted": 1,
        }
        if isinstance(error, RepresentativeValidationError):
            failure["failure_detail"] = error.detail
        return failure
    try:
        approved_result = active_approved_runner(
            object_type,
            object_id,
            expected_kind,
            operator_headers,
            approver_headers,
        )
    except Exception as error:
        return {
            "scenario": object_type,
            "status": "failed",
            "failure_stage": "approved_path",
            "error_type": type(error).__name__,
            "operations_attempted": 2,
            "query": query_result,
        }
    return {
        "scenario": object_type,
        "status": "passed",
        "operations_attempted": 2,
        "query": query_result,
        "approved_path": approved_result,
    }


def run_query(
    object_type: str,
    object_id: str,
    operator_headers: dict[str, str],
) -> dict[str, Any]:
    started = time.monotonic()
    status, created = request(
        "POST",
        "/api/v1/operations",
        {
            "message": f"representative real-model query for {object_type}",
            "requested_action": "query",
            "object_type": object_type,
            "object_id": object_id,
        },
        operator_headers,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if status != 202:
        raise RepresentativeValidationError(
            stage="create_operation",
            http_status=status,
            error_code=_safe_error_code(created),
        )
    operation_id = created["operation_id"]
    detail_status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    if detail_status != 200:
        raise RepresentativeValidationError(
            stage="load_operation",
            http_status=detail_status,
            error_code=_safe_error_code(detail),
        )
    if detail["status"] != "completed":
        raise RepresentativeValidationError(
            stage="operation_terminal",
            operation_status=detail.get("status"),
            error_code=_safe_error_code(detail),
        )
    assert detail["result"]["outcome"] == "query_completed"
    assert detail["plan"] is None
    assert detail["approval_binding"] is None
    assert detail["approval"] is None
    assert detail["work_order"] is None
    assert_database_counts(operation_id, approvals=0, work_orders=0)
    trace_status, trace = request(
        "GET",
        f"/api/v1/operations/{operation_id}/agent-trace",
        headers=operator_headers,
    )
    if trace_status != 200:
        raise RepresentativeValidationError(
            stage="load_agent_trace",
            http_status=trace_status,
            error_code=_safe_error_code(trace),
        )
    if trace.get("run", {}).get("model_mode") != "real":
        raise RepresentativeValidationError(stage="agent_trace_model_mode")
    try:
        assert_agent_trace(
            trace,
            expected_scenario=object_type,
            expected_status="completed",
            require_approval=False,
            require_citations=True,
        )
    except AssertionError as error:
        raise RepresentativeValidationError(stage="agent_trace_contract") from error
    return {
        "operation_id": operation_id,
        "status": detail["status"],
        "elapsed_ms": elapsed_ms,
        "model_expected": True,
        "approvals": 0,
        "work_orders": 0,
        "trace": _trace_summary(trace),
    }


def run_approved_path(
    object_type: str,
    object_id: str,
    expected_kind: str,
    operator_headers: dict[str, str],
    approver_headers: dict[str, str],
) -> dict[str, Any]:
    started = time.monotonic()
    status, created = request(
        "POST",
        "/api/v1/operations",
        {
            "message": f"representative real-model controlled action for {object_type}",
            "requested_action": "create_work_order",
            "object_type": object_type,
            "object_id": object_id,
        },
        operator_headers,
    )
    create_elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    assert status == 202, (object_type, status, created)
    operation_id = created["operation_id"]
    detail_status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    assert detail_status == 200
    if detail["status"] != "awaiting_approval":
        raise AssertionError(json.dumps(safe_failure_detail(detail), ensure_ascii=False))
    explanation = summarize_explanation(detail["plan"])

    approval_status, approved = submit_approval(
        operation_id,
        detail,
        "approved",
        approver_headers,
    )
    assert approval_status == 202, (object_type, approval_status, approved)
    assert approved["status"] == "completed"
    _, final = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    payload = final["work_order"]["payload"]
    actual_kind = (
        "repair"
        if "equipment_id" in payload
        else "task_recovery"
        if "task_id" in payload
        else "replenishment"
    )
    assert actual_kind == expected_kind
    assert_database_counts(operation_id, approvals=1, work_orders=1)
    trace_status, trace = request(
        "GET",
        f"/api/v1/operations/{operation_id}/agent-trace",
        headers=operator_headers,
    )
    assert trace_status == 200
    assert trace["run"]["model_mode"] == "real"
    assert_agent_trace(
        trace,
        expected_scenario=object_type,
        expected_status="completed",
        require_approval=True,
        require_citations=True,
    )
    return {
        "operation_id": operation_id,
        "status": final["status"],
        "create_operation_elapsed_ms": create_elapsed_ms,
        "model_expected": True,
        "explanation": explanation,
        "approvals": 1,
        "work_orders": 1,
        "work_order_kind": actual_kind,
        "trace": _trace_summary(trace),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", default="configured-openai-compatible")
    parser.add_argument(
        "--scenario",
        choices=("all", "inventory", "equipment", "task"),
        default="all",
    )
    args = parser.parse_args()

    wait_for_ready(60)
    assert_real_model_runtime()
    operator_headers = demo_headers("operator")
    approver_headers = demo_headers("approver")
    results: list[dict[str, Any]] = []
    selected = [
        scenario for scenario in SCENARIOS if args.scenario == "all" or scenario[0] == args.scenario
    ]
    for object_type, object_id, work_order_kind in selected:
        results.append(
            run_representative_scenario(
                object_type=object_type,
                object_id=object_id,
                expected_kind=work_order_kind,
                operator_headers=operator_headers,
                approver_headers=approver_headers,
            )
        )

    report = build_real_report(
        provider=args.provider,
        model=os.environ.get("OPERCERTA_MODEL_NAME", "configured-model"),
        results=results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    passed = all(result["status"] == "passed" for result in results)
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "operations": report["representative_operations"],
                "model_paths": sum(result["status"] == "passed" for result in results),
            }
        )
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
