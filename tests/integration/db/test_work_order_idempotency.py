import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import (
    IdempotencyConflict,
    OperationNotFound,
    WriteNotAuthorized,
)
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    operations,
    work_orders,
)
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository


async def seed_operation(
    engine: AsyncEngine,
    *,
    status: str,
    decision: str | None,
) -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=f"thread-{operation_id}",
                request_payload={"message": "synthetic work-order test"},
                status=status,
                next_audit_sequence=0,
            )
        )
        if decision is not None:
            await connection.execute(
                insert(approvals).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    approver_id="synthetic-approver",
                    decision=decision,
                    reason="synthetic work-order authorization",
                )
            )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


def command_for(operation_id: UUID, quantity: int = 4) -> WorkOrderCommand:
    return WorkOrderCommand(
        operation_id=operation_id,
        payload={"quantity": quantity, "sku": "SKU-DEMO-001"},
    )


async def work_order_facts(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[list[RowMapping], list[RowMapping], int]:
    async with engine.connect() as connection:
        order_rows = list(
            (
                await connection.execute(
                    select(work_orders).where(work_orders.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
        event_rows = list(
            (
                await connection.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.operation_id == operation_id,
                        audit_events.c.event_type == "work_order_created",
                    )
                    .order_by(audit_events.c.sequence)
                )
            )
            .mappings()
            .all()
        )
        next_sequence = (
            await connection.execute(
                select(operations.c.next_audit_sequence).where(operations.c.id == operation_id)
            )
        ).scalar_one()
    return order_rows, event_rows, next_sequence


async def work_order_facts_for_missing(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[list[RowMapping], list[RowMapping]]:
    async with engine.connect() as connection:
        order_rows = list(
            (
                await connection.execute(
                    select(work_orders).where(work_orders.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
        event_rows = list(
            (
                await connection.execute(
                    select(audit_events).where(audit_events.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
    return order_rows, event_rows


@pytest.mark.asyncio
async def test_missing_operation_is_rejected_without_writes(engine: AsyncEngine) -> None:
    operation_id = uuid4()

    with pytest.raises(OperationNotFound, match="operation_not_found"):
        await WorkOrderRepository(engine).create_or_get(command_for(operation_id))

    order_rows, event_rows = await work_order_facts_for_missing(engine, operation_id)
    assert order_rows == []
    assert event_rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "decision"),
    [
        ("resuming", None),
        ("resuming", "rejected"),
        ("planning", "approved"),
    ],
)
async def test_first_write_requires_approved_authorized_operation(
    engine: AsyncEngine,
    status: str,
    decision: str | None,
) -> None:
    operation_id = await seed_operation(engine, status=status, decision=decision)

    try:
        with pytest.raises(WriteNotAuthorized, match="write_not_authorized"):
            await WorkOrderRepository(engine).create_or_get(command_for(operation_id))

        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )
        assert order_rows == []
        assert event_rows == []
        assert next_sequence == 0
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["resuming", "executing", "verifying"])
async def test_first_write_accepts_each_authorized_status(
    engine: AsyncEngine,
    status: str,
) -> None:
    operation_id = await seed_operation(engine, status=status, decision="approved")

    try:
        result = await WorkOrderRepository(engine).create_or_get(command_for(operation_id))
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert result.replayed is False
        assert result.work_order.status == "created"
        assert result.work_order.created_at == result.work_order.updated_at
        assert result.work_order.created_at.utcoffset() is not None
        assert len(order_rows) == 1
        assert order_rows[0]["id"] == result.work_order.id
        assert len(event_rows) == 1
        assert event_rows[0]["payload"] == {
            "work_order_id": str(result.work_order.id),
            "idempotency_key": result.work_order.idempotency_key,
            "payload_hash": result.work_order.payload_hash,
        }
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_returned_nested_payload_is_independent_of_database_state(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id,
                payload={"items": [{"quantity": 4}]},
            )
        )
        returned_items = first.work_order.payload["items"]
        assert isinstance(returned_items, list)
        returned_item = returned_items[0]
        assert isinstance(returned_item, dict)
        returned_item["quantity"] = 99

        replay = await repository.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id,
                payload={"items": [{"quantity": 4}]},
            )
        )

        assert replay.replayed is True
        assert replay.work_order.id == first.work_order.id
        assert replay.work_order.payload == {"items": [{"quantity": 4}]}
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_identical_replay_returns_same_id_without_second_audit(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id))
        second = await repository.create_or_get(command_for(operation_id))
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert first.replayed is False
        assert second.replayed is True
        assert second.work_order.id == first.work_order.id
        assert len(order_rows) == 1
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_replay_still_works_after_operation_status_advances(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id))
        async with engine.begin() as connection:
            await connection.execute(
                update(operations).where(operations.c.id == operation_id).values(status="completed")
            )

        replay = await repository.create_or_get(command_for(operation_id))

        assert replay.replayed is True
        assert replay.work_order.id == first.work_order.id
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_changed_payload_raises_classified_conflict_without_mutation(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id, quantity=4))

        with pytest.raises(IdempotencyConflict, match="idempotency_conflict"):
            await repository.create_or_get(command_for(operation_id, quantity=5))

        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )
        assert len(order_rows) == 1
        assert order_rows[0]["id"] == first.work_order.id
        assert order_rows[0]["payload"] == {"quantity": 4, "sku": "SKU-DEMO-001"}
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_ten_concurrent_identical_commands_create_effectively_once(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        results = await asyncio.gather(
            *[repository.create_or_get(command_for(operation_id)) for _ in range(10)]
        )
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert sum(not result.replayed for result in results) == 1
        assert sum(result.replayed for result in results) == 9
        assert len({result.work_order.id for result in results}) == 1
        assert len(order_rows) == 1
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)
