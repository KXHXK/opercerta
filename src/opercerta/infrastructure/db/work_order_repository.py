import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.errors import (
    IdempotencyConflict,
    OperationNotFound,
    WriteNotAuthorized,
)
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    canonical_payload_json,
    derive_idempotency_key,
)
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    operations,
    work_orders,
)

AUTHORIZED_STATUSES = frozenset({"resuming", "executing", "verifying"})


class WorkOrderRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_or_get(self, command: WorkOrderCommand) -> WorkOrderWriteResult:
        canonical_json = canonical_payload_json(command.payload)
        payload_snapshot = cast(dict[str, JsonValue], json.loads(canonical_json))
        payload_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        idempotency_key = derive_idempotency_key(command.operation_id)

        try:
            return await self._create_or_get_once(
                operation_id=command.operation_id,
                idempotency_key=idempotency_key,
                payload_snapshot=payload_snapshot,
                payload_hash=payload_hash,
            )
        except IntegrityError:
            async with self._engine.connect() as connection:
                existing = await self._find_existing(connection, idempotency_key)
            if existing is None:
                raise
            return self._existing_result(
                existing,
                operation_id=command.operation_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )

    async def _create_or_get_once(
        self,
        *,
        operation_id: UUID,
        idempotency_key: str,
        payload_snapshot: dict[str, JsonValue],
        payload_hash: str,
    ) -> WorkOrderWriteResult:
        async with self._engine.begin() as connection:
            operation = (
                (
                    await connection.execute(
                        select(operations).where(operations.c.id == operation_id).with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if operation is None:
                raise OperationNotFound(operation_id)

            existing = await self._find_existing(connection, idempotency_key)
            if existing is not None:
                return self._existing_result(
                    existing,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    payload_hash=payload_hash,
                )

            approved = (
                await connection.execute(
                    select(approvals.c.id).where(
                        approvals.c.operation_id == operation_id,
                        approvals.c.decision == "approved",
                    )
                )
            ).scalar_one_or_none()
            status = str(operation["status"])
            if approved is None or status not in AUTHORIZED_STATUSES:
                raise WriteNotAuthorized(operation_id, status)

            work_order_id = uuid4()
            created_at = datetime.now(UTC)
            sequence = int(operation["next_audit_sequence"]) + 1
            await connection.execute(
                insert(work_orders).values(
                    id=work_order_id,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    payload=payload_snapshot,
                    payload_hash=payload_hash,
                    status="created",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    next_audit_sequence=sequence,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    sequence=sequence,
                    event_type="work_order_created",
                    payload={
                        "work_order_id": str(work_order_id),
                        "idempotency_key": idempotency_key,
                        "payload_hash": payload_hash,
                    },
                    created_at=created_at,
                )
            )

        return WorkOrderWriteResult(
            work_order=WorkOrderRecord(
                id=work_order_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                payload=payload_snapshot,
                payload_hash=payload_hash,
                status="created",
                created_at=created_at,
                updated_at=created_at,
            ),
            replayed=False,
        )

    async def _find_existing(
        self,
        connection: AsyncConnection,
        idempotency_key: str,
    ) -> RowMapping | None:
        return (
            (
                await connection.execute(
                    select(work_orders).where(work_orders.c.idempotency_key == idempotency_key)
                )
            )
            .mappings()
            .one_or_none()
        )

    def _existing_result(
        self,
        existing: RowMapping,
        *,
        operation_id: UUID,
        idempotency_key: str,
        payload_hash: str,
    ) -> WorkOrderWriteResult:
        if existing["payload_hash"] != payload_hash:
            raise IdempotencyConflict(operation_id, idempotency_key)
        payload_snapshot = cast(
            dict[str, JsonValue],
            json.loads(canonical_payload_json(cast(dict[str, JsonValue], existing["payload"]))),
        )
        return WorkOrderWriteResult(
            work_order=WorkOrderRecord(
                id=existing["id"],
                operation_id=existing["operation_id"],
                idempotency_key=existing["idempotency_key"],
                payload=payload_snapshot,
                payload_hash=existing["payload_hash"],
                status=existing["status"],
                created_at=existing["created_at"],
                updated_at=existing["updated_at"],
            ),
            replayed=True,
        )
