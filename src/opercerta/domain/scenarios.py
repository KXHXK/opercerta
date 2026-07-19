from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    model_validator,
)

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
SafeCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    ),
]


class ScenarioKind(StrEnum):
    INVENTORY = "inventory"
    EQUIPMENT = "equipment"
    TASK = "task"


class ReplenishmentParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["replenishment"] = "replenishment"
    recommended_quantity: PositiveInt


class RepairParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["repair"] = "repair"
    alert_code: SafeCode
    priority: Literal["normal", "high", "urgent"]


class TaskRecoveryParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["task_recovery"] = "task_recovery"
    recovery_action: Literal["manual_requeue"]


ActionParameters = Annotated[
    ReplenishmentParameters | RepairParameters | TaskRecoveryParameters,
    Field(discriminator="kind"),
]


class ApprovalBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: ScenarioKind
    subject_evidence_id: UUID
    policy_evidence_id: UUID
    rule_version: Version
    decision_facts_hash: Digest
    plan_hash: Digest
    parameters: ActionParameters

    @model_validator(mode="before")
    @classmethod
    def upgrade_inventory_binding(cls, value: object) -> object:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="python")
        if not isinstance(value, dict) or "scenario" in value:
            return value
        required = {
            "inventory_evidence_id",
            "policy_evidence_id",
            "rule_version",
            "decision_facts_hash",
            "plan_hash",
            "recommended_quantity",
        }
        if set(value) != required:
            return value
        return {
            "scenario": ScenarioKind.INVENTORY,
            "subject_evidence_id": value["inventory_evidence_id"],
            "policy_evidence_id": value["policy_evidence_id"],
            "rule_version": value["rule_version"],
            "decision_facts_hash": value["decision_facts_hash"],
            "plan_hash": value["plan_hash"],
            "parameters": {
                "kind": "replenishment",
                "recommended_quantity": value["recommended_quantity"],
            },
        }

    @model_validator(mode="after")
    def require_matching_scenario(self) -> Self:
        expected_kind = {
            ScenarioKind.INVENTORY: "replenishment",
            ScenarioKind.EQUIPMENT: "repair",
            ScenarioKind.TASK: "task_recovery",
        }[self.scenario]
        if self.parameters.kind != expected_kind:
            raise ValueError("approval parameters must match scenario")
        return self


class ScenarioError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
    ]
