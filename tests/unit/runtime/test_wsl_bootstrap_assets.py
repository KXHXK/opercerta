from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "scripts" / "bootstrap_wsl_environment.sh"
PROJECT_BOOTSTRAP = ROOT / "scripts" / "bootstrap_project_runtime.sh"
GIT_ATTRIBUTES = ROOT / ".gitattributes"


def bootstrap_text() -> str:
    assert BOOTSTRAP.is_file(), "WSL bootstrap script is missing"
    return BOOTSTRAP.read_text(encoding="utf-8")


def project_bootstrap_text() -> str:
    assert PROJECT_BOOTSTRAP.is_file(), "project runtime bootstrap script is missing"
    return PROJECT_BOOTSTRAP.read_text(encoding="utf-8")


def test_wsl_bootstrap_pins_the_project_development_toolchain() -> None:
    text = bootstrap_text()

    assert 'UV_VERSION="0.11.28"' in text
    assert 'PYTHON_VERSION="3.12.13"' in text
    assert 'NODE_VERSION="24.18.0"' in text
    assert 'NODE_SHA256="55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742"' in text
    assert "uv python install" in text
    assert "node --version" in text
    assert "npm --version" in text


def test_wsl_bootstrap_persists_node_path_for_interactive_and_login_shells() -> None:
    text = bootstrap_text()

    assert '"${HOME}/.bashrc"' in text
    assert '"${HOME}/.profile"' in text


def test_wsl_bootstrap_uses_verified_domestic_download_boundaries() -> None:
    text = bootstrap_text()

    assert "https://cdn.npmmirror.com/binaries/node/" in text
    assert "https://registry.npmmirror.com" in text
    assert "sha256sum -c" in text
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in text
    assert "UV_HTTP_TIMEOUT" in text
    assert "UV_HTTP_RETRIES" in text


def test_wsl_bootstrap_documents_the_drvfs_node_modules_boundary() -> None:
    text = bootstrap_text()

    assert "DrvFS" in text
    assert "node_modules" in text
    assert "Windows npm" in text
    assert "WSL npm" in text


def test_project_bootstrap_generates_ignored_local_credentials_and_redacts_diagnostics() -> None:
    text = project_bootstrap_text()

    assert "secrets.token_hex" in text
    assert "git check-ignore -q .env.compose" in text
    assert "OPERCERTA_MODEL_MODE=mock" in text
    assert "OPERCERTA_MODEL_API_KEY=not-used-in-mock-mode" in text
    assert "OPERCERTA_MODEL_API_KEY=" in text
    assert "***" in text


def test_project_bootstrap_runs_compose_and_restart_recovery_gates() -> None:
    text = project_bootstrap_text()

    assert "docker compose config --quiet" in text
    assert "docker compose up --build -d --wait" in text
    assert "python3 scripts/verify_agent_compose.py" in text
    assert "docker compose restart api mcp" in text
    assert "python3 scripts/verify_agent_compose.py --recovery-only" in text
    assert "http://127.0.0.1:8080/health/ready" in text


def test_repository_enforces_cross_platform_lf_without_rewriting_binary_assets() -> None:
    assert GIT_ATTRIBUTES.is_file()
    text = GIT_ATTRIBUTES.read_text(encoding="utf-8")

    assert "* text=auto eol=lf" in text
    for extension in ("png", "jpg", "jpeg", "gif", "ico", "woff", "woff2"):
        assert f"*.{extension} binary" in text
