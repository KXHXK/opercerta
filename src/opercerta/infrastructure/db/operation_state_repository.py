from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationNotFound,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import (
    OperationSnapshot,
    OperationTransitionResult,
    RecoveryView,
)
from opercerta.domain.recovery import OperationStatus
from opercerta.infrastructure.db.schema import approvals, audit_events, operations, work_orders


class OperationStateRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load_recovery_view(self, operation_id: UUID) -> RecoveryView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(
                            operations.c.id,
                            operations.c.thread_id,
                            operations.c.status,
                            operations.c.request_payload,
                            approvals.c.id.label("approval_id"),
                            approvals.c.decision,
                            work_orders.c.id.label("work_order_id"),
                            work_orders.c.payload_hash,
                        )
                        .select_from(
                            operations.outerjoin(
                                approvals,
                                and_(
                                    approvals.c.operation_id == operations.c.id,
                                    approvals.c.approval_cycle == operations.c.approval_cycle,
                                ),
                            ).outerjoin(
                                work_orders,
                                work_orders.c.operation_id == operations.c.id,
                            )
                        )
                        .where(operations.c.id == operation_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OperationNotFound(operation_id)
        return self._validated_view(operation_id, row)

    async def mark_awaiting_approval(
        self,
        operation_id: UUID,
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RECEIVED}),
            target=OperationStatus.AWAITING_APPROVAL,
            event_type="approval_requested",
            payload={"snapshot_version": 1},
        )

    async def mark_executing(
        self,
        operation_id: UUID,
        approval_id: UUID,
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.EXECUTING,
            event_type="execution_started",
            payload={"approval_id": str(approval_id)},
        )

    async def mark_verifying(
        self,
        operation_id: UUID,
        work_order_id: UUID,
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.EXECUTING}),
            target=OperationStatus.VERIFYING,
            event_type="verification_started",
            payload={"work_order_id": str(work_order_id)},
        )

    async def mark_completed(
        self,
        operation_id: UUID,
        work_order_id: UUID,
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.VERIFYING}),
            target=OperationStatus.COMPLETED,
            event_type="operation_completed",
            payload={"work_order_id": str(work_order_id)},
        )

    async def mark_rejected(
        self,
        operation_id: UUID,
        approval_id: UUID,
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.REJECTED,
            event_type="operation_rejected",
            payload={"approval_id": str(approval_id)},
        )

    async def _transition(
        self,
        operation_id: UUID,
        *,
        allowed: frozenset[OperationStatus],
        target: OperationStatus,
        event_type: str,
        payload: dict[str, object],
    ) -> OperationTransitionResult:
        async with self._engine.begin() as connection:
            operation = await self._locked_operation(connection, operation_id)
            current_raw = str(operation["status"])
            try:
                current = OperationStatus(current_raw)
            except ValueError:
                raise RecoveryStateConflict(
                    operation_id,
                    "unknown_operation_status",
                ) from None

            if current is target:
                await self._require_matching_event(
                    connection,
                    operation_id,
                    event_type=event_type,
                    payload=payload,
                )
                return OperationTransitionResult(
                    operation_id=operation_id,
                    status=target,
                    changed=False,
                    audit_sequence=None,
                )

            if current not in allowed:
                raise OperationTransitionConflict(
                    operation_id,
                    current.value,
                    target.value,
                )

            sequence = int(operation["next_audit_sequence"]) + 1
            changed_at = datetime.now(UTC)
            operation_values: dict[str, object] = {
                "status": target.value,
                "next_audit_sequence": sequence,
                "updated_at": changed_at,
            }
            if target is OperationStatus.AWAITING_APPROVAL:
                operation_values["approval_cycle"] = 1

            await connection.execute(
                update(operations).where(operations.c.id == operation_id).values(**operation_values)
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=payload,
                    created_at=changed_at,
                )
            )

        return OperationTransitionResult(
            operation_id=operation_id,
            status=target,
            changed=True,
            audit_sequence=sequence,
        )

    async def _locked_operation(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
    ) -> RowMapping:
        row = (
            (
                await connection.execute(
                    select(operations).where(operations.c.id == operation_id).with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OperationNotFound(operation_id)
        return row

    async def _require_matching_event(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        *,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        rows = (
            (
                await connection.execute(
                    select(audit_events.c.payload).where(
                        audit_events.c.operation_id == operation_id,
                        audit_events.c.event_type == event_type,
                    )
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1 or cast(dict[str, object], rows[0]["payload"]) != payload:
            raise RecoveryStateConflict(
                operation_id,
                "target_state_event_mismatch",
            )

    def _validated_view(
        self,
        operation_id: UUID,
        row: RowMapping,
    ) -> RecoveryView:
        if str(row["thread_id"]) != str(operation_id):
            raise RecoveryStateConflict(operation_id, "thread_id_mismatch")

        try:
            status = OperationStatus(str(row["status"]))
        except ValueError:
            raise RecoveryStateConflict(
                operation_id,
                "unknown_operation_status",
            ) from None

        try:
            snapshot = OperationSnapshot.model_validate(row["request_payload"])
        except ValidationError:
            raise InvalidOperationSnapshot(
                operation_id,
                "request_payload_failed_validation",
            ) from None

        approval_id = cast(UUID | None, row["approval_id"])
        decision_raw = cast(str | None, row["decision"])
        if (approval_id is None) != (decision_raw is None):
            raise RecoveryStateConflict(operation_id, "partial_approval_locator")
        decision: ApprovalDecision | None = None
        if decision_raw is not None:
            try:
                decision = ApprovalDecision(decision_raw)
            except ValueError:
                raise RecoveryStateConflict(
                    operation_id,
                    "invalid_approval_decision",
                ) from None

        work_order_id = cast(UUID | None, row["work_order_id"])
        payload_hash = cast(str | None, row["payload_hash"])
        if (work_order_id is None) != (payload_hash is None):
            raise RecoveryStateConflict(operation_id, "partial_work_order_locator")
        if payload_hash is not None and (
            len(payload_hash) != 64
            or any(character not in "0123456789abcdef" for character in payload_hash)
        ):
            raise RecoveryStateConflict(operation_id, "invalid_work_order_payload_hash")

        return RecoveryView(
            operation_id=operation_id,
            thread_id=str(row["thread_id"]),
            status=status,
            snapshot=snapshot,
            approval_id=approval_id,
            decision=decision,
            work_order_id=work_order_id,
            payload_hash=payload_hash,
        )
