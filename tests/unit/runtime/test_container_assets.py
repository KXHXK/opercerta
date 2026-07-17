from pathlib import Path


def test_compose_keeps_internal_services_off_host_and_unprivileged() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert all(name in compose for name in ("postgres:", "bootstrap:", "mcp:", "api:"))
    assert "privileged:" not in compose
    assert "docker.sock" not in compose
    assert "postgres:5432" not in compose
    assert "mcp:8001" not in compose


def test_postgres_18_uses_the_parent_data_mount() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert "postgres_data:/var/lib/postgresql\n" in compose
    assert "postgres_data:/var/lib/postgresql/data" not in compose


def test_image_uses_locked_dependencies_and_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER opercerta" in dockerfile


def test_image_copies_project_build_inputs_before_locked_sync() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    sync = dockerfile.index("RUN uv sync --frozen --no-dev")

    assert dockerfile.index("README.md") < sync
    assert dockerfile.index("COPY src ./src") < sync


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
        "COUNT(*) FROM approvals",
        "COUNT(*) FROM work_orders",
        "operation_completed",
    ):
        assert required in script
    assert all(
        token in script for token in ('"docker",', '"compose",', '"exec",', '"-T",', '"postgres",')
    )
    assert "OPERCERTA_DATABASE_URL" not in script
