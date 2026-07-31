"""Fail closed on tracked local secrets, placeholders and mutable Actions."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

_ALLOWED_ENV_NAMES = {".env.example", ".env.compose.example"}
_FORBIDDEN_SUFFIXES = {".pem", ".key"}
_PLACEHOLDER = re.compile(r"T[B]D|T[O]DO|稍后填[写]|待[定]|暂[定]")
_CREDENTIALS = (
    re.compile(r"Bearer [A-Za-z0-9._-]{16,}"),
    re.compile(r"postgresql[^\s]*://[^\s:]+:[^\s@]+@"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
)
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)", re.MULTILINE)
_PINNED_ACTION = re.compile(r"^[^@]+@[0-9a-f]{40}$")
_WRITE_PERMISSION = re.compile(
    r"^\s*(?:permissions:\s*write-all|[A-Za-z_-]+:\s*write)\s*$",
    re.MULTILINE,
)
_ATTACK_PATH = "src/opercerta/evaluation/executor.py"
_ALLOWED_ATTACK_LINES = {
    'return {"Authorization": f"Bearer x{token[1:]}"}',
    'return {"Authorization": "Bearer malformed-wrong-issuer-token"}',
}


def tracked_paths(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(Path(item) for item in result.stdout.split("\0") if item)


def _is_forbidden_path(path: Path) -> bool:
    name = path.name
    return (
        name.startswith(".env") and name not in _ALLOWED_ENV_NAMES
    ) or path.suffix.lower() in _FORBIDDEN_SUFFIXES


def _is_content_scope(relative: str) -> bool:
    return (
        relative
        in {
            "README.md",
            "README.zh-CN.md",
            "CONTRIBUTING.md",
            "CONTRIBUTING.zh-CN.md",
            "IMPLEMENTATION_HANDOFF.md",
            "DOCUMENT_INDEX.md",
        }
        or relative == "docs/development-log/current-state.md"
        or relative.startswith("docs/release-evidence/")
        or relative.startswith("src/")
        or relative.startswith(".github/workflows/")
    )


def scan_repository(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    paths = tracked_paths(root)
    relative_names = {path.as_posix() for path in paths}
    attack_counts: Counter[str] = Counter()

    for path in paths:
        relative = path.as_posix()
        if _is_forbidden_path(path):
            findings.append(f"forbidden tracked file: {relative}")
        if not _is_content_scope(relative):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF-8 scoped file: {relative}")
            continue

        if _PLACEHOLDER.search(text):
            findings.append(f"placeholder content: {relative}")

        for line in text.splitlines():
            stripped = line.strip()
            if relative == _ATTACK_PATH and stripped in _ALLOWED_ATTACK_LINES:
                attack_counts[stripped] += 1
                continue
            if any(pattern.search(line) for pattern in _CREDENTIALS):
                findings.append(f"credential-like content: {relative}")

        if relative.startswith(".github/workflows/"):
            for action in _USES.findall(text):
                if action.startswith("./"):
                    continue
                if not _PINNED_ACTION.fullmatch(action):
                    findings.append(f"unpinned action: {relative}: {action}")
            if _WRITE_PERMISSION.search(text):
                findings.append(f"write permission: {relative}")

    if _ATTACK_PATH in relative_names:
        for allowed_line in sorted(_ALLOWED_ATTACK_LINES):
            if attack_counts[allowed_line] != 1:
                findings.append(
                    "attack allowlist count: "
                    f"{_ATTACK_PATH}: expected 1, observed {attack_counts[allowed_line]}"
                )

    return tuple(findings)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_repository(root)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("repository safety checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
