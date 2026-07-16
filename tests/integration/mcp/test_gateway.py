from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from mcp.types import CallToolResult, TextContent

from opercerta.domain.errors import (
    EvidenceUnavailable,
    InvalidInventoryEvidence,
    InventoryNotFound,
    UnknownTool,
)
from opercerta.domain.replenishment import InventoryEvidence
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderWriteResult,
    derive_idempotency_key,
)
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from tests.integration.mcp.conftest import McpServerHarness

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
OPERATION_ID = UUID("10000000-0000-4000-8000-000000000001")
WORK_ORDER_ID = UUID("20000000-0000-4000-8000-000000000002")


def tool_result(
    *,
    structured: dict[str, Any] | None = None,
    error_text: str | None = None,
) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=error_text or "structured result",
            )
        ],
        structuredContent=structured,
        isError=error_text is not None,
    )


def inventory_payload() -> dict[str, Any]:
    return InventoryEvidence(
        evidence_id=UUID("30000000-0000-4000-8000-000000000003"),
        sku="SKU-LOW-001",
        on_hand_quantity=20,
        reserved_quantity=8,
        captured_at=NOW,
        source_version="inventory-seed-v1",
    ).model_dump(mode="json")


def work_order_result_payload() -> dict[str, Any]:
    return {
        "work_order": {
            "id": str(WORK_ORDER_ID),
            "operation_id": str(OPERATION_ID),
            "idempotency_key": derive_idempotency_key(OPERATION_ID),
            "payload": {
                "sku": "SKU-LOW-001",
                "quantity": 18,
                "approved_plan_hash": "b" * 64,
            },
            "payload_hash": "c" * 64,
            "status": "created",
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        },
        "replayed": False,
    }


class NoNetworkSessionFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, url: str, timeout_seconds: float) -> object:
        del url, timeout_seconds
        self.calls += 1
        raise AssertionError("network session must not be created")


class FakeSession:
    def __init__(self, factory: "SequenceSessionFactory") -> None:
        self._factory = factory

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> CallToolResult:
        self._factory.tool_calls.append((name, arguments.copy()))
        event = self._factory.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


class SequenceSessionFactory:
    def __init__(self, events: list[CallToolResult | Exception]) -> None:
        self.events = events
        self.attempts = 0
        self.tool_calls: list[tuple[str, dict[str, object]]] = []

    @asynccontextmanager
    async def __call__(
        self,
        url: str,
        timeout_seconds: float,
    ) -> AsyncIterator[FakeSession]:
        del url, timeout_seconds
        self.attempts += 1
        yield FakeSession(self)


@pytest.mark.parametrize(
    ("timeout_seconds", "max_attempts"),
    [
        (0, 2),
        (-1, 2),
        (1, 0),
        (1, -1),
    ],
)
def test_gateway_rejects_unbounded_runtime_configuration(
    timeout_seconds: float,
    max_attempts: int,
) -> None:
    with pytest.raises(ValueError):
        McpToolGateway(
            "http://127.0.0.1:1/mcp",
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )


@pytest.mark.asyncio
async def test_real_gateway_reads_inventory_and_policy(
    mcp_server: McpServerHarness,
) -> None:
    gateway = McpToolGateway(
        mcp_server.url,
        timeout_seconds=2,
        max_attempts=2,
    )

    inventory = await gateway.get_inventory("SKU-LOW-001")
    policy = await gateway.get_policy("SKU-LOW-001")

    assert inventory.sku == policy.sku == "SKU-LOW-001"
    assert inventory.on_hand_quantity == 20
    assert policy.rule_version == "replenishment-v1"


@pytest.mark.asyncio
async def test_unknown_tool_fails_before_network_session_creation() -> None:
    no_network = NoNetworkSessionFactory()
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=2,
        session_factory=no_network,
    )

    with pytest.raises(UnknownTool, match="unknown_tool"):
        await gateway.call_raw("inventory.delete", {})
    assert no_network.calls == 0


@pytest.mark.asyncio
async def test_one_transport_failure_retries_then_validates_success() -> None:
    factory = SequenceSessionFactory(
        [
            httpx.ConnectError("synthetic connection failure"),
            tool_result(structured=inventory_payload()),
        ]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        max_attempts=2,
        session_factory=factory,
    )

    result = await gateway.get_inventory("SKU-LOW-001")

    assert result.sku == "SKU-LOW-001"
    assert factory.attempts == 2


@pytest.mark.asyncio
async def test_two_transport_timeouts_become_evidence_unavailable() -> None:
    factory = SequenceSessionFactory(
        [
            httpx.ReadTimeout("synthetic timeout one"),
            TimeoutError("synthetic timeout two"),
        ]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        max_attempts=2,
        session_factory=factory,
    )

    with pytest.raises(EvidenceUnavailable, match="evidence_unavailable"):
        await gateway.get_inventory("SKU-LOW-001")
    assert factory.attempts == 2


@pytest.mark.asyncio
async def test_stable_inventory_not_found_is_not_retried() -> None:
    factory = SequenceSessionFactory(
        [
            tool_result(
                error_text=("Error executing tool inventory.get_snapshot: inventory_not_found")
            )
        ]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        max_attempts=2,
        session_factory=factory,
    )

    with pytest.raises(InventoryNotFound, match="inventory_not_found"):
        await gateway.get_inventory("SKU-UNKNOWN-001")
    assert factory.attempts == 1


@pytest.mark.asyncio
async def test_invalid_inventory_structured_output_is_rejected() -> None:
    factory = SequenceSessionFactory(
        [tool_result(structured={**inventory_payload(), "on_hand_quantity": "20"})]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        session_factory=factory,
    )

    with pytest.raises(
        InvalidInventoryEvidence,
        match="invalid_inventory_evidence",
    ):
        await gateway.get_inventory("SKU-LOW-001")


@pytest.mark.asyncio
async def test_unknown_server_error_text_is_hidden_by_stable_error() -> None:
    factory = SequenceSessionFactory(
        [
            tool_result(
                error_text=(
                    "Error executing tool inventory.get_snapshot: "
                    "postgresql://user:secret@host/database"
                )
            )
        ]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        session_factory=factory,
    )

    with pytest.raises(EvidenceUnavailable) as captured:
        await gateway.get_inventory("SKU-LOW-001")
    assert str(captured.value) == "evidence_unavailable"


@pytest.mark.asyncio
async def test_create_retry_reuses_identical_arguments_and_validates_result() -> None:
    factory = SequenceSessionFactory(
        [
            httpx.ConnectError("synthetic create failure"),
            tool_result(structured=work_order_result_payload()),
        ]
    )
    gateway = McpToolGateway(
        "http://127.0.0.1:1/mcp",
        timeout_seconds=0.1,
        max_attempts=2,
        session_factory=factory,
    )
    command = WorkOrderCommand(
        operation_id=OPERATION_ID,
        payload={
            "sku": "SKU-LOW-001",
            "quantity": 18,
            "approved_plan_hash": "b" * 64,
        },
    )

    result = await gateway.create_work_order(command, plan_hash="b" * 64)

    assert isinstance(result, WorkOrderWriteResult)
    assert result.work_order.id == WORK_ORDER_ID
    assert factory.attempts == 2
    assert len(factory.tool_calls) == 2
    assert factory.tool_calls[0] == factory.tool_calls[1]
    assert factory.tool_calls[0] == (
        "work_order.create",
        {
            "operation_id": OPERATION_ID,
            "sku": "SKU-LOW-001",
            "quantity": 18,
            "idempotency_key": derive_idempotency_key(OPERATION_ID),
            "approved_plan_hash": "b" * 64,
        },
    )
