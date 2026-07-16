from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationInfo, field_validator

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.json_values import require_json_object
from opercerta.domain.recovery import OperationStatus


class OperationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    request: dict[str, JsonValue]
    risk: dict[str, JsonValue]
    plan: dict[str, JsonValue]
    work_order_payload: dict[str, JsonValue]

    @field_validator("request", "risk", "plan", "work_order_payload", mode="before")
    @classmethod
    def require_plain_json_object(cls, value: object, info: ValidationInfo) -> object:
        if info.field_name is None:
            raise ValueError("snapshot field name is unavailable")
        return require_json_object(value, info.field_name)


class ApprovalResume(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: UUID
    decision: ApprovalDecision


@dataclass(frozen=True, slots=True)
class RecoveryView:
    operation_id: UUID
    thread_id: str
    status: OperationStatus
    snapshot: OperationSnapshot
    approval_id: UUID | None
    decision: ApprovalDecision | None
    work_order_id: UUID | None
    payload_hash: str | None


@dataclass(frozen=True, slots=True)
class OperationTransitionResult:
    operation_id: UUID
    status: OperationStatus
    changed: bool
    audit_sequence: int | None
