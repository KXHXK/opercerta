"""Verify the Docker Compose inventory replenishment demonstration without secrets."""

import argparse
import json
import os
import subprocess
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    base_url = os.environ.get("OPERCERTA_API_URL", "http://127.0.0.1:8080")
    data = json.dumps(payload).encode() if payload is not None else None
    http_request = Request(f"{base_url}{path}", data=data, method=method)
    if data is not None:
        http_request.add_header("Content-Type", "application/json")
    try:
        with urlopen(http_request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-only", action="store_true")
    args = parser.parse_args()
    assert request("GET", "/health/live") == (200, {"status": "live"})
    assert request("GET", "/health/ready")[0] == 200
    if args.recovery_only:
        return
    _, created = request(
        "POST",
        "/api/v1/operations",
        {
            "message": "create replenishment work order for low inventory",
            "requested_action": "create_work_order",
            "object_type": "inventory",
            "object_id": "SKU-LOW-001",
        },
    )
    operation_id = created["operation_id"]
    _, detail = request("GET", f"/api/v1/operations/{operation_id}")
    binding = detail["approval_binding"]
    approval = {
        "approver_id": "compose.verifier",
        "decision": "approved",
        "reason": "compose smoke test",
        "expected_inventory_evidence_id": binding["inventory_evidence_id"],
        "expected_policy_evidence_id": binding["policy_evidence_id"],
        "expected_rule_version": binding["rule_version"],
        "expected_decision_facts_hash": binding["decision_facts_hash"],
        "expected_plan_hash": binding["plan_hash"],
        "expected_recommended_quantity": binding["recommended_quantity"],
    }
    assert request("POST", f"/api/v1/operations/{operation_id}/approval", approval)[0] == 202
    duplicate_status, duplicate = request(
        "POST", f"/api/v1/operations/{operation_id}/approval", approval
    )
    assert duplicate_status == 409 and duplicate["code"] == "approval_already_decided"
    query = (
        "docker compose exec -T postgres sh -c "
        '\'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT 1"\''
    )
    assert subprocess.run(query, shell=True, check=False).returncode == 0


if __name__ == "__main__":
    main()
