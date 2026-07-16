from uuid import UUID, uuid4

import pytest
from langgraph.types import Command
from pydantic import SecretStr
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.infrastructure.db.schema import approvals, audit_events, operations, work_orders
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository
from opercerta.workflow.reliability_graph import (
    build_initial_state,
    build_reliability_graph,
)


def snapshot_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request": {"summary": "synthetic graph test"},
        "risk": {"level": "high"},
        "plan": {"step": "create_work_order"},
        "work_order_payload": {"quantity": 4},
    }


async def seed_received_operation(engine: AsyncEngine) -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=str(operation_id),
                request_payload=snapshot_data(),
                status="received",
                next_audit_sequence=0,
            )
        )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


async def business_facts(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[str, int, int, list[str]]:
    async with engine.connect() as connection:
        status = (
            await connection.execute(
                select(operations.c.status).where(operations.c.id == operation_id)
            )
        ).scalar_one()
        approval_count = (
            await connection.execute(
                select(func.count())
                .select_from(approvals)
                .where(approvals.c.operation_id == operation_id)
            )
        ).scalar_one()
        work_order_count = (
            await connection.execute(
                select(func.count())
                .select_from(work_orders)
                .where(work_orders.c.operation_id == operation_id)
            )
        ).scalar_one()
        event_types = list(
            (
                await connection.execute(
                    select(audit_events.c.event_type)
                    .where(audit_events.c.operation_id == operation_id)
                    .order_by(audit_events.c.sequence)
                )
            ).scalars()
        )
    return status, approval_count, work_order_count, event_types


def approval_command(operation_id: UUID, decision: ApprovalDecision) -> ApprovalCommand:
    return ApprovalCommand(
        operation_id=operation_id,
        approver_id="synthetic-approver",
        decision=decision,
        reason="synthetic graph decision",
    )


@pytest.mark.asyncio
async def test_graph_interrupts_before_approval_or_work_order_write(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    config = {"configurable": {"thread_id": thread_id}}
    states = OperationStateRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_reliability_graph(
                saver,
                states,
                WorkOrderRepository(engine),
            )
            view = await states.load_recovery_view(operation_id)

            result = await graph.ainvoke(build_initial_state(view), config=config)

            assert "__interrupt__" in result
            status, approval_count, work_order_count, event_types = await business_facts(
                engine,
                operation_id,
            )
            assert status == "awaiting_approval"
            assert approval_count == 0
            assert work_order_count == 0
            assert event_types == ["approval_requested"]
            await saver.adelete_thread(thread_id)
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_work_orders", "terminal_event"),
    [
        (ApprovalDecision.APPROVED, "completed", 1, "operation_completed"),
        (ApprovalDecision.REJECTED, "rejected", 0, "operation_rejected"),
    ],
)
async def test_no_crash_decision_uses_saved_approval(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    decision: ApprovalDecision,
    expected_status: str,
    expected_work_orders: int,
    terminal_event: str,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    config = {"configurable": {"thread_id": thread_id}}
    states = OperationStateRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_reliability_graph(
                saver,
                states,
                WorkOrderRepository(engine),
            )
            await graph.ainvoke(
                build_initial_state(await states.load_recovery_view(operation_id)),
                config=config,
            )
            approval = await ApprovalRepository(engine).submit_once(
                approval_command(operation_id, decision)
            )

            result = await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )

            status, approval_count, work_order_count, event_types = await business_facts(
                engine,
                operation_id,
            )
            assert status == expected_status
            assert approval_count == 1
            assert work_order_count == expected_work_orders
            assert event_types.count(terminal_event) == 1
            if decision is ApprovalDecision.APPROVED:
                assert result["replayed"] is False
                assert result["work_order"] is not None
            else:
                assert result["work_order"] is None
            await saver.adelete_thread(thread_id)
    finally:
        await cleanup_operation(engine, operation_id)
