import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.evaluation.contracts import EvalCase
from opercerta.evaluation.executor import ApiCaseExecutor
from tests.integration.api.test_operations_api import open_api_harness
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture


@pytest.mark.asyncio
async def test_api_executor_reads_real_low_inventory_operation_facts(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        executor = ApiCaseExecutor(
            harness.client,
            harness.authenticator,
            harness.operations,
        )
        execution = await executor.execute(
            EvalCase(
                id="RPL-001",
                title="低库存补货请求进入待审批",
                rule_refs=("test_rule",),
                actor="operator",
                steps=({"action": "create_operation", "sku": "SKU-LOW-001"},),
                expected={"status_code": 202},
            )
        )
        harness.operation_ids.extend(executor.operation_ids)

    assert execution.status_code == 202
    assert execution.terminal_status == "awaiting_approval"
    assert execution.approval_count == 0
    assert execution.work_order_count == 0
    assert execution.audit_event_names is not None
    assert "approval_requested" in execution.audit_event_names
