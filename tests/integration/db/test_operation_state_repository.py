from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationNotFound,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import OperationSnapshot
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.infrastructure.db.schema import audit_events, operations
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository


def snapshot_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request": {"summary": "synthetic operation state test"},
        "risk": {"level": "high"},
        "plan": {"step": "create_work_order"},
        "work_order_payload": {"quantity": 4},
    }


async def seed_operation(
    engine: AsyncEngine,
    *,
    status: str,
    snapshot: dict[str, object] | None = None,
    thread_id: str | None = None,
) -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=thread_id or str(operation_id),
                request_payload=snapshot if snapshot is not None else snapshot_data(),
                status=status,
                next_audit_sequence=0,
            )
        )
    return operation_id


async def submit_decision(
    engine: AsyncEngine,
    operation_id: UUID,
    decision: ApprovalDecision,
) -> UUID:
    record = await ApprovalRepository(engine).submit_once(
        ApprovalCommand(
            operation_id=operation_id,
            approver_id="synthetic-approver",
            decision=decision,
            reason="synthetic operation state decision",
        )
    )
    return record.id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


async def audit_facts(engine: AsyncEngine, operation_id: UUID) -> list[RowMapping]:
    async with engine.connect() as connection:
        return list(
            (
                await connection.execute(
                    select(audit_events)
                    .where(audit_events.c.operation_id == operation_id)
                    .order_by(audit_events.c.sequence)
                )
            )
            .mappings()
            .all()
        )


@pytest.mark.asyncio
async def test_load_recovery_view_validates_snapshot_and_locators(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="received")
    state_repository = OperationStateRepository(engine)

    try:
        await state_repository.mark_awaiting_approval(operation_id)
        approval_id = await submit_decision(
            engine,
            operation_id,
            ApprovalDecision.APPROVED,
        )
        result = await WorkOrderRepository(engine).create_or_get(
            WorkOrderCommand(operation_id=operation_id, payload={"quantity": 4})
        )

        view = await state_repository.load_recovery_view(operation_id)

        assert view.operation_id == operation_id
        assert view.thread_id == str(operation_id)
        assert view.status is OperationStatus.RESUMING
        assert view.snapshot == OperationSnapshot.model_validate(snapshot_data())
        assert view.approval_id == approval_id
        assert view.decision is ApprovalDecision.APPROVED
        assert view.work_order_id == result.work_order.id
        assert view.payload_hash == result.work_order.payload_hash
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_missing_operation_is_classified(engine: AsyncEngine) -> None:
    operation_id = uuid4()

    with pytest.raises(OperationNotFound, match="operation_not_found"):
        await OperationStateRepository(engine).load_recovery_view(operation_id)


@pytest.mark.asyncio
async def test_invalid_snapshot_and_thread_id_are_classified(engine: AsyncEngine) -> None:
    invalid_id = await seed_operation(
        engine,
        status="received",
        snapshot={"schema_version": 2},
    )
    mismatch_id = await seed_operation(
        engine,
        status="received",
        thread_id="wrong-thread",
    )
    repository = OperationStateRepository(engine)

    try:
        with pytest.raises(InvalidOperationSnapshot, match="invalid_operation_snapshot"):
            await repository.load_recovery_view(invalid_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.load_recovery_view(mismatch_id)
    finally:
        await cleanup_operation(engine, invalid_id)
        await cleanup_operation(engine, mismatch_id)


@pytest.mark.asyncio
async def test_full_transition_chain_is_atomic_and_ordered(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    repository = OperationStateRepository(engine)

    try:
        awaiting = await repository.mark_awaiting_approval(operation_id)
        approval_id = await submit_decision(
            engine,
            operation_id,
            ApprovalDecision.APPROVED,
        )
        executing = await repository.mark_executing(operation_id, approval_id)
        order = await WorkOrderRepository(engine).create_or_get(
            WorkOrderCommand(operation_id=operation_id, payload={"quantity": 4})
        )
        verifying = await repository.mark_verifying(operation_id, order.work_order.id)
        completed = await repository.mark_completed(operation_id, order.work_order.id)

        assert [awaiting.status, executing.status, verifying.status, completed.status] == [
            OperationStatus.AWAITING_APPROVAL,
            OperationStatus.EXECUTING,
            OperationStatus.VERIFYING,
            OperationStatus.COMPLETED,
        ]
        assert all(result.changed for result in [awaiting, executing, verifying, completed])
        rows = await audit_facts(engine, operation_id)
        assert [row["event_type"] for row in rows] == [
            "approval_requested",
            "approval_recorded",
            "execution_started",
            "work_order_created",
            "verification_started",
            "operation_completed",
        ]
        assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5, 6]
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_rejected_transition_writes_one_terminal_event(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    repository = OperationStateRepository(engine)

    try:
        await repository.mark_awaiting_approval(operation_id)
        approval_id = await submit_decision(
            engine,
            operation_id,
            ApprovalDecision.REJECTED,
        )

        result = await repository.mark_rejected(operation_id, approval_id)
        rows = await audit_facts(engine, operation_id)

        assert result.status is OperationStatus.REJECTED
        assert result.changed is True
        assert [row["event_type"] for row in rows] == [
            "approval_requested",
            "approval_recorded",
            "operation_rejected",
        ]
        assert rows[-1]["payload"] == {"approval_id": str(approval_id)}
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_same_target_is_safe_only_with_matching_event(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    repository = OperationStateRepository(engine)

    try:
        first = await repository.mark_awaiting_approval(operation_id)
        second = await repository.mark_awaiting_approval(operation_id)

        assert first.changed is True
        assert first.audit_sequence == 1
        assert second.changed is False
        assert second.audit_sequence is None
        assert len(await audit_facts(engine, operation_id)) == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_wrong_origin_and_incomplete_target_write_nothing(
    engine: AsyncEngine,
) -> None:
    wrong_id = await seed_operation(engine, status="planning")
    incomplete_id = await seed_operation(engine, status="awaiting_approval")
    repository = OperationStateRepository(engine)

    try:
        with pytest.raises(
            OperationTransitionConflict,
            match="operation_transition_conflict",
        ):
            await repository.mark_awaiting_approval(wrong_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.mark_awaiting_approval(incomplete_id)

        assert await audit_facts(engine, wrong_id) == []
        assert await audit_facts(engine, incomplete_id) == []
    finally:
        await cleanup_operation(engine, wrong_id)
        await cleanup_operation(engine, incomplete_id)
