from collections.abc import Awaitable, Callable
from typing import Protocol, cast
from uuid import UUID

from pydantic import BaseModel, JsonValue

from opercerta.agent.tool_executor import ReadToolResult
from opercerta.domain.agent import ReadToolName
from opercerta.domain.work_orders import WorkOrderCommand, WorkOrderRecord, WorkOrderWriteResult
from opercerta.observability.tracing import Tracing


class ControlledToolGateway(Protocol):
    async def get_inventory(self, sku: str) -> object: ...

    async def get_policy(self, sku: str) -> object: ...

    async def get_equipment(self, equipment_id: str) -> object: ...

    async def get_maintenance_policy(self, equipment_id: str) -> object: ...

    async def get_task(self, task_id: str) -> object: ...

    async def get_task_recovery_policy(self, task_id: str) -> object: ...

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> BaseModel | ReadToolResult: ...

    async def create_work_order(
        self,
        command: WorkOrderCommand,
        *,
        plan_hash: str,
    ) -> WorkOrderWriteResult: ...

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord: ...


class TracedControlledEvidenceGateway:
    """Apply MCP spans without coupling the production root to legacy graphs."""

    def __init__(self, delegate: ControlledToolGateway, tracing: Tracing) -> None:
        self._delegate = delegate
        self._tracing = tracing

    async def _read(self, loader: Callable[[], Awaitable[object]]) -> object:
        with self._tracing.span(
            "mcp.call",
            {"component": "mcp", "operation": "read"},
        ):
            return await loader()

    async def get_inventory(self, sku: str) -> object:
        return await self._read(lambda: self._delegate.get_inventory(sku))

    async def get_policy(self, sku: str) -> object:
        return await self._read(lambda: self._delegate.get_policy(sku))

    async def get_equipment(self, equipment_id: str) -> object:
        return await self._read(lambda: self._delegate.get_equipment(equipment_id))

    async def get_maintenance_policy(self, equipment_id: str) -> object:
        return await self._read(lambda: self._delegate.get_maintenance_policy(equipment_id))

    async def get_task(self, task_id: str) -> object:
        return await self._read(lambda: self._delegate.get_task(task_id))

    async def get_task_recovery_policy(self, task_id: str) -> object:
        return await self._read(lambda: self._delegate.get_task_recovery_policy(task_id))

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> BaseModel | ReadToolResult:
        result = await self._read(lambda: self._delegate.read_agent_tool(name, arguments))
        return cast(BaseModel | ReadToolResult, result)

    async def create_work_order(
        self,
        command: WorkOrderCommand,
        *,
        plan_hash: str,
    ) -> WorkOrderWriteResult:
        with self._tracing.span(
            "mcp.call",
            {"component": "mcp", "operation": "write"},
        ):
            return await self._delegate.create_work_order(command, plan_hash=plan_hash)

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord:
        result = await self._read(lambda: self._delegate.get_work_order(work_order_id))
        return cast(WorkOrderRecord, result)
