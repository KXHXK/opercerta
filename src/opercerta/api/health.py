from typing import Literal, Protocol

from pydantic import BaseModel

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
