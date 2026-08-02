from pathlib import Path

from scripts.run_real_model_quality_evaluation import count_resolvable_citations
from scripts.verify_real_model import _matching_signals


def test_real_model_runner_can_reuse_a_prebuilt_offline_image() -> None:
    script = Path("scripts/run_real_model_quality_evaluation.sh").read_text(encoding="utf-8")

    assert "OPERCERTA_EVAL_SKIP_BUILD" in script
    assert "docker compose up --no-build -d" in script


def test_count_resolvable_citations_requires_active_document_in_expected_scenario() -> None:
    statements: list[str] = []

    def scalar(sql: str) -> str:
        statements.append(sql)
        return "1"

    trace = {
        "events": [
            {
                "citations": [
                    {
                        "document_id": "11111111-1111-1111-1111-111111111111",
                        "chunk_id": "22222222-2222-2222-2222-222222222222",
                        "version": "v1",
                    }
                ]
            }
        ]
    }

    assert count_resolvable_citations(trace, "inventory", scalar=scalar) == 1
    assert "d.scenario = 'inventory'" in statements[0]
    assert "d.active IS TRUE" in statements[0]
    assert "d.version = 'v1'" in statements[0]


def test_count_resolvable_citations_rejects_malformed_identifiers_without_sql() -> None:
    trace = {
        "events": [
            {
                "citations": [
                    {
                        "document_id": "not-a-uuid'; DROP TABLE knowledge_documents;--",
                        "chunk_id": "22222222-2222-2222-2222-222222222222",
                        "version": "v1",
                    }
                ]
            }
        ]
    }

    assert (
        count_resolvable_citations(
            trace,
            "inventory",
            scalar=lambda _sql: (_ for _ in ()).throw(AssertionError("SQL must not run")),
        )
        == 0
    )


def test_matching_signals_can_recover_an_existing_active_signal() -> None:
    signals = [
        {
            "id": "signal-1",
            "object_type": "task",
            "object_id": "TASK-BLOCKED-001",
            "status": "open",
        },
        {
            "id": "signal-2",
            "object_type": "inventory",
            "object_id": "SKU-LOW-001",
            "status": "open",
        },
    ]

    assert _matching_signals(signals, "task", "TASK-BLOCKED-001") == [signals[0]]
