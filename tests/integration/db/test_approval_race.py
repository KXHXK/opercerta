import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import UniqueConstraint, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision, ApprovalRecord
from opercerta.domain.errors import ApprovalAlreadyDecided, OperationNotFound
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    evidence,
    metadata,
    operations,
    work_orders,
)


def test_schema_mapping_matches_reliability_migration() -> None:
    assert set(metadata.tables) == {
        "operations",
        "approvals",
        "work_orders",
        "audit_events",
        "evidence",
    }
    assert {
        constraint.name
        for constraint in work_orders.constraints
        if isinstance(constraint, UniqueConstraint)
    } == {"uq_work_orders_operation_id", "uq_work_orders_idempotency_key"}
    assert {
        constraint.name
        for constraint in evidence.constraints
        if isinstance(constraint, UniqueConstraint)
    } == {"uq_evidence_operation_evidence_id"}


async def seed_operation(engine: AsyncEngine, status: str = "awaiting_approval") -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=f"thread-{operation_id}",
                request_payload={"message": "synthetic approval race"},
                status=status,
                approval_cycle=1,
            )
        )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


def approval_command(operation_id: UUID, index: int) -> ApprovalCommand:
    return ApprovalCommand(
        operation_id=operation_id,
        approver_id=f"approver-{index}",
        decision=(ApprovalDecision.APPROVED if index % 2 == 0 else ApprovalDecision.REJECTED),
        reason=f"synthetic decision {index}",
    )


@pytest.mark.asyncio
async def test_ten_concurrent_decisions_commit_exactly_one(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine)
    repository = ApprovalRepository(engine)

    try:
        results = await asyncio.gather(
            *[repository.submit_once(approval_command(operation_id, index)) for index in range(10)],
            return_exceptions=True,
        )

        accepted = [result for result in results if isinstance(result, ApprovalRecord)]
        conflicts = [result for result in results if isinstance(result, ApprovalAlreadyDecided)]
        assert len(accepted) == 1
        assert len(conflicts) == 9
        assert len(accepted) + len(conflicts) == len(results)

        async with engine.connect() as connection:
            approval_rows = (
                (
                    await connection.execute(
                        select(approvals).where(approvals.c.operation_id == operation_id)
                    )
                )
                .mappings()
                .all()
            )
            operation = (
                (
                    await connection.execute(
                        select(operations).where(operations.c.id == operation_id)
                    )
                )
                .mappings()
                .one()
            )
            audit_rows = (
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

        winner = accepted[0]
        assert len(approval_rows) == 1
        assert approval_rows[0]["id"] == winner.id
        assert approval_rows[0]["decision"] == winner.decision.value
        assert operation["status"] == "resuming"
        assert operation["next_audit_sequence"] == 1
        assert [row["event_type"] for row in audit_rows] == ["approval_recorded"]
        assert audit_rows[0]["payload"] == {
            "approval_id": str(winner.id),
            "approval_cycle": 1,
            "decision": winner.decision.value,
        }
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_missing_operation_is_rejected_without_writes(engine: AsyncEngine) -> None:
    operation_id = uuid4()

    with pytest.raises(OperationNotFound, match="operation_not_found"):
        await ApprovalRepository(engine).submit_once(approval_command(operation_id, 0))

    async with engine.connect() as connection:
        approval_rows = (
            await connection.execute(
                select(approvals).where(approvals.c.operation_id == operation_id)
            )
        ).all()
        audit_rows = (
            await connection.execute(
                select(audit_events).where(audit_events.c.operation_id == operation_id)
            )
        ).all()

    assert approval_rows == []
    assert audit_rows == []


@pytest.mark.asyncio
async def test_non_waiting_operation_is_rejected_without_writes(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="resuming")

    try:
        with pytest.raises(ApprovalAlreadyDecided, match="approval_already_decided"):
            await ApprovalRepository(engine).submit_once(approval_command(operation_id, 0))

        async with engine.connect() as connection:
            approval_rows = (
                await connection.execute(
                    select(approvals).where(approvals.c.operation_id == operation_id)
                )
            ).all()
            audit_rows = (
                await connection.execute(
                    select(audit_events).where(audit_events.c.operation_id == operation_id)
                )
            ).all()

        assert approval_rows == []
        assert audit_rows == []
    finally:
        await cleanup_operation(engine, operation_id)
