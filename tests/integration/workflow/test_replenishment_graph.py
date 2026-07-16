import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.replenishment import (
    InventoryEvidence,
    ModelPlanExplanation,
    PolicyEvidence,
    ReplenishmentAssessment,
)
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.replenishment_graph import (
    build_replenishment_graph,
    build_replenishment_initial_state,
)
from tests.integration.mcp.conftest import (
    McpServerHarness,
)
from tests.integration.mcp.conftest import (
    mcp_server as _mcp_server_fixture,
)

mcp_server = _mcp_server_fixture

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


class CountingModelGateway(MockModelGateway):
    def __init__(self) -> None:
        self.calls = 0

    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        self.calls += 1
        return await super().explain_plan(assessment)


class FakeEvidenceGateway:
    def __init__(
        self,
        inventory: object,
        policy: object,
    ) -> None:
        self._inventory = inventory
        self._policy = policy

    async def get_inventory(self, sku: str) -> object:
        del sku
        return self._inventory

    async def get_policy(self, sku: str) -> object:
        del sku
        return self._policy


def request_for(sku: str) -> OperationRequest:
    return OperationRequest(
        message=f"Check {sku} and replenish if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id=sku,
    )


def config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


def inventory(
    *,
    captured_at: datetime = NOW,
    on_hand_quantity: int = 20,
) -> InventoryEvidence:
    return InventoryEvidence(
        evidence_id=UUID("10000000-0000-4000-8000-000000000001"),
        sku="SKU-LOW-001",
        on_hand_quantity=on_hand_quantity,
        reserved_quantity=8,
        captured_at=captured_at,
        source_version="inventory-seed-v1",
    )


def policy(*, captured_at: datetime = NOW) -> PolicyEvidence:
    return PolicyEvidence(
        evidence_id=UUID("20000000-0000-4000-8000-000000000002"),
        action="replenish_inventory",
        sku="SKU-LOW-001",
        reorder_point=15,
        target_stock=30,
        minimum_order_quantity=1,
        maximum_order_quantity=100,
        evidence_ttl_seconds=300,
        approval_required=True,
        rule_version="replenishment-v1",
        captured_at=captured_at,
    )


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_normal_inventory_completes_without_model_approval_or_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for("SKU-NORMAL-001")
    operation_id = await operations_repository.create(request)
    model = CountingModelGateway()

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_replenishment_graph(
                saver,
                operations_repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                model,
                lambda: NOW,
            )
            await graph.ainvoke(
                build_replenishment_initial_state(operation_id, request),
                config=config(operation_id),
            )
            await saver.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert detail.status is OperationStatus.COMPLETED
        assert detail.result is not None
        assert detail.result.outcome == "replenishment_not_required"
        assert detail.approval is None
        assert detail.work_order is None
        assert model.calls == 0
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_low_inventory_persists_plan_and_interrupts_before_any_write(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for("SKU-LOW-001")
    operation_id = await operations_repository.create(request)
    model = CountingModelGateway()

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_replenishment_graph(
                saver,
                operations_repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                model,
                lambda: NOW,
            )
            result = await graph.ainvoke(
                build_replenishment_initial_state(operation_id, request),
                config=config(operation_id),
            )
            snapshot = await graph.aget_state(config(operation_id))

            assert "__interrupt__" in result
            assert snapshot.interrupts
            json.dumps(snapshot.values, allow_nan=False)
            interrupt_value = snapshot.interrupts[0].value
            assert set(interrupt_value) == {
                "operation_id",
                "assessment",
                "plan",
                "approval_binding",
                "approval_expires_at",
            }
            await saver.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert detail.status is OperationStatus.AWAITING_APPROVAL
        assert detail.assessment is not None
        assert detail.assessment.recommended_quantity == 18
        assert detail.plan is not None
        assert detail.approval_binding is not None
        assert detail.approval is None
        assert detail.work_order is None
        assert model.calls == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sku", "expected_code"),
    [
        ("SKU-MISSING-001", "inventory_not_found"),
        ("SKU-LIMIT-001", "replenishment_quantity_out_of_policy"),
    ],
)
async def test_real_evidence_failures_end_safely_without_interrupt(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    sku: str,
    expected_code: str,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for(sku)
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_replenishment_graph(
                saver,
                operations_repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                CountingModelGateway(),
                lambda: NOW,
            )
            result = await graph.ainvoke(
                build_replenishment_initial_state(operation_id, request),
                config=config(operation_id),
            )
            snapshot = await graph.aget_state(config(operation_id))
            assert "__interrupt__" not in result
            assert snapshot.interrupts == ()
            await saver.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert detail.status is OperationStatus.FAILED
        assert detail.error is not None
        assert detail.error.code == expected_code
        assert detail.approval is None
        assert detail.work_order is None
        assert detail.event_types.count("operation_failed") == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gateway", "expected_code"),
    [
        (
            FakeEvidenceGateway(
                {
                    **inventory().model_dump(mode="json"),
                    "on_hand_quantity": "20",
                },
                policy(),
            ),
            "invalid_inventory_evidence",
        ),
        (
            FakeEvidenceGateway(
                inventory(captured_at=NOW - timedelta(seconds=301)),
                policy(captured_at=NOW - timedelta(seconds=301)),
            ),
            "evidence_expired",
        ),
    ],
)
async def test_invalid_or_expired_fake_evidence_fails_without_interrupt(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    gateway: Any,
    expected_code: str,
) -> None:
    operations_repository = ReplenishmentOperationRepository(engine)
    request = request_for("SKU-LOW-001")
    operation_id = await operations_repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_replenishment_graph(
                saver,
                operations_repository,
                EvidenceRepository(engine),
                gateway,
                CountingModelGateway(),
                lambda: NOW,
            )
            result = await graph.ainvoke(
                build_replenishment_initial_state(operation_id, request),
                config=config(operation_id),
            )
            snapshot = await graph.aget_state(config(operation_id))
            assert "__interrupt__" not in result
            assert snapshot.interrupts == ()
            await saver.adelete_thread(str(operation_id))

        detail = await operations_repository.load_detail(operation_id)
        assert detail.status is OperationStatus.FAILED
        assert detail.error is not None
        assert detail.error.code == expected_code
        assert detail.approval is None
        assert detail.work_order is None
    finally:
        await cleanup_operation(engine, operation_id)
