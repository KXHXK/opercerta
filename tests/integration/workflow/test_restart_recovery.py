from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision
from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.recovery import RecoveryAction
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.infrastructure.db.schema import approvals, audit_events, operations, work_orders
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository
from opercerta.workflow.recovery_coordinator import RecoveryCoordinator
from opercerta.workflow.reliability_graph import (
    ReliabilityGraph,
    build_initial_state,
    build_reliability_graph,
)


@dataclass(frozen=True, slots=True)
class BusinessFacts:
    status: str
    approval_ids: list[UUID]
    work_order_ids: list[UUID]
    event_types: list[str]


def snapshot_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request": {"summary": "synthetic restart test"},
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


async def load_business_facts(engine: AsyncEngine, operation_id: UUID) -> BusinessFacts:
    async with engine.connect() as connection:
        status = (
            await connection.execute(
                select(operations.c.status).where(operations.c.id == operation_id)
            )
        ).scalar_one()
        approval_ids = list(
            (
                await connection.execute(
                    select(approvals.c.id).where(approvals.c.operation_id == operation_id)
                )
            ).scalars()
        )
        work_order_ids = list(
            (
                await connection.execute(
                    select(work_orders.c.id).where(work_orders.c.operation_id == operation_id)
                )
            ).scalars()
        )
        event_types = list(
            (
                await connection.execute(
                    select(audit_events.c.event_type)
                    .where(audit_events.c.operation_id == operation_id)
                    .order_by(audit_events.c.sequence)
                )
            ).scalars()
        )
    return BusinessFacts(
        status=status,
        approval_ids=approval_ids,
        work_order_ids=work_order_ids,
        event_types=event_types,
    )


def approval_command(
    operation_id: UUID,
    decision: ApprovalDecision,
) -> ApprovalCommand:
    return ApprovalCommand(
        operation_id=operation_id,
        approver_id="synthetic-restart-approver",
        decision=decision,
        reason="synthetic restart decision",
    )


async def interrupt_graph(
    graph: ReliabilityGraph,
    states: OperationStateRepository,
    operation_id: UUID,
) -> None:
    result = await graph.ainvoke(
        build_initial_state(await states.load_recovery_view(operation_id)),
        config={"configurable": {"thread_id": str(operation_id)}},
    )
    assert "__interrupt__" in result


@pytest.mark.asyncio
async def test_rebuilds_business_row_before_first_checkpoint(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
        del graph_a

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            action = await RecoveryCoordinator(graph_b, states).recover(operation_id)
            snapshot = await graph_b.aget_state({"configurable": {"thread_id": thread_id}})
            assert snapshot.interrupts
            await saver_b.adelete_thread(thread_id)

        facts = await load_business_facts(engine, operation_id)
        assert action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS
        assert facts.status == "awaiting_approval"
        assert facts.approval_ids == []
        assert facts.work_order_ids == []
        assert facts.event_types == ["approval_requested"]
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_restart_at_interrupt_keeps_waiting_without_writes(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            await interrupt_graph(graph_a, states, operation_id)
        del graph_a

        before = await load_business_facts(engine, operation_id)
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            action = await RecoveryCoordinator(graph_b, states).recover(operation_id)
            snapshot = await graph_b.aget_state({"configurable": {"thread_id": thread_id}})
            assert snapshot.interrupts
            await saver_b.adelete_thread(thread_id)
        after = await load_business_facts(engine, operation_id)

        assert action is RecoveryAction.KEEP_WAITING
        assert after == before
        assert after.status == "awaiting_approval"
        assert after.approval_ids == []
        assert after.work_order_ids == []
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
async def test_restart_after_approval_uses_saved_decision(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    decision: ApprovalDecision,
    expected_status: str,
    expected_work_orders: int,
    terminal_event: str,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            await interrupt_graph(graph_a, states, operation_id)
        del graph_a

        approval = await ApprovalRepository(engine).submit_once(
            approval_command(operation_id, decision)
        )
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            action = await RecoveryCoordinator(graph_b, states).recover(operation_id)
            snapshot = await graph_b.aget_state({"configurable": {"thread_id": thread_id}})
            assert snapshot.next == ()
            assert snapshot.interrupts == ()
            await saver_b.adelete_thread(thread_id)

        facts = await load_business_facts(engine, operation_id)
        assert action is RecoveryAction.RESUME_DECISION
        assert facts.status == expected_status
        assert facts.approval_ids == [approval.id]
        assert len(facts.work_order_ids) == expected_work_orders
        assert facts.event_types.count("approval_recorded") == 1
        assert facts.event_types.count(terminal_event) == 1
        if decision is ApprovalDecision.APPROVED:
            assert facts.event_types.count("work_order_created") == 1
        else:
            assert "work_order_created" not in facts.event_types
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_restart_after_work_order_commit_replays_original_result(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            await interrupt_graph(graph_a, states, operation_id)
        del graph_a

        await ApprovalRepository(engine).submit_once(
            approval_command(operation_id, ApprovalDecision.APPROVED)
        )
        original = await work_order_repository.create_or_get(
            WorkOrderCommand(operation_id=operation_id, payload={"quantity": 4})
        )
        assert original.replayed is False

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            action = await RecoveryCoordinator(graph_b, states).recover(operation_id)
            snapshot = await graph_b.aget_state({"configurable": {"thread_id": thread_id}})
            assert snapshot.values["replayed"] is True
            assert snapshot.values["work_order"] == {
                "work_order_id": str(original.work_order.id),
                "payload_hash": original.work_order.payload_hash,
            }
            await saver_b.adelete_thread(thread_id)

        facts = await load_business_facts(engine, operation_id)
        assert action is RecoveryAction.RESUME_DECISION
        assert facts.status == "completed"
        assert facts.work_order_ids == [original.work_order.id]
        assert facts.event_types.count("work_order_created") == 1
        assert facts.event_types.count("operation_completed") == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_checkpoint_operation_id_mismatch_is_rejected_without_business_writes(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    target_id = await seed_received_operation(engine)
    other_id = await seed_received_operation(engine)
    target_thread = str(target_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            other_state = build_initial_state(await states.load_recovery_view(other_id))
            result = await graph_a.ainvoke(
                other_state,
                config={"configurable": {"thread_id": target_thread}},
            )
            assert "__interrupt__" in result
        del graph_a

        before = await load_business_facts(engine, target_id)
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
                await RecoveryCoordinator(graph_b, states).recover(target_id)
            await saver_b.adelete_thread(target_thread)
        after = await load_business_facts(engine, target_id)

        assert after == before
        assert after.status == "received"
    finally:
        await cleanup_operation(engine, target_id)
        await cleanup_operation(engine, other_id)


@pytest.mark.asyncio
async def test_terminal_business_state_with_pending_checkpoint_is_rejected(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            await interrupt_graph(graph_a, states, operation_id)
        del graph_a
        async with engine.begin() as connection:
            await connection.execute(
                update(operations).where(operations.c.id == operation_id).values(status="completed")
            )

        before = await load_business_facts(engine, operation_id)
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_reliability_graph(saver_b, states, work_order_repository)
            with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
                await RecoveryCoordinator(graph_b, states).recover(operation_id)
            await saver_b.adelete_thread(thread_id)
        after = await load_business_facts(engine, operation_id)

        assert after == before
        assert after.status == "completed"
        assert after.work_order_ids == []
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_closed_checkpointer_preserves_committed_approval(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    thread_id = str(operation_id)
    states = OperationStateRepository(engine)
    work_order_repository = WorkOrderRepository(engine)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_reliability_graph(saver_a, states, work_order_repository)
            await interrupt_graph(graph_a, states, operation_id)
        del graph_a
        approval = await ApprovalRepository(engine).submit_once(
            approval_command(operation_id, ApprovalDecision.APPROVED)
        )

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            closed_graph = build_reliability_graph(saver_b, states, work_order_repository)

        with pytest.raises(psycopg.OperationalError):
            await RecoveryCoordinator(closed_graph, states).recover(operation_id)

        facts = await load_business_facts(engine, operation_id)
        assert facts.status == "resuming"
        assert facts.approval_ids == [approval.id]
        assert facts.work_order_ids == []
        assert facts.event_types.count("approval_recorded") == 1

        async with open_checkpointer(checkpoint_database_url) as cleanup_saver:
            await cleanup_saver.adelete_thread(thread_id)
    finally:
        await cleanup_operation(engine, operation_id)
