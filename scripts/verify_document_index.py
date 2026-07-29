from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "DOCUMENT_INDEX.md"
EXCLUDED_PARTS = {".git", ".pytest_cache", ".worktrees", ".venv", "node_modules"}
ROOT_HEADING = re.compile(r"^## 根工作树（(?P<count>\d+) 份）$")
ROW = re.compile(r"^\| (?P<number>\d+) \|")


def current_markdown_paths() -> set[str]:
    paths: set[str] = set()
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        paths.add(relative.as_posix())
    return paths


def root_table() -> tuple[int, list[list[str]]]:
    lines = INDEX.read_text(encoding="utf-8").splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if ROOT_HEADING.match(line)), None
    )
    if heading_index is None:
        raise ValueError("missing root worktree heading with a declared document count")

    heading_match = ROOT_HEADING.match(lines[heading_index])
    assert heading_match is not None
    declared_count = int(heading_match.group("count"))
    rows: list[list[str]] = []
    for line in lines[heading_index + 1 :]:
        if line.startswith("## "):
            break
        if ROW.match(line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)
    return declared_count, rows


def verify() -> list[str]:
    errors: list[str] = []
    declared_count, rows = root_table()

    malformed = [row for row in rows if len(row) != 6]
    if malformed:
        errors.append(f"root table contains {len(malformed)} row(s) without six columns")

    valid_rows = [row for row in rows if len(row) == 6]
    numbers = [int(row[0]) for row in valid_rows]
    expected_numbers = list(range(1, len(valid_rows) + 1))
    if numbers != expected_numbers:
        errors.append("root table sequence must be contiguous and start at 1")

    indexed_paths = [row[2].strip("`") for row in valid_rows]
    if len(indexed_paths) != len(set(indexed_paths)):
        errors.append("root table contains duplicate paths")

    actual_paths = current_markdown_paths()
    missing = sorted(actual_paths - set(indexed_paths))
    stale = sorted(set(indexed_paths) - actual_paths)
    if missing:
        errors.append("documents missing from root table: " + ", ".join(missing))
    if stale:
        errors.append("stale root-table paths: " + ", ".join(stale))

    if declared_count != len(valid_rows) or declared_count != len(actual_paths):
        errors.append(
            "declared root count does not match table rows and current Markdown files: "
            f"declared={declared_count}, rows={len(valid_rows)}, files={len(actual_paths)}"
        )

    historical_headings = [
        line
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ") and "Worktree" in line
    ]
    if not historical_headings:
        errors.append("historical worktree tables are missing")
    elif any(not line.startswith("## 历史 Worktree：") for line in historical_headings):
        errors.append("every retained worktree table must be explicitly labeled as historical")

    return errors


def main() -> int:
    errors = verify()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    declared_count, _ = root_table()
    print(f"document index checks passed: {declared_count} current Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
