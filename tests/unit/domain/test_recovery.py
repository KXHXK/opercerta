from importlib import import_module

import pytest


def recovery_module():
    try:
        return import_module("opercerta.domain.recovery")
    except ImportError as exc:
        pytest.fail(f"recovery module is unavailable: {exc}", pytrace=False)


def invalid_recovery_facts_type():
    try:
        return import_module("opercerta.domain.errors").InvalidRecoveryFacts
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"InvalidRecoveryFacts is unavailable: {exc}", pytrace=False)


@pytest.mark.parametrize(
    ("status", "checkpoint", "has_approval", "has_work_order", "expected"),
    [
        ("received", "missing", False, False, "rebuild_from_business_facts"),
        ("awaiting_approval", "interrupted", False, False, "keep_waiting"),
        ("resuming", "interrupted", True, False, "resume_decision"),
        ("executing", "runnable", True, False, "replay_idempotent_execution"),
        ("verifying", "runnable", True, True, "verify_existing_work_order"),
        ("planning", "runnable", False, False, "continue_checkpoint"),
        ("completed", "runnable", True, True, "no_op"),
        ("rejected", "missing", True, False, "no_op"),
        ("expired", "interrupted", False, False, "no_op"),
        ("failed", "runnable", False, False, "no_op"),
    ],
)
def test_recovery_matrix(
    status: str,
    checkpoint: str,
    has_approval: bool,
    has_work_order: bool,
    expected: str,
) -> None:
    recovery = recovery_module()
    facts = recovery.RecoveryFacts(
        status=recovery.OperationStatus(status),
        checkpoint=recovery.CheckpointPhase(checkpoint),
        has_approval=has_approval,
        has_work_order=has_work_order,
    )

    assert recovery.choose_recovery_action(facts).value == expected


@pytest.mark.parametrize(
    ("status", "has_approval", "has_work_order", "expected_code"),
    [
        ("received", True, False, "approval_without_approval_state"),
        ("executing", False, True, "work_order_without_approval"),
    ],
)
def test_impossible_recovery_facts_are_rejected(
    status: str,
    has_approval: bool,
    has_work_order: bool,
    expected_code: str,
) -> None:
    recovery = recovery_module()
    invalid_recovery_facts = invalid_recovery_facts_type()

    with pytest.raises(invalid_recovery_facts, match=expected_code):
        recovery.RecoveryFacts(
            status=recovery.OperationStatus(status),
            checkpoint=recovery.CheckpointPhase.RUNNABLE,
            has_approval=has_approval,
            has_work_order=has_work_order,
        )
