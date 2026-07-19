import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.errors import InventoryNotFound
from opercerta.tools.catalog import SyntheticCatalog

ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = ROOT / "data" / "synthetic" / "inventory.json"
POLICY_PATH = ROOT / "data" / "synthetic" / "replenishment_policies.json"
EQUIPMENT_PATH = ROOT / "data" / "synthetic" / "equipment.json"
MAINTENANCE_POLICY_PATH = ROOT / "data" / "synthetic" / "maintenance_policies.json"
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
EXPECTED_SKUS = {
    "SKU-NORMAL-001",
    "SKU-LOW-001",
    "SKU-BACKORDER-001",
    "SKU-LIMIT-001",
    "SKU-MUTABLE-001",
}


def deterministic_ids() -> Iterator[UUID]:
    yield UUID("10000000-0000-4000-8000-000000000001")
    yield UUID("20000000-0000-4000-8000-000000000002")
    yield UUID("30000000-0000-4000-8000-000000000003")


def load_catalog() -> SyntheticCatalog:
    ids = deterministic_ids()
    return SyntheticCatalog.load(
        INVENTORY_PATH,
        POLICY_PATH,
        equipment_path=EQUIPMENT_PATH,
        maintenance_policy_path=MAINTENANCE_POLICY_PATH,
        id_factory=lambda: next(ids),
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_catalog_loads_exact_versioned_synthetic_skus() -> None:
    catalog = load_catalog()

    assert catalog.skus == frozenset(EXPECTED_SKUS)
    inventory = catalog.inventory_snapshot("SKU-LOW-001", NOW)
    policy = catalog.policy_constraints("SKU-LOW-001", NOW)
    assert inventory.source_version == "inventory-seed-v1"
    assert inventory.on_hand_quantity == 20
    assert inventory.reserved_quantity == 8
    assert policy.rule_version == "replenishment-v1"
    assert policy.approval_required is True
    assert policy.reorder_point == 15
    assert policy.target_stock == 30


def test_each_catalog_read_allocates_fresh_evidence_with_aware_capture_time() -> None:
    catalog = load_catalog()

    first = catalog.inventory_snapshot("SKU-LOW-001", NOW)
    second = catalog.inventory_snapshot("SKU-LOW-001", NOW)
    policy = catalog.policy_constraints("SKU-LOW-001", NOW)

    assert first.evidence_id != second.evidence_id != policy.evidence_id
    assert first.captured_at == second.captured_at == policy.captured_at == NOW
    assert first.captured_at.utcoffset() is not None


def test_catalog_returns_versioned_equipment_and_maintenance_policy() -> None:
    catalog = load_catalog()

    equipment = catalog.equipment_status("EQ-PUMP-001", NOW)
    policy = catalog.maintenance_policy_constraints("EQ-PUMP-001", NOW)

    assert equipment.source_version == "equipment-seed-v1"
    assert equipment.alert_code == "MOTOR_OVERHEAT"
    assert equipment.severity == "critical"
    assert policy.rule_version == "maintenance-v1"
    assert policy.maximum_heartbeat_age_seconds == 300


def test_missing_equipment_has_stable_error() -> None:
    catalog = load_catalog()

    with pytest.raises(LookupError, match="equipment_not_found"):
        catalog.equipment_status("EQ-UNKNOWN-001", NOW)


@pytest.mark.parametrize(
    "method_name",
    ["inventory_snapshot", "policy_constraints"],
)
def test_missing_sku_raises_stable_inventory_not_found(method_name: str) -> None:
    catalog = load_catalog()

    with pytest.raises(InventoryNotFound, match="inventory_not_found"):
        getattr(catalog, method_name)("SKU-UNKNOWN-001", NOW)


def test_replace_inventory_changes_only_an_existing_sku() -> None:
    catalog = load_catalog()
    before_normal = catalog.inventory_snapshot("SKU-NORMAL-001", NOW)

    catalog.replace_inventory(
        "SKU-MUTABLE-001",
        on_hand_quantity=11,
        reserved_quantity=3,
    )

    changed = catalog.inventory_snapshot("SKU-MUTABLE-001", NOW)
    after_normal = catalog.inventory_snapshot("SKU-NORMAL-001", NOW)
    assert (changed.on_hand_quantity, changed.reserved_quantity) == (11, 3)
    assert (
        after_normal.on_hand_quantity,
        after_normal.reserved_quantity,
    ) == (
        before_normal.on_hand_quantity,
        before_normal.reserved_quantity,
    )
    with pytest.raises(InventoryNotFound, match="inventory_not_found"):
        catalog.replace_inventory(
            "SKU-UNKNOWN-001",
            on_hand_quantity=1,
            reserved_quantity=0,
        )


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        (
            "duplicate-inventory.json",
            {
                "source_version": "inventory-v1",
                "items": [
                    {
                        "sku": "SKU-DUPLICATE-001",
                        "on_hand_quantity": 1,
                        "reserved_quantity": 0,
                    },
                    {
                        "sku": "SKU-DUPLICATE-001",
                        "on_hand_quantity": 2,
                        "reserved_quantity": 0,
                    },
                ],
            },
        ),
        (
            "invalid-inventory.json",
            {
                "source_version": "inventory-v1",
                "items": [
                    {
                        "sku": "SKU-INVALID-001",
                        "on_hand_quantity": "1",
                        "reserved_quantity": 0,
                    }
                ],
            },
        ),
    ],
)
def test_invalid_or_duplicate_inventory_seed_fails_startup(
    tmp_path: Path,
    filename: str,
    payload: object,
) -> None:
    inventory_path = tmp_path / filename
    write_json(inventory_path, payload)

    with pytest.raises((ValidationError, ValueError)):
        SyntheticCatalog.load(inventory_path, POLICY_PATH)


@pytest.mark.parametrize(
    "policy_change",
    [
        {"approval_required": False},
        {"approval_required": "true"},
        {"approval_required": 1},
        {"target_stock": 15, "reorder_point": 15},
        {"maximum_order_quantity": 0},
        {"evidence_ttl_seconds": 0},
        {"reorder_point": "15"},
    ],
)
def test_invalid_policy_seed_fails_startup(
    tmp_path: Path,
    policy_change: dict[str, object],
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["items"][0].update(policy_change)
    policy_path = tmp_path / "invalid-policy.json"
    write_json(policy_path, payload)

    with pytest.raises(ValidationError):
        SyntheticCatalog.load(INVENTORY_PATH, policy_path)
