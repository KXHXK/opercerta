from pathlib import Path

from opercerta.evaluation.contracts import load_suite


def test_three_business_suite_preserves_inventory_and_covers_all_scenarios() -> None:
    original = load_suite(Path("data/evals/replenishment-v3.json"))
    suite = load_suite(Path("data/evals/opercerta-three-business-v1.json"))

    assert {case.id for case in original.cases} <= {case.id for case in suite.cases}
    assert {case.scenario for case in suite.cases} == {"inventory", "equipment", "task"}
    assert len(suite.cases) > len(original.cases)


def test_new_scenario_cases_declare_observable_expected_contracts() -> None:
    suite = load_suite(Path("data/evals/opercerta-three-business-v1.json"))
    scenario_cases = [case for case in suite.cases if case.scenario != "inventory"]

    assert scenario_cases
    for case in scenario_cases:
        assert case.expected_tools
        assert "status_code" in case.expected
        assert "terminal_status" in case.expected
        assert "approval_count" in case.expected
        assert "work_order_count" in case.expected
