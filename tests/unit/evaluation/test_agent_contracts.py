import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from opercerta.evaluation.contracts import AgentEvalSuite, load_agent_suite
from scripts.run_agent_evaluation import build_case_command, build_report

SUITE_PATH = Path("data/evals/opercerta-agent-v1.json")


def test_agent_suite_freezes_all_required_negative_and_recovery_cases() -> None:
    suite = load_agent_suite(SUITE_PATH)

    assert suite.suite_version == "opercerta-agent-v1"
    assert suite.model_mode == "mock"
    assert [case.id for case in suite.cases] == [f"AGT-{index:03d}" for index in range(1, 10)]
    assert {case.requirement for case in suite.cases} == {
        "invalid_schema",
        "prompt_injection",
        "unknown_tool",
        "object_drift",
        "rag_cross_scenario",
        "fact_drift_after_approval",
        "concurrent_approval",
        "duplicate_write",
        "critical_node_restart",
    }


def test_every_agent_case_declares_a_complete_observable_contract() -> None:
    suite = load_agent_suite(SUITE_PATH)

    for case in suite.cases:
        assert case.input
        assert not set(case.allowed_tools) & set(case.forbidden_tools)
        assert case.expected.terminal_status
        assert case.expected.approval_state
        assert case.expected.verifier_branch
        assert case.expected.database_assertions
        assert case.evidence_tests
        assert all(
            nodeid.startswith("tests/") and "::test_" in nodeid for nodeid in case.evidence_tests
        )


def test_agent_case_rejects_overlapping_allowed_and_forbidden_tools() -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["allowed_tools"] = ["inventory.get_snapshot"]
    payload["cases"][0]["forbidden_tools"] = ["inventory.get_snapshot"]

    with pytest.raises(ValidationError, match="tool_contract_overlap"):
        AgentEvalSuite.model_validate(payload)


def test_agent_suite_rejects_missing_frozen_case() -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"].pop()

    with pytest.raises(ValidationError, match="agent_case_ids_must_be_frozen_and_ordered"):
        AgentEvalSuite.model_validate(payload)


def test_agent_evaluator_uses_declared_evidence_and_separates_report_dimensions() -> None:
    suite = load_agent_suite(SUITE_PATH)
    first = suite.cases[0]

    command = build_case_command(first)
    report = build_report(suite, {case.id: (True, "") for case in suite.cases})

    assert command[:3] == ["-m", "pytest", *first.evidence_tests[:1]]
    assert command[-1] == "-q"
    assert report["evidence_mode"] == "mock"
    assert report["summary"] == {"total": 9, "passed": 9, "failed": 0}
    assert set(report["dimensions"]) == {
        "task_terminal",
        "tool_selection",
        "citations",
        "approval",
        "database_effects",
        "recovery",
        "security",
    }
    serialized = json.dumps(report)
    assert "token" not in serialized.lower()
    assert "cost" not in serialized.lower()
