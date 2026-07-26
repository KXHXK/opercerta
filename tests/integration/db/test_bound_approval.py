import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import (
    ApprovalDecision,
    ApprovalRecord,
    BoundApprovalCommand,
)
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.errors import (
    ApprovalAlreadyDecided,
    ApprovalExpired,
    ApprovalSnapshotMismatch,
    OperationNotFound,
)
from opercerta.domain.replenishment import (
    ApprovalBinding,
    EvidenceBundle,
    InventoryEvidence,
    PolicyEvidence,
    ReplenishmentAssessment,
    ReplenishmentPlan,
)
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.db.schema import approvals, audit_events, operations

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class ApprovalFacts:
    status: str
    approval_expires_at: datetime | None
    approval_count: int
    binding: ApprovalBinding | None
    event_types: tuple[str, ...]
    last_event_payload: dict[str, object]


def operation_request() -> OperationRequest:
    return OperationRequest(
        message="Check SKU-LOW-001 and replenish if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )


def evidence_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        inventory=InventoryEvidence(
            evidence_id=UUID("10000000-0000-4000-8000-000000000001"),
            sku="SKU-LOW-001",
            on_hand_quantity=4,
            reserved_quantity=2,
            captured_at=NOW,
            source_version="inventory-seed-v1",
        ),
        policy=PolicyEvidence(
            evidence_id=UUID("20000000-0000-4000-8000-000000000002"),
            action="replenish_inventory",
            sku="SKU-LOW-001",
            reorder_point=8,
            target_stock=20,
            minimum_order_quantity=1,
            maximum_order_quantity=30,
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="replenishment-v1",
            captured_at=NOW,
        ),
    )


def assessment() -> ReplenishmentAssessment:
    return ReplenishmentAssessment(
        sku="SKU-LOW-001",
        available_quantity=2,
        reorder_point=8,
        target_stock=20,
        replenishment_required=True,
        recommended_quantity=18,
        decision_facts_hash="a" * 64,
    )


def plan() -> ReplenishmentPlan:
    return ReplenishmentPlan(
        action="replenish_inventory",
        sku="SKU-LOW-001",
        recommended_quantity=18,
        decision_facts_hash="a" * 64,
        rule_version="replenishment-v1",
        summary="Inventory is below the approved reorder point.",
        rationale="Eighteen units restore the approved target stock.",
        plan_hash="b" * 64,
    )


def binding() -> ApprovalBinding:
    bundle = evidence_bundle()
    replenishment_plan = plan()
    return ApprovalBinding(
        inventory_evidence_id=bundle.inventory.evidence_id,
        policy_evidence_id=bundle.policy.evidence_id,
        rule_version=replenishment_plan.rule_version,
        decision_facts_hash=replenishment_plan.decision_facts_hash,
        plan_hash=replenishment_plan.plan_hash,
        recommended_quantity=replenishment_plan.recommended_quantity,
    )


def command(
    operation_id: UUID,
    *,
    index: int = 1,
    expected_binding: ApprovalBinding | None = None,
) -> BoundApprovalCommand:
    return BoundApprovalCommand(
        operation_id=operation_id,
        approver_id=f"approver-{index}",
        decision=(ApprovalDecision.APPROVED if index % 2 else ApprovalDecision.REJECTED),
        reason=f"synthetic approval decision {index}",
        expected_binding=expected_binding or binding(),
    )


async def prepare_operation(
    engine: AsyncEngine,
    *,
    approval_expires_at: datetime = EXPIRES_AT,
) -> UUID:
    repository = ReplenishmentOperationRepository(engine)
    operation_id = await repository.create(operation_request())
    await repository.mark_gathering_evidence(operation_id)
    await repository.record_evidence(operation_id, evidence_bundle())
    await repository.record_validated_plan(operation_id, assessment(), plan())
    await repository.mark_awaiting_approval(
        operation_id,
        binding(),
        approval_expires_at,
    )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


async def approval_facts(engine: AsyncEngine, operation_id: UUID) -> ApprovalFacts:
    async with engine.connect() as connection:
        operation = (
            (await connection.execute(select(operations).where(operations.c.id == operation_id)))
            .mappings()
            .one()
        )
        approval_rows = (
            (
                await connection.execute(
                    select(approvals).where(approvals.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
        event_rows = (
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

    approval_binding = None
    if approval_rows:
        row = approval_rows[0]
        approval_binding = ApprovalBinding(
            inventory_evidence_id=row["inventory_evidence_id"],
            policy_evidence_id=row["policy_evidence_id"],
            rule_version=row["rule_version"],
            decision_facts_hash=row["decision_facts_hash"],
            plan_hash=row["plan_hash"],
            recommended_quantity=row["recommended_quantity"],
        )
    return ApprovalFacts(
        status=str(operation["status"]),
        approval_expires_at=operation["approval_expires_at"],
        approval_count=len(approval_rows),
        binding=approval_binding,
        event_types=tuple(str(row["event_type"]) for row in event_rows),
        last_event_payload=dict(event_rows[-1]["payload"]),
    )


@pytest.mark.asyncio
async def test_bound_approval_atomically_records_binding_and_resumes(
    engine: AsyncEngine,
) -> None:
    operation_id = await prepare_operation(engine)

    try:
        record = await ApprovalRepository(engine).submit_bound_once(
            command(operation_id),
            now=NOW,
        )
        facts = await approval_facts(engine, operation_id)

        assert record.operation_id == operation_id
        assert facts.status == "resuming"
        assert facts.approval_count == 1
        assert facts.binding == binding()
        assert facts.event_types[-1] == "approval_recorded"
        assert facts.last_event_payload == {
            "approval_id": str(record.id),
            "approval_cycle": 1,
            "decision": record.decision.value,
        }
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("inventory_evidence_id", UUID("30000000-0000-4000-8000-000000000003")),
        ("policy_evidence_id", UUID("40000000-0000-4000-8000-000000000004")),
        ("rule_version", "replenishment-v2"),
        ("decision_facts_hash", "c" * 64),
        ("plan_hash", "d" * 64),
        ("recommended_quantity", 19),
    ],
)
async def test_each_changed_binding_fact_is_rejected_without_writes(
    engine: AsyncEngine,
    field: str,
    changed_value: object,
) -> None:
    operation_id = await prepare_operation(engine)
    mismatched = binding().model_copy(update={field: changed_value})

    try:
        with pytest.raises(
            ApprovalSnapshotMismatch,
            match="approval_snapshot_mismatch",
        ):
            await ApprovalRepository(engine).submit_bound_once(
                command(operation_id, expected_binding=mismatched),
                now=NOW,
            )

        facts = await approval_facts(engine, operation_id)
        assert facts.status == "awaiting_approval"
        assert facts.approval_count == 0
        assert facts.event_types[-1] == "approval_requested"
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_approval_at_exact_expiry_commits_expired_state_then_raises(
    engine: AsyncEngine,
) -> None:
    operation_id = await prepare_operation(engine)

    try:
        with pytest.raises(ApprovalExpired, match="approval_expired"):
            await ApprovalRepository(engine).submit_bound_once(
                command(operation_id),
                now=EXPIRES_AT,
            )

        facts = await approval_facts(engine, operation_id)
        assert facts.status == "expired"
        assert facts.approval_count == 0
        assert facts.event_types[-1] == "approval_expired"
        assert facts.approval_expires_at is not None
        assert facts.last_event_payload == {
            "approval_expires_at": facts.approval_expires_at.isoformat()
        }
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_ten_concurrent_bound_decisions_commit_exactly_one(
    engine: AsyncEngine,
) -> None:
    operation_id = await prepare_operation(engine)
    repository = ApprovalRepository(engine)

    try:
        results = await asyncio.gather(
            *[
                repository.submit_bound_once(
                    command(operation_id, index=index),
                    now=NOW,
                )
                for index in range(10)
            ],
            return_exceptions=True,
        )

        assert sum(isinstance(item, ApprovalRecord) for item in results) == 1
        assert sum(isinstance(item, ApprovalAlreadyDecided) for item in results) == 9
        facts = await approval_facts(engine, operation_id)
        assert facts.status == "resuming"
        assert facts.approval_count == 1
        assert facts.binding == binding()
        assert facts.event_types.count("approval_recorded") == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_bound_approval_rejects_missing_operation_without_writes(
    engine: AsyncEngine,
) -> None:
    operation_id = uuid4()

    with pytest.raises(OperationNotFound, match="operation_not_found"):
        await ApprovalRepository(engine).submit_bound_once(
            command(operation_id),
            now=NOW,
        )

    async with engine.connect() as connection:
        approval_count = len(
            (
                await connection.execute(
                    select(approvals).where(approvals.c.operation_id == operation_id)
                )
            ).all()
        )
        event_count = len(
            (
                await connection.execute(
                    select(audit_events).where(audit_events.c.operation_id == operation_id)
                )
            ).all()
        )
    assert approval_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_bound_approval_requires_timezone_aware_now(
    engine: AsyncEngine,
) -> None:
    operation_id = await prepare_operation(engine)

    try:
        with pytest.raises(ValueError, match="timezone"):
            await ApprovalRepository(engine).submit_bound_once(
                command(operation_id),
                now=datetime(2026, 7, 16, 8, 0),
            )
        facts = await approval_facts(engine, operation_id)
        assert facts.status == "awaiting_approval"
        assert facts.approval_count == 0
    finally:
        await cleanup_operation(engine, operation_id)
