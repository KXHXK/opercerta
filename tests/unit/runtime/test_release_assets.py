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
    assert "scripts/verify_compose.py" in script
    assert "docker compose restart api mcp" in script
    assert "docker compose down -v --remove-orphans" in script


def test_learning_pack_covers_three_business_manual_failure_and_interview_explanation() -> None:
    handbook = (ROOT / "docs" / "learning" / "OperCerta核心技术手册.md").read_text(encoding="utf-8")
    manual = (ROOT / "docs" / "learning" / "OperCerta手动实验手册.md").read_text(encoding="utf-8")
    interview = (ROOT / "docs" / "learning" / "OperCerta面试讲解.md").read_text(encoding="utf-8")

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
