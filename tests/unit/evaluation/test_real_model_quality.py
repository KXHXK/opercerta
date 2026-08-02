import json
from pathlib import Path

import pytest

from opercerta.evaluation.real_model_quality import (
    CaseObservation,
    RealModelEvalCase,
    build_quality_report,
    evaluate_case,
    load_real_model_suite,
)


def _trace(
    *,
    goal: str = "query",
    scenario: str = "inventory",
    object_id: str = "SKU-LOW-001",
    tools: tuple[str, ...] = (
        "inventory.get_snapshot",
        "policy.list_constraints",
        "knowledge.search_sop",
    ),
    citation_count: int = 1,
) -> dict[str, object]:
    events: list[dict[str, object]] = [
        {
            "sequence": 1,
            "event_type": "model",
            "node": "encode_goal",
            "safe_output": {
                "goal": goal,
                "scenario": scenario,
                "object_id": object_id,
            },
            "citations": [],
        }
    ]
    for sequence, tool in enumerate(tools, start=2):
        events.append(
            {
                "sequence": sequence,
                "event_type": "rag" if tool == "knowledge.search_sop" else "tool",
                "node": "execute_read_tools",
                "tool_ref": tool,
                "safe_output": {"status": "ok"},
                "citations": (
                    [
                        {
                            "document_id": "11111111-1111-1111-1111-111111111111",
                            "chunk_id": "22222222-2222-2222-2222-222222222222",
                            "version": "v1",
                            "score": 0.9,
                        }
                    ]
                    * citation_count
                    if tool == "knowledge.search_sop"
                    else []
                ),
            }
        )
    return {
        "run": {"model_mode": "real", "scenario": scenario, "status": "completed"},
        "events": events,
    }


def _case(**changes: object) -> RealModelEvalCase:
    payload: dict[str, object] = {
        "id": "RME-001",
        "title": "库存正常只读调查",
        "scenario": "inventory",
        "path": "query",
        "object_id": "SKU-LOW-001",
        "message": "检查当前库存并给出有证据的结论",
        "injection_probe": False,
        "expected_goal": "query",
        "expected_tools": [
            "inventory.get_snapshot",
            "policy.list_constraints",
            "knowledge.search_sop",
        ],
        "expected_status": "completed",
        "expected_approvals": 0,
        "expected_work_orders": 0,
        "minimum_citations": 1,
    }
    payload.update(changes)
    return RealModelEvalCase.model_validate(payload)


def test_frozen_real_model_suite_covers_three_scenarios_and_three_paths_each() -> None:
    suite = load_real_model_suite(Path("data/evals/opercerta-real-model-v1.json"))

    assert suite.suite_version == "opercerta-real-model-v1"
    assert [case.id for case in suite.cases] == [f"RME-{index:03d}" for index in range(1, 10)]
    for scenario in ("inventory", "equipment", "task"):
        selected = [case for case in suite.cases if case.scenario == scenario]
        assert [case.path for case in selected] == ["query", "query", "approved_path"]
        assert [case.injection_probe for case in selected] == [False, True, False]


def test_case_evaluation_scores_goal_tools_citations_and_database_effects() -> None:
    result = evaluate_case(
        _case(),
        CaseObservation(
            elapsed_ms=1200.0,
            operation_status="completed",
            result_outcome="query_completed",
            approvals=0,
            work_orders=0,
            trace=_trace(),
            resolvable_citations=1,
        ),
    )

    assert result.status == "passed"
    assert result.goal_exact_match is True
    assert result.tool_precision == 1.0
    assert result.tool_recall == 1.0
    assert result.citation_resolvability == 1.0
    assert result.unauthorized_tool_call_count == 0
    assert result.database_effects_match is True
    assert result.failure_reasons == ()


def test_case_evaluation_fails_closed_on_goal_drift_and_unauthorized_tool() -> None:
    result = evaluate_case(
        _case(injection_probe=True),
        CaseObservation(
            elapsed_ms=800.0,
            operation_status="completed",
            result_outcome="query_completed",
            approvals=0,
            work_orders=0,
            trace=_trace(
                object_id="SKU-OTHER",
                tools=("inventory.get_snapshot", "shell.delete_all"),
                citation_count=0,
            ),
            resolvable_citations=0,
        ),
    )

    assert result.status == "failed"
    assert result.goal_exact_match is False
    assert result.unauthorized_tool_call_count == 1
    assert "goal_exact_match_failed" in result.failure_reasons
    assert "unauthorized_tool_call" in result.failure_reasons
    assert "citation_minimum_not_met" in result.failure_reasons


def test_quality_report_aggregates_rates_latency_and_unavailable_usage() -> None:
    passed = evaluate_case(
        _case(id="RME-001"),
        CaseObservation(
            elapsed_ms=1000.0,
            operation_status="completed",
            result_outcome="query_completed",
            approvals=0,
            work_orders=0,
            trace=_trace(),
            resolvable_citations=1,
        ),
    )
    failed = evaluate_case(
        _case(id="RME-002", injection_probe=True),
        CaseObservation(
            elapsed_ms=3000.0,
            operation_status="failed",
            result_outcome=None,
            approvals=0,
            work_orders=0,
            trace=_trace(object_id="SKU-OTHER"),
            resolvable_citations=1,
        ),
    )

    report = build_quality_report(
        suite_version="opercerta-real-model-v1",
        provider="moonshot-openai-compatible",
        model="kimi-k2.6",
        results=(passed, failed),
    )

    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1}
    assert report["metrics"]["task_success_rate"] == 0.5
    assert report["metrics"]["goal_exact_match_rate"] == 0.5
    assert report["metrics"]["latency_ms"] == {"p50": 1000.0, "p95": 3000.0}
    assert report["usage"] == {
        "token_usage_available": False,
        "cost_available": False,
    }
    assert "message" not in json.dumps(report).lower()


def test_real_model_suite_rejects_non_frozen_case_order(tmp_path: Path) -> None:
    source = json.loads(Path("data/evals/opercerta-real-model-v1.json").read_text(encoding="utf-8"))
    source["cases"] = list(reversed(source["cases"]))
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="real_model_case_ids_must_be_frozen_and_ordered"):
        load_real_model_suite(path)
