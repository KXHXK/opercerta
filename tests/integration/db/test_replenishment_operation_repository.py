import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.replenishment import (
    ApprovalBinding,
    EvidenceBundle,
    InventoryEvidence,
    OperationError,
    OperationResult,
    PolicyEvidence,
    ReplenishmentAssessment,
    ReplenishmentPlan,
)
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.db.schema import approvals, audit_events, operations
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository

NOW = datetime(2026, 7, 16, 4, 0, tzinfo=UTC)


def operation_request() -> OperationRequest:
    return OperationRequest(
        message="Check SKU-DEMO-001 and replenish if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-DEMO-001",
    )


def bundle(*, on_hand_quantity: int = 3) -> EvidenceBundle:
    return EvidenceBundle(
        inventory=InventoryEvidence(
            evidence_id=UUID("10000000-0000-0000-0000-000000000001"),
            sku="SKU-DEMO-001",
            on_hand_quantity=on_hand_quantity,
            reserved_quantity=1,
            captured_at=NOW,
            source_version="inventory-v1",
        ),
        policy=PolicyEvidence(
            evidence_id=UUID("20000000-0000-0000-0000-000000000002"),
            action="replenish_inventory",
            sku="SKU-DEMO-001",
            reorder_point=5,
            target_stock=12,
            minimum_order_quantity=1,
            maximum_order_quantity=20,
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="policy-v3",
            captured_at=NOW,
        ),
    )


def assessment(*, replenishment_required: bool = True) -> ReplenishmentAssessment:
    return ReplenishmentAssessment(
        sku="SKU-DEMO-001",
        available_quantity=2,
        reorder_point=5,
        target_stock=12,
        replenishment_required=replenishment_required,
        recommended_quantity=10 if replenishment_required else None,
        decision_facts_hash="a" * 64,
    )


def plan(
    *,
    summary: str = "Inventory is below its reorder point.",
) -> ReplenishmentPlan:
    return ReplenishmentPlan(
        action="replenish_inventory",
        sku="SKU-DEMO-001",
        recommended_quantity=10,
        decision_facts_hash="a" * 64,
        rule_version="policy-v3",
        summary=summary,
        rationale="Replenishing ten units restores the approved target stock.",
        plan_hash="b" * 64,
    )


def binding() -> ApprovalBinding:
    return ApprovalBinding(
        inventory_evidence_id=bundle().inventory.evidence_id,
        policy_evidence_id=bundle().policy.evidence_id,
        rule_version=plan().rule_version,
        decision_facts_hash=plan().decision_facts_hash,
        plan_hash=plan().plan_hash,
        recommended_quantity=plan().recommended_quantity,
    )


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


async def operation_facts(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[str, int, dict[str, object], list[tuple[int, str, dict[str, object]]]]:
    async with engine.connect() as connection:
        operation = (
            (await connection.execute(select(operations).where(operations.c.id == operation_id)))
            .mappings()
            .one()
        )
        events = (
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
    return (
        str(operation["status"]),
        int(operation["next_audit_sequence"]),
        dict(operation["request_payload"]),
        [
            (int(event["sequence"]), str(event["event_type"]), dict(event["payload"]))
            for event in events
        ],
    )


async def advance_to_awaiting_approval(
    repository: ReplenishmentOperationRepository,
    operation_id: UUID,
    *,
    approval_expires_at: datetime,
) -> None:
    await repository.mark_gathering_evidence(operation_id)
    await repository.record_evidence(operation_id, bundle())
    await repository.record_validated_plan(operation_id, assessment(), plan())
    await repository.mark_awaiting_approval(
        operation_id,
        binding(),
        approval_expires_at,
    )


@pytest.mark.asyncio
async def test_create_and_approval_lifecycle_persist_snapshot_and_ordered_audit(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    expires_at = NOW + timedelta(minutes=5)

    try:
        created = await repository.load_detail(operation_id)
        assert created.status is OperationStatus.RECEIVED
        assert created.thread_id == str(operation_id)
        assert created.snapshot.schema_version == 1
        assert created.audit_events[0].event_type == "operation_received"

        await advance_to_awaiting_approval(
            repository,
            operation_id,
            approval_expires_at=expires_at,
        )
        view = await repository.load_detail(operation_id)

        assert view.status is OperationStatus.AWAITING_APPROVAL
        assert view.snapshot.plan["plan_hash"] == plan().plan_hash
        assert view.snapshot.work_order_payload == {
            "sku": "SKU-DEMO-001",
            "quantity": 10,
            "approved_plan_hash": "b" * 64,
        }
        assert view.approval_expires_at == expires_at
        assert view.assessment == assessment()
        assert view.plan == plan()
        assert view.approval_binding == binding()
        assert [record.evidence_type for record in view.evidence] == [
            "inventory",
            "policy",
        ]
        assert view.event_types == (
            "operation_received",
            "evidence_gathering_started",
            "evidence_recorded",
            "plan_validated",
            "approval_requested",
        )
        assert view.last_audit_sequence == 5
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_reporting_completion_stores_no_replenishment_result(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    result = OperationResult(
        outcome="replenishment_not_required",
        message="Available inventory is above the reorder point.",
    )

    try:
        await repository.mark_gathering_evidence(operation_id)
        await repository.record_evidence(operation_id, bundle())
        await repository.record_validated_plan(
            operation_id,
            assessment=assessment(replenishment_required=False),
            plan=None,
        )
        await repository.mark_reporting(operation_id)
        await repository.complete_without_replenishment(operation_id, result)

        view = await repository.load_detail(operation_id)
        assert view.status is OperationStatus.COMPLETED
        assert view.result == result
        assert view.error is None
        assert view.plan is None
        assert view.snapshot.work_order_payload == {}
        assert view.event_types[-2:] == ("reporting_started", "operation_completed")
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_approved_execution_and_rejected_paths_store_terminal_facts(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    completed_id = await repository.create(operation_request())
    rejected_id = await repository.create(operation_request())

    try:
        await advance_to_awaiting_approval(
            repository,
            completed_id,
            approval_expires_at=NOW + timedelta(minutes=5),
        )
        approved = await ApprovalRepository(engine).submit_once(
            ApprovalCommand(
                operation_id=completed_id,
                approver_id="operator-1",
                decision=ApprovalDecision.APPROVED,
                reason="Approved replenishment",
            )
        )
        await repository.mark_executing(completed_id, approved.id)
        work_order = await WorkOrderRepository(engine).create_or_get(
            WorkOrderCommand(
                operation_id=completed_id,
                payload={
                    "sku": "SKU-DEMO-001",
                    "quantity": 10,
                    "approved_plan_hash": "b" * 64,
                },
            )
        )
        await repository.mark_verifying(completed_id, work_order.work_order.id)
        completed_result = OperationResult(
            outcome="work_order_completed",
            message="The replenishment work order completed.",
            work_order_id=work_order.work_order.id,
        )
        await repository.mark_completed(
            completed_id,
            completed_result,
            work_order.work_order.id,
        )

        completed = await repository.load_detail(completed_id)
        assert completed.status is OperationStatus.COMPLETED
        assert completed.result == completed_result
        assert completed.approval is not None
        assert completed.approval.decision is ApprovalDecision.APPROVED
        assert completed.approval.binding is None
        assert completed.approval_binding == binding()
        assert completed.work_order is not None
        assert completed.work_order.payload == {
            "sku": "SKU-DEMO-001",
            "quantity": 10,
            "approved_plan_hash": "b" * 64,
        }

        await advance_to_awaiting_approval(
            repository,
            rejected_id,
            approval_expires_at=NOW + timedelta(minutes=5),
        )
        rejected = await ApprovalRepository(engine).submit_once(
            ApprovalCommand(
                operation_id=rejected_id,
                approver_id="operator-2",
                decision=ApprovalDecision.REJECTED,
                reason="Insufficient justification",
            )
        )
        await repository.mark_rejected(rejected_id, rejected.id)
        rejected_view = await repository.load_detail(rejected_id)
        assert rejected_view.status is OperationStatus.REJECTED
        assert rejected_view.event_types[-1] == "operation_rejected"
    finally:
        await cleanup_operation(engine, completed_id)
        await cleanup_operation(engine, rejected_id)


@pytest.mark.asyncio
async def test_mark_failed_stores_stable_error_without_traceback(engine: AsyncEngine) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    error = OperationError(code="dependency_unavailable", message="Inventory service unavailable.")

    try:
        await repository.mark_failed(operation_id, error)
        view = await repository.load_detail(operation_id)

        assert view.status is OperationStatus.FAILED
        assert view.error == error
        assert view.result is None
        assert "traceback" not in view.audit_events[-1].payload
        assert view.audit_events[-1].payload == error.model_dump(mode="json")
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_load_detail_validates_complete_and_partial_approval_bindings(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    complete_id = await repository.create(operation_request())
    partial_id = await repository.create(operation_request())
    mismatched_id = await repository.create(operation_request())

    try:
        for operation_id in (complete_id, partial_id, mismatched_id):
            await advance_to_awaiting_approval(
                repository,
                operation_id,
                approval_expires_at=NOW + timedelta(minutes=5),
            )
            await ApprovalRepository(engine).submit_once(
                ApprovalCommand(
                    operation_id=operation_id,
                    approver_id="operator-1",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approved replenishment",
                )
            )

        async with engine.begin() as connection:
            await connection.execute(
                update(approvals)
                .where(approvals.c.operation_id == complete_id)
                .values(**binding().model_dump(mode="python"))
            )
            await connection.execute(
                update(approvals)
                .where(approvals.c.operation_id == partial_id)
                .values(inventory_evidence_id=binding().inventory_evidence_id)
            )
            await connection.execute(
                update(approvals)
                .where(approvals.c.operation_id == mismatched_id)
                .values(
                    **binding().model_copy(update={"plan_hash": "c" * 64}).model_dump(mode="python")
                )
            )

        complete = await repository.load_detail(complete_id)
        assert complete.approval is not None
        assert complete.approval.binding == binding()
        assert complete.approval_binding == complete.approval.binding

        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.load_detail(partial_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.load_detail(mismatched_id)
    finally:
        await cleanup_operation(engine, complete_id)
        await cleanup_operation(engine, partial_id)
        await cleanup_operation(engine, mismatched_id)


@pytest.mark.asyncio
async def test_same_target_replay_requires_matching_event_payload(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    matching_id = await repository.create(operation_request())
    mismatched_id = await repository.create(operation_request())

    try:
        await repository.mark_gathering_evidence(matching_id)
        before = await operation_facts(engine, matching_id)
        await repository.mark_gathering_evidence(matching_id)
        assert await operation_facts(engine, matching_id) == before
        await repository.record_evidence(matching_id, bundle())
        await repository.record_evidence(matching_id, bundle())
        before_changed_evidence = await operation_facts(engine, matching_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.record_evidence(
                matching_id,
                bundle(on_hand_quantity=4),
            )
        assert await operation_facts(engine, matching_id) == before_changed_evidence

        await repository.record_validated_plan(matching_id, assessment(), plan())
        await repository.record_validated_plan(matching_id, assessment(), plan())
        before_changed_plan = await operation_facts(engine, matching_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.record_validated_plan(
                matching_id,
                assessment(),
                plan(summary="Changed explanation for the same claimed hash."),
            )
        assert await operation_facts(engine, matching_id) == before_changed_plan

        await repository.mark_gathering_evidence(mismatched_id)
        async with engine.begin() as connection:
            await connection.execute(
                update(audit_events)
                .where(
                    audit_events.c.operation_id == mismatched_id,
                    audit_events.c.event_type == "evidence_gathering_started",
                )
                .values(payload={"unexpected": True})
            )
        before_mismatch = await operation_facts(engine, mismatched_id)
        with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
            await repository.mark_gathering_evidence(mismatched_id)
        assert await operation_facts(engine, mismatched_id) == before_mismatch
    finally:
        await cleanup_operation(engine, matching_id)
        await cleanup_operation(engine, mismatched_id)


@pytest.mark.asyncio
async def test_wrong_origin_transition_leaves_status_sequence_snapshot_and_audit_unchanged(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())

    try:
        before = await operation_facts(engine, operation_id)
        with pytest.raises(
            OperationTransitionConflict,
            match="operation_transition_conflict",
        ):
            await repository.mark_reporting(operation_id)
        assert await operation_facts(engine, operation_id) == before
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_due_approvals_expire_atomically_and_recovery_lists_exclude_terminals(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    due_id = await repository.create(operation_request())
    future_id = await repository.create(operation_request())

    try:
        await advance_to_awaiting_approval(
            repository,
            due_id,
            approval_expires_at=NOW,
        )
        await advance_to_awaiting_approval(
            repository,
            future_id,
            approval_expires_at=NOW + timedelta(minutes=5),
        )

        assert due_id in await repository.list_due_approval_ids(NOW, limit=10)
        assert future_id not in await repository.list_due_approval_ids(NOW, limit=10)
        assert due_id in await repository.list_recoverable_ids()

        assert await repository.mark_expired(due_id, NOW) is True
        assert await repository.mark_expired(due_id, NOW) is False
        view = await repository.load_detail(due_id)
        assert view.status is OperationStatus.EXPIRED
        assert view.event_types[-1] == "approval_expired"
        assert due_id not in await repository.list_recoverable_ids()
    finally:
        await cleanup_operation(engine, due_id)
        await cleanup_operation(engine, future_id)


@pytest.mark.asyncio
async def test_load_detail_holds_operation_read_lock_for_consistent_fact_set(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    load_task: asyncio.Task[object] | None = None
    transition_task: asyncio.Task[object] | None = None

    try:
        async with engine.connect() as blocker:
            async with blocker.begin():
                await blocker.execute(text("LOCK TABLE evidence IN ACCESS EXCLUSIVE MODE"))
                load_task = asyncio.create_task(repository.load_detail(operation_id))

                for _ in range(50):
                    waiting = (
                        await blocker.execute(
                            text(
                                """
                                SELECT count(*)
                                FROM pg_locks
                                WHERE relation = 'evidence'::regclass
                                  AND granted = false
                                """
                            )
                        )
                    ).scalar_one()
                    if waiting:
                        break
                    await asyncio.sleep(0.02)
                else:
                    pytest.fail("load_detail did not block on the evidence read")

                transition_task = asyncio.create_task(
                    repository.mark_gathering_evidence(operation_id)
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(
                        asyncio.shield(transition_task),
                        timeout=0.2,
                    )

        detail = await asyncio.wait_for(load_task, timeout=2)
        await asyncio.wait_for(transition_task, timeout=2)
        assert detail.status is OperationStatus.RECEIVED
        assert (await repository.load_detail(operation_id)).status is (
            OperationStatus.GATHERING_EVIDENCE
        )
    finally:
        for task in (load_task, transition_task):
            if task is not None and not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        await cleanup_operation(engine, operation_id)
