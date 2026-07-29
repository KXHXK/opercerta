from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "DOCUMENT_INDEX.md"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_document_index.py"


def _root_table_rows() -> list[list[str]]:
    lines = INDEX.read_text(encoding="utf-8").splitlines()
    headings = [index for index, line in enumerate(lines) if line.startswith("## ")]
    root_section = lines[headings[1] : headings[2]]
    rows: list[list[str]] = []
    for line in root_section:
        if re.match(r"^\| \d+ \|", line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def _current_markdown_paths() -> set[str]:
    excluded_parts = {".git", ".pytest_cache", ".worktrees", ".venv", "node_modules"}
    return {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.md")
        if not excluded_parts.intersection(path.relative_to(ROOT).parts)
    }


def test_root_document_table_matches_the_current_worktree() -> None:
    rows = _root_table_rows()
    numbers = [int(row[0]) for row in rows]
    indexed_paths = {row[2].strip("`") for row in rows}

    assert numbers == list(range(1, len(rows) + 1))
    assert indexed_paths == _current_markdown_paths()


def test_historical_worktree_tables_are_explicitly_labeled() -> None:
    headings = [
        line
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ") and "Worktree" in line
    ]

    assert headings
    assert all(line.startswith("## 历史 Worktree：") for line in headings)


def test_document_index_verifier_passes() -> None:
    assert VERIFY_SCRIPT.is_file()
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
