from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    PositiveInt,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from opercerta.domain.errors import EvidenceExpired, TaskRecoveryOutOfPolicy
from opercerta.domain.replenishment import Digest, ModelPlanExplanation, SafeText, Version
from opercerta.domain.scenarios import (
    ApprovalBinding,
    SafeCode,
    ScenarioKind,
    TaskRecoveryParameters,
)
from opercerta.domain.work_orders import hash_payload

TaskId = Annotated[
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


class TaskState(StrEnum):
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class TaskEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    task_id: TaskId
    state: TaskState
    due_at: datetime
    last_progress_at: datetime
    blocker_code: SafeCode | None
    retry_count: StrictInt
    captured_at: datetime
    source_version: Version

    @field_validator("due_at", "last_progress_at", "captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("retry_count")
    @classmethod
    def require_non_negative_retry(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry count must be non-negative")
        return value

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if (self.state is TaskState.BLOCKED) != (self.blocker_code is not None):
            raise ValueError("only blocked tasks may contain a blocker code")
        if self.last_progress_at > self.captured_at:
            raise ValueError("last progress cannot be later than capture time")
        return self


class TaskRecoveryPolicyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    action: Literal["recover_task"]
    task_id: TaskId
    blocked_states: tuple[TaskState, ...]
    overdue_grace_seconds: StrictInt
    maximum_retry_count: StrictInt
    recovery_action: Literal["manual_requeue"]
    evidence_ttl_seconds: PositiveInt
    approval_required: Literal[True]
    rule_version: Version
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("overdue_grace_seconds", "maximum_retry_count")
    @classmethod
    def require_non_negative_integer(cls, value: int) -> int:
        if value < 0:
            raise ValueError("task recovery limits must be non-negative")
        return value

    @field_validator("blocked_states")
    @classmethod
    def require_safe_blocked_states(cls, value: tuple[TaskState, ...]) -> tuple[TaskState, ...]:
        if not value or len(value) != len(set(value)) or TaskState.COMPLETED in value:
            raise ValueError("blocked states must be non-empty, unique and non-terminal")
        return value


class TaskRecoveryEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: TaskEvidence
    policy: TaskRecoveryPolicyEvidence

    @model_validator(mode="after")
    def require_matching_task(self) -> Self:
        if self.task.task_id != self.policy.task_id:
            raise ValueError("task and policy task ID must match")
        if self.task.evidence_id == self.policy.evidence_id:
            raise ValueError("task and policy evidence IDs must differ")
        return self


class TaskRecoveryAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: TaskId
    state: TaskState
    blocker_code: SafeCode | None
    retry_count: StrictInt
    recovery_required: bool
    reason: Literal["blocked", "overdue"] | None
    recovery_action: Literal["manual_requeue"] | None
    decision_facts_hash: Digest


class TaskRecoveryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["recover_task"]
    task_id: TaskId
    blocker_code: SafeCode | None
    retry_count: StrictInt
    recovery_action: Literal["manual_requeue"]
    decision_facts_hash: Digest
    rule_version: Version
    summary: SafeText
    rationale: SafeText
    plan_hash: Digest


class TaskRecoveryWorkOrderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["task_recovery"] = "task_recovery"
    task_id: TaskId
    blocker_code: SafeCode | None
    retry_count: StrictInt
    recovery_action: Literal["manual_requeue"]
    approved_plan_hash: Digest


def assess_task_recovery(
    bundle: TaskRecoveryEvidenceBundle,
    now: datetime,
) -> TaskRecoveryAssessment:
    _require_timezone(now)
    ttl = timedelta(seconds=bundle.policy.evidence_ttl_seconds)
    if now >= bundle.task.captured_at + ttl or now >= bundle.policy.captured_at + ttl:
        raise EvidenceExpired

    blocked = bundle.task.state in bundle.policy.blocked_states
    overdue = bundle.task.state is not TaskState.COMPLETED and now > bundle.task.due_at + timedelta(
        seconds=bundle.policy.overdue_grace_seconds
    )
    recovery_required = blocked or overdue
    if recovery_required and bundle.task.retry_count > bundle.policy.maximum_retry_count:
        raise TaskRecoveryOutOfPolicy
    reason: Literal["blocked", "overdue"] | None = (
        "blocked" if blocked else "overdue" if overdue else None
    )
    recovery_action: Literal["manual_requeue"] | None = (
        bundle.policy.recovery_action if recovery_required else None
    )
    facts: dict[str, JsonValue] = {
        "blocker_code": bundle.task.blocker_code,
        "reason": reason,
        "recovery_action": recovery_action,
        "recovery_required": recovery_required,
        "retry_count": bundle.task.retry_count,
        "state": bundle.task.state.value,
        "task_id": bundle.task.task_id,
    }
    return TaskRecoveryAssessment(
        task_id=bundle.task.task_id,
        state=bundle.task.state,
        blocker_code=bundle.task.blocker_code,
        retry_count=bundle.task.retry_count,
        recovery_required=recovery_required,
        reason=reason,
        recovery_action=recovery_action,
        decision_facts_hash=hash_payload(facts),
    )


def build_task_recovery_plan(
    assessment: TaskRecoveryAssessment,
    explanation: ModelPlanExplanation,
    policy: TaskRecoveryPolicyEvidence,
) -> TaskRecoveryPlan:
    if not assessment.recovery_required or assessment.recovery_action is None:
        raise ValueError("task recovery plan requires a recovery assessment")
    facts: dict[str, JsonValue] = {
        "action": "recover_task",
        "blocker_code": assessment.blocker_code,
        "decision_facts_hash": assessment.decision_facts_hash,
        "recovery_action": assessment.recovery_action,
        "retry_count": assessment.retry_count,
        "rule_version": policy.rule_version,
        "task_id": assessment.task_id,
    }
    return TaskRecoveryPlan(
        action="recover_task",
        task_id=assessment.task_id,
        blocker_code=assessment.blocker_code,
        retry_count=assessment.retry_count,
        recovery_action=assessment.recovery_action,
        decision_facts_hash=assessment.decision_facts_hash,
        rule_version=policy.rule_version,
        summary=explanation.summary,
        rationale=explanation.rationale,
        plan_hash=hash_payload(facts),
    )


def build_task_recovery_approval_binding(
    bundle: TaskRecoveryEvidenceBundle,
    plan: TaskRecoveryPlan,
) -> ApprovalBinding:
    return ApprovalBinding(
        scenario=ScenarioKind.TASK,
        subject_evidence_id=bundle.task.evidence_id,
        policy_evidence_id=bundle.policy.evidence_id,
        rule_version=plan.rule_version,
        decision_facts_hash=plan.decision_facts_hash,
        plan_hash=plan.plan_hash,
        parameters=TaskRecoveryParameters(recovery_action=plan.recovery_action),
    )
