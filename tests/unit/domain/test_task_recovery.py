from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from opercerta.domain.errors import TaskRecoveryOutOfPolicy
from opercerta.domain.replenishment import ModelPlanExplanation
from opercerta.domain.scenarios import ScenarioKind, TaskRecoveryParameters
from opercerta.domain.task_recovery import (
    TaskEvidence,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPolicyEvidence,
    assess_task_recovery,
    build_task_recovery_approval_binding,
    build_task_recovery_plan,
)

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def bundle(
    *,
    state: str = "blocked",
    due_at: datetime = NOW + timedelta(minutes=10),
    blocker_code: str | None = "UPSTREAM_TIMEOUT",
    retry_count: int = 1,
) -> TaskRecoveryEvidenceBundle:
    return TaskRecoveryEvidenceBundle(
        task=TaskEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000001"),
            task_id="TASK-SYNC-001",
            state=state,
            due_at=due_at,
            last_progress_at=NOW - timedelta(minutes=5),
            blocker_code=blocker_code,
            retry_count=retry_count,
            captured_at=NOW,
            source_version="task-seed-v1",
        ),
        policy=TaskRecoveryPolicyEvidence(
            evidence_id=UUID("40000000-0000-4000-8000-000000000002"),
            action="recover_task",
            task_id="TASK-SYNC-001",
            blocked_states=("blocked",),
            overdue_grace_seconds=300,
            maximum_retry_count=3,
            recovery_action="manual_requeue",
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="task-recovery-v1",
            captured_at=NOW,
        ),
    )


def test_task_is_not_overdue_at_exact_grace_boundary() -> None:
    assessment = assess_task_recovery(
        bundle(
            state="running",
            blocker_code=None,
            due_at=NOW - timedelta(seconds=300),
        ),
        NOW,
    )

    assert assessment.recovery_required is False


def test_task_is_overdue_after_grace_boundary() -> None:
    assessment = assess_task_recovery(
        bundle(
            state="running",
            blocker_code=None,
            due_at=NOW - timedelta(seconds=301),
        ),
        NOW,
    )

    assert assessment.recovery_required is True
    assert assessment.reason == "overdue"


def test_blocked_task_over_retry_cap_fails_closed() -> None:
    with pytest.raises(TaskRecoveryOutOfPolicy, match="task_recovery_out_of_policy"):
        assess_task_recovery(bundle(retry_count=4), NOW)


def test_completed_task_never_requires_recovery() -> None:
    assessment = assess_task_recovery(
        bundle(
            state="completed",
            blocker_code=None,
            due_at=NOW - timedelta(days=1),
        ),
        NOW,
    )

    assert assessment.recovery_required is False


def test_recovery_plan_and_binding_cover_blocker_and_retry_facts() -> None:
    evidence = bundle()
    assessment = assess_task_recovery(evidence, NOW)
    plan = build_task_recovery_plan(
        assessment,
        ModelPlanExplanation(
            summary="为阻塞任务创建人工重排工单。",
            rationale="阻塞状态和重试次数符合版本化恢复策略。",
        ),
        evidence.policy,
    )
    binding = build_task_recovery_approval_binding(evidence, plan)

    assert binding.scenario is ScenarioKind.TASK
    assert binding.parameters == TaskRecoveryParameters(recovery_action="manual_requeue")
    assert binding.plan_hash == plan.plan_hash
