from dataclasses import dataclass
from enum import StrEnum

from opercerta.domain.errors import InvalidRecoveryFacts


class OperationStatus(StrEnum):
    RECEIVED = "received"
    GATHERING_EVIDENCE = "gathering_evidence"
    PLANNING = "planning"
    VALIDATING = "validating"
    REPORTING = "reporting"
    AWAITING_APPROVAL = "awaiting_approval"
    NEEDS_REAPPROVAL = "needs_reapproval"
    RESUMING = "resuming"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ABORTED = "aborted"
    EXPIRED = "expired"
    FAILED = "failed"


class CheckpointPhase(StrEnum):
    MISSING = "missing"
    INTERRUPTED = "interrupted"
    RUNNABLE = "runnable"


class RecoveryAction(StrEnum):
    REBUILD_FROM_BUSINESS_FACTS = "rebuild_from_business_facts"
    KEEP_WAITING = "keep_waiting"
    RESUME_DECISION = "resume_decision"
    REPLAY_IDEMPOTENT_EXECUTION = "replay_idempotent_execution"
    VERIFY_EXISTING_WORK_ORDER = "verify_existing_work_order"
    CONTINUE_CHECKPOINT = "continue_checkpoint"
    NO_OP = "no_op"


TERMINAL_STATUSES = frozenset(
    {
        OperationStatus.COMPLETED,
        OperationStatus.REJECTED,
        OperationStatus.ABORTED,
        OperationStatus.EXPIRED,
        OperationStatus.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class RecoveryFacts:
    status: OperationStatus
    checkpoint: CheckpointPhase
    has_approval: bool
    has_work_order: bool

    def __post_init__(self) -> None:
        if self.has_work_order and not self.has_approval:
            raise InvalidRecoveryFacts("work_order_without_approval")
        if self.status is OperationStatus.RECEIVED and self.has_approval:
            raise InvalidRecoveryFacts("approval_without_approval_state")


def choose_recovery_action(facts: RecoveryFacts) -> RecoveryAction:
    if facts.status in TERMINAL_STATUSES:
        return RecoveryAction.NO_OP
    if facts.checkpoint is CheckpointPhase.MISSING:
        return RecoveryAction.REBUILD_FROM_BUSINESS_FACTS
    if facts.checkpoint is CheckpointPhase.INTERRUPTED:
        return RecoveryAction.RESUME_DECISION if facts.has_approval else RecoveryAction.KEEP_WAITING
    if facts.has_work_order:
        return RecoveryAction.VERIFY_EXISTING_WORK_ORDER
    if facts.status in {
        OperationStatus.RESUMING,
        OperationStatus.EXECUTING,
        OperationStatus.VERIFYING,
    }:
        return RecoveryAction.REPLAY_IDEMPOTENT_EXECUTION
    return RecoveryAction.CONTINUE_CHECKPOINT
