from typing import cast

import pytest
from pydantic import SecretStr
from pydantic_core import ValidationError

from opercerta.api.app import ProductionSettings
from opercerta.runtime import api, bootstrap, mcp


def production_values() -> dict[str, object]:
    return {
        "OPERCERTA_DATABASE_URL": "postgresql://user:secret@db/opercerta",
        "OPERCERTA_MCP_URL": "http://mcp:8001/mcp",
        "OPERCERTA_MCP_TIMEOUT_SECONDS": 2,
        "OPERCERTA_APPROVAL_TTL_SECONDS": 300,
        "OPERCERTA_MODEL_MODE": "mock",
        "OPERCERTA_JWT_SIGNING_KEY": "test-signing-key",
        "OPERCERTA_JWT_ISSUER": "opercerta-test",
        "OPERCERTA_JWT_AUDIENCE": "opercerta-api",
        "OPERCERTA_JWT_TTL_SECONDS": 300,
        "OPERCERTA_DEMO_TOKEN_ENABLED": False,
    }


def test_api_main_configures_logging_and_binds_all_container_interfaces(
    monkeypatch,
) -> None:
    events: list[tuple[object, ...]] = []
    application = object()
    monkeypatch.setenv("PORT", "9010")
    monkeypatch.setattr(api, "create_production_app", lambda: application)
    monkeypatch.setattr(
        api,
        "configure_json_logging",
        lambda service: events.append(("logging", service)),
    )
    monkeypatch.setattr(
        api.uvicorn,
        "run",
        lambda app, host, port, log_config: events.append(("uvicorn", app, host, port, log_config)),
    )

    api.main()

    assert events == [
        ("logging", "opercerta-api"),
        ("uvicorn", application, "0.0.0.0", 9010, None),
    ]


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


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"OPERCERTA_CACHE_ENABLED": True}, "Redis URL"),
        ({"OPERCERTA_MODEL_MODE": "real"}, "real model settings"),
        ({"OPERCERTA_OTLP_ENABLED": True}, "OTLP endpoint"),
    ],
)
def test_optional_production_services_fail_closed_without_configuration(
    updates: dict[str, object],
    message: str,
) -> None:
    values = production_values() | updates

    with pytest.raises(ValidationError, match=message):
        ProductionSettings.model_validate(values)


def test_production_secrets_are_redacted_from_representation() -> None:
    settings = ProductionSettings.model_validate(
        production_values()
        | {
            "OPERCERTA_MODEL_MODE": "real",
            "OPERCERTA_MODEL_BASE_URL": "https://model.example/v1",
            "OPERCERTA_MODEL_NAME": "demo-model",
            "OPERCERTA_MODEL_API_KEY": "must-not-leak",
        }
    )

    assert "must-not-leak" not in repr(settings)
    assert "**********" in repr(settings)
