import json

import pytest

from opercerta.infrastructure.cache import NullEvidenceCache, RedisEvidenceCache
from opercerta.observability.tracing import NOOP_TRACING
from opercerta.workflow.controlled_action_graph import CachedControlledEvidenceGateway


class FailingRedis:
    async def get(self, key: str) -> bytes | None:
        del key
        raise ConnectionError("redis unavailable")

    async def set(self, key: str, value: str, *, ex: int) -> None:
        del key, value, ex
        raise ConnectionError("redis unavailable")


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttl: int | None = None

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value.encode()
        self.ttl = ex


class CountingInventoryGateway:
    def __init__(self) -> None:
        self.inventory_calls = 0

    async def get_inventory(self, sku: str) -> dict[str, object]:
        self.inventory_calls += 1
        return {"sku": sku, "source_version": "inventory-v1"}


@pytest.mark.asyncio
async def test_cache_failure_becomes_miss_and_never_blocks_evidence() -> None:
    outcomes: list[str] = []
    cache = RedisEvidenceCache(FailingRedis(), outcomes.append)

    assert await cache.get("inventory:SKU-1") is None
    await cache.set("inventory:SKU-1", {"available": 1}, ttl_seconds=30)

    assert outcomes == ["error", "error"]


@pytest.mark.asyncio
async def test_cache_metrics_failure_never_blocks_cache_bypass() -> None:
    def failing_observer(outcome: str) -> None:
        del outcome
        raise RuntimeError("metrics unavailable")

    cache = RedisEvidenceCache(FailingRedis(), failing_observer)

    assert await cache.get("inventory:SKU-1") is None
    await cache.set("inventory:SKU-1", {"available": 1}, ttl_seconds=30)


@pytest.mark.asyncio
async def test_cache_round_trip_is_json_and_ttl_bounded() -> None:
    client = MemoryRedis()
    cache = RedisEvidenceCache(client)
    value = {"source_version": "v1", "available": 12}

    await cache.set("inventory:SKU-1", value, ttl_seconds=45)

    assert await cache.get("inventory:SKU-1") == value
    assert client.ttl == 45
    assert json.loads(client.values["inventory:SKU-1"]) == value


@pytest.mark.asyncio
async def test_null_cache_is_always_a_safe_miss() -> None:
    cache = NullEvidenceCache()
    await cache.set("key", {"ignored": True}, ttl_seconds=1)
    assert await cache.get("key") is None


@pytest.mark.asyncio
async def test_initial_evidence_gateway_reuses_cached_read() -> None:
    delegate = CountingInventoryGateway()
    cache = RedisEvidenceCache(MemoryRedis())
    gateway = CachedControlledEvidenceGateway(  # type: ignore[arg-type]
        delegate,
        cache,
        ttl_seconds=30,
        tracing=NOOP_TRACING,
    )
    # The production builder uses this wrapper only for initial/query collection.
    assert await gateway.get_inventory("SKU-1") == {
        "sku": "SKU-1",
        "source_version": "inventory-v1",
    }
    assert await gateway.get_inventory("SKU-1") == {
        "sku": "SKU-1",
        "source_version": "inventory-v1",
    }
    assert delegate.inventory_calls == 1
