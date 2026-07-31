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
    assert '"/api/v1/signals/scan"' in verifier
    assert 'action = "investigate" if signal_status == "open" else "retry"' in verifier
    assert "f\"/api/v1/signals/{matching_signals[0]['id']}/{action}\"" in verifier
    assert 'signal_status in {"open", "attention_required"}' in verifier
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
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    state = (ROOT / "docs" / "development-log" / "current-state.md").read_text(encoding="utf-8")

    assert "Private GitHub" not in readme
    assert "Private GitHub" not in state
    assert "not a public interactive product" in readme
    assert "不是公网交互产品" in readme_zh
    assert "少量兼容性代表验证" in state
    assert "Product Release gate" in state


def test_public_entry_documents_show_one_language_and_use_standard_switch_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    contributing_zh = (ROOT / "CONTRIBUTING.zh-CN.md").read_text(encoding="utf-8")

    separator = "\uff5c"
    assert f"**English**{separator}[简体中文](README.zh-CN.md)" in readme
    assert f"[English](README.md){separator}**简体中文**" in readme_zh
    assert f"**English**{separator}[简体中文](CONTRIBUTING.zh-CN.md)" in contributing
    assert f"[English](CONTRIBUTING.md){separator}**简体中文**" in contributing_zh
    for content in (readme, readme_zh, contributing, contributing_zh):
        assert "<details" not in content
        assert "<summary" not in content
    assert "## Quick Start" in readme
    assert "## 快速启动" not in readme
    assert "## 快速启动" in readme_zh
    assert "## Quick Start" not in readme_zh
    assert "## Development Environment" in contributing
    assert "## 开发环境" not in contributing
    assert "## 开发环境" in contributing_zh
    assert "## Development Environment" not in contributing_zh

    for phrase in (
        "FastAPI",
        "LangGraph",
        "FastMCP",
        "PostgreSQL",
        "pgvector",
        "Redis",
        "TypeScript",
        "Vite",
        "OpenTelemetry",
        "Prometheus",
        "GitHub Actions",
    ):
        assert phrase in readme
        assert phrase in readme_zh

    assert "[https://opercerta-kxh.netlify.app/](https://opercerta-kxh.netlify.app/)" in readme
    assert "Read-only project page" not in readme
    assert "v0.1.0-showcase.1" not in readme

    for forbidden in (
        "interview guide",
        "resume wording",
        "portfolio overview",
        "面试讲解",
        "简历",
        "求职",
        "四项目",
        "作品集",
    ):
        assert forbidden.lower() not in readme.lower()
        assert forbidden.lower() not in readme_zh.lower()


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
    assert "三业务只读、库存批准写入和无效 provider fail-closed" in interview

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


def test_current_demo_and_learning_docs_match_the_single_root_agent_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    demo = (ROOT / "docs" / "demo-script.md").read_text(encoding="utf-8")
    manual = (ROOT / "docs" / "learning" / "opercerta-manual-experiment-guide.md").read_text(
        encoding="utf-8"
    )
    interview = (ROOT / "docs" / "learning" / "opercerta-interview-guide.md").read_text(
        encoding="utf-8"
    )

    for content in (demo, manual):
        assert "扫描业务异常" in content
        assert "启动 Agent 调查" in content
    for content in (demo, interview):
        assert "三业务只读、库存批准写入和无效 provider fail-closed" in content
        assert "新 Agent 核心的 Real Kimi Tool Calling 代表 query 为 failed" not in content

    normalized_readme = " ".join(readme.split())
    normalized_readme_zh = " ".join(readme_zh.split())
    assert (
        "three read-only business paths, an approved inventory write, and "
        "invalid-provider fail-closed" in normalized_readme
    )
    assert "三业务只读、库存批准写入和无效 provider fail-closed" in normalized_readme_zh

    assert "667 条后端测试" in interview
    assert "v0.1.0-showcase.1" in interview
    assert ".worktrees/agent-core-implementation" not in manual
    assert "cd frontend" not in manual
    assert "cd web" in manual


def test_showcase_release_gate_and_owner_acceptance_are_explicit() -> None:
    amendment = (
        ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-07-31-showcase-release-gate-amendment-design.md"
    ).read_text(encoding="utf-8")
    ownership = (ROOT / "docs" / "learning" / "opercerta-ownership-acceptance.md").read_text(
        encoding="utf-8"
    )
    state = (ROOT / "docs" / "development-log" / "current-state.md").read_text(encoding="utf-8")
    handoff = (ROOT / "IMPLEMENTATION_HANDOFF.md").read_text(encoding="utf-8")

    for phrase in (
        "Showcase Release",
        "Product Release",
        "公开静态展示",
        "本地可复现完整 Agent MVP",
        "3\u20135 分钟录屏",
    ):
        assert phrase in amendment
    assert "Showcase Release gate: AWAITING_OWNER_VALIDATION" in state
    assert "Product Release gate: CLOSED" in state
    assert "PR #22" in handoff
    assert "671 passed" in handoff
    assert "不得由 Codex 自动代签" in ownership
    assert "operation_id" in ownership
    assert "work_order_id" in ownership


def test_public_repository_has_an_apache_license_and_current_test_count() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "671 tests passed" in readme
    assert "671 条通过" in readme_zh
