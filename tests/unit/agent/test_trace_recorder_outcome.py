from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from opercerta.agent.trace_recorder import TraceRecorder
from opercerta.domain.agent_trace import (
    AgentRunRecord,
    AgentRunStatus,
    AgentTraceAppendResult,
    AgentTraceCitationRecord,
    AgentTraceEventInput,
    AgentTraceEventRecord,
    AgentTraceSnapshot,
)
from opercerta.infrastructure.db.agent_trace_repository import AgentTraceRepository

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


class InMemoryTraceRepository(AgentTraceRepository):
    def __init__(self, operation_id: UUID) -> None:
        self.run = AgentRunRecord(
            id=uuid4(),
            operation_id=operation_id,
            run_key="primary",
            scenario="inventory",
            status=AgentRunStatus.AWAITING_HUMAN,
            model_mode="mock",
            initiated_by="demo.operator",
            next_sequence=0,
            started_at=NOW,
            ended_at=None,
        )
        self.events: list[AgentTraceEventRecord] = []

    async def load_snapshot(self, operation_id: UUID) -> AgentTraceSnapshot:
        assert operation_id == self.run.operation_id
        return AgentTraceSnapshot(run=self.run, events=tuple(self.events))

    async def append_event(
        self,
        run_id: UUID,
        command: AgentTraceEventInput,
    ) -> AgentTraceAppendResult:
        assert run_id == self.run.id
        existing = next(
            (event for event in self.events if event.semantic_key == command.semantic_key),
            None,
        )
        if existing is not None:
            return AgentTraceAppendResult(event=existing, replayed=True)
        event_id = uuid4()
        event = AgentTraceEventRecord(
            id=event_id,
            run_id=run_id,
            sequence=len(self.events) + 1,
            semantic_key=command.semantic_key,
            event_type=command.event_type,
            actor_type=command.actor_type,
            node=command.node,
            status=command.status,
            safe_input=command.safe_input,
            safe_output=command.safe_output,
            prompt_ref=command.prompt_ref,
            tool_ref=command.tool_ref,
            error_code=command.error_code,
            citations=tuple(
                AgentTraceCitationRecord(
                    id=uuid4(),
                    event_id=event_id,
                    **citation.model_dump(),
                )
                for citation in command.citations
            ),
            started_at=command.started_at,
            ended_at=command.ended_at,
        )
        self.events.append(event)
        self.run = self.run.model_copy(update={"next_sequence": len(self.events)})
        return AgentTraceAppendResult(event=event, replayed=False)

    async def finish_run(
        self,
        run_id: UUID,
        status: AgentRunStatus,
        ended_at: datetime,
    ) -> None:
        assert run_id == self.run.id
        self.run = self.run.model_copy(
            update={
                "status": status,
                "ended_at": None if status is AgentRunStatus.RUNNING else ended_at,
            }
        )

    async def load_run(self, run_id: UUID) -> AgentRunRecord:
        assert run_id == self.run.id
        return self.run


@pytest.mark.asyncio
async def test_projects_verifier_and_binding_guardrail_before_execution() -> None:
    operation_id = uuid4()
    repository = InMemoryTraceRepository(operation_id)
    recorder = TraceRecorder(repository, clock=lambda: NOW, model_mode="mock")

    run = await recorder.capture_operation_outcome(
        operation_id,
        status="completed",
        approval_cycle=1,
        approval={"id": str(uuid4()), "approver_id": "demo.approver", "decision": "approved"},
        verification={"decision": "proceed"},
        verification_route="proceed",
        work_order={"id": str(uuid4())},
        result={"outcome": "work_order_completed"},
        error_code=None,
    )

    assert run.status is AgentRunStatus.COMPLETED
    assert [event.node for event in repository.events] == [
        "approval_decision",
        "verify_current_facts",
        "verify_approval_binding",
        "execute_controlled_action",
        "operation_terminal",
    ]
    assert repository.events[1].safe_output == {
        "decision": "proceed",
        "route": "proceed",
        "summary": "批准后已绕过缓存重新取证并完成 Verifier 复核。",
    }
    assert repository.events[1].prompt_ref == "verifier:v1"
    assert repository.events[2].safe_output["binding_valid"] is True


@pytest.mark.asyncio
async def test_expired_approval_is_a_completed_safe_business_terminal() -> None:
    operation_id = uuid4()
    repository = InMemoryTraceRepository(operation_id)
    recorder = TraceRecorder(repository, clock=lambda: NOW, model_mode="mock")

    run = await recorder.capture_operation_outcome(
        operation_id,
        status="expired",
        approval_cycle=1,
        approval=None,
        verification=None,
        verification_route=None,
        work_order=None,
        result=None,
        error_code="approval_expired",
    )

    assert run.status is AgentRunStatus.COMPLETED
    assert repository.events[-1].node == "operation_terminal"
    assert repository.events[-1].safe_output == {"operation_status": "expired"}
    assert repository.events[-1].error_code == "approval_expired"


@pytest.mark.asyncio
async def test_reapproval_trace_keeps_verification_on_the_previous_approval_cycle() -> None:
    operation_id = uuid4()
    repository = InMemoryTraceRepository(operation_id)
    recorder = TraceRecorder(repository, clock=lambda: NOW, model_mode="mock")

    run = await recorder.capture_operation_outcome(
        operation_id,
        status="needs_reapproval",
        approval_cycle=2,
        approval=None,
        verification={"decision": "escalate"},
        verification_route="reapproval",
        work_order=None,
        result=None,
        error_code=None,
    )

    assert run.status is AgentRunStatus.AWAITING_HUMAN
    assert [event.semantic_key for event in repository.events] == [
        "model:verification:1",
        "guardrail:binding_verification:1",
        "human:approval_requested:2",
    ]
    assert repository.events[0].safe_input == {"approval_cycle": 1}
    assert repository.events[-1].safe_input == {"approval_cycle": 2}
