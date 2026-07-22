from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

ACTION_PINS = {
    "actions/checkout": "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "astral-sh/setup-uv": "11f9893b081a58869d3b5fccaea48c9e9e46f990",
}


def workflow_text() -> str:
    assert WORKFLOW.is_file(), "GitHub Actions workflow is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_has_read_only_triggers_concurrency_and_pinned_actions() -> None:
    text = workflow_text()

    assert "pull_request:" in text
    assert "workflow_dispatch:" in text
    assert "branches: [main]" in text
    assert "contents: read" in text
    assert "cancel-in-progress: true" in text
    assert "write-all" not in text
    for owner_action, sha in ACTION_PINS.items():
        assert f"{owner_action}@{sha}" in text


def test_ci_fast_jobs_use_frozen_python_postgres_and_frontend_gates() -> None:
    text = workflow_text()

    for job_name in (
        "repository-safety",
        "python-quality",
        "backend-tests",
        "frontend",
    ):
        assert f"name: {job_name}" in text
    assert 'python-version: "3.12"' in text
    assert 'version: "0.11.28"' in text
    assert "uv sync --frozen --all-groups" in text
    assert "python scripts/verify_repository_safety.py" in text
    assert "uv run ruff check ." in text
    assert "uv run ruff format --check ." in text
    assert "uv run mypy src" in text
    assert "image: pgvector/pgvector:0.8.2-pg18-trixie" in text
    assert "image: postgres:18" not in text
    assert (
        "OPERCERTA_DATABASE_URL: postgresql+psycopg://opercerta_ci@127.0.0.1:5432/opercerta_ci"
    ) in text
    assert "PGPASSWORD: opercerta_ci_only" in text
    assert "uv run pytest -q" in text
    assert "python scripts/run_opercerta_evaluation.py" in text
    assert "python scripts/run_agent_evaluation.py" in text
    assert 'node-version: "24"' in text
    assert "npm ci" in text
    assert "npm run test:run" in text
    assert "npm run build" in text


def test_ci_compose_smoke_is_main_or_manual_only_and_always_cleans_up() -> None:
    text = workflow_text()

    assert "name: compose-smoke" in text
    assert "needs: [repository-safety, python-quality, backend-tests, frontend]" in text
    assert "github.event_name == 'workflow_dispatch'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "docker compose up --build -d" in text
    assert "python scripts/verify_agent_compose.py" in text
    assert "docker compose restart api mcp" in text
    assert "python scripts/verify_agent_compose.py --recovery-only" in text
    assert "if: failure()" in text
    assert "docker compose ps" in text
    assert "if: always()" in text
    assert "docker compose down -v --remove-orphans" in text
