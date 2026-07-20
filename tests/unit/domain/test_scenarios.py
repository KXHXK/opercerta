from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

SUBJECT_EVIDENCE_ID = UUID("10000000-0000-4000-8000-000000000001")
POLICY_EVIDENCE_ID = UUID("20000000-0000-4000-8000-000000000002")


def approval_binding_type():
    try:
        return import_module("opercerta.domain.scenarios").ApprovalBinding
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"ApprovalBinding is unavailable: {exc}", pytrace=False)


def valid_binding() -> dict[str, object]:
    return {
        "scenario": "inventory",
        "subject_evidence_id": SUBJECT_EVIDENCE_ID,
        "policy_evidence_id": POLICY_EVIDENCE_ID,
        "rule_version": "replenishment-v1",
        "decision_facts_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "parameters": {
            "kind": "replenishment",
            "recommended_quantity": 18,
        },
    }


def test_inventory_binding_accepts_replenishment_parameters() -> None:
    binding = approval_binding_type().model_validate(valid_binding())

    assert binding.scenario.value == "inventory"
    assert binding.parameters.kind == "replenishment"


@pytest.mark.parametrize(
    ("scenario", "parameters"),
    [
        (
            "equipment",
            {"kind": "replenishment", "recommended_quantity": 18},
        ),
        (
            "task",
            {
                "kind": "repair",
                "alert_code": "MOTOR_OVERHEAT",
                "priority": "urgent",
            },
        ),
        (
            "inventory",
            {
                "kind": "task_recovery",
                "recovery_action": "manual_requeue",
            },
        ),
    ],
)
def test_binding_rejects_parameters_for_another_scenario(
    scenario: str,
    parameters: dict[str, object],
) -> None:
    value = valid_binding() | {
        "scenario": scenario,
        "parameters": parameters,
    }

    with pytest.raises(ValidationError, match="match scenario"):
        approval_binding_type().model_validate(value)


def test_binding_rejects_extra_authoritative_parameter() -> None:
    value = valid_binding()
    value["parameters"] = {
        "kind": "replenishment",
        "recommended_quantity": 18,
        "approved": True,
    }

    with pytest.raises(ValidationError):
        approval_binding_type().model_validate(value)


def test_binding_is_frozen() -> None:
    binding = approval_binding_type().model_validate(valid_binding())

    with pytest.raises(ValidationError):
        binding.rule_version = "changed"
