from pathlib import Path


def test_compose_keeps_internal_services_off_host_and_unprivileged() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert all(name in compose for name in ("postgres:", "redis:", "bootstrap:", "mcp:", "api:"))
    assert "privileged:" not in compose
    assert "docker.sock" not in compose
    assert "postgres:5432" not in compose
    assert "mcp:8001" not in compose
    assert "redis:6379" not in compose


def test_redis_is_internal_healthy_and_required_only_by_api() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    example = Path(".env.compose.example").read_text(encoding="utf-8")

    assert "redis-cli" in compose
    assert "image: redis:8.8.0-trixie" in compose
    assert "condition: service_healthy" in compose
    assert "OPERCERTA_REDIS_URL=redis://redis:6379/0" in example
    assert "OPERCERTA_CACHE_ENABLED=true" in example
    assert "OPERCERTA_CACHE_TTL_SECONDS=60" in example
    assert "OPERCERTA_OTLP_ENABLED=false" in example


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
    assert "OPERCERTA_JWT_SIGNING_KEY=CHANGE_ME_DEVELOPMENT_ONLY" in example
    assert "OPERCERTA_DEMO_TOKEN_ENABLED=true" in example


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
    assert '"/api/v1/auth/demo-token"' in script
    assert '"approver_id"' not in script
    assert "wait_for_ready" in script
    assert "time.monotonic" in script
