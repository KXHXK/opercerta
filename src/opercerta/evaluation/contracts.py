import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, model_validator

CaseId = Annotated[
    str,
    StringConstraints(pattern=r"^RPL-(?:00[1-9]|0[12][0-9]|030)$"),
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
RuleReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvalActor(StrEnum):
    ANONYMOUS = "anonymous"
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CaseId
    title: Title
    rule_refs: tuple[RuleReference, ...]
    actor: EvalActor
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

    suite_version: Annotated[str, StringConstraints(pattern=r"^replenishment-v[1-9][0-9]*$")]
    cases: tuple[EvalCase, ...]

    @model_validator(mode="after")
    def require_frozen_case_ids(self) -> "EvalSuite":
        expected = [f"RPL-{number:03d}" for number in range(1, 31)]
        if [case.id for case in self.cases] != expected:
            raise ValueError("case_ids_must_be_rpl_001_through_rpl_030")
        return self


def load_suite(path: Path) -> EvalSuite:
    return EvalSuite.model_validate(json.loads(path.read_text(encoding="utf-8")))
