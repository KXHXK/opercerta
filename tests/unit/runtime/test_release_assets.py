from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_release_compose_exposes_only_caddy_and_keeps_internal_services_private() -> None:
    compose = yaml.safe_load((ROOT / "compose.release.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert "ports" in services["caddy"]
    for service in ("postgres", "redis", "mcp", "api"):
        assert "ports" not in services[service]
    assert services["api"]["environment"]["OPERCERTA_METRICS_ENABLED"] == "false"


def test_release_compose_accepts_only_explicit_real_model_environment_passthrough() -> None:
    compose = yaml.safe_load((ROOT / "compose.release.yaml").read_text(encoding="utf-8"))
    environment = compose["services"]["api"]["environment"]

    assert environment["OPERCERTA_MODEL_MODE"] == "${OPERCERTA_MODEL_MODE:-mock}"
    assert environment["OPERCERTA_MODEL_BASE_URL"] == "${OPERCERTA_MODEL_BASE_URL:-}"
    assert environment["OPERCERTA_MODEL_NAME"] == "${OPERCERTA_MODEL_NAME:-}"
    assert environment["OPERCERTA_MODEL_API_KEY"] == "${OPERCERTA_MODEL_API_KEY:-}"
    assert environment["OPERCERTA_MODEL_THINKING_MODE"] == (
        "${OPERCERTA_MODEL_THINKING_MODE:-default}"
    )
    assert environment["OPERCERTA_MCP_TIMEOUT_SECONDS"] == ("${OPERCERTA_MCP_TIMEOUT_SECONDS:-2}")


def test_caddy_routes_web_and_api_without_exposing_internal_administration() -> None:
    caddyfile = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "reverse_proxy" in caddyfile
    assert "api:8080" in caddyfile
    assert "handle @api" in caddyfile
    assert "try_files {path} /index.html" in caddyfile
    assert "/metrics" not in caddyfile
    assert all(name not in caddyfile for name in ("postgres:5432", "redis:6379", "mcp:8001"))


def test_release_web_build_excludes_local_dependencies_from_context() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "web/node_modules" in ignored
    assert "web/dist" in ignored


def test_release_smoke_runs_only_through_caddy_and_always_cleans_up() -> None:
    script = (ROOT / "scripts" / "verify_release_compose.sh").read_text(encoding="utf-8")

    assert "COMPOSE_FILE=compose.release.yaml" in script
    assert 'OPERCERTA_API_URL="http://localhost:' in script
    assert "docker compose up --build -d" in script
    assert "scripts/verify_agent_compose.py" in script
    assert "docker compose restart api mcp" in script
    assert "docker compose down -v --remove-orphans" in script


def test_real_model_smoke_loads_ignored_config_and_limits_the_representative_set() -> None:
    shell = (ROOT / "scripts" / "run_real_model_validation.sh").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_real_model.py").read_text(encoding="utf-8")

    assert ".env.local" in shell
    assert "set -x" not in shell
    assert "OPERCERTA_MODEL_API_KEY" in shell
    assert "python3 -m scripts.verify_real_model" in shell
    assert "docker compose down -v --remove-orphans" in shell
    for object_type in ("inventory", "equipment", "task"):
        assert object_type in verifier
    assert '"query"' in verifier
    assert '"create_work_order"' in verifier
    assert "raw_model_output" not in verifier
    assert "token_usage_available" not in verifier
    assert "cost_available" not in verifier
    assert "assert_agent_trace" in verifier


def test_learning_pack_covers_three_business_manual_failure_and_interview_explanation() -> None:
    handbook = (ROOT / "docs" / "learning" / "opercerta-core-technical-guide.md").read_text(
        encoding="utf-8"
    )
    manual = (ROOT / "docs" / "learning" / "opercerta-manual-experiment-guide.md").read_text(
        encoding="utf-8"
    )
    interview = (ROOT / "docs" / "learning" / "opercerta-interview-guide.md").read_text(
        encoding="utf-8"
    )

    for scenario in ("库存补货", "设备维修", "作业异常恢复"):
        assert scenario in handbook
        assert scenario in manual
        assert scenario in interview
    assert "docker compose stop mcp" in manual
    assert "docker compose restart api mcp" in manual
    assert "exactly-once" in interview
    assert "30 秒" in interview
    assert "3 分钟" in interview
    assert "10 分钟" in interview
    assert "checkpoint" in handbook.lower()
    assert "PostgreSQL" in handbook


def test_release_documents_keep_verified_boundaries_truthful() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    state = (ROOT / "docs" / "development-log" / "current-state.md").read_text(encoding="utf-8")

    assert "Private GitHub" not in readme
    assert "Private GitHub" not in state
    assert "生产发布门禁" in readme
    assert "CLOSED" in readme
    assert "真实模型代表性" in state
    assert "尚未" in state


def test_agent_delivery_documents_cover_architecture_learning_and_truthful_evidence() -> None:
    handbook = (ROOT / "docs" / "learning" / "opercerta-core-technical-guide.md").read_text(
        encoding="utf-8"
    )
    manual = (ROOT / "docs" / "learning" / "opercerta-manual-experiment-guide.md").read_text(
        encoding="utf-8"
    )
    interview = (ROOT / "docs" / "learning" / "opercerta-interview-guide.md").read_text(
        encoding="utf-8"
    )
    evidence = (ROOT / "docs" / "release-evidence" / "agent-core-architecture.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "LangGraph + 最小 LangChain",
        "不是聊天框",
        "感知层",
        "语义理解与目标编码",
        "推理与规划",
        "Memory 的四种含义",
        "RAG 与 SQL/MCP 的边界",
        "Tool Calling 如何校验",
        "批准后为什么重新取证",
        "Agent Trace、audit 与 OpenTelemetry",
        "仍未上线",
    ):
        assert phrase in handbook

    for phrase in ("输入", "预期", "为什么", "常见错误", "面试怎么讲"):
        assert phrase in manual
    assert "scripts/verify_agent_compose.py" in manual
    assert "scripts/run_agent_evaluation.py" in manual
    assert "agent-trace" in manual

    assert "Plan-and-Execute" in interview
    assert "六层 Agent" in interview
    assert "真实 Kimi Tool Calling" in interview
    assert "未通过" in interview

    for phrase in (
        "642d3ba",
        "566 passed",
        "9/9",
        "tmp/evals/opercerta-agent-v1-mock-report.json",
        "tmp/real-model-agent-v1-report.json",
        "Kimi",
        "failed",
        "CLOSED",
    ):
        assert phrase in evidence
