from pathlib import Path


def test_compose_keeps_internal_services_off_host_and_unprivileged() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert all(name in compose for name in ("postgres:", "bootstrap:", "mcp:", "api:"))
    assert "privileged:" not in compose
    assert "docker.sock" not in compose
    assert "postgres:5432" not in compose
    assert "mcp:8001" not in compose


def test_image_uses_locked_dependencies_and_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER opercerta" in dockerfile


def test_compose_example_is_tracked_and_real_file_is_ignored() -> None:
    example = Path(".env.compose.example").read_text(encoding="utf-8")
    ignored = Path(".gitignore").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=CHANGE_ME" in example
    assert ".env.compose" in ignored


def test_smoke_script_checks_health_duplicate_approval_and_database_facts() -> None:
    script = Path("scripts/verify_compose.py").read_text(encoding="utf-8")

    for required in (
        "/health/live",
        "/health/ready",
        "approval_already_decided",
        "docker compose exec -T postgres",
    ):
        assert required in script
    assert "OPERCERTA_DATABASE_URL" not in script
