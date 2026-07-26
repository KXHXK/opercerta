from datetime import UTC, datetime
from uuid import UUID

import pytest

from opercerta.agent.tool_executor import ReadToolResult
from opercerta.domain.agent import CacheStatus, ReadToolName
from opercerta.domain.replenishment import InventoryEvidence
from opercerta.infrastructure.cache import RedisEvidenceCache
from opercerta.infrastructure.observation_gateway import CachedReadToolGateway
from opercerta.observability.tracing import NOOP_TRACING

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        del ex
        self.values[key] = value.encode()


class FailingRedis:
    async def get(self, key: str) -> bytes | None:
        del key
        raise ConnectionError("redis unavailable")

    async def set(self, key: str, value: str, *, ex: int) -> None:
        del key, value, ex
        raise ConnectionError("redis unavailable")


class CountingReadGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, object],
    ) -> InventoryEvidence:
        assert name is ReadToolName.INVENTORY_SNAPSHOT
        assert arguments == {"sku": "SKU-DEMO-001"}
        self.calls += 1
        return InventoryEvidence(
            evidence_id=UUID("30000000-0000-4000-8000-000000000026"),
            sku="SKU-DEMO-001",
            on_hand_quantity=3,
            reserved_quantity=1,
            captured_at=NOW,
            source_version="inventory-seed-v1",
        )


@pytest.mark.asyncio
async def test_agent_read_gateway_records_miss_then_hit_and_reuses_typed_evidence() -> None:
    delegate = CountingReadGateway()
    gateway = CachedReadToolGateway(
        delegate,  # type: ignore[arg-type]
        RedisEvidenceCache(MemoryRedis()),
        ttl_seconds=30,
        tracing=NOOP_TRACING,
    )

    first = await gateway.read_agent_tool(
        ReadToolName.INVENTORY_SNAPSHOT,
        {"sku": "SKU-DEMO-001"},
    )
    second = await gateway.read_agent_tool(
        ReadToolName.INVENTORY_SNAPSHOT,
        {"sku": "SKU-DEMO-001"},
    )

    assert isinstance(first, ReadToolResult)
    assert first.cache_status is CacheStatus.MISS
    assert second.cache_status is CacheStatus.HIT
    assert isinstance(second.evidence, InventoryEvidence)
    assert second.evidence.evidence_id == first.evidence.evidence_id
    assert delegate.calls == 1


@pytest.mark.asyncio
async def test_agent_read_gateway_bypasses_cache_when_fresh_evidence_is_required() -> None:
    delegate = CountingReadGateway()
    gateway = CachedReadToolGateway(
        delegate,  # type: ignore[arg-type]
        RedisEvidenceCache(MemoryRedis()),
        ttl_seconds=30,
        tracing=NOOP_TRACING,
        bypass_cache=True,
    )

    first = await gateway.read_agent_tool(
        ReadToolName.INVENTORY_SNAPSHOT,
        {"sku": "SKU-DEMO-001"},
    )
    second = await gateway.read_agent_tool(
        ReadToolName.INVENTORY_SNAPSHOT,
        {"sku": "SKU-DEMO-001"},
    )

    assert first.cache_status is CacheStatus.BYPASS
    assert second.cache_status is CacheStatus.BYPASS
    assert delegate.calls == 2


@pytest.mark.asyncio
async def test_agent_read_gateway_marks_redis_failure_and_uses_authoritative_source() -> None:
    delegate = CountingReadGateway()
    gateway = CachedReadToolGateway(
        delegate,  # type: ignore[arg-type]
        RedisEvidenceCache(FailingRedis()),
        ttl_seconds=30,
        tracing=NOOP_TRACING,
    )

    result = await gateway.read_agent_tool(
        ReadToolName.INVENTORY_SNAPSHOT,
        {"sku": "SKU-DEMO-001"},
    )

    assert result.cache_status is CacheStatus.UNAVAILABLE
    assert result.evidence.sku == "SKU-DEMO-001"
    assert delegate.calls == 1
