"""Prove a real-provider outage fails closed without approval or work-order writes."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.verify_compose import (
    assert_database_counts,
    demo_headers,
    postgres_scalar,
    request,
    wait_for_ready,
)

FAILURE_MESSAGE = "representative real-provider failure gate"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    wait_for_ready(60)
    headers = demo_headers("operator")
    status, body = request(
        "POST",
        "/api/v1/operations",
        {
            "message": FAILURE_MESSAGE,
            "requested_action": "query",
            "object_type": "inventory",
            "object_id": "SKU-LOW-001",
        },
        headers,
    )
    assert status == 503
    assert body == {
        "code": "dependency_unavailable",
        "message": "依赖服务暂时不可用。",
    }
    row = postgres_scalar(
        "SELECT id || '|' || status || '|' || COALESCE(error_code, '') "
        "FROM operations "
        f"WHERE request_payload->'request'->>'message' = '{FAILURE_MESSAGE}' "
        "ORDER BY created_at DESC LIMIT 1"
    )
    operation_id, operation_status, error_code = row.split("|")
    assert operation_status == "failed"
    assert error_code == "dependency_unavailable"
    assert_database_counts(operation_id, approvals=0, work_orders=0)

    report = {
        "executed_at": datetime.now(UTC).isoformat(),
        "mode": "real",
        "scenario": "inventory",
        "provider_state": "unavailable",
        "http_status": status,
        "operation_status": operation_status,
        "error_code": error_code,
        "approvals": 0,
        "work_orders": 0,
        "secret_or_provider_text_persisted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "failure_path": "fail_closed"}))


if __name__ == "__main__":
    main()
