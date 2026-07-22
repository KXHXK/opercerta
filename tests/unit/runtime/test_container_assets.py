from pathlib import Path


def test_compose_keeps_internal_services_off_host_and_unprivileged() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert all(name in compose for name in ("postgres:", "redis:", "bootstrap:", "mcp:", "api:"))
    assert "privileged:" not in compose
    assert "docker.sock" not in compose
    assert "postgres:5432" not in compose
    assert "mcp:8001" not in compose
    assert '"6379:6379"' not in compose
    assert "- 6379:6379" not in compose


def test_redis_is_internal_healthy_and_required_only_by_api() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    example = Path(".env.compose.example").read_text(encoding="utf-8")

    assert "redis-cli" in compose
    assert "image: redis:8.8.0-trixie" in compose
    assert "condition: service_healthy" in compose
    assert "OPERCERTA_REDIS_URL=redis://redis:6379/0" in example
    assert "OPERCERTA_CACHE_ENABLED=true" in example
    assert "OPERCERTA_CACHE_TTL_SECONDS=60" in example
    assert "OPERCERTA_CACHE_ENABLED: ${OPERCERTA_CACHE_ENABLED:-true}" in compose
    assert "OPERCERTA_OTLP_ENABLED=false" in example
    assert "OPERCERTA_MODEL_MODE: ${OPERCERTA_MODEL_MODE:-mock}" in compose
    assert "OPERCERTA_MODEL_BASE_URL: ${OPERCERTA_MODEL_BASE_URL:-}" in compose
    assert "OPERCERTA_MODEL_NAME: ${OPERCERTA_MODEL_NAME:-}" in compose
    assert "OPERCERTA_MODEL_API_KEY: ${OPERCERTA_MODEL_API_KEY:-}" in compose
    assert "OPERCERTA_MCP_TIMEOUT_SECONDS: ${OPERCERTA_MCP_TIMEOUT_SECONDS:-2}" in compose


def test_postgres_18_uses_the_parent_data_mount() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert "postgres_data:/var/lib/postgresql\n" in compose
    assert "postgres_data:/var/lib/postgresql/data" not in compose


def test_compose_pins_pgvector_and_persists_the_embedding_cache() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    example = Path(".env.compose.example").read_text(encoding="utf-8")

    assert "image: pgvector/pgvector:0.8.2-pg18-trixie" in compose
    assert "fastembed_cache:/home/opercerta/.cache/fastembed" in compose
    assert "OPERCERTA_EMBEDDING_CACHE_DIR: /home/opercerta/.cache/fastembed" in compose
    assert 'HF_HUB_DISABLE_XET: "1"' in compose
    assert "HF_HUB_OFFLINE: ${OPERCERTA_HF_HUB_OFFLINE:-false}" in compose
    assert "install -d -o opercerta -g opercerta /home/opercerta/.cache/fastembed" in Path(
        "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "OPERCERTA_KNOWLEDGE_ENABLED=true" in example
    assert "OPERCERTA_KNOWLEDGE_REQUIRED=false" in example


def test_image_uses_locked_dependencies_and_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "install -d -o opercerta -g opercerta /home/opercerta/.cache" in dockerfile
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
    for kind in ("replenishment", "repair", "task_recovery"):
        assert kind in script
    assert "rejected" in script
    assert "--recovery-only" in script


def test_performance_matrix_script_covers_declared_cache_tool_and_scenario_cells() -> None:
    script = Path("scripts/run_performance_matrix.sh").read_text(encoding="utf-8")

    assert "OPERCERTA_METRICS_ENABLED=true" in script
    assert "OPERCERTA_PERFORMANCE_CACHE_MODES:-disabled enabled" in script
    assert "OPERCERTA_PERFORMANCE_TOOL_MODES:-parallel sequential" in script
    assert "OPERCERTA_PERFORMANCE_SCENARIOS:-inventory equipment task" in script
    assert "--force-recreate api" in script
    assert "docker compose up --build -d" in script
    assert "redis-cli FLUSHDB" in script
