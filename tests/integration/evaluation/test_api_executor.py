from typing import cast

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.api.auth import JwtAuthenticator
from opercerta.domain.errors import UnknownTool
from opercerta.evaluation.contracts import EvalCase
from opercerta.evaluation.executor import ApiCaseExecutor
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from tests.integration.api.test_operations_api import open_api_harness
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture


class UnknownToolGateway:
    async def call_raw(self, name: str, arguments: dict[str, object]) -> object:
        del name, arguments
        raise UnknownTool


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


@pytest.mark.asyncio
async def test_api_executor_maps_unknown_mcp_tool_to_stable_case_result() -> None:
    executor = ApiCaseExecutor(
        cast(httpx.AsyncClient, None),
        cast(JwtAuthenticator, None),
        cast(ReplenishmentOperationRepository, None),
        gateway=cast(McpToolGateway, UnknownToolGateway()),
    )

    execution = await executor.execute(
        EvalCase(
            id="RPL-001",
            title="未知 MCP 工具",
            rule_refs=("test_rule",),
            actor="operator",
            steps=({"action": "invoke_mcp_tool", "tool": "inventory.delete_all"},),
            expected={"status_code": 400},
        )
    )

    assert execution.status_code == 400
    assert execution.error_code == "unknown_tool"
