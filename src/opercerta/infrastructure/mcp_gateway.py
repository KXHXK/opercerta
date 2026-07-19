from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Any, Protocol, cast
from uuid import UUID

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from opercerta.domain.errors import (
    EquipmentNotFound,
    EvidenceUnavailable,
    IdempotencyConflict,
    InvalidEquipmentEvidence,
    InvalidInventoryEvidence,
    InvalidMaintenancePolicyEvidence,
    InvalidPolicyEvidence,
    InvalidTaskEvidence,
    InvalidTaskRecoveryPolicyEvidence,
    InventoryNotFound,
    OperationNotFound,
    TaskNotFound,
    UnknownTool,
    WorkOrderNotFound,
    WorkOrderStorageFailed,
    WriteNotAuthorized,
)
from opercerta.domain.maintenance import EquipmentEvidence, MaintenancePolicyEvidence
from opercerta.domain.replenishment import InventoryEvidence, PolicyEvidence
from opercerta.domain.task_recovery import TaskEvidence, TaskRecoveryPolicyEvidence
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    derive_idempotency_key,
)

ALLOWED_TOOLS = frozenset(
    {
        "equipment.get_status",
        "inventory.get_snapshot",
        "policy.list_constraints",
        "task.get_status",
        "work_order.create",
        "work_order.get",
    }
)


class McpSessionFactory(Protocol):
    def __call__(
        self,
        url: str,
        timeout_seconds: float,
    ) -> AbstractAsyncContextManager[ClientSession]: ...


@asynccontextmanager
async def default_session_factory(
    url: str,
    timeout_seconds: float,
) -> AsyncIterator[ClientSession]:
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        trust_env=False,
    ) as http_client:
        async with streamable_http_client(
            url,
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=timeout_seconds),
            ) as session:
                await session.initialize()
                yield session


class McpToolGateway:
    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_attempts: int = 2,
        session_factory: McpSessionFactory = default_session_factory,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._session_factory = session_factory

    async def get_inventory(self, sku: str) -> InventoryEvidence:
        result = await self.call_raw(
            "inventory.get_snapshot",
            {"sku": sku},
        )
        self._raise_tool_error(
            "inventory.get_snapshot",
            {"sku": sku},
            result,
        )
        try:
            return InventoryEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidInventoryEvidence from None

    async def get_policy(self, sku: str) -> PolicyEvidence:
        arguments: dict[str, object] = {
            "action": "replenish_inventory",
            "sku": sku,
        }
        result = await self.call_raw("policy.list_constraints", arguments)
        self._raise_tool_error("policy.list_constraints", arguments, result)
        try:
            return PolicyEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidPolicyEvidence from None

    async def get_equipment(self, equipment_id: str) -> EquipmentEvidence:
        arguments: dict[str, object] = {"equipment_id": equipment_id}
        result = await self.call_raw("equipment.get_status", arguments)
        self._raise_tool_error("equipment.get_status", arguments, result)
        try:
            return EquipmentEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidEquipmentEvidence from None

    async def get_maintenance_policy(
        self,
        equipment_id: str,
    ) -> MaintenancePolicyEvidence:
        arguments: dict[str, object] = {
            "action": "repair_equipment",
            "equipment_id": equipment_id,
        }
        result = await self.call_raw("policy.list_constraints", arguments)
        self._raise_tool_error("policy.list_constraints", arguments, result)
        try:
            return MaintenancePolicyEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidMaintenancePolicyEvidence from None

    async def get_task(self, task_id: str) -> TaskEvidence:
        arguments: dict[str, object] = {"task_id": task_id}
        result = await self.call_raw("task.get_status", arguments)
        self._raise_tool_error("task.get_status", arguments, result)
        try:
            return TaskEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidTaskEvidence from None

    async def get_task_recovery_policy(self, task_id: str) -> TaskRecoveryPolicyEvidence:
        arguments: dict[str, object] = {
            "action": "recover_task",
            "task_id": task_id,
        }
        result = await self.call_raw("policy.list_constraints", arguments)
        self._raise_tool_error("policy.list_constraints", arguments, result)
        try:
            return TaskRecoveryPolicyEvidence.model_validate(result.structuredContent)
        except ValidationError:
            raise InvalidTaskRecoveryPolicyEvidence from None

    async def create_work_order(
        self,
        command: WorkOrderCommand,
        *,
        plan_hash: str,
    ) -> WorkOrderWriteResult:
        kind = command.payload.get("kind")
        arguments: dict[str, object]
        if kind == "repair":
            equipment_id = command.payload.get("equipment_id")
            alert_code = command.payload.get("alert_code")
            priority = command.payload.get("priority")
            if not all(isinstance(value, str) for value in (equipment_id, alert_code, priority)):
                raise WorkOrderStorageFailed
            arguments = {
                "operation_id": command.operation_id,
                "kind": "repair",
                "equipment_id": equipment_id,
                "alert_code": alert_code,
                "priority": priority,
                "idempotency_key": derive_idempotency_key(command.operation_id),
                "approved_plan_hash": plan_hash,
            }
        elif kind == "task_recovery":
            task_id = command.payload.get("task_id")
            blocker_code = command.payload.get("blocker_code")
            retry_count = command.payload.get("retry_count")
            recovery_action = command.payload.get("recovery_action")
            if (
                not isinstance(task_id, str)
                or (blocker_code is not None and not isinstance(blocker_code, str))
                or type(retry_count) is not int
                or recovery_action != "manual_requeue"
            ):
                raise WorkOrderStorageFailed
            arguments = {
                "operation_id": command.operation_id,
                "kind": "task_recovery",
                "task_id": task_id,
                "blocker_code": blocker_code,
                "retry_count": retry_count,
                "recovery_action": recovery_action,
                "idempotency_key": derive_idempotency_key(command.operation_id),
                "approved_plan_hash": plan_hash,
            }
        else:
            sku = command.payload.get("sku")
            quantity = command.payload.get("quantity")
            if not isinstance(sku, str) or type(quantity) is not int:
                raise WorkOrderStorageFailed
            arguments = {
                "operation_id": command.operation_id,
                "sku": sku,
                "quantity": quantity,
                "idempotency_key": derive_idempotency_key(command.operation_id),
                "approved_plan_hash": plan_hash,
            }
        result = await self.call_raw("work_order.create", arguments)
        self._raise_tool_error("work_order.create", arguments, result)
        try:
            return WorkOrderWriteResult.model_validate(result.structuredContent)
        except ValidationError:
            raise WorkOrderStorageFailed from None

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord:
        arguments: dict[str, object] = {"work_order_id": work_order_id}
        result = await self.call_raw("work_order.get", arguments)
        self._raise_tool_error("work_order.get", arguments, result)
        try:
            return WorkOrderRecord.model_validate(result.structuredContent)
        except ValidationError:
            raise WorkOrderStorageFailed from None

    async def call_raw(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> CallToolResult:
        if name not in ALLOWED_TOOLS:
            raise UnknownTool

        for attempt in range(1, self._max_attempts + 1):
            try:
                async with self._session_factory(
                    self._url,
                    self._timeout_seconds,
                ) as session:
                    return await session.call_tool(
                        name,
                        cast(dict[str, Any], arguments),
                    )
            except Exception as error:
                if not self._is_transport_failure(error):
                    raise
                if attempt == self._max_attempts:
                    raise EvidenceUnavailable from None

        raise AssertionError("MCP retry loop produced no result")

    def _raise_tool_error(
        self,
        name: str,
        arguments: dict[str, object],
        result: CallToolResult,
    ) -> None:
        if not result.isError:
            return
        code = self._stable_error_code(name, result)
        if code == InventoryNotFound.code:
            raise InventoryNotFound
        if code == EquipmentNotFound.code:
            raise EquipmentNotFound
        if code == TaskNotFound.code:
            raise TaskNotFound
        if code == EvidenceUnavailable.code:
            raise EvidenceUnavailable
        if code == InvalidInventoryEvidence.code:
            raise InvalidInventoryEvidence
        if code == InvalidPolicyEvidence.code:
            raise InvalidPolicyEvidence
        if code == InvalidEquipmentEvidence.code:
            raise InvalidEquipmentEvidence
        if code == InvalidMaintenancePolicyEvidence.code:
            raise InvalidMaintenancePolicyEvidence
        if code == InvalidTaskEvidence.code:
            raise InvalidTaskEvidence
        if code == InvalidTaskRecoveryPolicyEvidence.code:
            raise InvalidTaskRecoveryPolicyEvidence
        if code == WorkOrderNotFound.code:
            raise WorkOrderNotFound
        if code == WorkOrderStorageFailed.code:
            raise WorkOrderStorageFailed

        operation_id_value = arguments.get("operation_id")
        if code == OperationNotFound.code and operation_id_value is not None:
            raise OperationNotFound(UUID(str(operation_id_value)))
        if code == WriteNotAuthorized.code and operation_id_value is not None:
            raise WriteNotAuthorized(UUID(str(operation_id_value)), "remote")
        if code == IdempotencyConflict.code and operation_id_value is not None:
            raise IdempotencyConflict(
                UUID(str(operation_id_value)),
                str(arguments.get("idempotency_key", "")),
            )

        if name.startswith("work_order."):
            raise WorkOrderStorageFailed
        raise EvidenceUnavailable

    def _stable_error_code(
        self,
        name: str,
        result: CallToolResult,
    ) -> str | None:
        text_items = [item.text for item in result.content if isinstance(item, TextContent)]
        if len(text_items) != 1:
            return None
        prefix = f"Error executing tool {name}: "
        text = text_items[0]
        if not text.startswith(prefix):
            return None
        code = text.removeprefix(prefix)
        if not code or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in code
        ):
            return None
        return code

    def _is_transport_failure(self, error: BaseException) -> bool:
        if isinstance(
            error,
            (
                httpx.TransportError,
                TimeoutError,
                anyio.EndOfStream,
                anyio.BrokenResourceError,
                anyio.ClosedResourceError,
            ),
        ):
            return True
        if isinstance(error, BaseExceptionGroup):
            return bool(error.exceptions) and all(
                self._is_transport_failure(nested) for nested in error.exceptions
            )
        return False
