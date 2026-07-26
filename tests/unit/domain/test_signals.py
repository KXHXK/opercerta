from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.maintenance import MaintenanceEvidenceBundle, assess_maintenance
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.replenishment import EvidenceBundle, assess_replenishment
from opercerta.domain.signals import (
    OperationalSignal,
    SignalDraft,
    SignalSeverity,
    SignalStatus,
    SignalType,
    build_signal_draft,
    derive_signal_dedup_key,
    derive_signal_retry_dedup_key,
    signal_status_for_operation_terminal,
)
from opercerta.domain.task_recovery import TaskRecoveryEvidenceBundle, assess_task_recovery
from opercerta.tools.catalog import SyntheticCatalog

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def catalog() -> SyntheticCatalog:
    return SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
        equipment_path=ROOT / "data" / "synthetic" / "equipment.json",
        maintenance_policy_path=ROOT / "data" / "synthetic" / "maintenance_policies.json",
        task_path=ROOT / "data" / "synthetic" / "tasks.json",
        task_recovery_policy_path=ROOT / "data" / "synthetic" / "task_recovery_policies.json",
    )


def test_normal_inventory_does_not_create_a_signal(catalog: SyntheticCatalog) -> None:
    assessment = assess_replenishment(
        EvidenceBundle(
            inventory=catalog.inventory_snapshot("SKU-NORMAL-001", NOW),
            policy=catalog.policy_constraints("SKU-NORMAL-001", NOW),
        ),
        NOW,
    )

    assert build_signal_draft(assessment, NOW) is None


def test_inventory_shortage_signal_uses_deterministic_assessment(
    catalog: SyntheticCatalog,
) -> None:
    assessment = assess_replenishment(
        EvidenceBundle(
            inventory=catalog.inventory_snapshot("SKU-LOW-001", NOW),
            policy=catalog.policy_constraints("SKU-LOW-001", NOW),
        ),
        NOW,
    )

    signal = build_signal_draft(assessment, NOW)

    assert signal is not None
    assert signal.signal_type is SignalType.INVENTORY_SHORTAGE
    assert signal.severity is SignalSeverity.MEDIUM
    assert signal.reason_code == "inventory_below_reorder_point"
    assert signal.facts == {
        "available_quantity": 12,
        "recommended_quantity": 18,
        "reorder_point": 15,
        "target_stock": 30,
    }
    assert signal.facts_hash == assessment.decision_facts_hash


def test_equipment_and_task_signals_keep_scenario_specific_reason(
    catalog: SyntheticCatalog,
) -> None:
    maintenance = assess_maintenance(
        MaintenanceEvidenceBundle(
            equipment=catalog.equipment_status("EQ-PUMP-001", NOW),
            policy=catalog.maintenance_policy_constraints("EQ-PUMP-001", NOW),
        ),
        NOW,
    )
    task = assess_task_recovery(
        TaskRecoveryEvidenceBundle(
            task=catalog.task_status("TASK-BLOCKED-001", NOW),
            policy=catalog.task_recovery_policy_constraints("TASK-BLOCKED-001", NOW),
        ),
        NOW,
    )

    equipment_signal = build_signal_draft(maintenance, NOW)
    task_signal = build_signal_draft(task, NOW)

    assert equipment_signal is not None
    assert equipment_signal.signal_type is SignalType.EQUIPMENT_ATTENTION
    assert equipment_signal.severity is SignalSeverity.HIGH
    assert equipment_signal.reason_code == "equipment_alert"
    assert task_signal is not None
    assert task_signal.signal_type is SignalType.TASK_BLOCKED
    assert task_signal.reason_code == "task_blocked"


def test_signal_dedup_key_is_stable_and_bound_to_facts(
    catalog: SyntheticCatalog,
) -> None:
    assessment = assess_replenishment(
        EvidenceBundle(
            inventory=catalog.inventory_snapshot("SKU-LOW-001", NOW),
            policy=catalog.policy_constraints("SKU-LOW-001", NOW),
        ),
        NOW,
    )
    signal = build_signal_draft(assessment, NOW)
    assert signal is not None

    assert derive_signal_dedup_key(signal) == (
        f"signal:v1:inventory_shortage:SKU-LOW-001:{assessment.decision_facts_hash}"
    )


def test_signal_contract_rejects_untrusted_hash() -> None:
    with pytest.raises(ValidationError):
        SignalDraft(
            signal_type="inventory_shortage",
            object_type="inventory",
            object_id="SKU-LOW-001",
            source="demo_watchlist.v1",
            severity="medium",
            reason_code="inventory_below_reorder_point",
            facts_hash="not-a-hash",
            facts={"available_quantity": 12},
            detected_at=NOW,
        )


@pytest.mark.parametrize(
    ("operation_status", "signal_status"),
    [
        (OperationStatus.COMPLETED, SignalStatus.RESOLVED),
        (OperationStatus.REJECTED, SignalStatus.RESOLVED),
        (OperationStatus.ABORTED, SignalStatus.ATTENTION_REQUIRED),
        (OperationStatus.EXPIRED, SignalStatus.ATTENTION_REQUIRED),
        (OperationStatus.FAILED, SignalStatus.ATTENTION_REQUIRED),
    ],
)
def test_terminal_operation_maps_to_signal_feedback(
    operation_status: OperationStatus,
    signal_status: SignalStatus,
) -> None:
    assert signal_status_for_operation_terminal(operation_status) is signal_status


def test_nonterminal_operation_does_not_close_signal() -> None:
    assert signal_status_for_operation_terminal(OperationStatus.AWAITING_APPROVAL) is None


def test_retry_dedup_key_is_stable_and_bound_to_predecessor() -> None:
    predecessor_id = UUID("11111111-1111-1111-1111-111111111111")

    assert derive_signal_retry_dedup_key(predecessor_id) == (
        "signal:retry:v1:11111111-1111-1111-1111-111111111111"
    )


def test_operational_signal_preserves_successor_lineage() -> None:
    predecessor_id = UUID("11111111-1111-1111-1111-111111111111")
    signal = OperationalSignal(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        dedup_key=derive_signal_retry_dedup_key(predecessor_id),
        signal_type="inventory_shortage",
        object_type="inventory",
        object_id="SKU-LOW-001",
        source="demo_watchlist.v1",
        severity="medium",
        reason_code="inventory_below_reorder_point",
        facts_hash="a" * 64,
        facts={"available_quantity": 12},
        status="open",
        operation_id=None,
        predecessor_signal_id=predecessor_id,
        detected_at=NOW,
        updated_at=NOW,
        resolved_at=None,
    )

    assert signal.predecessor_signal_id == predecessor_id
