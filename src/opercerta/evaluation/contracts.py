import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, model_validator

CaseId = Annotated[
    str,
    StringConstraints(pattern=r"^(?:RPL-(?:00[1-9]|0[12][0-9]|030)|EQP-00[1-6]|TSK-00[1-6])$"),
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
RuleReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvalActor(StrEnum):
    ANONYMOUS = "anonymous"
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


class EvalScenario(StrEnum):
    INVENTORY = "inventory"
    EQUIPMENT = "equipment"
    TASK = "task"


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CaseId
    title: Title
    rule_refs: tuple[RuleReference, ...]
    actor: EvalActor
    scenario: EvalScenario = EvalScenario.INVENTORY
    expected_tools: tuple[str, ...] = ()
    steps: tuple[dict[str, JsonValue], ...]
    expected: dict[str, JsonValue]

    @model_validator(mode="after")
    def require_evaluable_content(self) -> "EvalCase":
        if not self.rule_refs:
            raise ValueError("rule_refs_must_not_be_empty")
        if not self.steps:
            raise ValueError("steps_must_not_be_empty")
        if "status_code" not in self.expected:
            raise ValueError("expected_status_code_required")
        return self


class EvalSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_version: Annotated[
        str,
        StringConstraints(pattern=r"^(?:replenishment-v[1-9][0-9]*|opercerta-three-business-v1)$"),
    ]
    extends: str | None = None
    cases: tuple[EvalCase, ...]

    @model_validator(mode="after")
    def require_frozen_case_ids(self) -> "EvalSuite":
        inventory_ids = [f"RPL-{number:03d}" for number in range(1, 31)]
        ids = [case.id for case in self.cases]
        if self.suite_version.startswith("replenishment-"):
            if ids != inventory_ids:
                raise ValueError("case_ids_must_be_rpl_001_through_rpl_030")
            return self
        expected = (
            inventory_ids
            + [f"EQP-{number:03d}" for number in range(1, 7)]
            + [f"TSK-{number:03d}" for number in range(1, 7)]
        )
        if ids != expected:
            raise ValueError("three_business_case_ids_must_be_frozen_and_ordered")
        if {case.scenario for case in self.cases} != set(EvalScenario):
            raise ValueError("three_business_suite_must_cover_all_scenarios")
        return self


def load_suite(path: Path) -> EvalSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evaluation_suite_must_be_an_object")
    extends = payload.get("extends")
    if extends is not None:
        if extends != "replenishment-v3.json":
            raise ValueError("unsupported_evaluation_suite_base")
        base = load_suite(path.with_name(extends))
        declared_cases = payload.get("cases")
        if not isinstance(declared_cases, list):
            raise ValueError("evaluation_suite_cases_must_be_a_list")
        payload["cases"] = [case.model_dump(mode="json") for case in base.cases] + declared_cases
    return EvalSuite.model_validate(payload)
