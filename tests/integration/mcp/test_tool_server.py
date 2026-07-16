from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.replenishment import InventoryEvidence, PolicyEvidence
from opercerta.domain.work_orders import (
    WorkOrderRecord,
    WorkOrderWriteResult,
    derive_idempotency_key,
)
from opercerta.infrastructure.db.schema import approvals, operations
from tests.integration.mcp.conftest import McpServerHarness


@dataclass(frozen=True, slots=True)
class SeededOperation:
    operation_id: UUID
    approved: bool


async def seed_operation(
    engine: AsyncEngine,
    *,
    approved: bool,
) -> SeededOperation:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=str(operation_id),
                request_payload={"message": "synthetic MCP tool test"},
                status="executing" if approved else "awaiting_approval",
                next_audit_sequence=0,
            )
        )
        if approved:
            await connection.execute(
                insert(approvals).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    approver_id="synthetic-tool-approver",
                    decision="approved",
                    reason="synthetic MCP transport approval",
                )
            )
    return SeededOperation(operation_id=operation_id, approved=approved)


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


def result_text(result: CallToolResult) -> str:
    content = result.content
    return "\n".join(str(item.text) for item in content if getattr(item, "type", None) == "text")


def expected_tool_error(tool_name: str, code: str) -> str:
    return f"Error executing tool {tool_name}: {code}"


@asynccontextmanager
async def open_mcp_session(url: str) -> AsyncIterator[ClientSession]:
    async with httpx.AsyncClient(trust_env=False) as http_client:
        async with streamable_http_client(
            url,
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


@pytest.mark.asyncio
async def test_real_transport_lists_exact_tools_and_returns_inventory(
    mcp_server: McpServerHarness,
) -> None:
    async with open_mcp_session(mcp_server.url) as session:
        listed = await session.list_tools()
        assert {tool.name for tool in listed.tools} == {
            "inventory.get_snapshot",
            "policy.list_constraints",
            "work_order.create",
            "work_order.get",
        }

        result = await session.call_tool(
            "inventory.get_snapshot",
            {"sku": "SKU-LOW-001"},
        )

    assert result.isError is False
    parsed = InventoryEvidence.model_validate(result.structuredContent)
    assert parsed.on_hand_quantity == 20
    assert parsed.reserved_quantity == 8


@pytest.mark.asyncio
async def test_inventory_and_policy_tools_return_stable_structured_contracts(
    mcp_server: McpServerHarness,
) -> None:
    async with open_mcp_session(mcp_server.url) as session:
        missing = await session.call_tool(
            "inventory.get_snapshot",
            {"sku": "SKU-UNKNOWN-001"},
        )
        policy_result = await session.call_tool(
            "policy.list_constraints",
            {
                "action": "replenish_inventory",
                "sku": "SKU-LOW-001",
            },
        )

    assert missing.isError is True
    assert result_text(missing) == expected_tool_error(
        "inventory.get_snapshot",
        "inventory_not_found",
    )
    assert policy_result.isError is False
    policy = PolicyEvidence.model_validate(policy_result.structuredContent)
    assert policy.rule_version == "replenishment-v1"
    assert policy.approval_required is True


@pytest.mark.asyncio
async def test_work_order_create_requires_approval_then_gets_same_record(
    engine: AsyncEngine,
    mcp_server: McpServerHarness,
) -> None:
    unauthorized = await seed_operation(engine, approved=False)
    authorized = await seed_operation(engine, approved=True)

    try:
        async with open_mcp_session(mcp_server.url) as session:
            denied = await session.call_tool(
                "work_order.create",
                {
                    "operation_id": str(unauthorized.operation_id),
                    "sku": "SKU-LOW-001",
                    "quantity": 18,
                    "idempotency_key": derive_idempotency_key(unauthorized.operation_id),
                    "approved_plan_hash": "b" * 64,
                },
            )
            created_result = await session.call_tool(
                "work_order.create",
                {
                    "operation_id": str(authorized.operation_id),
                    "sku": "SKU-LOW-001",
                    "quantity": 18,
                    "idempotency_key": derive_idempotency_key(authorized.operation_id),
                    "approved_plan_hash": "b" * 64,
                },
            )
            created = WorkOrderWriteResult.model_validate(created_result.structuredContent)
            fetched_result = await session.call_tool(
                "work_order.get",
                {"work_order_id": str(created.work_order.id)},
            )

        assert denied.isError is True
        assert result_text(denied) == expected_tool_error(
            "work_order.create",
            "write_not_authorized",
        )
        assert created_result.isError is False
        assert fetched_result.isError is False
        fetched = WorkOrderRecord.model_validate(fetched_result.structuredContent)
        assert fetched.id == created.work_order.id
        assert fetched.operation_id == authorized.operation_id
        assert fetched.payload == created.work_order.payload
    finally:
        await cleanup_operation(engine, unauthorized.operation_id)
        await cleanup_operation(engine, authorized.operation_id)


@pytest.mark.asyncio
async def test_tool_errors_are_stable_and_do_not_expose_connection_details(
    engine: AsyncEngine,
    mcp_server: McpServerHarness,
) -> None:
    missing_work_order_id = uuid4()

    async with open_mcp_session(mcp_server.url) as session:
        missing_get = await session.call_tool(
            "work_order.get",
            {"work_order_id": str(missing_work_order_id)},
        )
        missing_operation = await session.call_tool(
            "work_order.create",
            {
                "operation_id": str(uuid4()),
                "sku": "SKU-LOW-001",
                "quantity": 18,
                "idempotency_key": "work-order:v1:wrong",
                "approved_plan_hash": "b" * 64,
            },
        )

    assert missing_get.isError is True
    assert result_text(missing_get) == expected_tool_error(
        "work_order.get",
        "work_order_not_found",
    )
    assert missing_operation.isError is True
    assert result_text(missing_operation) == expected_tool_error(
        "work_order.create",
        "idempotency_conflict",
    )
    combined = f"{result_text(missing_get)}\n{result_text(missing_operation)}".lower()
    assert "postgresql" not in combined
    assert "password" not in combined
    assert "traceback" not in combined
