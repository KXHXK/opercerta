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
from opercerta.domain.errors import ApprovalAlreadyDecided
from opercerta.domain.maintenance import AlertSeverity, EquipmentState
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.scenarios import RepairParameters, ScenarioKind
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


def request_for(equipment_id: str) -> OperationRequest:
    return OperationRequest(
        message=f"检查设备 {equipment_id}, 必要时创建维修工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.EQUIPMENT,
        object_id=equipment_id,
    )


def config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


async def cleanup(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_healthy_equipment_completes_without_approval_or_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = request_for("EQ-FAN-001")
    operation_id = await repository.create(request)
    registry = build_default_scenario_registry()

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
        assert detail.status is OperationStatus.COMPLETED
        assert detail.result is not None
        assert detail.result.outcome == "maintenance_not_required"
        assert detail.approval is None
        assert detail.work_order is None
    finally:
        await cleanup(engine, operation_id)


@pytest.mark.asyncio
async def test_equipment_repair_requires_bound_approval_and_is_idempotent(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = request_for("EQ-PUMP-001")
    operation_id = await repository.create(request)
    registry = build_default_scenario_registry()

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
            interrupted = await graph.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config(operation_id),
            )
            assert "__interrupt__" in interrupted

            waiting = await repository.load_detail(operation_id)
            assert waiting.status is OperationStatus.AWAITING_APPROVAL
            assert waiting.approval_binding is not None
            assert waiting.approval_binding.scenario is ScenarioKind.EQUIPMENT
            assert waiting.approval_binding.parameters == RepairParameters(
                alert_code="MOTOR_OVERHEAT", priority="urgent"
            )
            command = BoundApprovalCommand(
                operation_id=operation_id,
                approver_id="maintenance.manager",
                decision=ApprovalDecision.APPROVED,
                reason="告警证据与维修计划一致",
                expected_binding=waiting.approval_binding,
            )
            approval = await ApprovalRepository(engine).submit_bound_once(command, NOW)
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

        completed = await repository.load_detail(operation_id)
        assert completed.status is OperationStatus.COMPLETED
        assert completed.work_order is not None
        assert completed.work_order.payload["kind"] == "repair"
        assert completed.work_order.payload["equipment_id"] == "EQ-PUMP-001"
        async with engine.connect() as connection:
            count = await connection.scalar(
                select(func.count())
                .select_from(work_orders)
                .where(work_orders.c.operation_id == operation_id)
            )
        assert count == 1
        with pytest.raises(ApprovalAlreadyDecided, match="approval_already_decided"):
            await ApprovalRepository(engine).submit_bound_once(command, NOW)
    finally:
        await cleanup(engine, operation_id)


@pytest.mark.asyncio
async def test_approved_repair_fails_if_equipment_recovers_before_write(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = request_for("EQ-MUTABLE-001")
    operation_id = await repository.create(request)
    registry = build_default_scenario_registry()

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
                    approver_id="maintenance.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="approve the original bound repair plan",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )
            mcp_server.catalog.replace_equipment(
                "EQ-MUTABLE-001",
                state=EquipmentState.HEALTHY,
                alert_code=None,
                severity=AlertSeverity.NONE,
                last_heartbeat=NOW,
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

        failed = await repository.load_detail(operation_id)
        assert failed.status is OperationStatus.FAILED
        assert failed.error is not None
        assert failed.error.code == "approval_snapshot_mismatch"
        assert failed.work_order is None
    finally:
        await cleanup(engine, operation_id)
