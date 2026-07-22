import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue, ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.contracts import ObjectType, OperationRequest
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationNotFound,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.maintenance import (
    MaintenanceAssessment,
    MaintenanceEvidenceBundle,
    MaintenancePlan,
    RepairWorkOrderPayload,
    build_maintenance_approval_binding,
)
from opercerta.domain.operation_state import OperationSnapshot
from opercerta.domain.recovery import TERMINAL_STATUSES, OperationStatus
from opercerta.domain.replenishment import (
    ApprovalBinding as ReplenishmentApprovalBinding,
)
from opercerta.domain.replenishment import (
    EvidenceBundle,
    OperationError,
    OperationResult,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    build_approval_binding,
)
from opercerta.domain.scenarios import ApprovalBinding
from opercerta.domain.task_recovery import (
    TaskRecoveryAssessment,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPlan,
    TaskRecoveryWorkOrderPayload,
    build_task_recovery_approval_binding,
)
from opercerta.domain.work_orders import WorkOrderRecord, canonical_payload_json
from opercerta.infrastructure.db.evidence_repository import (
    EvidenceRecord,
    EvidenceRepository,
)
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    evidence,
    operations,
    work_orders,
)

SnapshotBuilder = Callable[[OperationSnapshot], OperationSnapshot]
TransactionWrite = Callable[[AsyncConnection], Awaitable[None]]
TransactionValidator = Callable[[AsyncConnection], Awaitable[None]]
_UNSET = object()


@dataclass(frozen=True, slots=True)
class AuditEventView:
    id: UUID
    operation_id: UUID
    sequence: int
    event_type: str
    payload: Mapping[str, JsonValue]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalRowView:
    id: UUID
    operation_id: UUID
    approver_id: str
    decision: ApprovalDecision
    reason: str
    created_at: datetime
    binding: ApprovalBinding | None
    approval_cycle: int


@dataclass(frozen=True, slots=True)
class OperationDetail:
    operation_id: UUID
    thread_id: str
    status: OperationStatus
    snapshot: OperationSnapshot
    result: OperationResult | None
    error: OperationError | None
    approval_expires_at: datetime | None
    approval_cycle: int
    evidence: tuple[EvidenceRecord, ...]
    approval: ApprovalRowView | None
    work_order: WorkOrderRecord | None
    audit_events: tuple[AuditEventView, ...]

    @property
    def assessment(
        self,
    ) -> ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment | None:
        value = self.snapshot.risk.get("assessment")
        if value is None:
            return None
        try:
            try:
                object_type = self._object_type()
            except RecoveryStateConflict:
                object_type = ObjectType.INVENTORY
            if object_type is ObjectType.INVENTORY:
                return ReplenishmentAssessment.model_validate(value)
            if object_type is ObjectType.EQUIPMENT:
                return MaintenanceAssessment.model_validate(value)
            if object_type is ObjectType.TASK:
                return TaskRecoveryAssessment.model_validate(value)
            raise ValueError("unsupported assessment object type")
        except ValidationError:
            raise RecoveryStateConflict(
                self.operation_id,
                "invalid_snapshot_assessment",
            ) from None

    @property
    def plan(self) -> ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan | None:
        if not self.snapshot.plan:
            return None
        try:
            try:
                object_type = self._object_type()
            except RecoveryStateConflict:
                object_type = ObjectType.INVENTORY
            if object_type is ObjectType.INVENTORY:
                return ReplenishmentPlan.model_validate(self.snapshot.plan)
            if object_type is ObjectType.EQUIPMENT:
                return MaintenancePlan.model_validate(self.snapshot.plan)
            if object_type is ObjectType.TASK:
                return TaskRecoveryPlan.model_validate(self.snapshot.plan)
            raise ValueError("unsupported plan object type")
        except ValidationError:
            raise RecoveryStateConflict(
                self.operation_id,
                "invalid_snapshot_plan",
            ) from None

    @property
    def approval_binding(self) -> ApprovalBinding | None:
        value = self.snapshot.risk.get("approval_binding")
        if value is None:
            return None
        try:
            return ApprovalBinding.model_validate(value)
        except ValidationError:
            raise RecoveryStateConflict(
                self.operation_id,
                "invalid_snapshot_approval_binding",
            ) from None

    def _object_type(self) -> ObjectType:
        try:
            request = OperationRequest.model_validate(self.snapshot.request)
        except ValidationError:
            raise RecoveryStateConflict(
                self.operation_id,
                "invalid_snapshot_request",
            ) from None
        if request.object_type is None:
            raise RecoveryStateConflict(self.operation_id, "snapshot_object_type_missing")
        return request.object_type

    @property
    def last_audit_sequence(self) -> int:
        return self.audit_events[-1].sequence if self.audit_events else 0

    @property
    def event_types(self) -> tuple[str, ...]:
        return tuple(event.event_type for event in self.audit_events)

    @property
    def evidence_records(self) -> tuple[EvidenceRecord, ...]:
        return self.evidence

    @property
    def approval_row(self) -> ApprovalRowView | None:
        return self.approval

    @property
    def work_order_row(self) -> WorkOrderRecord | None:
        return self.work_order


class ReplenishmentOperationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._evidence_repository = EvidenceRepository(engine)

    async def create(self, request: OperationRequest) -> UUID:
        operation_id = uuid4()
        created_at = datetime.now(UTC)
        request_payload = cast(dict[str, JsonValue], request.model_dump(mode="json"))
        snapshot = OperationSnapshot(
            schema_version=1,
            request=request_payload,
            risk={},
            plan={},
            work_order_payload={},
        )
        event_payload: dict[str, JsonValue] = {"request": request_payload}
        async with self._engine.begin() as connection:
            await connection.execute(
                insert(operations).values(
                    id=operation_id,
                    thread_id=str(operation_id),
                    request_payload=snapshot.model_dump(mode="json"),
                    status=OperationStatus.RECEIVED.value,
                    next_audit_sequence=1,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    sequence=1,
                    event_type="operation_received",
                    payload=event_payload,
                    created_at=created_at,
                )
            )
        return operation_id

    async def mark_gathering_evidence(self, operation_id: UUID) -> None:
        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RECEIVED}),
            target=OperationStatus.GATHERING_EVIDENCE,
            event_type="evidence_gathering_started",
            payload={},
        )

    async def record_evidence(
        self,
        operation_id: UUID,
        bundle: EvidenceBundle | MaintenanceEvidenceBundle | TaskRecoveryEvidenceBundle,
    ) -> None:
        bundle_payload = cast(dict[str, JsonValue], bundle.model_dump(mode="json"))

        async def save_evidence(connection: AsyncConnection) -> None:
            await self._evidence_repository._save_in_connection(
                connection,
                operation_id,
                bundle,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.GATHERING_EVIDENCE}),
            target=OperationStatus.PLANNING,
            event_type="evidence_recorded",
            payload={"bundle": bundle_payload},
            snapshot_builder=lambda snapshot: self._replace_risk_value(
                snapshot,
                "evidence",
                bundle_payload,
            ),
            transaction_write=save_evidence,
        )

    async def record_validated_plan(
        self,
        operation_id: UUID,
        assessment: ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment,
        plan: ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan | None,
    ) -> None:
        self._require_plan_matches_assessment(assessment, plan)
        assessment_payload = cast(
            dict[str, JsonValue],
            assessment.model_dump(mode="json"),
        )
        plan_payload = (
            cast(dict[str, JsonValue], plan.model_dump(mode="json")) if plan is not None else {}
        )
        work_order_payload = self._work_order_payload(plan)
        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.PLANNING}),
            target=OperationStatus.VALIDATING,
            event_type="plan_validated",
            payload={
                "assessment": assessment_payload,
                "plan": plan_payload,
            },
            snapshot_builder=lambda snapshot: OperationSnapshot(
                schema_version=1,
                request=snapshot.request,
                risk={**snapshot.risk, "assessment": assessment_payload},
                plan=plan_payload,
                work_order_payload=work_order_payload,
            ),
        )

    async def record_query_assessment(
        self,
        operation_id: UUID,
        assessment: ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment,
    ) -> None:
        assessment_payload = cast(
            dict[str, JsonValue],
            assessment.model_dump(mode="json"),
        )
        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.PLANNING}),
            target=OperationStatus.VALIDATING,
            event_type="query_assessed",
            payload={"assessment": assessment_payload},
            snapshot_builder=lambda snapshot: OperationSnapshot(
                schema_version=1,
                request=snapshot.request,
                risk={**snapshot.risk, "assessment": assessment_payload},
                plan={},
                work_order_payload={},
            ),
        )

    async def mark_reporting(self, operation_id: UUID) -> None:
        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.VALIDATING}),
            target=OperationStatus.REPORTING,
            event_type="reporting_started",
            payload={},
        )

    async def mark_awaiting_approval(
        self,
        operation_id: UUID,
        binding: ApprovalBinding | ReplenishmentApprovalBinding,
        approval_expires_at: datetime,
    ) -> None:
        self._require_timezone(approval_expires_at)
        scenario_binding = ApprovalBinding.model_validate(binding)
        binding_payload = cast(dict[str, JsonValue], scenario_binding.model_dump(mode="json"))

        def bind(snapshot: OperationSnapshot) -> OperationSnapshot:
            self._require_binding_matches_snapshot(snapshot, scenario_binding)
            return self._replace_risk_value(
                snapshot,
                "approval_binding",
                binding_payload,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.VALIDATING}),
            target=OperationStatus.AWAITING_APPROVAL,
            event_type="approval_requested",
            payload={
                "approval_expires_at": approval_expires_at.isoformat(),
                **binding_payload,
            },
            snapshot_builder=bind,
            approval_expires_at=approval_expires_at,
            approval_cycle=1,
        )

    async def mark_needs_reapproval(
        self,
        operation_id: UUID,
        approval_id: UUID,
        bundle: EvidenceBundle | MaintenanceEvidenceBundle | TaskRecoveryEvidenceBundle,
        assessment: ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment,
        plan: ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan,
        binding: ApprovalBinding,
        approval_expires_at: datetime,
        reason: str,
    ) -> None:
        self._require_timezone(approval_expires_at)
        bundle_payload = cast(dict[str, JsonValue], bundle.model_dump(mode="json"))
        assessment_payload = cast(dict[str, JsonValue], assessment.model_dump(mode="json"))
        plan_payload = cast(dict[str, JsonValue], plan.model_dump(mode="json"))
        binding_payload = cast(dict[str, JsonValue], binding.model_dump(mode="json"))

        def replace_approved_facts(snapshot: OperationSnapshot) -> OperationSnapshot:
            next_snapshot = OperationSnapshot(
                schema_version=1,
                request=snapshot.request,
                risk={
                    **snapshot.risk,
                    "evidence": bundle_payload,
                    "assessment": assessment_payload,
                    "approval_binding": binding_payload,
                },
                plan=plan_payload,
                work_order_payload=self._work_order_payload(plan),
            )
            self._require_binding_matches_snapshot(next_snapshot, binding)
            return next_snapshot

        async def validate_approval(connection: AsyncConnection) -> None:
            await self._require_approval_locator(
                connection,
                operation_id,
                approval_id,
                ApprovalDecision.APPROVED,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.NEEDS_REAPPROVAL,
            event_type="reapproval_requested",
            payload={
                "approval_id": str(approval_id),
                "reason": reason,
                **binding_payload,
            },
            snapshot_builder=replace_approved_facts,
            transaction_validator=validate_approval,
            approval_expires_at=approval_expires_at,
            increment_approval_cycle=True,
        )

    async def mark_verifier_aborted(
        self,
        operation_id: UUID,
        approval_id: UUID,
        reason: str,
    ) -> None:
        async def validate_approval(connection: AsyncConnection) -> None:
            await self._require_approval_locator(
                connection,
                operation_id,
                approval_id,
                ApprovalDecision.APPROVED,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.ABORTED,
            event_type="verification_aborted",
            payload={"approval_id": str(approval_id), "reason": reason},
            transaction_validator=validate_approval,
            approval_expires_at=None,
        )

    async def mark_executing(self, operation_id: UUID, approval_id: UUID) -> None:
        async def validate_approval(connection: AsyncConnection) -> None:
            await self._require_approval_locator(
                connection,
                operation_id,
                approval_id,
                ApprovalDecision.APPROVED,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.EXECUTING,
            event_type="execution_started",
            payload={"approval_id": str(approval_id)},
            transaction_validator=validate_approval,
        )

    async def mark_verifying(self, operation_id: UUID, work_order_id: UUID) -> None:
        async def validate_work_order(connection: AsyncConnection) -> None:
            await self._require_work_order_locator(
                connection,
                operation_id,
                work_order_id,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.EXECUTING}),
            target=OperationStatus.VERIFYING,
            event_type="verification_started",
            payload={"work_order_id": str(work_order_id)},
            transaction_validator=validate_work_order,
        )

    async def mark_completed(
        self,
        operation_id: UUID,
        result: OperationResult,
        work_order_id: UUID,
    ) -> None:
        if result.outcome != "work_order_completed" or result.work_order_id != work_order_id:
            raise ValueError("completed result must match work order")
        result_payload = cast(dict[str, JsonValue], result.model_dump(mode="json"))

        async def validate_work_order(connection: AsyncConnection) -> None:
            await self._require_work_order_locator(
                connection,
                operation_id,
                work_order_id,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.VERIFYING}),
            target=OperationStatus.COMPLETED,
            event_type="operation_completed",
            payload=result_payload,
            transaction_validator=validate_work_order,
            result_payload=result_payload,
            error_code=None,
        )

    async def mark_rejected(self, operation_id: UUID, approval_id: UUID) -> None:
        async def validate_approval(connection: AsyncConnection) -> None:
            await self._require_approval_locator(
                connection,
                operation_id,
                approval_id,
                ApprovalDecision.REJECTED,
            )

        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.REJECTED,
            event_type="operation_rejected",
            payload={"approval_id": str(approval_id)},
            transaction_validator=validate_approval,
        )

    async def complete_without_replenishment(
        self,
        operation_id: UUID,
        result: OperationResult,
    ) -> None:
        if (
            result.outcome
            not in {
                "replenishment_not_required",
                "maintenance_not_required",
                "task_recovery_not_required",
                "query_completed",
            }
            or result.work_order_id is not None
        ):
            raise ValueError("non-action result must not reference a work order")
        result_payload = cast(dict[str, JsonValue], result.model_dump(mode="json"))
        await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.REPORTING}),
            target=OperationStatus.COMPLETED,
            event_type="operation_completed",
            payload=result_payload,
            result_payload=result_payload,
            error_code=None,
        )

    async def mark_failed(self, operation_id: UUID, error: OperationError) -> None:
        error_payload = cast(dict[str, JsonValue], error.model_dump(mode="json"))
        await self._transition(
            operation_id,
            allowed=frozenset(set(OperationStatus) - set(TERMINAL_STATUSES)),
            target=OperationStatus.FAILED,
            event_type="operation_failed",
            payload=error_payload,
            result_payload=error_payload,
            error_code=error.code,
        )

    async def mark_expired(self, operation_id: UUID, now: datetime) -> bool:
        self._require_timezone(now)
        return await self._transition(
            operation_id,
            allowed=frozenset(
                {
                    OperationStatus.AWAITING_APPROVAL,
                    OperationStatus.NEEDS_REAPPROVAL,
                }
            ),
            target=OperationStatus.EXPIRED,
            event_type="approval_expired",
            payload={},
            due_at=now,
        )

    async def load_detail(self, operation_id: UUID) -> OperationDetail:
        async with self._engine.begin() as connection:
            operation = (
                (
                    await connection.execute(
                        select(operations)
                        .where(operations.c.id == operation_id)
                        .with_for_update(read=True)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if operation is None:
                raise OperationNotFound(operation_id)
            evidence_rows = (
                (
                    await connection.execute(
                        select(evidence)
                        .where(evidence.c.operation_id == operation_id)
                        .order_by(
                            evidence.c.created_at,
                            evidence.c.evidence_type,
                            evidence.c.id,
                        )
                    )
                )
                .mappings()
                .all()
            )
            approval = (
                (
                    await connection.execute(
                        select(approvals).where(
                            approvals.c.operation_id == operation_id,
                            approvals.c.approval_cycle == int(operation["approval_cycle"]),
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            work_order = (
                (
                    await connection.execute(
                        select(work_orders).where(work_orders.c.operation_id == operation_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
            event_rows = (
                (
                    await connection.execute(
                        select(audit_events)
                        .where(audit_events.c.operation_id == operation_id)
                        .order_by(audit_events.c.sequence)
                    )
                )
                .mappings()
                .all()
            )

        status = self._status(operation_id, operation["status"])
        thread_id = str(operation["thread_id"])
        if thread_id != str(operation_id):
            raise RecoveryStateConflict(operation_id, "thread_id_mismatch")
        snapshot = self._snapshot(operation_id, operation["request_payload"])
        work_order_view = self._work_order_view(operation_id, work_order)
        result, error = self._terminal_payloads(
            operation_id,
            status,
            operation,
            work_order_view,
        )
        snapshot_binding = self._snapshot_approval_binding(operation_id, snapshot)
        return OperationDetail(
            operation_id=operation_id,
            thread_id=thread_id,
            status=status,
            snapshot=snapshot,
            result=result,
            error=error,
            approval_expires_at=cast(datetime | None, operation["approval_expires_at"]),
            approval_cycle=int(operation["approval_cycle"]),
            evidence=tuple(self._evidence_repository._record(row) for row in evidence_rows),
            approval=self._approval_view(
                operation_id,
                approval,
                snapshot_binding=snapshot_binding,
            ),
            work_order=work_order_view,
            audit_events=tuple(self._audit_event(row) for row in event_rows),
        )

    async def list_recoverable_ids(self) -> list[UUID]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(operations.c.id)
                    .where(
                        operations.c.status.not_in([status.value for status in TERMINAL_STATUSES])
                    )
                    .order_by(operations.c.created_at, operations.c.id)
                )
            ).scalars()
        return list(rows)

    async def list_due_approval_ids(self, now: datetime, limit: int) -> list[UUID]:
        self._require_timezone(now)
        if limit < 1:
            return []
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(operations.c.id)
                    .where(
                        operations.c.status.in_(
                            [
                                OperationStatus.AWAITING_APPROVAL.value,
                                OperationStatus.NEEDS_REAPPROVAL.value,
                            ]
                        ),
                        operations.c.approval_expires_at.is_not(None),
                        operations.c.approval_expires_at <= now,
                    )
                    .order_by(operations.c.approval_expires_at, operations.c.id)
                    .limit(limit)
                )
            ).scalars()
        return list(rows)

    async def _transition(
        self,
        operation_id: UUID,
        *,
        allowed: frozenset[OperationStatus],
        target: OperationStatus,
        event_type: str,
        payload: dict[str, JsonValue],
        snapshot_builder: SnapshotBuilder | None = None,
        transaction_validator: TransactionValidator | None = None,
        transaction_write: TransactionWrite | None = None,
        result_payload: dict[str, JsonValue] | None | object = _UNSET,
        error_code: str | None | object = _UNSET,
        approval_expires_at: datetime | None | object = _UNSET,
        approval_cycle: int | object = _UNSET,
        increment_approval_cycle: bool = False,
        due_at: datetime | None = None,
    ) -> bool:
        async with self._engine.begin() as connection:
            operation = await self._locked_operation(connection, operation_id)
            current = self._status(operation_id, operation["status"])
            if due_at is not None:
                expires_at = cast(datetime | None, operation["approval_expires_at"])
                if expires_at is None:
                    raise RecoveryStateConflict(
                        operation_id,
                        "approval_expiry_missing",
                    )
                if due_at < expires_at:
                    return False
                payload = {"approval_expires_at": expires_at.isoformat()}
            if current is target:
                await self._require_matching_event(
                    connection,
                    operation_id,
                    event_type=event_type,
                    payload=payload,
                )
                return False
            if transaction_validator is not None:
                await transaction_validator(connection)
            if current not in allowed:
                raise OperationTransitionConflict(
                    operation_id,
                    current.value,
                    target.value,
                )

            snapshot = self._snapshot(operation_id, operation["request_payload"])
            next_snapshot = snapshot_builder(snapshot) if snapshot_builder else snapshot
            next_snapshot = OperationSnapshot.model_validate(next_snapshot.model_dump(mode="json"))
            if transaction_write is not None:
                await transaction_write(connection)

            sequence = int(operation["next_audit_sequence"]) + 1
            changed_at = datetime.now(UTC)
            values: dict[str, object] = {
                "status": target.value,
                "next_audit_sequence": sequence,
                "request_payload": next_snapshot.model_dump(mode="json"),
                "updated_at": changed_at,
            }
            if result_payload is not _UNSET:
                values["result_payload"] = result_payload
            if error_code is not _UNSET:
                values["error_code"] = error_code
            if approval_expires_at is not _UNSET:
                values["approval_expires_at"] = approval_expires_at
            if approval_cycle is not _UNSET and increment_approval_cycle:
                raise ValueError("approval cycle update is ambiguous")
            if approval_cycle is not _UNSET:
                values["approval_cycle"] = approval_cycle
            elif increment_approval_cycle:
                values["approval_cycle"] = int(operation["approval_cycle"]) + 1
            await connection.execute(
                update(operations).where(operations.c.id == operation_id).values(**values)
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
        return True

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

    async def _require_approval_locator(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        approval_id: UUID,
        expected_decision: ApprovalDecision,
    ) -> None:
        row = (
            (
                await connection.execute(
                    select(
                        approvals.c.operation_id,
                        approvals.c.decision,
                        approvals.c.approval_cycle,
                        operations.c.approval_cycle.label("current_approval_cycle"),
                    )
                    .select_from(
                        approvals.join(
                            operations,
                            approvals.c.operation_id == operations.c.id,
                        )
                    )
                    .where(approvals.c.id == approval_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise RecoveryStateConflict(operation_id, "approval_locator_missing")
        if row["operation_id"] != operation_id:
            raise RecoveryStateConflict(operation_id, "approval_operation_mismatch")
        if row["decision"] != expected_decision.value:
            raise RecoveryStateConflict(operation_id, "approval_decision_mismatch")
        if row["approval_cycle"] != row["current_approval_cycle"]:
            raise RecoveryStateConflict(operation_id, "stale_approval_cycle")

    async def _require_work_order_locator(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        work_order_id: UUID,
    ) -> None:
        located_operation_id = (
            await connection.execute(
                select(work_orders.c.operation_id).where(work_orders.c.id == work_order_id)
            )
        ).scalar_one_or_none()
        if located_operation_id is None:
            raise RecoveryStateConflict(operation_id, "work_order_locator_missing")
        if located_operation_id != operation_id:
            raise RecoveryStateConflict(operation_id, "work_order_operation_mismatch")

    async def _require_matching_event(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        *,
        event_type: str,
        payload: dict[str, JsonValue],
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
            .scalars()
            .all()
        )
        if len(rows) != 1 or cast(dict[str, JsonValue], rows[0]) != payload:
            raise RecoveryStateConflict(
                operation_id,
                "target_state_event_mismatch",
            )

    def _replace_risk_value(
        self,
        snapshot: OperationSnapshot,
        key: str,
        value: dict[str, JsonValue],
    ) -> OperationSnapshot:
        return OperationSnapshot(
            schema_version=1,
            request=snapshot.request,
            risk={**snapshot.risk, key: value},
            plan=snapshot.plan,
            work_order_payload=snapshot.work_order_payload,
        )

    def _require_plan_matches_assessment(
        self,
        assessment: ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment,
        plan: ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan | None,
    ) -> None:
        if isinstance(assessment, TaskRecoveryAssessment):
            if not assessment.recovery_required:
                if plan is not None:
                    raise ValueError("non-recovery assessment must not have a plan")
                return
            if (
                not isinstance(plan, TaskRecoveryPlan)
                or plan.task_id != assessment.task_id
                or plan.blocker_code != assessment.blocker_code
                or plan.retry_count != assessment.retry_count
                or plan.recovery_action != assessment.recovery_action
                or plan.decision_facts_hash != assessment.decision_facts_hash
            ):
                raise ValueError("task recovery plan does not match assessment")
            return
        if isinstance(assessment, MaintenanceAssessment):
            if not assessment.maintenance_required:
                if plan is not None:
                    raise ValueError("non-maintenance assessment must not have a plan")
                return
            if (
                not isinstance(plan, MaintenancePlan)
                or plan.equipment_id != assessment.equipment_id
                or plan.alert_code != assessment.alert_code
                or plan.priority != assessment.priority
                or plan.decision_facts_hash != assessment.decision_facts_hash
            ):
                raise ValueError("maintenance plan does not match assessment")
            return
        if isinstance(plan, (MaintenancePlan, TaskRecoveryPlan)):
            raise ValueError("non-replenishment plan cannot satisfy replenishment assessment")
        if not assessment.replenishment_required:
            if plan is not None or assessment.recommended_quantity is not None:
                raise ValueError("non-replenishment assessment must not have a plan")
            return
        if (
            plan is None
            or assessment.recommended_quantity is None
            or plan.sku != assessment.sku
            or plan.recommended_quantity != assessment.recommended_quantity
            or plan.decision_facts_hash != assessment.decision_facts_hash
        ):
            raise ValueError("replenishment plan does not match assessment")

    def _require_binding_matches_snapshot(
        self,
        snapshot: OperationSnapshot,
        binding: ApprovalBinding,
    ) -> None:
        evidence_payload = snapshot.risk.get("evidence")
        if evidence_payload is None or not snapshot.plan:
            raise ValueError("approval binding requires evidence and plan")
        request = OperationRequest.model_validate(snapshot.request)
        if request.object_type is ObjectType.INVENTORY:
            evidence_bundle = EvidenceBundle.model_validate(evidence_payload)
            inventory_plan = ReplenishmentPlan.model_validate(snapshot.plan)
            expected = ApprovalBinding.model_validate(
                build_approval_binding(evidence_bundle, inventory_plan)
            )
        elif request.object_type is ObjectType.EQUIPMENT:
            maintenance_bundle = MaintenanceEvidenceBundle.model_validate(evidence_payload)
            maintenance_plan = MaintenancePlan.model_validate(snapshot.plan)
            expected = build_maintenance_approval_binding(
                maintenance_bundle,
                maintenance_plan,
            )
        elif request.object_type is ObjectType.TASK:
            task_bundle = TaskRecoveryEvidenceBundle.model_validate(evidence_payload)
            task_plan = TaskRecoveryPlan.model_validate(snapshot.plan)
            expected = build_task_recovery_approval_binding(task_bundle, task_plan)
        else:
            raise ValueError("unsupported approval binding object type")
        if expected != binding:
            raise ValueError("approval binding does not match snapshot")

    def _work_order_payload(
        self,
        plan: ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan | None,
    ) -> dict[str, JsonValue]:
        if plan is None:
            return {}
        if isinstance(plan, ReplenishmentPlan):
            return {
                "sku": plan.sku,
                "quantity": plan.recommended_quantity,
                "approved_plan_hash": plan.plan_hash,
            }
        if isinstance(plan, MaintenancePlan):
            return cast(
                dict[str, JsonValue],
                RepairWorkOrderPayload(
                    equipment_id=plan.equipment_id,
                    alert_code=plan.alert_code,
                    priority=plan.priority,
                    approved_plan_hash=plan.plan_hash,
                ).model_dump(mode="json"),
            )
        return cast(
            dict[str, JsonValue],
            TaskRecoveryWorkOrderPayload(
                task_id=plan.task_id,
                blocker_code=plan.blocker_code,
                retry_count=plan.retry_count,
                recovery_action=plan.recovery_action,
                approved_plan_hash=plan.plan_hash,
            ).model_dump(mode="json"),
        )

    def _snapshot(self, operation_id: UUID, value: object) -> OperationSnapshot:
        try:
            return OperationSnapshot.model_validate(value)
        except ValidationError:
            raise InvalidOperationSnapshot(
                operation_id,
                "request_payload_failed_validation",
            ) from None

    def _status(self, operation_id: UUID, value: object) -> OperationStatus:
        try:
            return OperationStatus(str(value))
        except ValueError:
            raise RecoveryStateConflict(
                operation_id,
                "unknown_operation_status",
            ) from None

    def _terminal_payloads(
        self,
        operation_id: UUID,
        status: OperationStatus,
        operation: RowMapping,
        work_order: WorkOrderRecord | None,
    ) -> tuple[OperationResult | None, OperationError | None]:
        payload = operation["result_payload"]
        error_code = cast(str | None, operation["error_code"])

        if status is OperationStatus.COMPLETED:
            if payload is None:
                raise RecoveryStateConflict(operation_id, "completed_result_missing")
            if error_code is not None:
                raise RecoveryStateConflict(operation_id, "completed_error_code_present")
            try:
                result = OperationResult.model_validate(payload)
            except ValidationError:
                raise RecoveryStateConflict(
                    operation_id,
                    "invalid_completed_result",
                ) from None
            if result.outcome == "work_order_completed":
                if work_order is None:
                    raise RecoveryStateConflict(
                        operation_id,
                        "completed_work_order_missing",
                    )
                if result.work_order_id != work_order.id:
                    raise RecoveryStateConflict(
                        operation_id,
                        "completed_work_order_id_mismatch",
                    )
            elif result.work_order_id is not None or work_order is not None:
                raise RecoveryStateConflict(
                    operation_id,
                    "completed_unexpected_work_order",
                )
            return result, None

        if status is OperationStatus.FAILED:
            if payload is None:
                raise RecoveryStateConflict(operation_id, "failed_error_missing")
            try:
                error = OperationError.model_validate(payload)
            except ValidationError:
                raise RecoveryStateConflict(
                    operation_id,
                    "invalid_failed_error",
                ) from None
            if error.code != error_code:
                raise RecoveryStateConflict(
                    operation_id,
                    "failed_error_code_mismatch",
                )
            return None, error

        if status in {
            OperationStatus.REJECTED,
            OperationStatus.ABORTED,
            OperationStatus.EXPIRED,
        }:
            if payload is not None or error_code is not None:
                raise RecoveryStateConflict(
                    operation_id,
                    "empty_terminal_facts_required",
                )
            if work_order is not None:
                raise RecoveryStateConflict(
                    operation_id,
                    "empty_terminal_work_order_present",
                )
            return None, None

        if payload is not None or error_code is not None:
            raise RecoveryStateConflict(
                operation_id,
                "nonterminal_facts_present",
            )
        return None, None

    def _audit_event(self, row: RowMapping) -> AuditEventView:
        payload = cast(dict[str, JsonValue], row["payload"])
        immutable_payload = MappingProxyType(self._copy_json(payload))
        return AuditEventView(
            id=cast(UUID, row["id"]),
            operation_id=cast(UUID, row["operation_id"]),
            sequence=int(row["sequence"]),
            event_type=str(row["event_type"]),
            payload=immutable_payload,
            created_at=cast(datetime, row["created_at"]),
        )

    def _snapshot_approval_binding(
        self,
        operation_id: UUID,
        snapshot: OperationSnapshot,
    ) -> ApprovalBinding | None:
        value = snapshot.risk.get("approval_binding")
        if value is None:
            return None
        try:
            return ApprovalBinding.model_validate(value)
        except ValidationError:
            raise RecoveryStateConflict(
                operation_id,
                "invalid_snapshot_approval_binding",
            ) from None

    def _approval_view(
        self,
        operation_id: UUID,
        row: RowMapping | None,
        *,
        snapshot_binding: ApprovalBinding | None,
    ) -> ApprovalRowView | None:
        if row is None:
            return None
        binding: ApprovalBinding | None
        binding_payload = row["binding_payload"]
        if binding_payload is not None:
            try:
                binding = ApprovalBinding.model_validate(binding_payload)
            except ValidationError:
                raise RecoveryStateConflict(
                    operation_id,
                    "invalid_approval_binding",
                ) from None
        else:
            binding_names = (
                "inventory_evidence_id",
                "policy_evidence_id",
                "rule_version",
                "decision_facts_hash",
                "plan_hash",
                "recommended_quantity",
            )
            binding_values = {name: row[name] for name in binding_names}
            populated = [value is not None for value in binding_values.values()]
            if not any(populated):
                binding = None
            elif not all(populated):
                raise RecoveryStateConflict(operation_id, "partial_approval_binding")
            else:
                try:
                    binding = ApprovalBinding.model_validate(binding_values)
                except ValidationError:
                    raise RecoveryStateConflict(
                        operation_id,
                        "invalid_approval_binding",
                    ) from None
        if binding is not None and (snapshot_binding is None or binding != snapshot_binding):
            raise RecoveryStateConflict(
                operation_id,
                "approval_binding_mismatch",
            )
        try:
            decision = ApprovalDecision(str(row["decision"]))
        except ValueError:
            raise RecoveryStateConflict(
                operation_id,
                "invalid_approval_decision",
            ) from None
        return ApprovalRowView(
            id=cast(UUID, row["id"]),
            operation_id=cast(UUID, row["operation_id"]),
            approver_id=str(row["approver_id"]),
            decision=decision,
            reason=str(row["reason"]),
            created_at=cast(datetime, row["created_at"]),
            binding=binding,
            approval_cycle=int(row["approval_cycle"]),
        )

    def _work_order_view(
        self,
        operation_id: UUID,
        row: RowMapping | None,
    ) -> WorkOrderRecord | None:
        if row is None:
            return None
        values = dict(row)
        values["payload"] = self._copy_json(cast(dict[str, JsonValue], row["payload"]))
        try:
            return WorkOrderRecord.model_validate(values)
        except ValidationError:
            raise RecoveryStateConflict(
                operation_id,
                "invalid_work_order_row",
            ) from None

    def _copy_json(self, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            json.loads(canonical_payload_json(value)),
        )

    def _require_timezone(self, value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
