from dataclasses import dataclass
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from opercerta.api.app import AppRuntime, create_app
from opercerta.application.operation_runner import OperationRunner
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)


@dataclass
class ExplodingProbe:
    calls: int = 0

    async def check(self) -> object:
        self.calls += 1
        raise RuntimeError("secret must never reach response")


def create_test_app(probe: ExplodingProbe):
    runtime = AppRuntime(
        runner=cast(OperationRunner, object()),
        operations=cast(ReplenishmentOperationRepository, object()),
        readiness=probe,
    )
    return create_app(runtime)


@pytest.mark.asyncio
async def test_live_is_200_without_calling_dependencies() -> None:
    probe = ExplodingProbe()
    app = create_test_app(probe)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert probe.calls == 0


@pytest.mark.asyncio
async def test_ready_returns_safe_503_when_probe_raises() -> None:
    app = create_test_app(ExplodingProbe())
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "database": "unavailable",
            "checkpoint": "unavailable",
            "mcp": "unavailable",
        },
    }
    assert "secret" not in response.text
