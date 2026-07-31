import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def load_safety_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_repository_safety",
        ROOT / "scripts" / "verify_repository_safety.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_repository = load_safety_module().scan_repository

PINNED_CHECKOUT = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
ATTACK_PATH = "src/opercerta/evaluation/executor.py"
ATTACK_LINES = """\
def headers(token: str) -> dict[str, str]:
    if token == "tampered":
        return {"Authorization": f"Bearer x{token[1:]}"}
    return {"Authorization": "Bearer malformed-wrong-issuer-token"}
"""


def tracked_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    return tmp_path


def clean_files() -> dict[str, str]:
    return {
        "README.md": (
            "# OperCerta\nMissing Bearer token is rejected.\nOperCerta release gate: CLOSED\n"
        ),
        ATTACK_PATH: ATTACK_LINES,
        ".github/workflows/ci.yml": (
            "permissions:\n  contents: read\n"
            f"steps:\n  - uses: actions/checkout@{PINNED_CHECKOUT}\n"
        ),
    }


def test_clean_repository_and_exact_attack_allowlist_pass(tmp_path: Path) -> None:
    root = tracked_repo(tmp_path, clean_files())

    assert scan_repository(root) == ()


def test_forbidden_local_environment_file_fails(tmp_path: Path) -> None:
    files = clean_files() | {".env.local": "SECRET=value\n"}
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("forbidden tracked file: .env.local" in item for item in findings)


def test_unknown_credential_and_duplicate_attack_sample_fail(tmp_path: Path) -> None:
    files = clean_files()
    files["README.md"] += "Authorization example: Bearer actual-looking-token\n"
    files[ATTACK_PATH] += 'return {"Authorization": "Bearer malformed-wrong-issuer-token"}\n'
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("credential-like content: README.md" in item for item in findings)
    assert any("attack allowlist count" in item for item in findings)


def test_unpinned_action_and_write_permission_fail(tmp_path: Path) -> None:
    files = clean_files()
    files[".github/workflows/ci.yml"] = """\
permissions: write-all
steps:
  - uses: actions/checkout@v7
"""
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("unpinned action" in item for item in findings)
    assert any("write permission" in item for item in findings)


def test_bilingual_public_documents_are_in_secret_scan_scope(tmp_path: Path) -> None:
    files = clean_files() | {
        "README.zh-CN.md": "# OperCerta\nBearer actual-looking-token\n",
        "CONTRIBUTING.md": "# Contributing\nSafe content.\n",
        "CONTRIBUTING.zh-CN.md": "# 贡献指南\nSafe content.\n",
    }
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("credential-like content: README.zh-CN.md" in item for item in findings)
