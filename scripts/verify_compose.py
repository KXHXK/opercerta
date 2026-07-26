"""Verify three OperCerta Compose scenarios and restart recovery without secrets."""

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

RECOVERY_MARKER = Path("tmp/compose-recovery-operation.txt")


@dataclass(frozen=True)
class ComposeVerificationResult:
    completed: tuple[tuple[str, str], ...]
    recovery_operation_id: str


def decode_response_body(body: bytes) -> Any | None:
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def api_request_timeout_seconds() -> float:
    try:
        configured = float(os.environ.get("OPERCERTA_API_REQUEST_TIMEOUT_SECONDS", "10"))
    except ValueError:
        configured = 10.0
    return max(1.0, min(configured, 600.0))


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    base_url = os.environ.get("OPERCERTA_API_URL", "http://127.0.0.1:8080")
    data = json.dumps(payload).encode() if payload is not None else None
    http_request = Request(f"{base_url}{path}", data=data, method=method)
    if data is not None:
        http_request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        http_request.add_header(name, value)
    try:
        with urlopen(http_request, timeout=api_request_timeout_seconds()) as response:
            return response.status, decode_response_body(response.read())
    except HTTPError as error:
        return error.code, decode_response_body(error.read())


def postgres_scalar(sql: str) -> str:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "$1"',
        "sh",
        sql,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def demo_headers(account: str) -> dict[str, str]:
    status, body = request("POST", "/api/v1/auth/demo-token", {"account": account})
    assert status == 200
    return {"Authorization": f"Bearer {body['access_token']}"}


def wait_for_ready(timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status, body = request("GET", "/health/ready")
        except OSError:
            status, body = 503, None
        if status == 200 and body == {
            "status": "ready",
            "dependencies": {"database": "ready", "checkpoint": "ready", "mcp": "ready"},
        }:
            return
        time.sleep(0.5)
    raise AssertionError("API did not become ready before the smoke timeout")


def investigate_signal(
    signal: dict[str, Any],
    operator_headers: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    status, created = request(
        "POST",
        f"/api/v1/signals/{signal['id']}/investigate",
        headers=operator_headers,
    )
    assert status == 202
    operation_id = str(UUID(created["operation_id"]))
    detail_status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    assert detail_status == 200
    return operation_id, detail


def scan_signals(operator_headers: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    status, result = request("POST", "/api/v1/signals/scan", headers=operator_headers)
    assert status == 200
    assert result["scanned_count"] == 3
    assert result["issues"] == []
    signals = {(signal["object_type"], signal["object_id"]): signal for signal in result["signals"]}
    assert set(signals) == {
        ("inventory", "SKU-LOW-001"),
        ("equipment", "EQ-PUMP-001"),
        ("task", "TASK-BLOCKED-001"),
    }
    return signals


def submit_approval(
    operation_id: str,
    detail: dict[str, Any],
    decision: str,
    approver_headers: dict[str, str],
) -> tuple[int, Any]:
    return request(
        "POST",
        f"/api/v1/operations/{operation_id}/approval",
        {
            "decision": decision,
            "reason": f"compose smoke {decision}",
            "expected_binding": detail["approval_binding"],
        },
        approver_headers,
    )


def assert_database_counts(
    operation_id: str,
    *,
    approvals: int,
    work_orders: int,
) -> None:
    assert postgres_scalar(
        f"SELECT COUNT(*) FROM approvals WHERE operation_id = '{operation_id}'"
    ) == str(approvals)
    assert postgres_scalar(
        f"SELECT COUNT(*) FROM work_orders WHERE operation_id = '{operation_id}'"
    ) == str(work_orders)


def verify_recovery_only(operator_headers: dict[str, str]) -> None:
    operation_id = read_recovery_operation_id()
    status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    assert status == 200
    assert detail["status"] == "awaiting_approval"
    assert detail["approval"] is None
    assert detail["work_order"] is None
    assert_database_counts(operation_id, approvals=0, work_orders=0)
    approver_headers = demo_headers("approver")
    approved_status, approved = submit_approval(
        operation_id,
        detail,
        "approved",
        approver_headers,
    )
    assert approved_status == 202 and approved["status"] == "completed"
    assert_database_counts(operation_id, approvals=1, work_orders=1)
    assert (
        postgres_scalar(
            f"SELECT status FROM operational_signals WHERE operation_id = '{operation_id}'"
        )
        == "resolved"
    )


def read_recovery_operation_id() -> str:
    return str(UUID(RECOVERY_MARKER.read_text(encoding="utf-8").strip()))


def verify_full(
    operator_headers: dict[str, str],
    approver_headers: dict[str, str],
) -> ComposeVerificationResult:
    direct_status, direct_body = request(
        "POST",
        "/api/v1/operations",
        {
            "message": "compose smoke must not bypass signal",
            "requested_action": "create_work_order",
            "object_type": "inventory",
            "object_id": "SKU-LOW-001",
        },
        operator_headers,
    )
    assert direct_status == 422 and direct_body["code"] == "request_validation_failed"
    signals = scan_signals(operator_headers)
    scenarios = (
        ("inventory", "SKU-LOW-001", "replenishment"),
        ("equipment", "EQ-PUMP-001", "repair"),
    )
    completed: list[tuple[str, str]] = []
    for object_type, object_id, work_order_kind in scenarios:
        signal = signals[(object_type, object_id)]
        operation_id, detail = investigate_signal(signal, operator_headers)
        approved_status, approved = submit_approval(
            operation_id,
            detail,
            "approved",
            approver_headers,
        )
        if approved_status != 202 or approved["status"] != "completed":
            _, failed_detail = request(
                "GET",
                f"/api/v1/operations/{operation_id}",
                headers=operator_headers,
            )
            raise AssertionError(
                (
                    object_type,
                    approved_status,
                    approved,
                    failed_detail.get("error"),
                    failed_detail.get("audit_events"),
                )
            )
        _, final = request(
            "GET",
            f"/api/v1/operations/{operation_id}",
            headers=operator_headers,
        )
        payload = final["work_order"]["payload"]
        observed_kind = (
            "repair"
            if "equipment_id" in payload
            else "task_recovery"
            if "task_id" in payload
            else "replenishment"
        )
        assert observed_kind == work_order_kind
        assert_database_counts(operation_id, approvals=1, work_orders=1)
        assert (
            postgres_scalar(
                f"SELECT status FROM operational_signals WHERE operation_id = '{operation_id}'"
            )
            == "resolved"
        )
        completed.append((operation_id, object_type))

    inventory_id = completed[0][0]
    _, inventory_detail = request(
        "GET",
        f"/api/v1/operations/{inventory_id}",
        headers=operator_headers,
    )
    duplicate_status, duplicate = submit_approval(
        inventory_id,
        inventory_detail,
        "approved",
        approver_headers,
    )
    assert duplicate_status == 409 and duplicate["code"] == "approval_already_decided"
    assert_database_counts(inventory_id, approvals=1, work_orders=1)

    recovery_id, _ = investigate_signal(
        signals[("task", "TASK-BLOCKED-001")],
        operator_headers,
    )
    RECOVERY_MARKER.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY_MARKER.write_text(recovery_id + "\n", encoding="utf-8")

    operation_id = completed[0][0]
    event_types = postgres_scalar(
        "SELECT event_type FROM audit_events "
        f"WHERE operation_id = '{operation_id}' ORDER BY sequence"
    ).splitlines()
    assert event_types.count("work_order_created") == 1
    assert event_types[-1] == "operation_completed"
    return ComposeVerificationResult(tuple(completed), recovery_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-only", action="store_true")
    args = parser.parse_args()
    wait_for_ready()
    assert request("GET", "/health/live") == (200, {"status": "live"})
    assert request("GET", "/health/ready")[0] == 200
    operator_headers = demo_headers("operator")
    if args.recovery_only:
        verify_recovery_only(operator_headers)
        return
    approver_headers = demo_headers("approver")
    verify_full(operator_headers, approver_headers)


if __name__ == "__main__":
    main()
