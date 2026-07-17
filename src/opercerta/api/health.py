from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.infrastructure.checkpoints import open_checkpointer

DependencyName = Literal["database", "checkpoint", "mcp"]
DependencyState = Literal["ready", "unavailable"]
ReadinessStatus = Literal["ready", "not_ready"]


class ReadinessReport(BaseModel):
    status: ReadinessStatus
    dependencies: dict[DependencyName, DependencyState]


class ReadinessProbe(Protocol):
    async def check(self) -> ReadinessReport: ...


class UnavailableReadinessProbe:
    async def check(self) -> ReadinessReport:
        return not_ready_report()


def not_ready_report() -> ReadinessReport:
    return ReadinessReport(
        status="not_ready",
        dependencies={
            "database": "unavailable",
            "checkpoint": "unavailable",
            "mcp": "unavailable",
        },
    )


class ProductionReadinessProbe:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        database_url: SecretStr,
        mcp_health_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._engine = engine
        self._database_url = database_url
        self._mcp_health_url = mcp_health_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def check(self) -> ReadinessReport:
        dependencies: dict[DependencyName, DependencyState] = {
            "database": "unavailable",
            "checkpoint": "unavailable",
            "mcp": "unavailable",
        }
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            dependencies["database"] = "ready"
        except Exception:
            return _report_for(dependencies)

        try:
            async with open_checkpointer(self._database_url):
                pass
            dependencies["checkpoint"] = "ready"
        except Exception:
            return _report_for(dependencies)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.get(self._mcp_health_url)
                response.raise_for_status()
            dependencies["mcp"] = "ready"
        except Exception:
            return _report_for(dependencies)

        return _report_for(dependencies)


def _report_for(
    dependencies: dict[DependencyName, DependencyState],
) -> ReadinessReport:
    return ReadinessReport(
        status="ready" if all(state == "ready" for state in dependencies.values()) else "not_ready",
        dependencies=dependencies,
    )
