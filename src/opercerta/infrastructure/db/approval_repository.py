from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import ApprovalCommand, ApprovalRecord
from opercerta.domain.errors import ApprovalAlreadyDecided, OperationNotFound
from opercerta.infrastructure.db.schema import approvals, audit_events, operations


class ApprovalRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def submit_once(self, command: ApprovalCommand) -> ApprovalRecord:
        approval_id = uuid4()
        created_at = datetime.now(UTC)

        async with self._engine.begin() as connection:
            operation = (
                (
                    await connection.execute(
                        select(operations)
                        .where(operations.c.id == command.operation_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if operation is None:
                raise OperationNotFound(command.operation_id)

            existing = (
                (
                    await connection.execute(
                        select(approvals).where(
                            approvals.c.operation_id == command.operation_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None or operation["status"] != "awaiting_approval":
                raise ApprovalAlreadyDecided(command.operation_id)

            sequence = operation["next_audit_sequence"] + 1
            await connection.execute(
                insert(approvals).values(
                    id=approval_id,
                    operation_id=command.operation_id,
                    approver_id=command.approver_id,
                    decision=command.decision.value,
                    reason=command.reason,
                    created_at=created_at,
                )
            )
            await connection.execute(
                update(operations)
                .where(operations.c.id == command.operation_id)
                .values(
                    status="resuming",
                    next_audit_sequence=sequence,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=command.operation_id,
                    sequence=sequence,
                    event_type="approval_recorded",
                    payload={
                        "approval_id": str(approval_id),
                        "decision": command.decision.value,
                    },
                    created_at=created_at,
                )
            )

        return ApprovalRecord(
            id=approval_id,
            operation_id=command.operation_id,
            approver_id=command.approver_id,
            decision=command.decision,
            reason=command.reason,
            created_at=created_at,
        )
