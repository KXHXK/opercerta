from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from opercerta.application.signal_detection import ScanTarget, SignalDetector
from opercerta.domain.contracts import ObjectType
from opercerta.domain.maintenance import (
    AlertSeverity,
    EquipmentEvidence,
    EquipmentState,
    MaintenancePolicyEvidence,
    MaintenancePriority,
    PriorityMapping,
)
from opercerta.domain.replenishment import InventoryEvidence, PolicyEvidence
from opercerta.domain.signals import OperationalSignal, SignalDraft, SignalStatus
from opercerta.domain.task_recovery import (
    TaskEvidence,
    TaskRecoveryPolicyEvidence,
    TaskState,
)

NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)


class RecordingSignals:
    def __init__(self) -> None:
        self.drafts: list[SignalDraft] = []

    async def upsert_detected(self, draft: SignalDraft) -> OperationalSignal:
        self.drafts.append(draft)
        return OperationalSignal(
            id=UUID(int=len(self.drafts)),
            dedup_key=f"signal:v1:{draft.signal_type.value}:{draft.object_id}:{draft.facts_hash}",
            **draft.model_dump(),
            status=SignalStatus.OPEN,
            operation_id=None,
            updated_at=draft.detected_at,
            resolved_at=None,
        )


class DemoGateway:
    async def get_inventory(self, sku: str) -> InventoryEvidence:
        available = 12 if sku == "SKU-LOW-001" else 25
        return InventoryEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000011"),
            sku=sku,
            on_hand_quantity=available,
            reserved_quantity=0,
            captured_at=NOW,
            source_version="inventory.v1",
        )

    async def get_policy(self, sku: str) -> PolicyEvidence:
        return PolicyEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000012"),
            action="replenish_inventory",
            sku=sku,
            reorder_point=15,
            target_stock=30,
            minimum_order_quantity=1,
            maximum_order_quantity=100,
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="inventory-policy.v1",
            captured_at=NOW,
        )

    async def get_equipment(self, equipment_id: str) -> EquipmentEvidence:
        return EquipmentEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000021"),
            equipment_id=equipment_id,
            state=EquipmentState.DEGRADED,
            alert_code="TEMP_HIGH",
            severity=AlertSeverity.WARNING,
            last_heartbeat=NOW - timedelta(seconds=10),
            captured_at=NOW,
            source_version="equipment.v1",
        )

    async def get_maintenance_policy(self, equipment_id: str) -> MaintenancePolicyEvidence:
        return MaintenancePolicyEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000022"),
            action="repair_equipment",
            equipment_id=equipment_id,
            allowed_alert_levels=("warning", "critical"),
            maximum_heartbeat_age_seconds=120,
            priority_mapping=PriorityMapping(
                warning=MaintenancePriority.HIGH,
                critical=MaintenancePriority.URGENT,
                stale_heartbeat=MaintenancePriority.HIGH,
            ),
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="maintenance-policy.v1",
            captured_at=NOW,
        )

    async def get_task(self, task_id: str) -> TaskEvidence:
        return TaskEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000031"),
            task_id=task_id,
            state=TaskState.BLOCKED,
            due_at=NOW + timedelta(hours=1),
            last_progress_at=NOW - timedelta(minutes=5),
            blocker_code="UPSTREAM_WAIT",
            retry_count=0,
            captured_at=NOW,
            source_version="task.v1",
        )

    async def get_task_recovery_policy(self, task_id: str) -> TaskRecoveryPolicyEvidence:
        return TaskRecoveryPolicyEvidence(
            evidence_id=UUID("00000000-0000-0000-0000-000000000032"),
            action="recover_task",
            task_id=task_id,
            blocked_states=(TaskState.BLOCKED,),
            overdue_grace_seconds=60,
            maximum_retry_count=3,
            recovery_action="manual_requeue",
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="task-policy.v1",
            captured_at=NOW,
        )


@pytest.mark.asyncio
async def test_scan_detects_three_business_anomalies_without_a_model() -> None:
    repository = RecordingSignals()
    result = await SignalDetector(DemoGateway(), repository).scan(now=NOW)

    assert [signal.object_id for signal in result.signals] == [
        "SKU-LOW-001",
        "EQ-PUMP-001",
        "TASK-BLOCKED-001",
    ]
    assert result.issues == ()
    assert len(repository.drafts) == 3
    assert result.scanned_at == NOW


@pytest.mark.asyncio
async def test_normal_object_does_not_create_a_signal() -> None:
    repository = RecordingSignals()
    result = await SignalDetector(
        DemoGateway(),
        repository,
        targets=(ScanTarget(ObjectType.INVENTORY, "SKU-NORMAL-001"),),
    ).scan(now=NOW)

    assert result.signals == ()
    assert repository.drafts == []


@pytest.mark.asyncio
async def test_one_failed_source_does_not_hide_other_detected_signals() -> None:
    class PartiallyUnavailableGateway(DemoGateway):
        async def get_equipment(self, equipment_id: str) -> EquipmentEvidence:
            raise TimeoutError("internal address must not leak")

    result = await SignalDetector(PartiallyUnavailableGateway(), RecordingSignals()).scan(now=NOW)

    assert [signal.object_id for signal in result.signals] == [
        "SKU-LOW-001",
        "TASK-BLOCKED-001",
    ]
    assert len(result.issues) == 1
    assert result.issues[0].object_id == "EQ-PUMP-001"
    assert result.issues[0].code == "signal_source_unavailable"
