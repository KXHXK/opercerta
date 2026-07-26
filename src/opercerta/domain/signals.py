from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator

from opercerta.domain.contracts import ObjectType
from opercerta.domain.maintenance import MaintenanceAssessment, MaintenancePriority
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.replenishment import Digest, ReplenishmentAssessment
from opercerta.domain.task_recovery import TaskRecoveryAssessment

ObjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SafeCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
DedupKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class SignalType(StrEnum):
    INVENTORY_SHORTAGE = "inventory_shortage"
    EQUIPMENT_ATTENTION = "equipment_attention"
    TASK_BLOCKED = "task_blocked"


class SignalSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    ATTENTION_REQUIRED = "attention_required"


class SignalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_type: SignalType
    object_type: ObjectType
    object_id: ObjectId
    source: SafeCode
    severity: SignalSeverity
    reason_code: SafeCode
    facts_hash: Digest
    facts: dict[str, JsonValue]
    detected_at: datetime

    @field_validator("detected_at")
    @classmethod
    def require_aware_detected_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at must include timezone")
        return value


class OperationalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    dedup_key: DedupKey
    signal_type: SignalType
    object_type: ObjectType
    object_id: ObjectId
    source: SafeCode
    severity: SignalSeverity
    reason_code: SafeCode
    facts_hash: Digest
    facts: dict[str, JsonValue]
    status: SignalStatus
    operation_id: UUID | None
    predecessor_signal_id: UUID | None = None
    detected_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    @field_validator("detected_at", "updated_at", "resolved_at")
    @classmethod
    def require_aware_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("signal timestamps must include timezone")
        return value


class SignalCaseOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    status: OperationStatus


class SignalCaseView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_key: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=96),
    ]
    object_type: ObjectType
    object_id: ObjectId
    current_signal: OperationalSignal
    current_operation: SignalCaseOperation | None
    history_count: Annotated[int, Field(ge=0)]
    lineage: Annotated[tuple[OperationalSignal, ...], Field(min_length=1)]


SignalAssessment = ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment


def build_signal_draft(
    assessment: SignalAssessment,
    detected_at: datetime,
) -> SignalDraft | None:
    if isinstance(assessment, ReplenishmentAssessment):
        if not assessment.replenishment_required:
            return None
        return SignalDraft(
            signal_type=SignalType.INVENTORY_SHORTAGE,
            object_type=ObjectType.INVENTORY,
            object_id=assessment.sku,
            source="demo_watchlist.v1",
            severity=SignalSeverity.MEDIUM,
            reason_code="inventory_below_reorder_point",
            facts_hash=assessment.decision_facts_hash,
            facts={
                "available_quantity": assessment.available_quantity,
                "recommended_quantity": assessment.recommended_quantity,
                "reorder_point": assessment.reorder_point,
                "target_stock": assessment.target_stock,
            },
            detected_at=detected_at,
        )

    if isinstance(assessment, MaintenanceAssessment):
        if not assessment.maintenance_required or assessment.reason is None:
            return None
        priority = assessment.priority
        severity = (
            SignalSeverity.HIGH
            if priority in {MaintenancePriority.HIGH, MaintenancePriority.URGENT}
            else SignalSeverity.MEDIUM
        )
        return SignalDraft(
            signal_type=SignalType.EQUIPMENT_ATTENTION,
            object_type=ObjectType.EQUIPMENT,
            object_id=assessment.equipment_id,
            source="demo_watchlist.v1",
            severity=severity,
            reason_code=f"equipment_{assessment.reason}",
            facts_hash=assessment.decision_facts_hash,
            facts={
                "alert_code": assessment.alert_code,
                "heartbeat_age_seconds": assessment.heartbeat_age_seconds,
                "priority": priority.value if priority is not None else None,
                "reason": assessment.reason,
                "state": assessment.state.value,
            },
            detected_at=detected_at,
        )

    if not assessment.recovery_required or assessment.reason is None:
        return None
    return SignalDraft(
        signal_type=SignalType.TASK_BLOCKED,
        object_type=ObjectType.TASK,
        object_id=assessment.task_id,
        source="demo_watchlist.v1",
        severity=SignalSeverity.MEDIUM,
        reason_code=f"task_{assessment.reason}",
        facts_hash=assessment.decision_facts_hash,
        facts={
            "blocker_code": assessment.blocker_code,
            "reason": assessment.reason,
            "recovery_action": assessment.recovery_action,
            "retry_count": assessment.retry_count,
            "state": assessment.state.value,
        },
        detected_at=detected_at,
    )


def derive_signal_dedup_key(signal: SignalDraft) -> str:
    return f"signal:v1:{signal.signal_type.value}:{signal.object_id}:{signal.facts_hash}"


def derive_signal_retry_dedup_key(predecessor_signal_id: UUID) -> str:
    return f"signal:retry:v1:{predecessor_signal_id}"


def signal_status_for_operation_terminal(
    operation_status: OperationStatus,
) -> SignalStatus | None:
    if operation_status in {OperationStatus.COMPLETED, OperationStatus.REJECTED}:
        return SignalStatus.RESOLVED
    if operation_status in {
        OperationStatus.ABORTED,
        OperationStatus.EXPIRED,
        OperationStatus.FAILED,
    }:
        return SignalStatus.ATTENTION_REQUIRED
    return None
