from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.approvals import (
    ApprovalCommand,
    ApprovalRecord,
    BoundApprovalCommand,
)
from opercerta.domain.errors import (
    ApprovalAlreadyDecided,
    ApprovalExpired,
    ApprovalSnapshotMismatch,
    OperationNotFound,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import OperationSnapshot
from opercerta.domain.replenishment import (
    EvidenceBundle,
    ReplenishmentPlan,
    build_approval_binding,
)
from opercerta.domain.scenarios import (
    ApprovalBinding,
    ReplenishmentParameters,
)
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
                        select(approvals).where(approvals.c.operation_id == command.operation_id)
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

    async def submit_bound_once(
        self,
        command: BoundApprovalCommand,
        now: datetime,
    ) -> ApprovalRecord:
        self._require_timezone(now)
        approval_id = uuid4()
        record: ApprovalRecord | None = None
        expired = False

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
                        select(approvals).where(approvals.c.operation_id == command.operation_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None or operation["status"] != "awaiting_approval":
                raise ApprovalAlreadyDecided(command.operation_id)

            expires_at = cast(datetime | None, operation["approval_expires_at"])
            if expires_at is None:
                raise RecoveryStateConflict(
                    command.operation_id,
                    "approval_expiry_missing",
                )

            sequence = int(operation["next_audit_sequence"]) + 1
            if now >= expires_at:
                await connection.execute(
                    update(operations)
                    .where(operations.c.id == command.operation_id)
                    .values(
                        status="expired",
                        next_audit_sequence=sequence,
                        updated_at=now,
                    )
                )
                await connection.execute(
                    insert(audit_events).values(
                        id=uuid4(),
                        operation_id=command.operation_id,
                        sequence=sequence,
                        event_type="approval_expired",
                        payload={"approval_expires_at": expires_at.isoformat()},
                        created_at=now,
                    )
                )
                expired = True
            else:
                current_binding = self._current_binding(operation["request_payload"])
                if command.expected_binding != current_binding:
                    raise ApprovalSnapshotMismatch

                await connection.execute(
                    insert(approvals).values(
                        id=approval_id,
                        operation_id=command.operation_id,
                        approver_id=command.approver_id,
                        decision=command.decision.value,
                        reason=command.reason,
                        subject_evidence_id=current_binding.subject_evidence_id,
                        binding_payload=current_binding.model_dump(mode="json"),
                        **self._legacy_inventory_values(current_binding),
                        created_at=now,
                    )
                )
                await connection.execute(
                    update(operations)
                    .where(operations.c.id == command.operation_id)
                    .values(
                        status="resuming",
                        next_audit_sequence=sequence,
                        updated_at=now,
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
                        created_at=now,
                    )
                )
                record = ApprovalRecord(
                    id=approval_id,
                    operation_id=command.operation_id,
                    approver_id=command.approver_id,
                    decision=command.decision,
                    reason=command.reason,
                    created_at=now,
                )

        if expired:
            raise ApprovalExpired
        if record is None:
            raise AssertionError("bound approval transaction produced no result")
        return record

    def _current_binding(
        self,
        snapshot_value: object,
    ) -> ApprovalBinding:
        try:
            snapshot = OperationSnapshot.model_validate(snapshot_value)
            stored_binding = ApprovalBinding.model_validate(snapshot.risk.get("approval_binding"))
            bundle = EvidenceBundle.model_validate(snapshot.risk.get("evidence"))
            plan = ReplenishmentPlan.model_validate(snapshot.plan)
        except ValidationError:
            raise ApprovalSnapshotMismatch from None

        derived_binding = ApprovalBinding.model_validate(build_approval_binding(bundle, plan))
        if stored_binding != derived_binding:
            raise ApprovalSnapshotMismatch
        return stored_binding

    def _legacy_inventory_values(
        self,
        binding: ApprovalBinding,
    ) -> dict[str, object]:
        parameters = binding.parameters
        if not isinstance(parameters, ReplenishmentParameters):
            return {}
        return {
            "inventory_evidence_id": binding.subject_evidence_id,
            "policy_evidence_id": binding.policy_evidence_id,
            "rule_version": binding.rule_version,
            "decision_facts_hash": binding.decision_facts_hash,
            "plan_hash": binding.plan_hash,
            "recommended_quantity": parameters.recommended_quantity,
        }

    def _require_timezone(self, value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
