import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from opercerta.domain.contracts import ObjectType
from opercerta.domain.maintenance import (
    EquipmentEvidence,
    MaintenanceEvidenceBundle,
    MaintenancePolicyEvidence,
    assess_maintenance,
)
from opercerta.domain.replenishment import (
    EvidenceBundle,
    InventoryEvidence,
    PolicyEvidence,
    assess_replenishment,
)
from opercerta.domain.signals import OperationalSignal, SignalDraft, build_signal_draft
from opercerta.domain.task_recovery import (
    TaskEvidence,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPolicyEvidence,
    assess_task_recovery,
)


class SignalEvidenceGateway(Protocol):
    async def get_inventory(self, sku: str) -> InventoryEvidence: ...

    async def get_policy(self, sku: str) -> PolicyEvidence: ...

    async def get_equipment(self, equipment_id: str) -> EquipmentEvidence: ...

    async def get_maintenance_policy(self, equipment_id: str) -> MaintenancePolicyEvidence: ...

    async def get_task(self, task_id: str) -> TaskEvidence: ...

    async def get_task_recovery_policy(self, task_id: str) -> TaskRecoveryPolicyEvidence: ...


class SignalStore(Protocol):
    async def upsert_detected(self, draft: SignalDraft) -> OperationalSignal: ...


@dataclass(frozen=True, slots=True)
class ScanTarget:
    object_type: ObjectType
    object_id: str


@dataclass(frozen=True, slots=True)
class SignalScanIssue:
    object_type: ObjectType
    object_id: str
    code: str


@dataclass(frozen=True, slots=True)
class SignalScanResult:
    signals: tuple[OperationalSignal, ...]
    issues: tuple[SignalScanIssue, ...]
    scanned_count: int
    scanned_at: datetime


DEFAULT_SIGNAL_TARGETS = (
    ScanTarget(ObjectType.INVENTORY, "SKU-LOW-001"),
    ScanTarget(ObjectType.EQUIPMENT, "EQ-PUMP-001"),
    ScanTarget(ObjectType.TASK, "TASK-BLOCKED-001"),
)


class SignalDetector:
    def __init__(
        self,
        gateway: SignalEvidenceGateway,
        store: SignalStore,
        *,
        targets: tuple[ScanTarget, ...] = DEFAULT_SIGNAL_TARGETS,
    ) -> None:
        self._gateway = gateway
        self._store = store
        self._targets = targets

    async def scan(self, *, now: datetime | None = None) -> SignalScanResult:
        detected_at = now or datetime.now(UTC)
        signals: list[OperationalSignal] = []
        issues: list[SignalScanIssue] = []
        for target in self._targets:
            try:
                draft = await self._detect(target, detected_at)
            except Exception:
                issues.append(
                    SignalScanIssue(
                        object_type=target.object_type,
                        object_id=target.object_id,
                        code="signal_source_unavailable",
                    )
                )
                continue
            if draft is not None:
                signals.append(await self._store.upsert_detected(draft))
        return SignalScanResult(
            signals=tuple(signals),
            issues=tuple(issues),
            scanned_count=len(self._targets),
            scanned_at=detected_at,
        )

    async def _detect(self, target: ScanTarget, now: datetime) -> SignalDraft | None:
        if target.object_type is ObjectType.INVENTORY:
            inventory, inventory_policy = await asyncio.gather(
                self._gateway.get_inventory(target.object_id),
                self._gateway.get_policy(target.object_id),
            )
            return build_signal_draft(
                assess_replenishment(
                    EvidenceBundle(inventory=inventory, policy=inventory_policy), now
                ),
                now,
            )
        elif target.object_type is ObjectType.EQUIPMENT:
            equipment, maintenance_policy = await asyncio.gather(
                self._gateway.get_equipment(target.object_id),
                self._gateway.get_maintenance_policy(target.object_id),
            )
            return build_signal_draft(
                assess_maintenance(
                    MaintenanceEvidenceBundle(
                        equipment=equipment,
                        policy=maintenance_policy,
                    ),
                    now,
                ),
                now,
            )
        elif target.object_type is ObjectType.TASK:
            task, task_policy = await asyncio.gather(
                self._gateway.get_task(target.object_id),
                self._gateway.get_task_recovery_policy(target.object_id),
            )
            return build_signal_draft(
                assess_task_recovery(
                    TaskRecoveryEvidenceBundle(task=task, policy=task_policy), now
                ),
                now,
            )
        raise ValueError("unsupported signal target")
