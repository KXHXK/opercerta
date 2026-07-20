"""Run a bounded real-model validation through the public release entrypoint."""

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    assert status == 202, (object_type, status, created)
    operation_id = created["operation_id"]
    detail_status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    assert detail_status == 200
    assert detail["status"] == "completed"
    assert detail["result"]["outcome"] == "query_completed"
    assert detail["plan"] is None
    assert detail["approval_binding"] is None
    assert detail["approval"] is None
    assert detail["work_order"] is None
    assert_database_counts(operation_id, approvals=0, work_orders=0)
    return {
        "operation_id": operation_id,
        "status": detail["status"],
        "elapsed_ms": elapsed_ms,
        "model_expected": False,
        "approvals": 0,
        "work_orders": 0,
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
    return {
        "operation_id": operation_id,
        "status": final["status"],
        "create_operation_elapsed_ms": create_elapsed_ms,
        "model_expected": True,
        "explanation": explanation,
        "approvals": 1,
        "work_orders": 1,
        "work_order_kind": actual_kind,
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
            {
                "scenario": object_type,
                "query": run_query(object_type, object_id, operator_headers),
                "approved_path": run_approved_path(
                    object_type,
                    object_id,
                    work_order_kind,
                    operator_headers,
                    approver_headers,
                ),
            }
        )

    report = {
        "executed_at": datetime.now(UTC).isoformat(),
        "provider": args.provider,
        "model": os.environ.get("OPERCERTA_MODEL_NAME", "configured-model"),
        "mode": "real",
        "representative_operations": len(selected) * 2,
        "expected_model_calls": len(selected),
        "token_usage_available": False,
        "token_usage": None,
        "cost_available": False,
        "cost": None,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "operations": len(selected) * 2,
                "model_paths": len(selected),
            }
        )
    )


if __name__ == "__main__":
    main()
