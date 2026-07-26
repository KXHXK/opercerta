from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.recovery import RecoveryAction
from opercerta.workflow.controlled_agent_root_recovery import (
    ControlledAgentRootRecoveryCoordinator,
)

OPERATION_ID = UUID("82000000-0000-4000-8000-000000000026")
NOW = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)


class FakeGraph:
    def __init__(self, snapshot: object) -> None:
        self.snapshot = snapshot
        self.invocations: list[object] = []

    async def aget_state(self, config: object) -> object:
        self.config = config
        return self.snapshot

    async def ainvoke(self, value: object, config: object) -> dict[str, object]:
        self.invocations.append(value)
        return {}


class FakeOperations:
    def __init__(self, detail: object) -> None:
        self.detail = detail

    async def load_detail(self, operation_id: UUID) -> object:
        assert operation_id == OPERATION_ID
        return self.detail


def snapshot(*, interrupted: bool) -> object:
    return SimpleNamespace(
        created_at=NOW.isoformat(),
        interrupts=(object(),) if interrupted else (),
        tasks=(),
        values={"operation_id": str(OPERATION_ID)},
        next=("approval_interrupt",) if interrupted else ("model_decide",),
    )


@pytest.mark.asyncio
async def test_awaiting_approval_restart_keeps_the_root_interrupt() -> None:
    graph = FakeGraph(snapshot(interrupted=True))
    detail = SimpleNamespace(
        operation_id=OPERATION_ID,
        thread_id=str(OPERATION_ID),
        status=SimpleNamespace(value="awaiting_approval"),
        approval=None,
    )

    action = await ControlledAgentRootRecoveryCoordinator(
        graph,
        FakeOperations(detail),  # type: ignore[arg-type]
    ).recover(OPERATION_ID)

    assert action is RecoveryAction.KEEP_WAITING
    assert graph.invocations == []


@pytest.mark.asyncio
async def test_persisted_approval_resumes_the_same_interrupted_root() -> None:
    graph = FakeGraph(snapshot(interrupted=True))
    approval_id = uuid4()
    detail = SimpleNamespace(
        operation_id=OPERATION_ID,
        thread_id=str(OPERATION_ID),
        status=SimpleNamespace(value="resuming"),
        approval=SimpleNamespace(
            id=approval_id,
            decision=ApprovalDecision.APPROVED,
        ),
    )

    action = await ControlledAgentRootRecoveryCoordinator(
        graph,
        FakeOperations(detail),  # type: ignore[arg-type]
    ).recover(OPERATION_ID)

    assert action is RecoveryAction.RESUME_DECISION
    assert len(graph.invocations) == 1
