from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import RowMapping, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.agent_trace import (
    AgentRunRecord,
    AgentRunStatus,
    AgentTraceAppendResult,
    AgentTraceCitationRecord,
    AgentTraceEventInput,
    AgentTraceEventRecord,
    AgentTraceSnapshot,
)
from opercerta.domain.errors import OperationNotFound
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.schema import (
    agent_runs,
    agent_trace_citations,
    agent_trace_events,
    operations,
)


class AgentTraceRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def start_run(
        self,
        *,
        operation_id: UUID,
        scenario: ScenarioKind,
        model_mode: str,
        run_key: str,
        started_at: datetime,
    ) -> AgentRunRecord:
        async with self._engine.begin() as connection:
            run_id = (
                await connection.execute(
                    insert(agent_runs)
                    .values(
                        id=uuid4(),
                        operation_id=operation_id,
                        run_key=run_key,
                        scenario=scenario.value,
                        status=AgentRunStatus.RUNNING.value,
                        model_mode=model_mode,
                        initiated_by=None,
                        next_sequence=0,
                        started_at=started_at,
                        ended_at=None,
                    )
                    .on_conflict_do_nothing(constraint="uq_agent_runs_operation_run_key")
                    .returning(agent_runs.c.id)
                )
            ).scalar_one_or_none()
            row = (
                (
                    await connection.execute(
                        select(agent_runs).where(
                            agent_runs.c.id == run_id
                            if run_id is not None
                            else (
                                (agent_runs.c.operation_id == operation_id)
                                & (agent_runs.c.run_key == run_key)
                            )
                        )
                    )
                )
                .mappings()
                .one()
            )
            if row["scenario"] != scenario.value or row["model_mode"] != model_mode:
                raise ValueError("agent run replay contract mismatch")
        return self._run(row)

    async def append_event(
        self,
        run_id: UUID,
        command: AgentTraceEventInput,
    ) -> AgentTraceAppendResult:
        async with self._engine.begin() as connection:
            run = (
                (
                    await connection.execute(
                        select(agent_runs).where(agent_runs.c.id == run_id).with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise OperationNotFound(run_id)
            existing = await self._event_by_semantic_key(
                connection,
                run_id,
                command.semantic_key,
            )
            if existing is not None:
                return AgentTraceAppendResult(
                    event=await self._event_record(connection, existing),
                    replayed=True,
                )
            sequence = int(run["next_sequence"]) + 1
            event_id = uuid4()
            await connection.execute(
                insert(agent_trace_events).values(
                    id=event_id,
                    run_id=run_id,
                    sequence=sequence,
                    semantic_key=command.semantic_key,
                    event_type=command.event_type.value,
                    actor_type=command.actor_type.value,
                    node=command.node,
                    status=command.status.value,
                    safe_input=command.safe_input,
                    safe_output=command.safe_output,
                    prompt_ref=command.prompt_ref,
                    tool_ref=command.tool_ref,
                    error_code=command.error_code,
                    started_at=command.started_at,
                    ended_at=command.ended_at,
                )
            )
            if command.citations:
                await connection.execute(
                    insert(agent_trace_citations),
                    [
                        {
                            "id": uuid4(),
                            "event_id": event_id,
                            "document_id": citation.document_id,
                            "chunk_id": citation.chunk_id,
                            "version": citation.version,
                            "rank": citation.rank,
                            "score": citation.score,
                        }
                        for citation in command.citations
                    ],
                )
            await connection.execute(
                update(agent_runs).where(agent_runs.c.id == run_id).values(next_sequence=sequence)
            )
            created = await self._event_by_semantic_key(
                connection,
                run_id,
                command.semantic_key,
            )
            if created is None:
                raise RuntimeError("agent trace event write was not visible")
            return AgentTraceAppendResult(
                event=await self._event_record(connection, created),
                replayed=False,
            )

    async def finish_run(
        self,
        run_id: UUID,
        status: AgentRunStatus,
        ended_at: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                update(agent_runs)
                .where(agent_runs.c.id == run_id)
                .values(
                    status=status.value,
                    ended_at=(None if status is AgentRunStatus.RUNNING else ended_at),
                )
            )
            if result.rowcount != 1:
                raise OperationNotFound(run_id)

    async def claim_owner(self, operation_id: UUID, subject: str) -> bool:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(agent_runs)
                        .where(
                            agent_runs.c.operation_id == operation_id,
                            agent_runs.c.run_key == "primary",
                        )
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise OperationNotFound(operation_id)
            owner = row["initiated_by"]
            if owner is not None and owner != subject:
                return False
            if owner is None:
                await connection.execute(
                    update(agent_runs)
                    .where(agent_runs.c.id == row["id"])
                    .values(initiated_by=subject)
                )
        return True

    async def owner_for(self, operation_id: UUID) -> str | None:
        async with self._engine.connect() as connection:
            owner = await connection.scalar(
                select(agent_runs.c.initiated_by).where(
                    agent_runs.c.operation_id == operation_id,
                    agent_runs.c.run_key == "primary",
                )
            )
        return cast(str | None, owner)

    async def operation_status(self, operation_id: UUID) -> str:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                select(operations.c.status).where(operations.c.id == operation_id)
            )
        if value is None:
            raise OperationNotFound(operation_id)
        return str(value)

    async def load_run(self, run_id: UUID) -> AgentRunRecord:
        async with self._engine.connect() as connection:
            row = (
                (await connection.execute(select(agent_runs).where(agent_runs.c.id == run_id)))
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OperationNotFound(run_id)
        return self._run(row)

    async def load_snapshot(self, operation_id: UUID) -> AgentTraceSnapshot:
        async with self._engine.connect() as connection:
            run = (
                (
                    await connection.execute(
                        select(agent_runs).where(
                            agent_runs.c.operation_id == operation_id,
                            agent_runs.c.run_key == "primary",
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise OperationNotFound(operation_id)
            rows = (
                (
                    await connection.execute(
                        select(agent_trace_events)
                        .where(agent_trace_events.c.run_id == run["id"])
                        .order_by(agent_trace_events.c.sequence)
                    )
                )
                .mappings()
                .all()
            )
            events = tuple([await self._event_record(connection, row) for row in rows])
        return AgentTraceSnapshot(run=self._run(run), events=events)

    async def _event_by_semantic_key(
        self,
        connection: AsyncConnection,
        run_id: UUID,
        semantic_key: str,
    ) -> RowMapping | None:
        return (
            (
                await connection.execute(
                    select(agent_trace_events).where(
                        agent_trace_events.c.run_id == run_id,
                        agent_trace_events.c.semantic_key == semantic_key,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )

    async def _event_record(
        self,
        connection: AsyncConnection,
        row: RowMapping,
    ) -> AgentTraceEventRecord:
        citation_rows = (
            (
                await connection.execute(
                    select(agent_trace_citations)
                    .where(agent_trace_citations.c.event_id == row["id"])
                    .order_by(agent_trace_citations.c.rank)
                )
            )
            .mappings()
            .all()
        )
        return AgentTraceEventRecord(
            id=row["id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            semantic_key=row["semantic_key"],
            event_type=row["event_type"],
            actor_type=row["actor_type"],
            node=row["node"],
            status=row["status"],
            safe_input=cast(dict[str, JsonValue], row["safe_input"]),
            safe_output=cast(dict[str, JsonValue], row["safe_output"]),
            prompt_ref=row["prompt_ref"],
            tool_ref=row["tool_ref"],
            error_code=row["error_code"],
            citations=tuple(
                AgentTraceCitationRecord(
                    id=citation["id"],
                    event_id=citation["event_id"],
                    document_id=citation["document_id"],
                    chunk_id=citation["chunk_id"],
                    version=citation["version"],
                    rank=citation["rank"],
                    score=float(citation["score"]),
                )
                for citation in citation_rows
            ),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    def _run(self, row: RowMapping) -> AgentRunRecord:
        return AgentRunRecord(
            id=row["id"],
            operation_id=row["operation_id"],
            run_key=row["run_key"],
            scenario=row["scenario"],
            status=row["status"],
            model_mode=row["model_mode"],
            initiated_by=row["initiated_by"],
            next_sequence=row["next_sequence"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
