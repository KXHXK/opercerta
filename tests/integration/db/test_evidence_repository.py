from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import EvidenceConflict
from opercerta.domain.replenishment import (
    EvidenceBundle,
    InventoryEvidence,
    PolicyEvidence,
)
from opercerta.infrastructure.db.evidence_repository import (
    EvidenceRepository,
    hash_json,
)
from opercerta.infrastructure.db.schema import operations

NOW = datetime(2026, 7, 16, 4, 0, tzinfo=UTC)


def bundle(
    *,
    inventory_evidence_id: UUID | None = None,
    policy_evidence_id: UUID | None = None,
    on_hand_quantity: int = 3,
) -> EvidenceBundle:
    return EvidenceBundle(
        inventory=InventoryEvidence(
            evidence_id=inventory_evidence_id or uuid4(),
            sku="SKU-DEMO-001",
            on_hand_quantity=on_hand_quantity,
            reserved_quantity=1,
            captured_at=NOW,
            source_version="inventory-v1",
        ),
        policy=PolicyEvidence(
            evidence_id=policy_evidence_id or uuid4(),
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


async def seed_operation(engine: AsyncEngine) -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=str(operation_id),
                request_payload={
                    "schema_version": 1,
                    "request": {"message": "evidence repository test"},
                    "risk": {},
                    "plan": {},
                    "work_order_payload": {},
                },
                status="received",
            )
        )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_save_bundle_persists_ordered_hashed_evidence(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine)
    repository = EvidenceRepository(engine)

    try:
        saved = await repository.save_bundle(operation_id, bundle())
        rows = await repository.list_for_operation(operation_id)

        assert saved == tuple(rows)
        assert [row.evidence_type for row in rows] == ["inventory", "policy"]
        assert all(row.content_hash == hash_json(row.content) for row in rows)
        assert all(row.expires_at == NOW + timedelta(seconds=300) for row in rows)
        assert rows[0].source_tool == "inventory"
        assert rows[1].source_tool == "policy"
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_identical_bundle_replays_but_changed_same_ids_conflicts(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine)
    repository = EvidenceRepository(engine)
    original = bundle()
    changed = bundle(
        inventory_evidence_id=original.inventory.evidence_id,
        policy_evidence_id=original.policy.evidence_id,
        on_hand_quantity=4,
    )

    try:
        first = await repository.save_bundle(operation_id, original)
        replay = await repository.save_bundle(operation_id, original)
        assert replay == first

        with pytest.raises(EvidenceConflict, match="evidence_conflict"):
            await repository.save_bundle(operation_id, changed)

        assert await repository.list_for_operation(operation_id) == list(first)
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_save_refresh_appends_new_evidence_ids(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine)
    repository = EvidenceRepository(engine)

    try:
        initial = await repository.save_bundle(operation_id, bundle())
        refreshed = await repository.save_refresh(operation_id, bundle())
        rows = await repository.list_for_operation(operation_id)

        assert len(rows) == 4
        assert {row.evidence_id for row in rows} == {
            *(row.evidence_id for row in initial),
            *(row.evidence_id for row in refreshed),
        }
    finally:
        await cleanup_operation(engine, operation_id)
