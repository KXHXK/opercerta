from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_evaluation_script_exposes_frozen_suite_and_output_arguments() -> None:
    script = (ROOT / "scripts" / "run_replenishment_evaluation.py").read_text(encoding="utf-8")

    assert "--suite" in script
    assert "--output-dir" in script
    assert "test_frozen_suite.py" in script
    assert "OPERCERTA_EVALUATION_OUTPUT_DIR" in script


def test_three_business_evaluation_script_uses_versioned_suite() -> None:
    script = (ROOT / "scripts" / "run_opercerta_evaluation.py").read_text(encoding="utf-8")

    assert "opercerta-three-business-v1.json" in script
    assert "--output-dir" in script
    assert "test_frozen_suite.py" in script


def test_performance_matrix_reports_only_measured_dimensions() -> None:
    script = (ROOT / "scripts" / "run_performance_matrix.py").read_text(encoding="utf-8")

    for required in (
        "cache_mode",
        "tool_mode",
        "repetitions",
        "p50_ms",
        "p95_ms",
        "error_rate",
        "completed_operations",
        "tool_calls",
        "cache_hits",
        "model_usage",
    ):
        assert required in script
