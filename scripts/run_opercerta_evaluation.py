"""Run the versioned three-business suite through real integration boundaries."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("data/evals/opercerta-three-business-v1.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/evals"))
    args = parser.parse_args()

    environment = os.environ.copy()
    environment["OPERCERTA_EVALUATION_SUITE"] = str(args.suite)
    environment["OPERCERTA_EVALUATION_OUTPUT_DIR"] = str(args.output_dir)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/evaluation/test_frozen_suite.py",
            "-q",
        ],
        check=False,
        env=environment,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
