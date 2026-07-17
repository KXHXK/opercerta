from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_evaluation_script_exposes_frozen_suite_and_output_arguments() -> None:
    script = (ROOT / "scripts" / "run_replenishment_evaluation.py").read_text(encoding="utf-8")

    assert "--suite" in script
    assert "--output-dir" in script
    assert "test_frozen_suite.py" in script
    assert "OPERCERTA_EVALUATION_OUTPUT_DIR" in script
