import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from opentelemetry.context import attach, detach
from opentelemetry.propagate import extract
from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from opercerta.observability.tracing import configure_tracing, instrument_sqlalchemy_engine
from opercerta.tools.app import create_mcp_app
from opercerta.tools.catalog import SyntheticCatalog

ROOT = Path(__file__).resolve().parents[3]


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    database_url: SecretStr = Field(validation_alias="OPERCERTA_DATABASE_URL")
    otlp_enabled: bool = Field(default=False, validation_alias="OPERCERTA_OTLP_ENABLED")
    otlp_endpoint: AnyHttpUrl | None = Field(
        default=None, validation_alias="OPERCERTA_OTLP_ENDPOINT"
    )


def create_mcp_runtime_app(settings: McpSettings | None = None) -> FastAPI:
    active_settings = settings or McpSettings()
    parsed_url = make_url(active_settings.database_url.get_secret_value())
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed_url.password is not None:
        os.environ["PGPASSWORD"] = parsed_url.password
    engine = create_async_engine(parsed_url.set(password=None), pool_pre_ping=True)
    tracing, tracer_provider = configure_tracing(
        enabled=active_settings.otlp_enabled,
        endpoint=(
            str(active_settings.otlp_endpoint)
            if active_settings.otlp_endpoint is not None
            else None
        ),
        service_name="opercerta-mcp",
    )
    instrument_sqlalchemy_engine(engine.sync_engine, tracing)

    async def shutdown() -> None:
        await engine.dispose()
        if tracer_provider is not None:
            tracer_provider.shutdown()
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword

    app = create_mcp_app(
        SyntheticCatalog.load(
            ROOT / "data" / "synthetic" / "inventory.json",
            ROOT / "data" / "synthetic" / "replenishment_policies.json",
            equipment_path=ROOT / "data" / "synthetic" / "equipment.json",
            maintenance_policy_path=ROOT / "data" / "synthetic" / "maintenance_policies.json",
            task_path=ROOT / "data" / "synthetic" / "tasks.json",
            task_recovery_policy_path=ROOT / "data" / "synthetic" / "task_recovery_policies.json",
        ),
        engine,
        clock=lambda: datetime.now(UTC),
        on_shutdown=shutdown,
    )

    @app.middleware("http")
    async def trace_mcp_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        token = attach(extract(request.headers))
        try:
            with tracing.span(
                "mcp.request",
                {"component": "mcp", "operation": request.method},
            ):
                return await call_next(request)
        finally:
            detach(token)

    return app


def main(settings: McpSettings | None = None) -> None:
    uvicorn.run(
        create_mcp_runtime_app(settings),
        host="0.0.0.0",
        port=int(os.environ.get("MCP_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
