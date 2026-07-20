from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictInt, StringConstraints, model_validator

from opercerta.api.auth import DemoAccount
from opercerta.domain.approvals import (
    ApprovalDecision,
    ApprovalReason,
)
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.maintenance import MaintenanceAssessment, MaintenancePlan
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.replenishment import (
    ApprovalBinding,
    Digest,
    OperationError,
    OperationResult,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    Version,
)
from opercerta.domain.scenarios import ApprovalBinding as ScenarioApprovalBinding
from opercerta.domain.task_recovery import TaskRecoveryAssessment, TaskRecoveryPlan
from opercerta.domain.work_orders import WorkOrderRecord

ErrorCode = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
]


class OperationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    status: OperationStatus
    created_at: datetime


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ApprovalDecision
    reason: ApprovalReason
    expected_binding: ScenarioApprovalBinding | None = None
    expected_inventory_evidence_id: UUID | None = None
    expected_policy_evidence_id: UUID | None = None
    expected_rule_version: Version | None = None
    expected_decision_facts_hash: Digest | None = None
    expected_plan_hash: Digest | None = None
    expected_recommended_quantity: StrictInt | None = None

    @model_validator(mode="after")
    def require_one_binding_shape(self) -> "ApprovalRequest":
        legacy = (
            self.expected_inventory_evidence_id,
            self.expected_policy_evidence_id,
            self.expected_rule_version,
            self.expected_decision_facts_hash,
            self.expected_plan_hash,
            self.expected_recommended_quantity,
        )
        if self.expected_binding is not None:
            if any(value is not None for value in legacy):
                raise ValueError("use either expected_binding or legacy inventory fields")
        elif not all(value is not None for value in legacy):
            raise ValueError("approval binding is required")
        return self

    def approval_binding(self) -> ScenarioApprovalBinding:
        if self.expected_binding is not None:
            return self.expected_binding
        return ScenarioApprovalBinding.model_validate(
            ApprovalBinding(
                inventory_evidence_id=self.expected_inventory_evidence_id,
                policy_evidence_id=self.expected_policy_evidence_id,
                rule_version=self.expected_rule_version,
                decision_facts_hash=self.expected_decision_facts_hash,
                plan_hash=self.expected_plan_hash,
                recommended_quantity=self.expected_recommended_quantity,
            )
        )


class DemoTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account: DemoAccount


class DemoTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    approver_id: str
    decision: ApprovalDecision
    reason: str
    created_at: datetime


class OperationDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    status: OperationStatus
    request: OperationRequest
    evidence: tuple[dict[str, JsonValue], ...]
    assessment: ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment | None
    plan: ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan | None
    approval_binding: ScenarioApprovalBinding | None
    approval: ApprovalResponse | None
    work_order: WorkOrderRecord | None
    result: OperationResult | None
    error: OperationError | None
    last_audit_sequence: int


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ErrorCode
    message: str
