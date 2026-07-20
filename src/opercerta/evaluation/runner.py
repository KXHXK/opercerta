"""Run frozen evaluation cases and preserve every per-case result."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from opercerta.evaluation.contracts import EvalCase, EvalSuite

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|authorization|database_url)\s*[=:]\s*[^\s,;]+"
)
_DATABASE_URL = re.compile(r"(?i)\bpostgres(?:ql)?(?:\+[a-z0-9_-]+)?://[^\s,;]+")
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")


class CaseExecution(BaseModel):
    """Observable result returned by a real evaluation boundary executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status_code: int
    error_code: str | None = None
    terminal_status: str | None = None
    approval_count: int | None = None
    work_order_count: int | None = None
    audit_event_names: tuple[str, ...] | None = None
    tool_names: tuple[str, ...] = ()


class CaseExecutor(Protocol):
    """Executes a case through the selected real boundary harness."""

    async def execute(self, case: EvalCase) -> CaseExecution: ...


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    scenario: str
    status: str
    duration_ms: int = Field(ge=0)
    expected: Mapping[str, object]
    expected_tools: tuple[str, ...]
    actual: CaseExecution | None = None
    failure_summary: str | None = None


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_version: str
    started_at: datetime
    finished_at: datetime
    environment: Mapping[str, str]
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    cases: tuple[EvaluationCaseResult, ...]


async def run_suite(
    suite: EvalSuite,
    output_dir: Path,
    *,
    executor: CaseExecutor,
    environment: Mapping[str, str] | None = None,
) -> EvaluationReport:
    """Execute all frozen cases; never hide a failed assertion or exception."""
    started_at = datetime.now(UTC)
    results: list[EvaluationCaseResult] = []
    for case in suite.cases:
        started = perf_counter()
        execution: CaseExecution | None = None
        try:
            execution = await executor.execute(case)
            _assert_expected(case, execution)
        except Exception as error:  # report every case and continue with the suite
            results.append(
                EvaluationCaseResult(
                    id=case.id,
                    scenario=case.scenario.value,
                    status="failed",
                    duration_ms=_duration_ms(started),
                    expected=dict(case.expected),
                    expected_tools=case.expected_tools,
                    actual=execution,
                    failure_summary=_safe_failure_summary(error),
                )
            )
        else:
            results.append(
                EvaluationCaseResult(
                    id=case.id,
                    scenario=case.scenario.value,
                    status="passed",
                    duration_ms=_duration_ms(started),
                    expected=dict(case.expected),
                    expected_tools=case.expected_tools,
                    actual=execution,
                )
            )

    report = EvaluationReport(
        suite_version=suite.suite_version,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        environment=dict(environment or {"execution": "unspecified"}),
        total=len(results),
        passed=sum(result.status == "passed" for result in results),
        failed=sum(result.status == "failed" for result in results),
        cases=tuple(results),
    )
    _write_report(report, output_dir)
    return report


def _assert_expected(case: EvalCase, execution: CaseExecution) -> None:
    expected = case.expected
    actual = execution.model_dump(exclude_none=True)
    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        if field == "audit_event_names" and isinstance(expected_value, list):
            actual_events = actual_value if isinstance(actual_value, tuple) else ()
            missing = [event for event in expected_value if event not in actual_events]
            if missing:
                raise AssertionError(f"audit_event_names missing {missing!r}, got {actual_value!r}")
            continue
        if actual_value != expected_value:
            raise AssertionError(f"{field} expected {expected_value!r}, got {actual_value!r}")
    missing_tools = [name for name in case.expected_tools if name not in execution.tool_names]
    if missing_tools:
        raise AssertionError(f"tool_names missing {missing_tools!r}, got {execution.tool_names!r}")


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _safe_failure_summary(error: Exception) -> str:
    summary = str(error)
    summary = _SENSITIVE_ASSIGNMENT.sub(r"\1=[redacted]", summary)
    summary = _DATABASE_URL.sub("database_url=[redacted]", summary)
    summary = _BEARER_TOKEN.sub("Bearer [redacted]", summary)
    return f"{type(error).__name__}: {summary[:500]}"


def _write_report(report: EvaluationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report.suite_version}-report.json"
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
