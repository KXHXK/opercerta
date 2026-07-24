"""Verify a real Compose Agent trajectory, citations, writes, and restart recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

if __package__:
    from scripts import verify_compose
else:
    import verify_compose

ALLOWED_TOOLS = {
    "inventory.get_snapshot",
    "equipment.get_status",
    "task.get_status",
    "policy.list_constraints",
    "knowledge.search_sop",
    "work_order.create",
    "work_order.get",
}
FORBIDDEN_TEXT = (
    "authorization",
    "bearer ",
    "api_key",
    "database_url",
    "password",
    "stack_trace",
    "traceback",
)


def _decode_knowledge_report(output: str) -> list[dict[str, Any]]:
    array_start = next(
        (offset for offset in range(len(output)) if output[offset] == "["),
        -1,
    )
    assert array_start >= 0, "knowledge ingestion report is missing"
    payload, _ = json.JSONDecoder().raw_decode(output[array_start:])
    assert isinstance(payload, list)
    return payload


def ingest_knowledge() -> list[dict[str, Any]]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mcp",
        "python",
        "scripts/ingest_knowledge.py",
        "--cache-dir",
        "/home/opercerta/.cache/fastembed",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 0, "knowledge ingestion failed"
    payload = _decode_knowledge_report(result.stdout)
    assert len(payload) == 3
    assert {item["scenario"] for item in payload} == {"inventory", "equipment", "task"}
    return payload


def assert_agent_trace(
    trace: dict[str, Any],
    *,
    expected_scenario: str,
    expected_status: str,
    require_approval: bool,
    require_citations: bool,
) -> None:
    run = trace["run"]
    events = trace["events"]
    assert run["scenario"] == expected_scenario
    assert run["status"] == expected_status
    sequences = [event["sequence"] for event in events]
    assert sequences == list(range(1, len(events) + 1)), "trace sequences must be contiguous"
    event_types = {event["event_type"] for event in events}
    required = {"perception", "model", "tool", "rule", "feedback"}
    if require_approval:
        required |= {"human", "execution", "guardrail"}
    if require_approval:
        nodes = [event.get("node") for event in events]
        try:
            verifier_index = nodes.index("verify_current_facts")
            binding_index = nodes.index("verify_approval_binding")
            execution_index = nodes.index("execute_controlled_action")
        except ValueError as error:
            raise AssertionError(
                "approved Agent Trace requires Verifier, binding guardrail, and execution nodes"
            ) from error
        assert verifier_index < binding_index < execution_index, (
            "Verifier and binding guardrail must complete before controlled execution"
        )
    assert required <= event_types
    tool_refs = {event.get("tool_ref") for event in events if event.get("tool_ref")}
    forbidden_tools = tool_refs - ALLOWED_TOOLS
    assert not forbidden_tools, f"forbidden tool in Agent Trace: {sorted(forbidden_tools)}"
    if require_citations:
        assert any(event.get("citations") for event in events), "Agent Trace citation is required"
        assert "rag" in event_types
    serialized = json.dumps(trace, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in serialized, f"forbidden trace content: {forbidden}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-only", action="store_true")
    args = parser.parse_args()
    verify_compose.wait_for_ready()
    operator_headers = verify_compose.demo_headers("operator")
    if args.recovery_only:
        verify_compose.verify_recovery_only(operator_headers)
        recovery_id = verify_compose.read_recovery_operation_id()
        status, trace = verify_compose.request(
            "GET",
            f"/api/v1/operations/{recovery_id}/agent-trace",
            headers=operator_headers,
        )
        assert status == 200
        assert_agent_trace(
            trace,
            expected_scenario="task",
            expected_status="awaiting_human",
            require_approval=False,
            require_citations=True,
        )
        assert "human" in {event["event_type"] for event in trace["events"]}
        return
    ingest_knowledge()
    approver_headers = verify_compose.demo_headers("approver")
    result = verify_compose.verify_full(operator_headers, approver_headers)
    for operation_id, scenario in result.completed:
        status, trace = verify_compose.request(
            "GET",
            f"/api/v1/operations/{operation_id}/agent-trace",
            headers=operator_headers,
        )
        assert status == 200
        assert_agent_trace(
            trace,
            expected_scenario=scenario,
            expected_status="completed",
            require_approval=True,
            require_citations=True,
        )


if __name__ == "__main__":
    main()
