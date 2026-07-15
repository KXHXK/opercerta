from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.approvals import (
    ApprovalCommand,
    ApprovalDecision,
    ApprovalRecord,
)
from opercerta.domain.errors import ApprovalAlreadyDecided, OperationNotFound

OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")
APPROVAL_ID = UUID("00000000-0000-4000-8000-000000000002")


def valid_command_data() -> dict[str, object]:
    return {
        "operation_id": OPERATION_ID,
        "approver_id": "approver-1",
        "decision": ApprovalDecision.APPROVED,
        "reason": "synthetic approval reason",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approver_id", "   "),
        ("approver_id", "a" * 129),
        ("decision", "unknown"),
        ("reason", "   "),
        ("reason", "r" * 1_001),
    ],
)
def test_approval_command_rejects_invalid_fields(field: str, value: object) -> None:
    data = valid_command_data()
    data[field] = value

    with pytest.raises(ValidationError):
        ApprovalCommand.model_validate(data)


def test_approval_command_rejects_extra_fields() -> None:
    data = valid_command_data()
    data["role"] = "approver"

    with pytest.raises(ValidationError):
        ApprovalCommand.model_validate(data)


def test_approval_command_strips_human_text() -> None:
    command = ApprovalCommand(
        operation_id=OPERATION_ID,
        approver_id="  approver-1  ",
        decision=ApprovalDecision.REJECTED,
        reason="  synthetic rejection reason  ",
    )

    assert command.approver_id == "approver-1"
    assert command.reason == "synthetic rejection reason"


def test_approval_command_is_immutable() -> None:
    command = ApprovalCommand.model_validate(valid_command_data())

    with pytest.raises(ValidationError, match="Instance is frozen"):
        command.reason = "changed after validation"


def test_approval_record_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValidationError, match="created_at must include timezone"):
        ApprovalRecord(
            id=APPROVAL_ID,
            **valid_command_data(),
            created_at=datetime(2026, 7, 15, 12, 0),
        )


def test_approval_errors_expose_stable_codes() -> None:
    not_found = OperationNotFound(OPERATION_ID)
    conflict = ApprovalAlreadyDecided(OPERATION_ID)

    assert not_found.code == "operation_not_found"
    assert not_found.operation_id == OPERATION_ID
    assert conflict.code == "approval_already_decided"
    assert conflict.operation_id == OPERATION_ID
