from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import BaseModel

from opercerta.agent.tool_executor import ReadToolResult, ToolExecutor
from opercerta.domain.agent import CacheStatus, ToolCallProposal
from opercerta.domain.errors import EvidenceUnavailable
from opercerta.domain.replenishment import InventoryEvidence

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
EVIDENCE_ID = UUID("30000000-0000-4000-8000-000000000003")


class FakeReadGateway:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, object]] = []

    async def read_agent_tool(self, name: object, arguments: object) -> object:
        self.calls.append((name, arguments))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class EvidenceWithoutId(BaseModel):
    value: str


def proposal() -> ToolCallProposal:
    return ToolCallProposal(
        tool_call_id="call-001",
        tool_name="inventory.get_snapshot",
        arguments={"sku": "SKU-DEMO-001"},
    )


@pytest.mark.asyncio
async def test_executor_returns_hashed_typed_observation() -> None:
    evidence = InventoryEvidence(
        evidence_id=EVIDENCE_ID,
        sku="SKU-DEMO-001",
        on_hand_quantity=3,
        reserved_quantity=1,
        captured_at=NOW,
        source_version="inventory-seed-v1",
    )
    gateway = FakeReadGateway(evidence)

    observation = await ToolExecutor(gateway).execute(proposal())

    assert observation.tool_call_id == "call-001"
    assert observation.tool_name == "inventory.get_snapshot"
    assert observation.arguments_hash == (
        "549e9aab59c3bf2f193bf1c9db29ea2398ab2cd5d87a99cf3fede36290e9377b"
    )
    assert observation.status == "ok"
    assert observation.evidence_ref == EVIDENCE_ID
    assert observation.structured_payload["sku"] == "SKU-DEMO-001"
    assert observation.cache_status is CacheStatus.BYPASS
    assert gateway.calls == [(proposal().tool_name, {"sku": "SKU-DEMO-001"})]


@pytest.mark.asyncio
async def test_executor_projects_gateway_cache_status_into_observation() -> None:
    evidence = InventoryEvidence(
        evidence_id=EVIDENCE_ID,
        sku="SKU-DEMO-001",
        on_hand_quantity=3,
        reserved_quantity=1,
        captured_at=NOW,
        source_version="inventory-seed-v1",
    )
    gateway = FakeReadGateway(ReadToolResult(evidence=evidence, cache_status=CacheStatus.HIT))

    observation = await ToolExecutor(gateway).execute(proposal())  # type: ignore[arg-type]

    assert observation.cache_status is CacheStatus.HIT
    assert observation.structured_payload["sku"] == "SKU-DEMO-001"


@pytest.mark.asyncio
async def test_executor_reduces_expected_failure_to_safe_observation() -> None:
    observation = await ToolExecutor(FakeReadGateway(EvidenceUnavailable())).execute(proposal())

    assert observation.status == "error"
    assert observation.evidence_ref is None
    assert observation.safe_summary == "只读证据不可用。"
    assert observation.structured_payload == {"error_code": "evidence_unavailable"}


@pytest.mark.asyncio
async def test_executor_does_not_hide_programming_errors() -> None:
    with pytest.raises(RuntimeError, match="unexpected_bug"):
        await ToolExecutor(FakeReadGateway(RuntimeError("unexpected_bug"))).execute(proposal())


@pytest.mark.asyncio
async def test_executor_rejects_success_payload_without_evidence_id() -> None:
    with pytest.raises(TypeError, match="read_tool_evidence_invalid"):
        await ToolExecutor(FakeReadGateway(EvidenceWithoutId(value="invalid"))).execute(proposal())
