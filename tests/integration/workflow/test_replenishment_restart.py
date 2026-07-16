from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.application.operation_runner import OperationRunner
from opercerta.domain.approvals import (
    ApprovalDecision,
    BoundApprovalCommand,
)
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.recovery import OperationStatus, RecoveryAction
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    OperationDetail,
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.replenishment_graph import (
    ReplenishmentGraph,
    build_replenishment_graph,
    build_replenishment_initial_state,
)
from opercerta.workflow.replenishment_recovery import (
    ReplenishmentRecoveryCoordinator,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import (
    mcp_server as _mcp_server_fixture,
)

mcp_server = _mcp_server_fixture

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def request_for(sku: str = "SKU-LOW-001") -> OperationRequest:
    return OperationRequest(
        message=f"Check {sku} and replenish if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id=sku,
    )


def config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


def build_graph(
    saver: object,
    operations_repository: ReplenishmentOperationRepository,
    engine: AsyncEngine,
    mcp_server: McpServerHarness,
    *,
    approval_ttl_seconds: int = 300,
) -> ReplenishmentGraph:
    return build_replenishment_graph(
        saver,  # type: ignore[arg-type]
        operations_repository,
        EvidenceRepository(engine),
        McpToolGateway(mcp_server.url, timeout_seconds=2),
        MockModelGateway(),
        lambda: NOW,
        approval_ttl_seconds=approval_ttl_seconds,
    )


def bound_command(
    detail: OperationDetail,
    decision: ApprovalDecision,
) -> BoundApprovalCommand:
    assert detail.approval_binding is not None
    return BoundApprovalCommand(
        operation_id=detail.operation_id,
        approver_id="inventory.restart.manager",
        decision=decision,
        reason=f"{decision.value} after restart review",
        expected_binding=detail.approval_binding,
    )


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


async def interrupt_low_inventory(
    graph: ReplenishmentGraph,
    operations_repository: ReplenishmentOperationRepository,
    operation_id: UUID,
    request: OperationRequest,
) -> OperationDetail:
    result = await graph.ainvoke(
        build_replenishment_initial_state(operation_id, request),
        config=config(operation_id),
    )
    assert "__interrupt__" in result
    return await operations_repository.load_detail(operation_id)


@pytest.mark.asyncio
async def test_rebuilds_business_row_before_first_checkpoint_with_saver_b(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            build_graph(saver_a, operations_repository, engine, mcp_server)

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_graph(
                saver_b,
                operations_repository,
                engine,
                mcp_server,
            )
            action = await ReplenishmentRecoveryCoordinator(
                graph_b,
                operations_repository,
            ).recover(operation_id)
            snapshot = await graph_b.aget_state(config(operation_id))
            assert snapshot.interrupts
            await saver_b.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS
        assert detail.status is OperationStatus.AWAITING_APPROVAL
        assert detail.approval is None
        assert detail.work_order is None
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_restart_at_waiting_interrupt_keeps_waiting_without_writes(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_graph(
                saver_a,
                operations_repository,
                engine,
                mcp_server,
            )
            before = await interrupt_low_inventory(
                graph_a,
                operations_repository,
                operation_id,
                request,
            )

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_graph(
                saver_b,
                operations_repository,
                engine,
                mcp_server,
            )
            action = await ReplenishmentRecoveryCoordinator(
                graph_b,
                operations_repository,
            ).recover(operation_id)
            await saver_b.adelete_thread(str(operation_id))

        after = await operations_repository.load_detail(operation_id)
        assert action is RecoveryAction.KEEP_WAITING
        assert after.status is OperationStatus.AWAITING_APPROVAL
        assert after.event_types == before.event_types
        assert after.approval is None
        assert after.work_order is None
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_work_orders"),
    [
        (ApprovalDecision.APPROVED, OperationStatus.COMPLETED, 1),
        (ApprovalDecision.REJECTED, OperationStatus.REJECTED, 0),
    ],
)
async def test_restart_resumes_committed_bound_decision(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    decision: ApprovalDecision,
    expected_status: OperationStatus,
    expected_work_orders: int,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_graph(
                saver_a,
                operations_repository,
                engine,
                mcp_server,
            )
            waiting = await interrupt_low_inventory(
                graph_a,
                operations_repository,
                operation_id,
                request,
            )

        approval = await ApprovalRepository(engine).submit_bound_once(
            bound_command(waiting, decision),
            NOW,
        )

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_graph(
                saver_b,
                operations_repository,
                engine,
                mcp_server,
            )
            action = await ReplenishmentRecoveryCoordinator(
                graph_b,
                operations_repository,
            ).recover(operation_id)
            await saver_b.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert action is RecoveryAction.RESUME_DECISION
        assert detail.status is expected_status
        assert detail.approval is not None
        assert detail.approval.id == approval.id
        assert int(detail.work_order is not None) == expected_work_orders
        assert detail.event_types.count("approval_recorded") == 1
        assert detail.event_types.count("work_order_created") == expected_work_orders
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_restart_replays_prewritten_work_order_and_keeps_original_id(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_graph(
                saver_a,
                operations_repository,
                engine,
                mcp_server,
            )
            waiting = await interrupt_low_inventory(
                graph_a,
                operations_repository,
                operation_id,
                request,
            )

        await ApprovalRepository(engine).submit_bound_once(
            bound_command(waiting, ApprovalDecision.APPROVED),
            NOW,
        )
        assert waiting.plan is not None
        prewritten = await WorkOrderRepository(engine).create_or_get(
            WorkOrderCommand(
                operation_id=operation_id,
                payload={
                    "approved_plan_hash": waiting.plan.plan_hash,
                    "quantity": waiting.plan.recommended_quantity,
                    "sku": waiting.plan.sku,
                },
            )
        )
        assert prewritten.replayed is False

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_graph(
                saver_b,
                operations_repository,
                engine,
                mcp_server,
            )
            action = await ReplenishmentRecoveryCoordinator(
                graph_b,
                operations_repository,
            ).recover(operation_id)
            snapshot = await graph_b.aget_state(config(operation_id))
            assert snapshot.values["replayed"] is True
            await saver_b.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert action is RecoveryAction.RESUME_DECISION
        assert detail.status is OperationStatus.COMPLETED
        assert detail.work_order is not None
        assert detail.work_order.id == prewritten.work_order.id
        assert detail.event_types.count("work_order_created") == 1
        assert detail.event_types.count("operation_completed") == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_runner_expires_due_approval_before_recovery_scan(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_graph(
                saver_a,
                operations_repository,
                engine,
                mcp_server,
                approval_ttl_seconds=1,
            )
            await interrupt_low_inventory(
                graph_a,
                operations_repository,
                operation_id,
                request,
            )

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_graph(
                saver_b,
                operations_repository,
                engine,
                mcp_server,
                approval_ttl_seconds=1,
            )
            recovery = ReplenishmentRecoveryCoordinator(
                graph_b,
                operations_repository,
            )
            runner = OperationRunner(
                graph_b,
                ApprovalRepository(engine),
                operations_repository,
                recovery,
                ApprovalExpiryService(
                    operations_repository,
                    lambda: NOW + timedelta(seconds=2),
                ),
                lambda: NOW + timedelta(seconds=2),
            )
            recovered = await runner.recover_all()
            await saver_b.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert recovered == []
        assert detail.status is OperationStatus.EXPIRED
        assert detail.approval is None
        assert detail.work_order is None
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_runner_persists_request_and_bound_approval_before_graph_resume(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for()
    operation_id: UUID | None = None

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_graph(
                saver,
                operations_repository,
                engine,
                mcp_server,
            )
            runner = OperationRunner(
                graph,
                ApprovalRepository(engine),
                operations_repository,
                ReplenishmentRecoveryCoordinator(
                    graph,
                    operations_repository,
                ),
                ApprovalExpiryService(operations_repository, lambda: NOW),
                lambda: NOW,
            )
            operation_id = await runner.start(request)
            waiting = await operations_repository.load_detail(operation_id)
            returned_id = await runner.submit_approval(
                bound_command(waiting, ApprovalDecision.APPROVED),
                NOW,
            )
            await saver.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert returned_id == operation_id
        assert detail.status is OperationStatus.COMPLETED
        assert detail.approval is not None
        assert detail.work_order is not None
    finally:
        if operation_id is not None:
            await cleanup_operation(engine, operation_id)
