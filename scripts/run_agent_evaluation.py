"""Run the frozen Agent safety/recovery evidence suite and write a transparent report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from opercerta.evaluation.contracts import AgentEvalCase, AgentEvalSuite, load_agent_suite

DIMENSIONS = (
    "task_terminal",
    "tool_selection",
    "citations",
    "approval",
    "database_effects",
    "recovery",
    "security",
)


def build_case_command(case: AgentEvalCase) -> list[str]:
    return ["-m", "pytest", *case.evidence_tests, "-q"]


def build_report(
    suite: AgentEvalSuite,
    outcomes: dict[str, tuple[bool, str]],
) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for case in suite.cases:
        passed, failure_summary = outcomes[case.id]
        cases.append(
            {
                "id": case.id,
                "requirement": case.requirement,
                "status": "passed" if passed else "failed",
                "evidence_tests": list(case.evidence_tests),
                "expected": case.expected.model_dump(mode="json"),
                "failure_summary": failure_summary or None,
            }
        )
    passed_count = sum(case["status"] == "passed" for case in cases)
    dimensions = {
        name: {
            "total": len(cases),
            "passed": passed_count,
            "failed": len(cases) - passed_count,
        }
        for name in DIMENSIONS
    }
    return {
        "suite_version": suite.suite_version,
        "evidence_mode": suite.model_mode,
        "executed_at": datetime.now(UTC).isoformat(),
        "boundary": "pytest+FastAPI+LangGraph+FastMCP+PostgreSQL",
        "summary": {
            "total": len(cases),
            "passed": passed_count,
            "failed": len(cases) - passed_count,
        },
        "dimensions": dimensions,
        "cases": cases,
    }


def _safe_failure(output: str) -> str:
    lowered = output.lower()
    for marker in ("password=", "token=", "authorization:", "database_url="):
        if marker in lowered:
            return "pytest failed; detailed output omitted because it may contain credentials"
    return output[-1000:].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("data/evals/opercerta-agent-v1.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/evals"))
    args = parser.parse_args()
    suite = load_agent_suite(args.suite)
    outcomes: dict[str, tuple[bool, str]] = {}
    for case in suite.cases:
        result = subprocess.run(
            [sys.executable, *build_case_command(case)],
            check=False,
            capture_output=True,
            text=True,
        )
        outcomes[case.id] = (
            result.returncode == 0,
            "" if result.returncode == 0 else _safe_failure(result.stdout + result.stderr),
        )
    report = build_report(suite, outcomes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "opercerta-agent-v1-mock-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    raise SystemExit(1 if report["summary"]["failed"] else 0)  # type: ignore[index]


if __name__ == "__main__":
    main()
