from pathlib import Path

import pytest

from opercerta.evaluation.contracts import EvalCase, EvalSuite
from opercerta.evaluation.runner import CaseExecution, run_suite


class StatusExecutor:
    async def execute(self, case: EvalCase) -> CaseExecution:
        del case
        return CaseExecution(status_code=202)


class SecretFailingExecutor:
    async def execute(self, case: EvalCase) -> CaseExecution:
        del case
        raise RuntimeError("token=not-for-report password=also-not-for-report")


@pytest.mark.asyncio
async def test_runner_records_a_failed_assertion_instead_of_skipping_it(
    tmp_path: Path,
) -> None:
    suite = EvalSuite(
        suite_version="replenishment-v1",
        cases=tuple(
            EvalCase(
                id=f"RPL-{number:03d}",
                title=f"synthetic case {number}",
                rule_refs=("test_rule",),
                actor="operator",
                steps=({"action": "return_status", "status_code": 202},),
                expected={"status_code": 418},
            )
            for number in range(1, 31)
        ),
    )

    report = await run_suite(suite, tmp_path, executor=StatusExecutor())

    assert report.total == 30
    assert report.passed == 0
    assert report.failed == 30
    assert report.cases[0].failure_summary
    assert (tmp_path / "replenishment-v1-report.json").is_file()


@pytest.mark.asyncio
async def test_runner_redacts_sensitive_failure_text(tmp_path: Path) -> None:
    suite = EvalSuite(
        suite_version="replenishment-v1",
        cases=tuple(
            EvalCase(
                id=f"RPL-{number:03d}",
                title=f"synthetic case {number}",
                rule_refs=("test_rule",),
                actor="operator",
                steps=({"action": "raise"},),
                expected={"status_code": 202},
            )
            for number in range(1, 31)
        ),
    )

    report = await run_suite(suite, tmp_path, executor=SecretFailingExecutor())

    serialized = (tmp_path / "replenishment-v1-report.json").read_text(encoding="utf-8")
    assert report.failed == 30
    assert "not-for-report" not in serialized
    assert "[redacted]" in serialized
