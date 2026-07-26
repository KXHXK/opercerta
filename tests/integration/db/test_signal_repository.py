import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    SignalAlreadyClaimed,
    SignalObjectMismatch,
    SignalRetryNotAllowed,
)
from opercerta.domain.replenishment import OperationError
from opercerta.domain.signals import SignalDraft
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operational_signals, operations
from opercerta.infrastructure.db.signal_repository import SignalRepository

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)


def inventory_signal() -> SignalDraft:
    return SignalDraft(
        signal_type="inventory_shortage",
        object_type="inventory",
        object_id="SKU-LOW-001",
        source="demo_watchlist.v1",
        severity="medium",
        reason_code="inventory_below_reorder_point",
        facts_hash="a" * 64,
        facts={
            "available_quantity": 12,
            "reorder_point": 15,
            "target_stock": 30,
            "recommended_quantity": 18,
        },
        detected_at=NOW,
    )


@pytest.mark.asyncio
async def test_concurrent_detection_returns_one_durable_signal(engine: AsyncEngine) -> None:
    repository = SignalRepository(engine)
    results = await asyncio.gather(
        *[repository.upsert_detected(inventory_signal()) for _ in range(10)]
    )
    signal_id = results[0].id
    try:
        assert {result.id for result in results} == {signal_id}
        assert all(result.status.value == "open" for result in results)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(operational_signals)
                    .where(operational_signals.c.id == signal_id)
                )
                == 1
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal_id)
            )


@pytest.mark.asyncio
async def test_signal_and_operation_are_bound_once_under_concurrency(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operations_repository = OperationRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    request = OperationRequest(
        message="分析已检测到的库存短缺并在需要时提出补货工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
        trigger_signal_id=signal.id,
    )
    results = await asyncio.gather(
        *[operations_repository.create(request) for _ in range(10)],
        return_exceptions=True,
    )
    winners = [result for result in results if isinstance(result, UUID)]
    conflicts = [result for result in results if isinstance(result, SignalAlreadyClaimed)]
    try:
        assert len(winners) == 1
        assert len(conflicts) == 9
        linked = await signals.load(signal.id)
        assert linked.operation_id == winners[0]
        assert linked.status.value == "investigating"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(operations)
                    .where(operations.c.id == winners[0])
                )
                == 1
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )
            if winners:
                await connection.execute(delete(operations).where(operations.c.id == winners[0]))


@pytest.mark.asyncio
async def test_operation_cannot_change_the_detected_business_object(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    try:
        with pytest.raises(SignalObjectMismatch):
            await OperationRepository(engine).create(
                OperationRequest(
                    message="尝试改变 signal 绑定对象",
                    requested_action=ActionType.CREATE_WORK_ORDER,
                    object_type=ObjectType.INVENTORY,
                    object_id="SKU-NORMAL-001",
                    trigger_signal_id=signal.id,
                )
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )


@pytest.mark.asyncio
async def test_failed_operation_returns_signal_to_human_attention(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    operation_id = await operation_repository.create(
        OperationRequest(
            message="调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=signal.id,
        )
    )
    try:
        await operation_repository.mark_failed(
            operation_id,
            OperationError(code="dependency_unavailable", message="Dependency unavailable."),
        )
        linked = await signals.load(signal.id)
        assert linked.status.value == "attention_required"
        assert linked.operation_id == operation_id
        assert linked.resolved_at is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )


@pytest.mark.asyncio
async def test_reconcile_repairs_legacy_terminal_signal_and_is_idempotent(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    operation_id = await operation_repository.create(
        OperationRequest(
            message="调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=signal.id,
        )
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(status="expired", updated_at=NOW + timedelta(minutes=1))
            )

        assert (await signals.load(signal.id)).status.value == "investigating"
        assert await signals.reconcile_terminal_links(NOW + timedelta(minutes=2)) == 1
        repaired = await signals.load(signal.id)
        assert repaired.status.value == "attention_required"
        assert repaired.operation_id == operation_id
        assert repaired.resolved_at is None
        assert await signals.reconcile_terminal_links(NOW + timedelta(minutes=3)) == 0
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )


@pytest.mark.asyncio
async def test_concurrent_retry_creates_one_successor_signal(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    operation_id = await operation_repository.create(
        OperationRequest(
            message="调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=signal.id,
        )
    )
    await operation_repository.mark_failed(
        operation_id,
        OperationError(code="dependency_unavailable", message="Dependency unavailable."),
    )
    successors = []
    try:
        successors = await asyncio.gather(
            *[signals.create_successor(signal.id, NOW + timedelta(minutes=1)) for _ in range(10)]
        )
        assert len({item.id for item in successors}) == 1
        assert all(item.predecessor_signal_id == signal.id for item in successors)
        assert all(item.status.value == "open" for item in successors)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(operational_signals)
                    .where(operational_signals.c.predecessor_signal_id == signal.id)
                )
                == 1
            )
    finally:
        async with engine.begin() as connection:
            if successors:
                await connection.execute(
                    delete(operational_signals).where(operational_signals.c.id == successors[0].id)
                )
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )


@pytest.mark.asyncio
async def test_open_signal_cannot_be_retried(engine: AsyncEngine) -> None:
    signals = SignalRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    try:
        with pytest.raises(SignalRetryNotAllowed):
            await signals.create_successor(signal.id, NOW + timedelta(minutes=1))
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )
