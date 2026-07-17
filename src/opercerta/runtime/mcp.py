import os
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from opercerta.tools.app import create_mcp_app
from opercerta.tools.catalog import SyntheticCatalog

ROOT = Path(__file__).resolve().parents[3]


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    database_url: SecretStr = Field(validation_alias="OPERCERTA_DATABASE_URL")


def create_mcp_runtime_app(settings: McpSettings | None = None) -> FastAPI:
    active_settings = settings or McpSettings()
    parsed_url = make_url(active_settings.database_url.get_secret_value())
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed_url.password is not None:
        os.environ["PGPASSWORD"] = parsed_url.password
    engine = create_async_engine(parsed_url.set(password=None), pool_pre_ping=True)

    async def shutdown() -> None:
        await engine.dispose()
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword

    return create_mcp_app(
        SyntheticCatalog.load(
            ROOT / "data" / "synthetic" / "inventory.json",
            ROOT / "data" / "synthetic" / "replenishment_policies.json",
        ),
        engine,
        clock=lambda: datetime.now(UTC),
        on_shutdown=shutdown,
    )


def main(settings: McpSettings | None = None) -> None:
    uvicorn.run(
        create_mcp_runtime_app(settings),
        host="0.0.0.0",
        port=int(os.environ.get("MCP_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
