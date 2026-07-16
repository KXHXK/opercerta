from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictInt, StringConstraints

from opercerta.domain.approvals import (
    ApprovalDecision,
    ApprovalReason,
    ApproverId,
)
from opercerta.domain.contracts import OperationRequest
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

    approver_id: ApproverId
    decision: ApprovalDecision
    reason: ApprovalReason
    expected_inventory_evidence_id: UUID
    expected_policy_evidence_id: UUID
    expected_rule_version: Version
    expected_decision_facts_hash: Digest
    expected_plan_hash: Digest
    expected_recommended_quantity: StrictInt

    def approval_binding(self) -> ApprovalBinding:
        return ApprovalBinding(
            inventory_evidence_id=self.expected_inventory_evidence_id,
            policy_evidence_id=self.expected_policy_evidence_id,
            rule_version=self.expected_rule_version,
            decision_facts_hash=self.expected_decision_facts_hash,
            plan_hash=self.expected_plan_hash,
            recommended_quantity=self.expected_recommended_quantity,
        )


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
    assessment: ReplenishmentAssessment | None
    plan: ReplenishmentPlan | None
    approval_binding: ApprovalBinding | None
    approval: ApprovalResponse | None
    work_order: WorkOrderRecord | None
    result: OperationResult | None
    error: OperationError | None
    last_audit_sequence: int


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ErrorCode
    message: str
