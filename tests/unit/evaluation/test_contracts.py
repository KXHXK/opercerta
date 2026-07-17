import pytest
from pydantic import ValidationError

from opercerta.evaluation.contracts import EvalCase, EvalSuite


def valid_case(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "title": "合成契约用例",
        "rule_refs": ["docs/specs/2026-07-14-opercerta-design.md#api"],
        "actor": "operator",
        "steps": [{"method": "GET", "path": "/health/live"}],
        "expected": {"status_code": 200},
    }


def test_case_rejects_empty_rule_references() -> None:
    case = valid_case("RPL-001")
    case["rule_refs"] = []

    with pytest.raises(ValidationError):
        EvalCase.model_validate(case)


@pytest.mark.parametrize("actor", ["administrator", "anonymous-user", ""])
def test_case_rejects_unknown_actor(actor: str) -> None:
    case = valid_case("RPL-001")
    case["actor"] = actor

    with pytest.raises(ValidationError):
        EvalCase.model_validate(case)


def test_suite_rejects_duplicate_or_non_contiguous_ids() -> None:
    with pytest.raises(ValueError, match="case_ids_must_be_rpl_001_through_rpl_030"):
        EvalSuite.model_validate(
            {
                "suite_version": "replenishment-v1",
                "cases": [valid_case("RPL-001"), valid_case("RPL-001")],
            }
        )
