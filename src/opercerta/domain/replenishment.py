from datetime import datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from opercerta.domain.errors import (
    EvidenceExpired,
    ReplenishmentQuantityOutOfPolicy,
)
from opercerta.domain.work_orders import hash_payload

Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return value


class InventoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    sku: Sku
    on_hand_quantity: StrictInt
    reserved_quantity: StrictInt
    captured_at: datetime
    source_version: Version

    @field_validator("on_hand_quantity", "reserved_quantity")
    @classmethod
    def require_non_negative_quantity(cls, value: int) -> int:
        if value < 0:
            raise ValueError("inventory quantities must be non-negative")
        return value

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)


class PolicyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    action: Literal["replenish_inventory"]
    sku: Sku
    reorder_point: StrictInt
    target_stock: StrictInt
    minimum_order_quantity: StrictInt
    maximum_order_quantity: StrictInt
    evidence_ttl_seconds: StrictInt
    approval_required: Literal[True]
    rule_version: Version
    captured_at: datetime

    @field_validator(
        "reorder_point",
        "target_stock",
        "minimum_order_quantity",
        "maximum_order_quantity",
        "evidence_ttl_seconds",
    )
    @classmethod
    def require_non_negative_integer(cls, value: int) -> int:
        if value < 0:
            raise ValueError("policy integers must be non-negative")
        return value

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def require_safe_policy_relationships(self) -> Self:
        if self.target_stock <= self.reorder_point:
            raise ValueError("target_stock must be greater than reorder_point")
        if self.minimum_order_quantity < 1:
            raise ValueError("minimum_order_quantity must be positive")
        if self.maximum_order_quantity < self.minimum_order_quantity:
            raise ValueError("maximum_order_quantity must be at least minimum_order_quantity")
        if self.evidence_ttl_seconds < 1:
            raise ValueError("evidence_ttl_seconds must be positive")
        return self


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory: InventoryEvidence
    policy: PolicyEvidence

    @model_validator(mode="after")
    def require_matching_sku(self) -> Self:
        if self.inventory.sku != self.policy.sku:
            raise ValueError("inventory and policy SKU must match")
        return self


class InventoryPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: Sku
    available_quantity: StrictInt


class ReplenishmentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: Sku
    available_quantity: StrictInt
    reorder_point: StrictInt
    target_stock: StrictInt
    replenishment_required: bool
    recommended_quantity: StrictInt | None
    decision_facts_hash: Digest


class ModelPlanExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: SafeText
    rationale: SafeText


class ReplenishmentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["replenish_inventory"]
    sku: Sku
    recommended_quantity: StrictInt
    decision_facts_hash: Digest
    rule_version: Version
    summary: SafeText
    rationale: SafeText
    plan_hash: Digest


class ApprovalBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory_evidence_id: UUID
    policy_evidence_id: UUID
    rule_version: Version
    decision_facts_hash: Digest
    plan_hash: Digest
    recommended_quantity: StrictInt


class OperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["replenishment_not_required", "work_order_completed"]
    message: SafeText
    work_order_id: UUID | None = None


class OperationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
    ]
    message: SafeText


def assess_replenishment(
    bundle: EvidenceBundle,
    now: datetime,
) -> ReplenishmentAssessment:
    _require_timezone(now)
    expires_after = timedelta(seconds=bundle.policy.evidence_ttl_seconds)
    if (
        now >= bundle.inventory.captured_at + expires_after
        or now >= bundle.policy.captured_at + expires_after
    ):
        raise EvidenceExpired

    position = InventoryPosition(
        sku=bundle.inventory.sku,
        available_quantity=(bundle.inventory.on_hand_quantity - bundle.inventory.reserved_quantity),
    )
    replenishment_required = position.available_quantity < bundle.policy.reorder_point
    recommended_quantity = (
        bundle.policy.target_stock - position.available_quantity if replenishment_required else None
    )
    if recommended_quantity is not None and not (
        bundle.policy.minimum_order_quantity
        <= recommended_quantity
        <= bundle.policy.maximum_order_quantity
    ):
        raise ReplenishmentQuantityOutOfPolicy

    decision_facts: dict[str, JsonValue] = {
        "available_quantity": position.available_quantity,
        "recommended_quantity": recommended_quantity,
        "reorder_point": bundle.policy.reorder_point,
        "replenishment_required": replenishment_required,
        "sku": position.sku,
        "target_stock": bundle.policy.target_stock,
    }
    return ReplenishmentAssessment(
        sku=position.sku,
        available_quantity=position.available_quantity,
        reorder_point=bundle.policy.reorder_point,
        target_stock=bundle.policy.target_stock,
        replenishment_required=replenishment_required,
        recommended_quantity=recommended_quantity,
        decision_facts_hash=hash_payload(decision_facts),
    )


def build_plan(
    assessment: ReplenishmentAssessment,
    explanation: ModelPlanExplanation,
    rule_version: str,
) -> ReplenishmentPlan:
    if assessment.recommended_quantity is None:
        raise ValueError("recommended quantity is required")

    normalized_rule_version = rule_version.strip()
    plan_facts: dict[str, JsonValue] = {
        "action": "replenish_inventory",
        "decision_facts_hash": assessment.decision_facts_hash,
        "recommended_quantity": assessment.recommended_quantity,
        "rule_version": normalized_rule_version,
        "sku": assessment.sku,
    }
    return ReplenishmentPlan(
        action="replenish_inventory",
        sku=assessment.sku,
        recommended_quantity=assessment.recommended_quantity,
        decision_facts_hash=assessment.decision_facts_hash,
        rule_version=normalized_rule_version,
        summary=explanation.summary,
        rationale=explanation.rationale,
        plan_hash=hash_payload(plan_facts),
    )


def build_approval_binding(
    bundle: EvidenceBundle,
    plan: ReplenishmentPlan,
) -> ApprovalBinding:
    return ApprovalBinding(
        inventory_evidence_id=bundle.inventory.evidence_id,
        policy_evidence_id=bundle.policy.evidence_id,
        rule_version=plan.rule_version,
        decision_facts_hash=plan.decision_facts_hash,
        plan_hash=plan.plan_hash,
        recommended_quantity=plan.recommended_quantity,
    )
