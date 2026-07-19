from datetime import UTC, datetime
from uuid import UUID

import pytest
from langgraph.types import Command
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.recovery import OperationStatus
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations, work_orders
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


@pytest.mark.asyncio
async def test_restart_after_task_decision_creates_exactly_one_recovery_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    registry = build_default_scenario_registry()
    request = OperationRequest(
        message="resume blocked task recovery after restart",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.TASK,
        object_id="TASK-BLOCKED-001",
    )
    operation_id = await repository.create(request)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_controlled_action_graph(
                saver_a,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                registry,
            )
            await graph_a.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config(operation_id),
            )

        waiting = await repository.load_detail(operation_id)
        assert waiting.approval_binding is not None
        approval = await ApprovalRepository(engine).submit_bound_once(
            BoundApprovalCommand(
                operation_id=operation_id,
                approver_id="task.restart.manager",
                decision=ApprovalDecision.APPROVED,
                reason="continue bound task recovery after restart",
                expected_binding=waiting.approval_binding,
            ),
            NOW,
        )

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_controlled_action_graph(
                saver_b,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                registry,
            )
            await graph_b.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config(operation_id),
            )
            await saver_b.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status is OperationStatus.COMPLETED
        assert detail.work_order is not None
        assert detail.work_order.payload["kind"] == "task_recovery"
        async with engine.connect() as connection:
            count = await connection.scalar(
                select(func.count())
                .select_from(work_orders)
                .where(work_orders.c.operation_id == operation_id)
            )
        assert count == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
