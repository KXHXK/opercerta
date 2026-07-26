from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import SignalNotFound, SignalRetryNotAllowed
from opercerta.domain.recovery import TERMINAL_STATUSES, OperationStatus
from opercerta.domain.signals import (
    OperationalSignal,
    SignalCaseOperation,
    SignalCaseView,
    SignalDraft,
    SignalStatus,
    derive_signal_dedup_key,
    derive_signal_retry_dedup_key,
    signal_status_for_operation_terminal,
)
from opercerta.infrastructure.db.schema import operational_signals, operations


class SignalRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def upsert_detected(self, draft: SignalDraft) -> OperationalSignal:
        dedup_key = derive_signal_dedup_key(draft)
        values = {
            "id": uuid4(),
            "dedup_key": dedup_key,
            "signal_type": draft.signal_type.value,
            "object_type": draft.object_type.value,
            "object_id": draft.object_id,
            "source": draft.source,
            "severity": draft.severity.value,
            "reason_code": draft.reason_code,
            "facts_hash": draft.facts_hash,
            "facts": draft.facts,
            "status": SignalStatus.OPEN.value,
            "predecessor_signal_id": None,
            "detected_at": draft.detected_at,
            "updated_at": draft.detected_at,
        }
        async with self._engine.begin() as connection:
            result = await connection.execute(
                insert(operational_signals)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[operational_signals.c.dedup_key])
                .returning(operational_signals)
            )
            row = result.mappings().one_or_none()
            if row is None:
                row = (
                    (
                        await connection.execute(
                            select(operational_signals).where(
                                operational_signals.c.dedup_key == dedup_key
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
        return self._signal(row)

    async def load(self, signal_id: UUID) -> OperationalSignal:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(operational_signals).where(operational_signals.c.id == signal_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SignalNotFound(signal_id)
        return self._signal(row)

    async def list_active(self, *, limit: int = 50) -> tuple[OperationalSignal, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(operational_signals)
                        .where(
                            operational_signals.c.status.in_(
                                [
                                    SignalStatus.OPEN.value,
                                    SignalStatus.INVESTIGATING.value,
                                    SignalStatus.ATTENTION_REQUIRED.value,
                                ]
                            )
                        )
                        .order_by(operational_signals.c.detected_at.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(self._signal(row) for row in rows)

    async def list_cases(
        self,
        *,
        limit: int = 50,
        object_keys: set[tuple[str, str]] | None = None,
    ) -> tuple[SignalCaseView, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._engine.connect() as connection:
            statement = (
                select(
                    operational_signals,
                    operations.c.status.label("operation_status"),
                )
                .outerjoin(
                    operations,
                    operations.c.id == operational_signals.c.operation_id,
                )
                .order_by(
                    operational_signals.c.detected_at.asc(),
                    operational_signals.c.id.asc(),
                )
            )
            if object_keys:
                statement = statement.where(
                    tuple_(
                        operational_signals.c.object_type,
                        operational_signals.c.object_id,
                    ).in_(object_keys)
                )
            rows = (await connection.execute(statement)).mappings().all()

        grouped: dict[tuple[str, str], list[tuple[OperationalSignal, object]]] = {}
        for row in rows:
            signal = self._signal(row)
            grouped.setdefault((signal.object_type.value, signal.object_id), []).append(
                (signal, row["operation_status"])
            )

        cases: list[SignalCaseView] = []
        for (object_type, object_id), items in grouped.items():
            lineage = self._ordered_lineage([signal for signal, _ in items])
            operation_statuses = {signal.id: status_value for signal, status_value in items}
            # A case advances along one durable successor chain.  An actionable
            # ancestor is no longer current once it already has a successor;
            # retrying that ancestor would merely rediscover the existing child
            # and can never start a new investigation.  The lineage leaf is the
            # only state users may act on, including when that leaf is terminal.
            current = lineage[-1]
            operation_status = operation_statuses[current.id]
            current_operation = (
                SignalCaseOperation(
                    operation_id=current.operation_id,
                    status=str(operation_status),
                )
                if current.operation_id is not None and operation_status is not None
                else None
            )
            cases.append(
                SignalCaseView(
                    case_key=f"{object_type}:{object_id}",
                    object_type=object_type,
                    object_id=object_id,
                    current_signal=current,
                    current_operation=current_operation,
                    history_count=len(lineage) - 1,
                    lineage=lineage,
                )
            )
        cases.sort(key=lambda item: item.current_signal.updated_at, reverse=True)
        return tuple(cases[:limit])

    async def create_successor(
        self,
        predecessor_signal_id: UUID,
        created_at: datetime | None = None,
    ) -> OperationalSignal:
        timestamp = created_at or datetime.now(UTC)
        async with self._engine.begin() as connection:
            predecessor = (
                (
                    await connection.execute(
                        select(operational_signals)
                        .where(operational_signals.c.id == predecessor_signal_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if predecessor is None:
                raise SignalNotFound(predecessor_signal_id)
            if predecessor["status"] != SignalStatus.ATTENTION_REQUIRED.value:
                raise SignalRetryNotAllowed(predecessor_signal_id)

            existing = (
                (
                    await connection.execute(
                        select(operational_signals).where(
                            operational_signals.c.predecessor_signal_id == predecessor_signal_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._signal(existing)

            successor_id = uuid4()
            successor = (
                (
                    await connection.execute(
                        insert(operational_signals)
                        .values(
                            id=successor_id,
                            dedup_key=derive_signal_retry_dedup_key(predecessor_signal_id),
                            signal_type=predecessor["signal_type"],
                            object_type=predecessor["object_type"],
                            object_id=predecessor["object_id"],
                            source=predecessor["source"],
                            severity=predecessor["severity"],
                            reason_code=predecessor["reason_code"],
                            facts_hash=predecessor["facts_hash"],
                            facts=predecessor["facts"],
                            status=SignalStatus.OPEN.value,
                            operation_id=None,
                            predecessor_signal_id=predecessor_signal_id,
                            detected_at=timestamp,
                            updated_at=timestamp,
                            resolved_at=None,
                        )
                        .returning(operational_signals)
                    )
                )
                .mappings()
                .one()
            )
        return self._signal(successor)

    async def reconcile_terminal_links(
        self,
        changed_at: datetime | None = None,
    ) -> int:
        timestamp = changed_at or datetime.now(UTC)
        terminal_values = [status.value for status in TERMINAL_STATUSES]
        repaired = 0
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        select(
                            operational_signals.c.id,
                            operational_signals.c.status,
                            operations.c.status.label("operation_status"),
                        )
                        .join(
                            operations,
                            operations.c.id == operational_signals.c.operation_id,
                        )
                        .where(operations.c.status.in_(terminal_values))
                        .with_for_update(of=operational_signals)
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                target = signal_status_for_operation_terminal(
                    OperationStatus(str(row["operation_status"]))
                )
                if target is None or row["status"] == target.value:
                    continue
                await connection.execute(
                    update(operational_signals)
                    .where(operational_signals.c.id == row["id"])
                    .values(
                        status=target.value,
                        updated_at=timestamp,
                        resolved_at=(timestamp if target is SignalStatus.RESOLVED else None),
                    )
                )
                repaired += 1
        return repaired

    def _signal(self, row: RowMapping) -> OperationalSignal:
        return OperationalSignal(
            id=cast(UUID, row["id"]),
            dedup_key=str(row["dedup_key"]),
            signal_type=str(row["signal_type"]),
            object_type=str(row["object_type"]),
            object_id=str(row["object_id"]),
            source=str(row["source"]),
            severity=str(row["severity"]),
            reason_code=str(row["reason_code"]),
            facts_hash=str(row["facts_hash"]),
            facts=cast(dict[str, JsonValue], row["facts"]),
            status=str(row["status"]),
            operation_id=cast(UUID | None, row["operation_id"]),
            predecessor_signal_id=cast(
                UUID | None,
                row["predecessor_signal_id"],
            ),
            detected_at=row["detected_at"],
            updated_at=row["updated_at"],
            resolved_at=row["resolved_at"],
        )

    @staticmethod
    def _ordered_lineage(
        signals: list[OperationalSignal],
    ) -> tuple[OperationalSignal, ...]:
        by_id = {signal.id: signal for signal in signals}
        child_by_predecessor = {
            signal.predecessor_signal_id: signal
            for signal in signals
            if signal.predecessor_signal_id is not None
        }
        roots = sorted(
            (signal for signal in signals if signal.predecessor_signal_id not in by_id),
            key=lambda signal: (signal.detected_at, str(signal.id)),
        )
        ordered: list[OperationalSignal] = []
        visited: set[UUID] = set()
        for root in roots:
            current: OperationalSignal | None = root
            while current is not None and current.id not in visited:
                ordered.append(current)
                visited.add(current.id)
                current = child_by_predecessor.get(current.id)
        ordered.extend(
            sorted(
                (signal for signal in signals if signal.id not in visited),
                key=lambda signal: (signal.detected_at, str(signal.id)),
            )
        )
        return tuple(ordered)
