import logging
from collections.abc import Callable
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import (
    EvidenceUnavailable,
    IdempotencyConflict,
    InventoryNotFound,
    WorkOrderNotFound,
    WorkOrderStorageFailed,
    WriteNotAuthorized,
)
from opercerta.domain.replenishment import InventoryEvidence, PolicyEvidence
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
    server = FastMCP(
        "OperCerta Tools",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
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

    @server.tool(name="policy.list_constraints", structured_output=True)
    async def policy_list_constraints(
        action: Literal["replenish_inventory"],
        sku: str,
    ) -> PolicyEvidence:
        del action
        try:
            return catalog.policy_constraints(sku, clock())
        except InventoryNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("policy.list_constraints", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="work_order.create", structured_output=True)
    async def work_order_create(
        operation_id: UUID,
        sku: str,
        quantity: int,
        idempotency_key: str,
        approved_plan_hash: str,
    ) -> WorkOrderWriteResult:
        expected_key = derive_idempotency_key(operation_id)
        if idempotency_key != expected_key:
            raise ToolError(IdempotencyConflict.code)
        command = WorkOrderCommand(
            operation_id=operation_id,
            payload={
                "sku": sku,
                "quantity": quantity,
                "approved_plan_hash": approved_plan_hash,
            },
        )
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
