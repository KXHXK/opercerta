from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import ApprovalResume, OperationSnapshot

OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")


def valid_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request": {"summary": "synthetic"},
        "risk": {"level": "high"},
        "plan": {"step": "create_work_order"},
        "work_order_payload": {"quantity": 4},
    }


def test_snapshot_accepts_complete_plain_json() -> None:
    snapshot = OperationSnapshot.model_validate(valid_snapshot())

    assert snapshot.schema_version == 1
    assert snapshot.work_order_payload == {"quantity": 4}


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": 2},
        {"request": []},
        {"risk": {1: "value"}},
        {"plan": {"steps": ("one",)}},
        {"work_order_payload": {"value": object()}},
        {"work_order_payload": {"value": float("nan")}},
        {"work_order_payload": {"value": float("inf")}},
        {"work_order_payload": {"value": float("-inf")}},
        {"extra": True},
    ],
)
def test_snapshot_rejects_invalid_or_non_json_input(mutation: dict[str, object]) -> None:
    data = valid_snapshot()
    data.update(mutation)

    with pytest.raises(ValidationError):
        OperationSnapshot.model_validate(data)


@pytest.mark.parametrize("missing", ["request", "risk", "plan", "work_order_payload"])
def test_snapshot_never_fabricates_missing_fields(missing: str) -> None:
    data = valid_snapshot()
    data.pop(missing)

    with pytest.raises(ValidationError):
        OperationSnapshot.model_validate(data)


def test_snapshot_and_resume_fields_cannot_be_reassigned() -> None:
    snapshot = OperationSnapshot.model_validate(valid_snapshot())
    with pytest.raises(ValidationError):
        snapshot.schema_version = 1

    resume = ApprovalResume(
        approval_id=OPERATION_ID,
        decision=ApprovalDecision.APPROVED,
    )
    with pytest.raises(ValidationError):
        resume.decision = ApprovalDecision.REJECTED


@pytest.mark.parametrize(
    "data",
    [
        {"approval_id": OPERATION_ID},
        {"decision": "approved"},
        {"approval_id": "not-a-uuid", "decision": "approved"},
        {"approval_id": OPERATION_ID, "decision": "unknown"},
        {"approval_id": OPERATION_ID, "decision": "approved", "extra": True},
    ],
)
def test_approval_resume_rejects_incomplete_or_invalid_data(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ApprovalResume.model_validate(data)


def test_errors_keep_only_stable_safe_fields() -> None:
    invalid = InvalidOperationSnapshot(
        OPERATION_ID,
        "request_payload_failed_validation",
    )
    transition = OperationTransitionConflict(
        OPERATION_ID,
        "received",
        "completed",
    )
    conflict = RecoveryStateConflict(OPERATION_ID, "thread_id_mismatch")

    assert (invalid.code, str(invalid)) == (
        "invalid_operation_snapshot",
        invalid.code,
    )
    assert invalid.operation_id == OPERATION_ID
    assert invalid.reason == "request_payload_failed_validation"
    assert transition.code == "operation_transition_conflict"
    assert transition.operation_id == OPERATION_ID
    assert transition.current_status == "received"
    assert transition.target_status == "completed"
    assert conflict.code == "recovery_state_conflict"
    assert conflict.operation_id == OPERATION_ID
    assert conflict.reason == "thread_id_mismatch"
