from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.errors import EvidenceExpired
from opercerta.domain.maintenance import (
    EquipmentEvidence,
    MaintenanceEvidenceBundle,
    MaintenancePriority,
    assess_maintenance,
    build_maintenance_approval_binding,
    build_maintenance_plan,
)
from opercerta.domain.replenishment import ModelPlanExplanation
from opercerta.domain.scenarios import RepairParameters, ScenarioKind

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
EQUIPMENT_ID = UUID("10000000-0000-4000-8000-000000000001")
POLICY_ID = UUID("20000000-0000-4000-8000-000000000002")


def bundle(
    *,
    state: str = "offline",
    alert_code: str | None = "MOTOR_OVERHEAT",
    severity: str = "critical",
    last_heartbeat: datetime = NOW - timedelta(seconds=60),
    captured_at: datetime = NOW,
) -> MaintenanceEvidenceBundle:
    return MaintenanceEvidenceBundle.model_validate(
        {
            "equipment": {
                "evidence_id": EQUIPMENT_ID,
                "equipment_id": "EQ-PUMP-001",
                "state": state,
                "alert_code": alert_code,
                "severity": severity,
                "last_heartbeat": last_heartbeat,
                "captured_at": captured_at,
                "source_version": "equipment-seed-v1",
            },
            "policy": {
                "evidence_id": POLICY_ID,
                "action": "repair_equipment",
                "equipment_id": "EQ-PUMP-001",
                "allowed_alert_levels": ["warning", "critical"],
                "maximum_heartbeat_age_seconds": 300,
                "priority_mapping": {
                    "warning": "high",
                    "critical": "urgent",
                    "stale_heartbeat": "urgent",
                },
                "evidence_ttl_seconds": 300,
                "approval_required": True,
                "rule_version": "maintenance-v1",
                "captured_at": captured_at,
            },
        }
    )


def test_maintenance_rejects_naive_heartbeat() -> None:
    payload = bundle().equipment.model_dump(mode="python")
    payload["last_heartbeat"] = datetime(2026, 7, 20, 7, 59)

    with pytest.raises(ValidationError, match="timezone"):
        EquipmentEvidence.model_validate(payload)


def test_equipment_and_policy_identifiers_must_match() -> None:
    payload = bundle().model_dump(mode="python")
    payload["policy"]["equipment_id"] = "EQ-OTHER-001"

    with pytest.raises(ValidationError, match="equipment ID"):
        MaintenanceEvidenceBundle.model_validate(payload)


def test_healthy_equipment_needs_no_repair() -> None:
    assessment = assess_maintenance(
        bundle(state="healthy", alert_code=None, severity="none"),
        NOW,
    )

    assert assessment.maintenance_required is False
    assert assessment.priority is None
    assert assessment.reason is None


def test_critical_alert_requires_urgent_repair() -> None:
    assessment = assess_maintenance(bundle(), NOW)

    assert assessment.maintenance_required is True
    assert assessment.priority is MaintenancePriority.URGENT
    assert assessment.reason == "alert"


def test_stale_heartbeat_requires_repair_after_not_at_boundary() -> None:
    boundary = assess_maintenance(
        bundle(
            state="healthy",
            alert_code=None,
            severity="none",
            last_heartbeat=NOW - timedelta(seconds=300),
        ),
        NOW,
    )
    stale = assess_maintenance(
        bundle(
            state="healthy",
            alert_code=None,
            severity="none",
            last_heartbeat=NOW - timedelta(seconds=301),
        ),
        NOW,
    )

    assert boundary.maintenance_required is False
    assert stale.maintenance_required is True
    assert stale.reason == "stale_heartbeat"
    assert stale.priority is MaintenancePriority.URGENT


def test_expired_equipment_evidence_fails_closed() -> None:
    with pytest.raises(EvidenceExpired, match="evidence_expired"):
        assess_maintenance(
            bundle(
                captured_at=NOW - timedelta(seconds=300),
                last_heartbeat=NOW - timedelta(seconds=360),
            ),
            NOW,
        )


def test_plan_and_binding_cover_exact_equipment_facts() -> None:
    evidence = bundle()
    assessment = assess_maintenance(evidence, NOW)
    plan = build_maintenance_plan(
        assessment,
        ModelPlanExplanation(
            summary="为过热泵创建紧急维修工单。",
            rationale="告警和心跳证据已通过版本化规则校验。",
        ),
        evidence.policy.rule_version,
    )
    binding = build_maintenance_approval_binding(evidence, plan)

    assert binding.scenario is ScenarioKind.EQUIPMENT
    assert binding.subject_evidence_id == EQUIPMENT_ID
    assert binding.parameters == RepairParameters(
        alert_code="MOTOR_OVERHEAT",
        priority="urgent",
    )
    assert plan.plan_hash == binding.plan_hash
    assert plan.decision_facts_hash == binding.decision_facts_hash
