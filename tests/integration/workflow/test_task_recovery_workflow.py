from datetime import UTC, datetime, timedelta
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
from opercerta.domain.scenarios import ScenarioKind
from opercerta.domain.task_recovery import TaskState
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


def request_for(task_id: str) -> OperationRequest:
    return OperationRequest(
        message=f"recover task {task_id} when policy requires it",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.TASK,
        object_id=task_id,
    )


def config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


async def cleanup(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_id", "expected_status", "expected_error"),
    [
        ("TASK-NORMAL-001", OperationStatus.COMPLETED, None),
        ("TASK-RETRY-LIMIT-001", OperationStatus.FAILED, "task_recovery_out_of_policy"),
    ],
)
async def test_task_query_terminal_paths_fail_closed(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    task_id: str,
    expected_status: OperationStatus,
    expected_error: str | None,
) -> None:
    repository = OperationRepository(engine)
    registry = build_default_scenario_registry()
    request = request_for(task_id)
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
                registry,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config(operation_id),
            )
            await saver.adelete_thread(str(operation_id))
        detail = await repository.load_detail(operation_id)
        assert detail.status is expected_status
        assert (detail.error.code if detail.error is not None else None) == expected_error
        assert detail.work_order is None
    finally:
        await cleanup(engine, operation_id)


@pytest.mark.asyncio
async def test_task_recovery_revalidates_blocker_and_writes_once(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    registry = build_default_scenario_registry()
    request = request_for("TASK-BLOCKED-001")
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
                registry,
            )
            result = await graph.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config(operation_id),
            )
            assert "__interrupt__" in result
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            assert waiting.approval_binding.scenario is ScenarioKind.TASK
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="task.recovery.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="bound task recovery facts are valid",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )
            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config(operation_id),
            )
            await saver.adelete_thread(str(operation_id))
        detail = await repository.load_detail(operation_id)
        assert detail.error is None, detail.error
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
        await cleanup(engine, operation_id)


@pytest.mark.asyncio
async def test_task_recovered_before_approval_write_fails_binding_revalidation(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    registry = build_default_scenario_registry()
    request = request_for("TASK-MUTABLE-001")
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
                registry,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config(operation_id),
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="task.recovery.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="approve original blocker facts",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )
            mcp_server.catalog.replace_task(
                "TASK-MUTABLE-001",
                state=TaskState.RUNNING,
                due_at=NOW + timedelta(minutes=10),
                last_progress_at=NOW,
                blocker_code=None,
                retry_count=1,
            )
            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config(operation_id),
            )
            await saver.adelete_thread(str(operation_id))
        detail = await repository.load_detail(operation_id)
        assert detail.status is OperationStatus.FAILED
        assert detail.error is not None
        assert detail.error.code == "approval_snapshot_mismatch"
        assert detail.work_order is None
    finally:
        await cleanup(engine, operation_id)
