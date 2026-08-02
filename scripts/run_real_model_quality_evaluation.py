"""Run the frozen nine-path real-model quality evaluation through Compose."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from opercerta.evaluation.real_model_quality import (
    CaseObservation,
    RealModelCaseResult,
    RealModelEvalCase,
    build_quality_report,
    evaluate_case,
    load_real_model_suite,
)
from scripts.verify_agent_compose import ingest_knowledge
from scripts.verify_compose import (
    demo_headers,
    postgres_scalar,
    request,
    wait_for_ready,
)
from scripts.verify_real_model import (
    RepresentativeValidationError,
    assert_real_model_runtime,
    run_approved_path,
    run_query,
)

Scalar = Callable[[str], str]


def count_resolvable_citations(
    trace: dict[str, object],
    scenario: str,
    *,
    scalar: Scalar = postgres_scalar,
) -> int:
    if scenario not in {"inventory", "equipment", "task"}:
        raise ValueError("unsupported evaluation scenario")
    events = trace.get("events")
    if not isinstance(events, list):
        return 0
    resolved = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        citations = event.get("citations")
        if not isinstance(citations, list):
            continue
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            try:
                document_id = UUID(str(citation["document_id"]))
                chunk_id = UUID(str(citation["chunk_id"]))
            except (KeyError, TypeError, ValueError):
                continue
            version = citation.get("version")
            if (
                not isinstance(version, str)
                or not version
                or len(version) > 64
                or not all(
                    character.isalnum() or character in {".", "-", "_"} for character in version
                )
            ):
                continue
            sql = (
                "SELECT COUNT(*) FROM knowledge_chunks c "
                "JOIN knowledge_documents d ON d.id = c.document_id "
                f"WHERE d.id = '{document_id}' AND c.id = '{chunk_id}' "
                f"AND d.scenario = '{scenario}' AND d.version = '{version}' "
                "AND d.active IS TRUE"
            )
            if scalar(sql) == "1":
                resolved += 1
    return resolved


def _database_count(table: str, operation_id: str) -> int:
    validated = UUID(operation_id)
    return int(postgres_scalar(f"SELECT COUNT(*) FROM {table} WHERE operation_id = '{validated}'"))


def _load_observation(
    case: RealModelEvalCase,
    runtime_result: dict[str, Any],
) -> CaseObservation:
    operation_id = str(UUID(runtime_result["operation_id"]))
    operator_headers = demo_headers("operator")
    detail_status, detail = request(
        "GET",
        f"/api/v1/operations/{operation_id}",
        headers=operator_headers,
    )
    if detail_status != 200 or not isinstance(detail, dict):
        raise AssertionError("evaluation operation detail unavailable")
    trace_status, trace = request(
        "GET",
        f"/api/v1/operations/{operation_id}/agent-trace",
        headers=operator_headers,
    )
    if trace_status != 200 or not isinstance(trace, dict):
        raise AssertionError("evaluation Agent Trace unavailable")
    result = detail.get("result")
    outcome = result.get("outcome") if isinstance(result, dict) else None
    elapsed = runtime_result.get("elapsed_ms", runtime_result.get("create_operation_elapsed_ms"))
    if not isinstance(elapsed, int | float):
        raise AssertionError("evaluation latency unavailable")
    return CaseObservation(
        elapsed_ms=float(elapsed),
        operation_status=str(detail.get("status", "unknown")),
        result_outcome=outcome if isinstance(outcome, str) else None,
        approvals=_database_count("approvals", operation_id),
        work_orders=_database_count("work_orders", operation_id),
        trace=trace,
        resolvable_citations=count_resolvable_citations(trace, case.scenario),
    )


def _safe_failed_result(case: RealModelEvalCase, stage: str) -> RealModelCaseResult:
    return RealModelCaseResult(
        id=case.id,
        title=case.title,
        scenario=case.scenario,
        path=case.path,
        injection_probe=case.injection_probe,
        status="failed",
        elapsed_ms=0.0,
        goal_exact_match=False,
        tool_precision=0.0,
        tool_recall=0.0,
        evidence_completeness=0.0,
        citation_count=0,
        citation_resolvability=0.0,
        model_call_count=0,
        tool_call_count=0,
        unauthorized_tool_call_count=0,
        actual_approvals=0,
        actual_work_orders=0,
        approval_bypass=False,
        unexpected_work_order_count=0,
        database_effects_match=False,
        failure_reasons=(stage,),
    )


def run_case(
    case: RealModelEvalCase,
    *,
    operator_headers: dict[str, str],
    approver_headers: dict[str, str],
) -> RealModelCaseResult:
    try:
        if case.path == "query":
            runtime_result = run_query(
                case.scenario,
                case.object_id,
                operator_headers,
                message=case.message,
            )
        else:
            expected_kind = {
                "inventory": "replenishment",
                "equipment": "repair",
                "task": "task_recovery",
            }[case.scenario]
            runtime_result = run_approved_path(
                case.scenario,
                case.object_id,
                expected_kind,
                operator_headers,
                approver_headers,
            )
        return evaluate_case(case, _load_observation(case, runtime_result))
    except Exception as error:
        # Reports preserve only a bounded failure category, never provider text,
        # prompts, raw responses, environment values, or exception messages.
        if isinstance(error, RepresentativeValidationError):
            safe_stage = error.detail.get("stage")
            if isinstance(safe_stage, str):
                parts = ["runtime", safe_stage]
                for name in ("operation_status", "error_code"):
                    value = error.detail.get(name)
                    if isinstance(value, str):
                        parts.append(value)
                return _safe_failed_result(case, "_".join(parts))
        return _safe_failed_result(case, f"runtime_{type(error).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("data/evals/opercerta-real-model-v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/evals/opercerta-real-model-v1-report.json"),
    )
    parser.add_argument("--provider", default="moonshot-openai-compatible")
    parser.add_argument("--case-id")
    args = parser.parse_args()

    suite = load_real_model_suite(args.suite)
    wait_for_ready(90)
    assert_real_model_runtime()
    ingest_knowledge()
    operator_headers = demo_headers("operator")
    approver_headers = demo_headers("approver")
    selected_cases = tuple(
        case for case in suite.cases if args.case_id is None or case.id == args.case_id
    )
    if not selected_cases:
        raise ValueError("requested real-model evaluation case does not exist")
    results = tuple(
        run_case(
            case,
            operator_headers=operator_headers,
            approver_headers=approver_headers,
        )
        for case in selected_cases
    )
    report = build_quality_report(
        suite_version=suite.suite_version,
        provider=args.provider,
        model=os.environ.get("OPERCERTA_MODEL_NAME", "configured-model"),
        results=results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise TypeError("evaluation summary must be an object")
    print(json.dumps(summary, ensure_ascii=False))
    if summary.get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
