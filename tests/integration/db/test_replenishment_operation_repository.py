import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalDecision
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import OperationSnapshot
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
    OperationDetail,
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    operations,
    work_orders,
)
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


async def seed_work_order(
    engine: AsyncEngine,
    operation_id: UUID,
    *,
    work_order_id: UUID | None = None,
) -> UUID:
    seeded_id = work_order_id or uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(work_orders).values(
                id=seeded_id,
                operation_id=operation_id,
                idempotency_key=f"work-order:v1:{operation_id}",
                payload={
                    "sku": "SKU-DEMO-001",
                    "quantity": 10,
                    "approved_plan_hash": "b" * 64,
                },
                payload_hash="c" * 64,
                status="created",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return seeded_id


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


@pytest.mark.parametrize(
    ("attribute", "snapshot", "expected_reason"),
    [
        (
            "assessment",
            OperationSnapshot(
                schema_version=1,
                request={},
                risk={"assessment": {}},
                plan={},
                work_order_payload={},
            ),
            "invalid_snapshot_assessment",
        ),
        (
            "plan",
            OperationSnapshot(
                schema_version=1,
                request={},
                risk={},
                plan={"action": "replenish_inventory"},
                work_order_payload={},
            ),
            "invalid_snapshot_plan",
        ),
        (
            "approval_binding",
            OperationSnapshot(
                schema_version=1,
                request={},
                risk={"approval_binding": {}},
                plan={},
                work_order_payload={},
            ),
            "invalid_snapshot_approval_binding",
        ),
    ],
)
def test_operation_detail_snapshot_properties_hide_validation_errors(
    attribute: str,
    snapshot: OperationSnapshot,
    expected_reason: str,
) -> None:
    operation_id = uuid4()
    detail = OperationDetail(
        operation_id=operation_id,
        thread_id=str(operation_id),
        status=OperationStatus.RECEIVED,
        snapshot=snapshot,
        result=None,
        error=None,
        approval_expires_at=None,
        evidence=(),
        approval=None,
        work_order=None,
        audit_events=(),
    )

    with pytest.raises(RecoveryStateConflict) as captured:
        getattr(detail, attribute)
    assert captured.value.operation_id == operation_id
    assert captured.value.reason == expected_reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "result_payload", "error_code", "expected_reason"),
    [
        (
            OperationStatus.COMPLETED,
            None,
            None,
            "completed_result_missing",
        ),
        (
            OperationStatus.COMPLETED,
            {
                "outcome": "replenishment_not_required",
                "message": "No replenishment is needed.",
                "work_order_id": None,
            },
            "unexpected_error",
            "completed_error_code_present",
        ),
        (
            OperationStatus.COMPLETED,
            {"outcome": "not_a_real_outcome", "message": "Invalid."},
            None,
            "invalid_completed_result",
        ),
        (
            OperationStatus.COMPLETED,
            {
                "outcome": "replenishment_not_required",
                "message": "No replenishment is needed.",
                "work_order_id": str(UUID("30000000-0000-0000-0000-000000000003")),
            },
            None,
            "completed_unexpected_work_order",
        ),
        (
            OperationStatus.FAILED,
            None,
            "dependency_unavailable",
            "failed_error_missing",
        ),
        (
            OperationStatus.FAILED,
            {
                "outcome": "replenishment_not_required",
                "message": "This is a result, not an error.",
                "work_order_id": None,
            },
            "dependency_unavailable",
            "invalid_failed_error",
        ),
        (
            OperationStatus.FAILED,
            {
                "code": "dependency_unavailable",
                "message": "Inventory is unavailable.",
            },
            "different_code",
            "failed_error_code_mismatch",
        ),
        (
            OperationStatus.REJECTED,
            {
                "outcome": "replenishment_not_required",
                "message": "No replenishment is needed.",
                "work_order_id": None,
            },
            None,
            "empty_terminal_facts_required",
        ),
        (
            OperationStatus.EXPIRED,
            None,
            "approval_expired",
            "empty_terminal_facts_required",
        ),
        (
            OperationStatus.RECEIVED,
            {
                "outcome": "replenishment_not_required",
                "message": "No replenishment is needed.",
                "work_order_id": None,
            },
            None,
            "nonterminal_facts_present",
        ),
        (
            OperationStatus.EXECUTING,
            None,
            "dependency_unavailable",
            "nonterminal_facts_present",
        ),
    ],
)
async def test_load_detail_rejects_status_inconsistent_terminal_facts(
    engine: AsyncEngine,
    status: OperationStatus,
    result_payload: dict[str, object] | None,
    error_code: str | None,
    expected_reason: str,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())

    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    status=status.value,
                    result_payload=result_payload,
                    error_code=error_code,
                )
            )

        with pytest.raises(RecoveryStateConflict) as captured:
            await repository.load_detail(operation_id)
        assert captured.value.reason == expected_reason
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [OperationStatus.REJECTED, OperationStatus.EXPIRED],
)
async def test_load_detail_rejects_empty_terminal_status_with_work_order(
    engine: AsyncEngine,
    status: OperationStatus,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())

    try:
        await seed_work_order(engine, operation_id)
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    status=status.value,
                    result_payload=None,
                    error_code=None,
                )
            )

        with pytest.raises(RecoveryStateConflict) as captured:
            await repository.load_detail(operation_id)
        assert captured.value.reason == "empty_terminal_work_order_present"
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "result_payload", "error_code"),
    [
        (
            OperationStatus.FAILED,
            {
                "code": "verification_failed",
                "message": "The work order could not be verified.",
            },
            "verification_failed",
        ),
        (OperationStatus.EXECUTING, None, None),
        (OperationStatus.VERIFYING, None, None),
    ],
)
async def test_load_detail_allows_work_order_for_failed_and_recoverable_statuses(
    engine: AsyncEngine,
    status: OperationStatus,
    result_payload: dict[str, object] | None,
    error_code: str | None,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())

    try:
        work_order_id = await seed_work_order(engine, operation_id)
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    status=status.value,
                    result_payload=result_payload,
                    error_code=error_code,
                )
            )

        detail = await repository.load_detail(operation_id)
        assert detail.status is status
        assert detail.work_order is not None
        assert detail.work_order.id == work_order_id
        if status is OperationStatus.FAILED:
            assert detail.error is not None
            assert detail.error.code == error_code
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_load_detail_rejects_completed_work_order_fact_mismatches(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    missing_id = await repository.create(operation_request())
    mismatched_id = await repository.create(operation_request())
    unexpected_id = await repository.create(operation_request())
    result_reference_id = uuid4()

    try:
        mismatched_row_id = await seed_work_order(engine, mismatched_id)
        assert mismatched_row_id != result_reference_id
        await seed_work_order(engine, unexpected_id)
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == missing_id)
                .values(
                    status=OperationStatus.COMPLETED.value,
                    result_payload={
                        "outcome": "work_order_completed",
                        "message": "Work order completed.",
                        "work_order_id": str(result_reference_id),
                    },
                    error_code=None,
                )
            )
            await connection.execute(
                update(operations)
                .where(operations.c.id == mismatched_id)
                .values(
                    status=OperationStatus.COMPLETED.value,
                    result_payload={
                        "outcome": "work_order_completed",
                        "message": "Work order completed.",
                        "work_order_id": str(result_reference_id),
                    },
                    error_code=None,
                )
            )
            await connection.execute(
                update(operations)
                .where(operations.c.id == unexpected_id)
                .values(
                    status=OperationStatus.COMPLETED.value,
                    result_payload={
                        "outcome": "replenishment_not_required",
                        "message": "No replenishment is needed.",
                        "work_order_id": None,
                    },
                    error_code=None,
                )
            )

        for operation_id, expected_reason in (
            (missing_id, "completed_work_order_missing"),
            (mismatched_id, "completed_work_order_id_mismatch"),
            (unexpected_id, "completed_unexpected_work_order"),
        ):
            with pytest.raises(RecoveryStateConflict) as captured:
                await repository.load_detail(operation_id)
            assert captured.value.reason == expected_reason
    finally:
        await cleanup_operation(engine, missing_id)
        await cleanup_operation(engine, mismatched_id)
        await cleanup_operation(engine, unexpected_id)


@pytest.mark.asyncio
async def test_load_detail_accepts_completed_result_matching_work_order_row(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())

    try:
        work_order_id = await seed_work_order(engine, operation_id)
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    status=OperationStatus.COMPLETED.value,
                    result_payload={
                        "outcome": "work_order_completed",
                        "message": "Work order completed.",
                        "work_order_id": str(work_order_id),
                    },
                    error_code=None,
                )
            )

        detail = await repository.load_detail(operation_id)
        assert detail.result is not None
        assert detail.result.work_order_id == work_order_id
        assert detail.work_order is not None
        assert detail.work_order.id == work_order_id
    finally:
        await cleanup_operation(engine, operation_id)


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
async def test_approval_locators_must_match_operation_and_decision_before_transition(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_ids: list[UUID] = []

    try:
        cases = (
            ("executing", ApprovalDecision.APPROVED, "missing", "approval_locator_missing"),
            (
                "executing",
                ApprovalDecision.APPROVED,
                "wrong_operation",
                "approval_operation_mismatch",
            ),
            (
                "executing",
                ApprovalDecision.REJECTED,
                "same",
                "approval_decision_mismatch",
            ),
            ("rejected", ApprovalDecision.REJECTED, "missing", "approval_locator_missing"),
            (
                "rejected",
                ApprovalDecision.REJECTED,
                "wrong_operation",
                "approval_operation_mismatch",
            ),
            (
                "rejected",
                ApprovalDecision.APPROVED,
                "same",
                "approval_decision_mismatch",
            ),
        )
        for target, decision, locator_kind, expected_reason in cases:
            operation_id = await repository.create(operation_request())
            operation_ids.append(operation_id)
            await advance_to_awaiting_approval(
                repository,
                operation_id,
                approval_expires_at=NOW + timedelta(minutes=5),
            )
            approval = await ApprovalRepository(engine).submit_once(
                ApprovalCommand(
                    operation_id=operation_id,
                    approver_id=f"{target}-{locator_kind}",
                    decision=decision,
                    reason="Recorded decision",
                )
            )
            locator_id = approval.id
            if locator_kind == "missing":
                locator_id = uuid4()
            elif locator_kind == "wrong_operation":
                locator_operation_id = await repository.create(operation_request())
                operation_ids.append(locator_operation_id)
                await advance_to_awaiting_approval(
                    repository,
                    locator_operation_id,
                    approval_expires_at=NOW + timedelta(minutes=5),
                )
                locator_approval = await ApprovalRepository(engine).submit_once(
                    ApprovalCommand(
                        operation_id=locator_operation_id,
                        approver_id=f"locator-{target}",
                        decision=decision,
                        reason="Recorded decision",
                    )
                )
                locator_id = locator_approval.id

            before = await operation_facts(engine, operation_id)
            with pytest.raises(RecoveryStateConflict) as captured:
                if target == "executing":
                    await repository.mark_executing(operation_id, locator_id)
                else:
                    await repository.mark_rejected(operation_id, locator_id)
            assert captured.value.reason == expected_reason
            assert await operation_facts(engine, operation_id) == before
    finally:
        for operation_id in operation_ids:
            await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_work_order_locator_must_match_operation_before_verifying(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_ids: list[UUID] = []

    try:
        for locator_kind, expected_reason in (
            ("missing", "work_order_locator_missing"),
            ("wrong_operation", "work_order_operation_mismatch"),
        ):
            operation_id = await repository.create(operation_request())
            operation_ids.append(operation_id)
            await advance_to_awaiting_approval(
                repository,
                operation_id,
                approval_expires_at=NOW + timedelta(minutes=5),
            )
            approval = await ApprovalRepository(engine).submit_once(
                ApprovalCommand(
                    operation_id=operation_id,
                    approver_id=f"operator-{locator_kind}",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approved",
                )
            )
            await repository.mark_executing(operation_id, approval.id)
            write_result = await WorkOrderRepository(engine).create_or_get(
                WorkOrderCommand(
                    operation_id=operation_id,
                    payload={
                        "sku": "SKU-DEMO-001",
                        "quantity": 10,
                        "approved_plan_hash": "b" * 64,
                    },
                )
            )
            work_order_id = write_result.work_order.id
            if locator_kind == "missing":
                work_order_id = uuid4()
            else:
                locator_operation_id = await repository.create(operation_request())
                operation_ids.append(locator_operation_id)
                await advance_to_awaiting_approval(
                    repository,
                    locator_operation_id,
                    approval_expires_at=NOW + timedelta(minutes=5),
                )
                locator_approval = await ApprovalRepository(engine).submit_once(
                    ApprovalCommand(
                        operation_id=locator_operation_id,
                        approver_id="locator-operator",
                        decision=ApprovalDecision.APPROVED,
                        reason="Approved",
                    )
                )
                await repository.mark_executing(locator_operation_id, locator_approval.id)
                locator_work_order = await WorkOrderRepository(engine).create_or_get(
                    WorkOrderCommand(
                        operation_id=locator_operation_id,
                        payload={
                            "sku": "SKU-DEMO-001",
                            "quantity": 10,
                            "approved_plan_hash": "b" * 64,
                        },
                    )
                )
                work_order_id = locator_work_order.work_order.id

            before = await operation_facts(engine, operation_id)
            with pytest.raises(RecoveryStateConflict) as captured:
                await repository.mark_verifying(operation_id, work_order_id)
            assert captured.value.reason == expected_reason
            assert await operation_facts(engine, operation_id) == before
    finally:
        for operation_id in operation_ids:
            await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_completed_work_order_locator_must_match_operation_before_transition(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_ids: list[UUID] = []

    try:
        for locator_kind, expected_reason in (
            ("missing", "work_order_locator_missing"),
            ("wrong_operation", "work_order_operation_mismatch"),
        ):
            operation_id = await repository.create(operation_request())
            operation_ids.append(operation_id)
            await advance_to_awaiting_approval(
                repository,
                operation_id,
                approval_expires_at=NOW + timedelta(minutes=5),
            )
            approval = await ApprovalRepository(engine).submit_once(
                ApprovalCommand(
                    operation_id=operation_id,
                    approver_id=f"complete-{locator_kind}",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approved",
                )
            )
            await repository.mark_executing(operation_id, approval.id)
            write_result = await WorkOrderRepository(engine).create_or_get(
                WorkOrderCommand(
                    operation_id=operation_id,
                    payload={
                        "sku": "SKU-DEMO-001",
                        "quantity": 10,
                        "approved_plan_hash": "b" * 64,
                    },
                )
            )
            own_work_order_id = write_result.work_order.id
            await repository.mark_verifying(operation_id, own_work_order_id)

            locator_id = uuid4()
            if locator_kind == "wrong_operation":
                locator_operation_id = await repository.create(operation_request())
                operation_ids.append(locator_operation_id)
                locator_id = await seed_work_order(engine, locator_operation_id)

            invalid_result = OperationResult(
                outcome="work_order_completed",
                message="The replenishment work order completed.",
                work_order_id=locator_id,
            )
            before = await operation_facts(engine, operation_id)
            with pytest.raises(RecoveryStateConflict) as captured:
                await repository.mark_completed(operation_id, invalid_result, locator_id)
            assert captured.value.reason == expected_reason
            assert await operation_facts(engine, operation_id) == before

            valid_result = invalid_result.model_copy(update={"work_order_id": own_work_order_id})
            await repository.mark_completed(
                operation_id,
                valid_result,
                own_work_order_id,
            )
            assert (await repository.load_detail(operation_id)).result == valid_result
    finally:
        for operation_id in operation_ids:
            await cleanup_operation(engine, operation_id)


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
    missing_expiry_id = await repository.create(operation_request())

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
        await advance_to_awaiting_approval(
            repository,
            missing_expiry_id,
            approval_expires_at=NOW + timedelta(minutes=5),
        )

        assert due_id in await repository.list_due_approval_ids(NOW, limit=10)
        assert future_id not in await repository.list_due_approval_ids(NOW, limit=10)
        assert due_id in await repository.list_recoverable_ids()

        assert await repository.mark_expired(future_id, NOW) is False
        assert (await repository.load_detail(future_id)).status is (
            OperationStatus.AWAITING_APPROVAL
        )

        persisted_expiry = (await repository.load_detail(due_id)).approval_expires_at
        assert persisted_expiry is not None
        assert await repository.mark_expired(due_id, NOW + timedelta(minutes=1)) is True
        first_expiration_facts = await operation_facts(engine, due_id)
        assert first_expiration_facts[3][-1][1:] == (
            "approval_expired",
            {"approval_expires_at": persisted_expiry.isoformat()},
        )
        assert await repository.mark_expired(due_id, NOW + timedelta(days=1)) is False
        assert await operation_facts(engine, due_id) == first_expiration_facts

        view = await repository.load_detail(due_id)
        assert view.status is OperationStatus.EXPIRED
        assert view.event_types[-1] == "approval_expired"
        assert due_id not in await repository.list_recoverable_ids()

        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == missing_expiry_id)
                .values(approval_expires_at=None)
            )
        with pytest.raises(RecoveryStateConflict) as captured:
            await repository.mark_expired(missing_expiry_id, NOW + timedelta(days=1))
        assert captured.value.reason == "approval_expiry_missing"
    finally:
        await cleanup_operation(engine, due_id)
        await cleanup_operation(engine, future_id)
        await cleanup_operation(engine, missing_expiry_id)


@pytest.mark.asyncio
async def test_expiration_replay_checks_due_before_target_event_identity(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    expires_at = NOW + timedelta(minutes=5)

    try:
        await advance_to_awaiting_approval(
            repository,
            operation_id,
            approval_expires_at=expires_at,
        )
        assert await repository.mark_expired(operation_id, expires_at) is True
        async with engine.begin() as connection:
            await connection.execute(
                update(audit_events)
                .where(
                    audit_events.c.operation_id == operation_id,
                    audit_events.c.event_type == "approval_expired",
                )
                .values(payload={"approval_expires_at": "different"})
            )

        assert (
            await repository.mark_expired(operation_id, expires_at - timedelta(seconds=1)) is False
        )
        with pytest.raises(RecoveryStateConflict) as captured:
            await repository.mark_expired(operation_id, expires_at + timedelta(seconds=1))
        assert captured.value.reason == "target_state_event_mismatch"
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_expiration_replay_rejects_changed_persisted_expiry_fact(
    engine: AsyncEngine,
) -> None:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    original_expiry = NOW
    changed_expiry = NOW + timedelta(minutes=5)

    try:
        await advance_to_awaiting_approval(
            repository,
            operation_id,
            approval_expires_at=original_expiry,
        )
        assert await repository.mark_expired(operation_id, original_expiry) is True
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(approval_expires_at=changed_expiry)
            )

        with pytest.raises(RecoveryStateConflict) as captured:
            await repository.mark_expired(operation_id, changed_expiry)
        assert captured.value.reason == "target_state_event_mismatch"
    finally:
        await cleanup_operation(engine, operation_id)


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
