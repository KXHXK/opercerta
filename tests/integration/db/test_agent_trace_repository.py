import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.agent_trace import (
    AgentRunStatus,
    AgentTraceActor,
    AgentTraceCitationInput,
    AgentTraceEventInput,
    AgentTraceEventType,
    AgentTraceStatus,
)
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.agent_trace_repository import AgentTraceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import agent_trace_citations, agent_trace_events, operations

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_trace_events_are_sequenced_and_semantic_replay_is_idempotent(
    engine: AsyncEngine,
) -> None:
    operation_id = await OperationRepository(engine).create(
        OperationRequest(
            message="为 SKU-LOW-001 生成补货工单",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
        )
    )
    repository = AgentTraceRepository(engine)
    document_id = uuid4()
    chunk_id = uuid4()
    command = AgentTraceEventInput(
        semantic_key="tool:inventory.get_snapshot:call-r0-s0",
        event_type=AgentTraceEventType.TOOL,
        actor_type=AgentTraceActor.TOOL,
        node="execute_read_tools",
        status=AgentTraceStatus.COMPLETED,
        safe_input={"tool_name": "inventory.get_snapshot", "object_id": "SKU-LOW-001"},
        safe_output={"summary": "库存事实已验证。"},
        tool_ref="inventory.get_snapshot",
        citations=(
            AgentTraceCitationInput(
                document_id=document_id,
                chunk_id=chunk_id,
                version="1.0.0",
                rank=1,
                score=0.75,
            ),
        ),
        started_at=NOW,
        ended_at=NOW,
    )

    try:
        run = await repository.start_run(
            operation_id=operation_id,
            scenario=ScenarioKind.INVENTORY,
            model_mode="mock",
            run_key="primary",
            started_at=NOW,
        )
        results = await asyncio.gather(
            *[repository.append_event(run.id, command) for _ in range(10)]
        )
        second = await repository.append_event(
            run.id,
            command.model_copy(
                update={
                    "semantic_key": "rule:policy_guard",
                    "event_type": AgentTraceEventType.RULE,
                    "actor_type": AgentTraceActor.POLICY,
                    "node": "calculate_policy_facts",
                    "tool_ref": None,
                    "citations": (),
                }
            ),
        )
        await repository.finish_run(run.id, AgentRunStatus.AWAITING_HUMAN, NOW)
        snapshot = await repository.load_snapshot(operation_id)

        assert len({result.event.id for result in results}) == 1
        assert sum(result.replayed for result in results) == 9
        assert [event.sequence for event in snapshot.events] == [1, 2]
        assert second.event.sequence == 2
        assert snapshot.run.status is AgentRunStatus.AWAITING_HUMAN
        assert snapshot.events[0].citations[0].chunk_id == chunk_id
        async with engine.connect() as connection:
            assert (
                int(
                    await connection.scalar(select(func.count()).select_from(agent_trace_events))
                    or 0
                )
                == 2
            )
            assert (
                int(
                    await connection.scalar(select(func.count()).select_from(agent_trace_citations))
                    or 0
                )
                == 1
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_claim_owner_is_idempotent_but_cannot_be_reassigned(engine: AsyncEngine) -> None:
    operation_id = await OperationRepository(engine).create(
        OperationRequest(
            message="查询设备状态",
            requested_action=ActionType.QUERY,
            object_type=ObjectType.EQUIPMENT,
            object_id="EQ-PUMP-001",
        )
    )
    repository = AgentTraceRepository(engine)
    try:
        await repository.start_run(
            operation_id=operation_id,
            scenario=ScenarioKind.EQUIPMENT,
            model_mode="mock",
            run_key="primary",
            started_at=NOW,
        )
        assert await repository.claim_owner(operation_id, "demo.operator")
        assert await repository.claim_owner(operation_id, "demo.operator")
        assert not await repository.claim_owner(operation_id, "other.operator")
        assert await repository.owner_for(operation_id) == "demo.operator"
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
