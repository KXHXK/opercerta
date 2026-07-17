import os
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.evaluation.contracts import load_suite
from opercerta.evaluation.executor import ApiCaseExecutor
from opercerta.evaluation.runner import run_suite
from tests.integration.api.test_operations_api import NOW, open_api_harness
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture


@pytest.mark.asyncio
async def test_frozen_replenishment_suite_runs_at_real_boundaries(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    tmp_path: Path,
) -> None:
    suite_path = Path(
        os.environ.get("OPERCERTA_EVALUATION_SUITE", "data/evals/replenishment-v3.json")
    )
    suite = load_suite(suite_path)
    output_dir = Path(os.environ.get("OPERCERTA_EVALUATION_OUTPUT_DIR", str(tmp_path)))
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        executor = ApiCaseExecutor(
            harness.client,
            harness.authenticator,
            harness.operations,
            approvals=harness.approvals,
            runner=harness.runner,
            catalog=harness.mcp_server.catalog,
            gateway=harness.gateway,
            clock=lambda: NOW,
        )
        report = await run_suite(
            suite,
            output_dir,
            executor=executor,
            environment={"boundary": "FastAPI+FastMCP+PostgreSQL"},
        )
        harness.operation_ids.extend(executor.operation_ids)

    assert report.total == 30
    assert report.failed == 0, [
        (case.id, case.failure_summary) for case in report.cases if case.status == "failed"
    ]
    assert report.passed == 30
    assert (output_dir / f"{suite.suite_version}-report.json").is_file()
