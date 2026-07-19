import logging
from collections.abc import Callable
from datetime import datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import (
    EquipmentNotFound,
    EvidenceUnavailable,
    IdempotencyConflict,
    InventoryNotFound,
    WorkOrderNotFound,
    WorkOrderStorageFailed,
    WriteNotAuthorized,
)
from opercerta.domain.maintenance import EquipmentEvidence, RepairWorkOrderPayload
from opercerta.domain.replenishment import InventoryEvidence
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    derive_idempotency_key,
)
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository
from opercerta.tools.catalog import SyntheticCatalog

LOGGER = logging.getLogger(__name__)


def log_safe_tool_failure(tool_name: str, error: Exception) -> None:
    LOGGER.error(
        "tool_failure tool=%s exception_type=%s correlation_id=%s",
        tool_name,
        type(error).__name__,
        uuid4(),
    )


def build_mcp_server(
    catalog: SyntheticCatalog,
    engine: AsyncEngine,
    clock: Callable[[], datetime],
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
) -> FastMCP:
    allowed_hosts = [
        host,
        f"{host}:{port}",
        "localhost",
        f"localhost:{port}",
        "mcp",
        f"mcp:{port}",
    ]
    server = FastMCP(
        "OperCerta Tools",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
    )

    @server.tool(name="inventory.get_snapshot", structured_output=True)
    async def inventory_get_snapshot(sku: str) -> InventoryEvidence:
        try:
            return catalog.inventory_snapshot(sku, clock())
        except InventoryNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("inventory.get_snapshot", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="equipment.get_status", structured_output=True)
    async def equipment_get_status(equipment_id: str) -> EquipmentEvidence:
        try:
            return catalog.equipment_status(equipment_id, clock())
        except EquipmentNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("equipment.get_status", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="policy.list_constraints", structured_output=True)
    async def policy_list_constraints(
        action: Literal["replenish_inventory", "repair_equipment"],
        sku: str | None = None,
        equipment_id: str | None = None,
    ) -> dict[str, JsonValue]:
        try:
            if action == "replenish_inventory" and sku is not None and equipment_id is None:
                return cast(
                    dict[str, JsonValue],
                    catalog.policy_constraints(sku, clock()).model_dump(mode="json"),
                )
            if action == "repair_equipment" and equipment_id is not None and sku is None:
                return cast(
                    dict[str, JsonValue],
                    catalog.maintenance_policy_constraints(equipment_id, clock()).model_dump(
                        mode="json"
                    ),
                )
            raise ValueError("action subject mismatch")
        except (InventoryNotFound, EquipmentNotFound) as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("policy.list_constraints", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="work_order.create", structured_output=True)
    async def work_order_create(
        operation_id: UUID,
        idempotency_key: str,
        approved_plan_hash: str,
        kind: Literal["replenishment", "repair"] = "replenishment",
        sku: str | None = None,
        quantity: int | None = None,
        equipment_id: str | None = None,
        alert_code: str | None = None,
        priority: Literal["normal", "high", "urgent"] | None = None,
    ) -> WorkOrderWriteResult:
        expected_key = derive_idempotency_key(operation_id)
        if idempotency_key != expected_key:
            raise ToolError(IdempotencyConflict.code)
        if kind == "replenishment":
            if (
                sku is None
                or quantity is None
                or any(value is not None for value in (equipment_id, alert_code, priority))
            ):
                raise ToolError(WorkOrderStorageFailed.code)
            payload: dict[str, JsonValue] = {
                "sku": sku,
                "quantity": quantity,
                "approved_plan_hash": approved_plan_hash,
            }
        else:
            if (
                equipment_id is None
                or alert_code is None
                or priority is None
                or sku is not None
                or quantity is not None
            ):
                raise ToolError(WorkOrderStorageFailed.code)
            payload = cast(
                dict[str, JsonValue],
                RepairWorkOrderPayload(
                    equipment_id=equipment_id,
                    alert_code=alert_code,
                    priority=priority,
                    approved_plan_hash=approved_plan_hash,
                ).model_dump(mode="json"),
            )
        command = WorkOrderCommand(operation_id=operation_id, payload=payload)
        try:
            return await WorkOrderRepository(engine).create_or_get(command)
        except (WriteNotAuthorized, IdempotencyConflict) as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("work_order.create", error)
            raise ToolError(WorkOrderStorageFailed.code) from None

    @server.tool(name="work_order.get", structured_output=True)
    async def work_order_get(work_order_id: UUID) -> WorkOrderRecord:
        try:
            return await WorkOrderRepository(engine).get(work_order_id)
        except WorkOrderNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("work_order.get", error)
            raise ToolError(WorkOrderStorageFailed.code) from None

    return server
