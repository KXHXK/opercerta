from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.recovery import OperationStatus
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_shared_entrypoint_preserves_inventory_no_action_result(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="查询正常库存并在需要时补货",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-NORMAL-001",
    )
    operation_id = await repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_action_graph(
                saver,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status is OperationStatus.COMPLETED
        assert detail.result is not None
        assert detail.result.outcome == "replenishment_not_required"
        assert detail.approval is None
        assert detail.work_order is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
