from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from opercerta.domain.errors import (
    EvidenceExpired,
    ReplenishmentQuantityOutOfPolicy,
)
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.replenishment import (
    ApprovalBinding,
    EvidenceBundle,
    InventoryEvidence,
    InventoryPosition,
    ModelPlanExplanation,
    PolicyEvidence,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    assess_replenishment,
    build_approval_binding,
    build_plan,
)

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
INVENTORY_ID = UUID("00000000-0000-4000-8000-000000000101")
POLICY_ID = UUID("00000000-0000-4000-8000-000000000102")


def bundle(
    *,
    on_hand: int = 20,
    reserved: int = 8,
    reorder: int = 15,
    target: int = 30,
    minimum: int = 1,
    maximum: int = 100,
    captured_at: datetime = NOW,
) -> EvidenceBundle:
    return EvidenceBundle(
        inventory=InventoryEvidence(
            evidence_id=INVENTORY_ID,
            sku="SKU-LOW-001",
            on_hand_quantity=on_hand,
            reserved_quantity=reserved,
            captured_at=captured_at,
            source_version="inventory-seed-v1",
        ),
        policy=PolicyEvidence(
            evidence_id=POLICY_ID,
            action="replenish_inventory",
            sku="SKU-LOW-001",
            reorder_point=reorder,
            target_stock=target,
            minimum_order_quantity=minimum,
            maximum_order_quantity=maximum,
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="replenishment-v1",
            captured_at=captured_at,
        ),
    )


@pytest.mark.parametrize(
    "invalid_value",
    ["1", True, 1.0],
    ids=["string", "bool", "integer-valued-float"],
)
@pytest.mark.parametrize(
    "model_type,valid_data,field",
    [
        (
            InventoryEvidence,
            {
                "evidence_id": INVENTORY_ID,
                "sku": "SKU-LOW-001",
                "on_hand_quantity": 20,
                "reserved_quantity": 8,
                "captured_at": NOW,
                "source_version": "inventory-seed-v1",
            },
            "on_hand_quantity",
        ),
        (
            InventoryEvidence,
            {
                "evidence_id": INVENTORY_ID,
                "sku": "SKU-LOW-001",
                "on_hand_quantity": 20,
                "reserved_quantity": 8,
                "captured_at": NOW,
                "source_version": "inventory-seed-v1",
            },
            "reserved_quantity",
        ),
        (
            PolicyEvidence,
            {
                "evidence_id": POLICY_ID,
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "reorder_point": 15,
                "target_stock": 30,
                "minimum_order_quantity": 1,
                "maximum_order_quantity": 100,
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "replenishment-v1",
                "captured_at": NOW,
            },
            "reorder_point",
        ),
        (
            PolicyEvidence,
            {
                "evidence_id": POLICY_ID,
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "reorder_point": 0,
                "target_stock": 30,
                "minimum_order_quantity": 1,
                "maximum_order_quantity": 100,
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "replenishment-v1",
                "captured_at": NOW,
            },
            "target_stock",
        ),
        (
            PolicyEvidence,
            {
                "evidence_id": POLICY_ID,
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "reorder_point": 15,
                "target_stock": 30,
                "minimum_order_quantity": 1,
                "maximum_order_quantity": 100,
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "replenishment-v1",
                "captured_at": NOW,
            },
            "minimum_order_quantity",
        ),
        (
            PolicyEvidence,
            {
                "evidence_id": POLICY_ID,
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "reorder_point": 15,
                "target_stock": 30,
                "minimum_order_quantity": 1,
                "maximum_order_quantity": 100,
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "replenishment-v1",
                "captured_at": NOW,
            },
            "maximum_order_quantity",
        ),
        (
            PolicyEvidence,
            {
                "evidence_id": POLICY_ID,
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "reorder_point": 15,
                "target_stock": 30,
                "minimum_order_quantity": 1,
                "maximum_order_quantity": 100,
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "replenishment-v1",
                "captured_at": NOW,
            },
            "evidence_ttl_seconds",
        ),
        (
            InventoryPosition,
            {"sku": "SKU-LOW-001", "available_quantity": 12},
            "available_quantity",
        ),
        (
            ReplenishmentAssessment,
            {
                "sku": "SKU-LOW-001",
                "available_quantity": 12,
                "reorder_point": 15,
                "target_stock": 30,
                "replenishment_required": True,
                "recommended_quantity": 18,
                "decision_facts_hash": "0" * 64,
            },
            "available_quantity",
        ),
        (
            ReplenishmentAssessment,
            {
                "sku": "SKU-LOW-001",
                "available_quantity": 12,
                "reorder_point": 15,
                "target_stock": 30,
                "replenishment_required": True,
                "recommended_quantity": 18,
                "decision_facts_hash": "0" * 64,
            },
            "reorder_point",
        ),
        (
            ReplenishmentAssessment,
            {
                "sku": "SKU-LOW-001",
                "available_quantity": 12,
                "reorder_point": 15,
                "target_stock": 30,
                "replenishment_required": True,
                "recommended_quantity": 18,
                "decision_facts_hash": "0" * 64,
            },
            "target_stock",
        ),
        (
            ReplenishmentAssessment,
            {
                "sku": "SKU-LOW-001",
                "available_quantity": 12,
                "reorder_point": 15,
                "target_stock": 30,
                "replenishment_required": True,
                "recommended_quantity": 18,
                "decision_facts_hash": "0" * 64,
            },
            "recommended_quantity",
        ),
        (
            ReplenishmentPlan,
            {
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
                "recommended_quantity": 18,
                "decision_facts_hash": "0" * 64,
                "rule_version": "replenishment-v1",
                "summary": "summary",
                "rationale": "rationale",
                "plan_hash": "1" * 64,
            },
            "recommended_quantity",
        ),
        (
            ApprovalBinding,
            {
                "inventory_evidence_id": INVENTORY_ID,
                "policy_evidence_id": POLICY_ID,
                "rule_version": "replenishment-v1",
                "decision_facts_hash": "0" * 64,
                "plan_hash": "1" * 64,
                "recommended_quantity": 18,
            },
            "recommended_quantity",
        ),
    ],
)
def test_integer_domain_fields_reject_coercion(
    model_type: type[BaseModel],
    valid_data: dict[str, object],
    field: str,
    invalid_value: object,
) -> None:
    data = valid_data.copy()
    data[field] = invalid_value

    with pytest.raises(ValidationError):
        model_type.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sku", ""),
        ("on_hand_quantity", -1),
        ("reserved_quantity", -1),
        ("captured_at", datetime(2026, 7, 16, 8, 0)),
    ],
)
def test_inventory_evidence_rejects_invalid_input(field: str, value: object) -> None:
    data = bundle().inventory.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        InventoryEvidence.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"target_stock": 15, "reorder_point": 15},
        {"minimum_order_quantity": 0},
        {"maximum_order_quantity": 0, "minimum_order_quantity": 1},
        {"evidence_ttl_seconds": 0},
        {"approval_required": False},
        {"action": "repair_equipment"},
    ],
)
def test_policy_rejects_unsafe_contracts(changes: dict[str, object]) -> None:
    data = bundle().policy.model_dump()
    data.update(changes)
    with pytest.raises(ValidationError):
        PolicyEvidence.model_validate(data)


def test_low_inventory_calculates_exact_replenishment() -> None:
    result = assess_replenishment(bundle(), NOW + timedelta(seconds=30))
    assert result.available_quantity == 12
    assert result.replenishment_required is True
    assert result.recommended_quantity == 18


def test_normal_inventory_requires_no_approval_or_order() -> None:
    result = assess_replenishment(
        bundle(on_hand=40, reserved=5, reorder=20, target=50),
        NOW + timedelta(seconds=30),
    )
    assert result.available_quantity == 35
    assert result.replenishment_required is False
    assert result.recommended_quantity is None


def test_over_reserved_inventory_keeps_negative_available_quantity() -> None:
    result = assess_replenishment(
        bundle(on_hand=2, reserved=7, reorder=5, target=10),
        NOW + timedelta(seconds=30),
    )
    assert result.available_quantity == -5
    assert result.recommended_quantity == 15


def test_quantity_outside_policy_is_rejected_not_clamped() -> None:
    with pytest.raises(
        ReplenishmentQuantityOutOfPolicy,
        match="replenishment_quantity_out_of_policy",
    ):
        assess_replenishment(
            bundle(on_hand=0, reserved=0, reorder=10, target=100, maximum=20),
            NOW + timedelta(seconds=30),
        )


def test_expired_inventory_or_policy_is_rejected() -> None:
    with pytest.raises(EvidenceExpired, match="evidence_expired"):
        assess_replenishment(bundle(), NOW + timedelta(seconds=301))


def test_plan_hash_uses_normalized_rule_version() -> None:
    assessment = assess_replenishment(bundle(), NOW + timedelta(seconds=30))
    explanation = ModelPlanExplanation(summary="summary", rationale="rationale")

    normalized = build_plan(assessment, explanation, "replenishment-v1")
    padded = build_plan(assessment, explanation, " replenishment-v1 ")

    assert padded.rule_version == normalized.rule_version
    assert padded.plan_hash == normalized.plan_hash


@pytest.mark.asyncio
async def test_mock_model_cannot_supply_deterministic_fields() -> None:
    current_bundle = bundle()
    assessment = assess_replenishment(
        current_bundle,
        NOW + timedelta(seconds=30),
    )
    explanation = await MockModelGateway().explain_plan(assessment)
    assert explanation.summary
    assert set(explanation.model_fields_set) == {"summary", "rationale"}
    plan = build_plan(
        assessment,
        explanation,
        current_bundle.policy.rule_version,
    )
    binding = build_approval_binding(current_bundle, plan)
    assert plan.action == "replenish_inventory"
    assert plan.recommended_quantity == 18
    assert binding.recommended_quantity == 18
    assert len(binding.decision_facts_hash) == 64
    assert len(binding.plan_hash) == 64
