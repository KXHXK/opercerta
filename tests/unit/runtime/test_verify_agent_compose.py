import subprocess

import pytest

from scripts.verify_agent_compose import assert_agent_trace, ingest_knowledge


def complete_trace() -> dict[str, object]:
    return {
        "run": {
            "scenario": "inventory",
            "status": "completed",
            "model_mode": "mock",
            "next_sequence": 8,
        },
        "events": [
            {"sequence": 1, "event_type": "perception", "tool_ref": None, "citations": []},
            {"sequence": 2, "event_type": "model", "tool_ref": None, "citations": []},
            {
                "sequence": 3,
                "event_type": "tool",
                "tool_ref": "inventory.get_snapshot",
                "citations": [],
            },
            {
                "sequence": 4,
                "event_type": "rag",
                "tool_ref": "knowledge.search_sop",
                "citations": [{"document_id": "a", "chunk_id": "b", "version": "1.0.0", "rank": 1}],
            },
            {"sequence": 5, "event_type": "rule", "tool_ref": None, "citations": []},
            {"sequence": 6, "event_type": "human", "tool_ref": None, "citations": []},
            {"sequence": 7, "event_type": "execution", "tool_ref": None, "citations": []},
            {"sequence": 8, "event_type": "feedback", "tool_ref": None, "citations": []},
        ],
    }


def test_agent_trace_assertion_accepts_complete_redacted_rag_trajectory() -> None:
    assert_agent_trace(
        complete_trace(),
        expected_scenario="inventory",
        expected_status="completed",
        require_approval=True,
        require_citations=True,
    )


def test_agent_trace_assertion_rejects_sequence_gap() -> None:
    trace = complete_trace()
    trace["events"][3]["sequence"] = 9  # type: ignore[index]

    with pytest.raises(AssertionError, match="contiguous"):
        assert_agent_trace(
            trace,
            expected_scenario="inventory",
            expected_status="completed",
            require_approval=True,
            require_citations=True,
        )


def test_agent_trace_assertion_rejects_forbidden_tool_or_secret() -> None:
    trace = complete_trace()
    trace["events"][2]["tool_ref"] = "shell.delete_all"  # type: ignore[index]
    trace["events"][2]["safe_output"] = {"authorization": "Bearer secret"}  # type: ignore[index]

    with pytest.raises(AssertionError, match="forbidden tool"):
        assert_agent_trace(
            trace,
            expected_scenario="inventory",
            expected_status="completed",
            require_approval=True,
            require_citations=True,
        )


def test_agent_trace_assertion_requires_real_citation_records_when_requested() -> None:
    trace = complete_trace()
    trace["events"][3]["citations"] = []  # type: ignore[index]

    with pytest.raises(AssertionError, match="citation"):
        assert_agent_trace(
            trace,
            expected_scenario="inventory",
            expected_status="completed",
            require_approval=True,
            require_citations=True,
        )


def test_knowledge_ingest_runs_real_fastembed_inside_mcp_container(monkeypatch) -> None:
    observed: list[list[str]] = []

    def fake_run(command, **kwargs):
        observed.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"level":"ERROR","message":"synthetic library log"}\n'
                '[{"scenario":"inventory"},{"scenario":"equipment"},{"scenario":"task"}]'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = ingest_knowledge()

    assert observed == [
        [
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
    ]
    assert {item["scenario"] for item in report} == {"inventory", "equipment", "task"}
