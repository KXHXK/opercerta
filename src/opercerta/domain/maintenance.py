from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    PositiveInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from opercerta.domain.errors import EvidenceExpired
from opercerta.domain.replenishment import Digest, ModelPlanExplanation, SafeText, Version
from opercerta.domain.scenarios import (
    ApprovalBinding,
    RepairParameters,
    SafeCode,
    ScenarioKind,
)
from opercerta.domain.work_orders import hash_payload

EquipmentId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return value


class EquipmentState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class AlertSeverity(StrEnum):
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


class MaintenancePriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EquipmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    equipment_id: EquipmentId
    state: EquipmentState
    alert_code: SafeCode | None
    severity: AlertSeverity
    last_heartbeat: datetime
    captured_at: datetime
    source_version: Version

    @field_validator("last_heartbeat", "captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def require_consistent_alert(self) -> Self:
        if (self.alert_code is None) != (self.severity is AlertSeverity.NONE):
            raise ValueError("alert code and severity must be present together")
        if self.last_heartbeat > self.captured_at:
            raise ValueError("last heartbeat cannot be later than capture time")
        return self


class PriorityMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    warning: MaintenancePriority
    critical: MaintenancePriority
    stale_heartbeat: MaintenancePriority

    @model_validator(mode="after")
    def require_escalating_priorities(self) -> Self:
        rank = {
            MaintenancePriority.NORMAL: 0,
            MaintenancePriority.HIGH: 1,
            MaintenancePriority.URGENT: 2,
        }
        if rank[self.critical] < rank[self.warning]:
            raise ValueError("critical priority cannot be lower than warning priority")
        return self


class MaintenancePolicyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    action: Literal["repair_equipment"]
    equipment_id: EquipmentId
    allowed_alert_levels: tuple[Literal["warning", "critical"], ...]
    maximum_heartbeat_age_seconds: PositiveInt
    priority_mapping: PriorityMapping
    evidence_ttl_seconds: PositiveInt
    approval_required: Literal[True]
    rule_version: Version
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("allowed_alert_levels")
    @classmethod
    def require_unique_alert_levels(
        cls,
        value: tuple[Literal["warning", "critical"], ...],
    ) -> tuple[Literal["warning", "critical"], ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("allowed alert levels must be non-empty and unique")
        return value


class MaintenanceEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equipment: EquipmentEvidence
    policy: MaintenancePolicyEvidence

    @model_validator(mode="after")
    def require_matching_equipment(self) -> Self:
        if self.equipment.equipment_id != self.policy.equipment_id:
            raise ValueError("equipment and policy equipment ID must match")
        if self.equipment.evidence_id == self.policy.evidence_id:
            raise ValueError("equipment and policy evidence IDs must differ")
        return self


class MaintenanceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equipment_id: EquipmentId
    state: EquipmentState
    alert_code: SafeCode | None
    maintenance_required: bool
    reason: Literal["alert", "stale_heartbeat"] | None
    priority: MaintenancePriority | None
    heartbeat_age_seconds: int
    decision_facts_hash: Digest


class MaintenancePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["repair_equipment"]
    equipment_id: EquipmentId
    alert_code: SafeCode
    priority: MaintenancePriority
    decision_facts_hash: Digest
    rule_version: Version
    summary: SafeText
    rationale: SafeText
    plan_hash: Digest


class RepairWorkOrderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["repair"] = "repair"
    equipment_id: EquipmentId
    alert_code: SafeCode
    priority: MaintenancePriority
    approved_plan_hash: Digest


def assess_maintenance(
    bundle: MaintenanceEvidenceBundle,
    now: datetime,
) -> MaintenanceAssessment:
    _require_timezone(now)
    ttl = timedelta(seconds=bundle.policy.evidence_ttl_seconds)
    if now >= bundle.equipment.captured_at + ttl or now >= bundle.policy.captured_at + ttl:
        raise EvidenceExpired

    heartbeat_age = max(0, int((now - bundle.equipment.last_heartbeat).total_seconds()))
    stale = heartbeat_age > bundle.policy.maximum_heartbeat_age_seconds
    alert_allowed = bundle.equipment.severity.value in bundle.policy.allowed_alert_levels
    maintenance_required = stale or alert_allowed

    reason: Literal["alert", "stale_heartbeat"] | None = None
    priority: MaintenancePriority | None = None
    alert_code: str | None = bundle.equipment.alert_code
    if alert_allowed:
        reason = "alert"
        priority = getattr(bundle.policy.priority_mapping, bundle.equipment.severity.value)
    if stale and (
        priority is None
        or _priority_rank(bundle.policy.priority_mapping.stale_heartbeat) > _priority_rank(priority)
    ):
        reason = "stale_heartbeat"
        priority = bundle.policy.priority_mapping.stale_heartbeat
        alert_code = "STALE_HEARTBEAT"

    facts: dict[str, JsonValue] = {
        "alert_code": alert_code,
        "alert_allowed": alert_allowed,
        "equipment_id": bundle.equipment.equipment_id,
        "heartbeat_stale": stale,
        "last_heartbeat": bundle.equipment.last_heartbeat.isoformat(),
        "maintenance_required": maintenance_required,
        "priority": priority.value if priority is not None else None,
        "reason": reason,
        "severity": bundle.equipment.severity.value,
        "source_version": bundle.equipment.source_version,
        "state": bundle.equipment.state.value,
    }
    return MaintenanceAssessment(
        equipment_id=bundle.equipment.equipment_id,
        state=bundle.equipment.state,
        alert_code=alert_code,
        maintenance_required=maintenance_required,
        reason=reason,
        priority=priority,
        heartbeat_age_seconds=heartbeat_age,
        decision_facts_hash=hash_payload(facts),
    )


def build_maintenance_plan(
    assessment: MaintenanceAssessment,
    explanation: ModelPlanExplanation,
    rule_version: str,
) -> MaintenancePlan:
    if (
        not assessment.maintenance_required
        or assessment.alert_code is None
        or assessment.priority is None
    ):
        raise ValueError("maintenance plan requires a repair assessment")
    normalized_rule_version = rule_version.strip()
    facts: dict[str, JsonValue] = {
        "action": "repair_equipment",
        "alert_code": assessment.alert_code,
        "decision_facts_hash": assessment.decision_facts_hash,
        "equipment_id": assessment.equipment_id,
        "priority": assessment.priority.value,
        "rule_version": normalized_rule_version,
    }
    return MaintenancePlan(
        action="repair_equipment",
        equipment_id=assessment.equipment_id,
        alert_code=assessment.alert_code,
        priority=assessment.priority,
        decision_facts_hash=assessment.decision_facts_hash,
        rule_version=normalized_rule_version,
        summary=explanation.summary,
        rationale=explanation.rationale,
        plan_hash=hash_payload(facts),
    )


def build_maintenance_approval_binding(
    bundle: MaintenanceEvidenceBundle,
    plan: MaintenancePlan,
) -> ApprovalBinding:
    return ApprovalBinding(
        scenario=ScenarioKind.EQUIPMENT,
        subject_evidence_id=bundle.equipment.evidence_id,
        policy_evidence_id=bundle.policy.evidence_id,
        rule_version=plan.rule_version,
        decision_facts_hash=plan.decision_facts_hash,
        plan_hash=plan.plan_hash,
        parameters=RepairParameters(
            alert_code=plan.alert_code,
            priority=plan.priority.value,
        ),
    )


def _priority_rank(priority: MaintenancePriority) -> int:
    return {
        MaintenancePriority.NORMAL: 0,
        MaintenancePriority.HIGH: 1,
        MaintenancePriority.URGENT: 2,
    }[priority]
