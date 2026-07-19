from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.api.health import ProductionReadinessProbe
from opercerta.tools.app import create_mcp_app
from opercerta.tools.catalog import SyntheticCatalog

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


@asynccontextmanager
async def open_mcp_session(
    app: object,
    base_url: str = "http://127.0.0.1:8001",
) -> AsyncIterator[ClientSession]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=base_url,
        trust_env=False,
    ) as http_client:
        async with streamable_http_client(
            f"{base_url}/mcp",
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


@pytest.mark.asyncio
async def test_mcp_health_routes_coexist_with_inventory_tools(
    engine: AsyncEngine,
) -> None:
    catalog = SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
    )
    app = create_mcp_app(catalog, engine, clock=lambda: NOW)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8001",
            trust_env=False,
        ) as client:
            assert (await client.get("/health/live")).json() == {"status": "live"}
            assert (await client.get("/health/ready")).json() == {"status": "ready"}

        async with open_mcp_session(app) as session:
            listed = await session.list_tools()

    assert {tool.name for tool in listed.tools} == {
        "equipment.get_status",
        "inventory.get_snapshot",
        "policy.list_constraints",
        "work_order.create",
        "work_order.get",
    }


@pytest.mark.asyncio
async def test_mcp_accepts_the_internal_docker_service_host(
    engine: AsyncEngine,
) -> None:
    catalog = SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
    )
    app = create_mcp_app(catalog, engine, clock=lambda: NOW)

    async with app.router.lifespan_context(app):
        async with open_mcp_session(app, "http://mcp:8001") as session:
            listed = await session.list_tools()

    assert {tool.name for tool in listed.tools} == {
        "equipment.get_status",
        "inventory.get_snapshot",
        "policy.list_constraints",
        "work_order.create",
        "work_order.get",
    }


@pytest.mark.asyncio
async def test_production_probe_maps_mcp_failure_to_safe_state(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    probe = ProductionReadinessProbe(
        engine=engine,
        database_url=checkpoint_database_url,
        mcp_health_url="http://mcp.test/health/ready",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )

    report = await probe.check()

    assert report.model_dump() == {
        "status": "not_ready",
        "dependencies": {
            "database": "ready",
            "checkpoint": "ready",
            "mcp": "unavailable",
        },
    }
