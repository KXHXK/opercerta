from typing import cast

from pydantic import SecretStr

from opercerta.runtime import api, bootstrap, mcp


def test_api_main_binds_all_container_interfaces(monkeypatch) -> None:
    calls: list[tuple[object, str, int]] = []
    application = object()
    monkeypatch.setenv("PORT", "9010")
    monkeypatch.setattr(api, "create_production_app", lambda: application)
    monkeypatch.setattr(
        api.uvicorn,
        "run",
        lambda app, host, port: calls.append((app, host, port)),
    )

    api.main()

    assert calls == [(application, "0.0.0.0", 9010)]


def test_mcp_main_binds_all_container_interfaces(monkeypatch) -> None:
    calls: list[tuple[object, str, int]] = []
    application = object()
    settings = cast(mcp.McpSettings, object())
    monkeypatch.setenv("MCP_PORT", "8001")
    monkeypatch.setattr(mcp, "create_mcp_runtime_app", lambda value: application)
    monkeypatch.setattr(
        mcp.uvicorn,
        "run",
        lambda app, host, port: calls.append((app, host, port)),
    )

    mcp.main(settings)

    assert calls == [(application, "0.0.0.0", 8001)]


def test_bootstrap_runs_migration_before_checkpoint_setup(monkeypatch) -> None:
    events: list[str] = []
    settings = bootstrap.BootstrapSettings(
        OPERCERTA_DATABASE_URL=SecretStr("postgresql://test.example/opercerta"),
    )
    monkeypatch.setattr(bootstrap, "upgrade_database", lambda: events.append("migration"))

    async def record_setup(database_url: SecretStr) -> None:
        assert database_url == settings.database_url
        events.append("checkpoint")

    monkeypatch.setattr(bootstrap, "setup_checkpointer", record_setup)

    bootstrap.main(settings)

    assert events == ["migration", "checkpoint"]
