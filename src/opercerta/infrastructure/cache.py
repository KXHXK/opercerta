import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, cast

from opercerta.domain.agent import CacheStatus


@dataclass(frozen=True)
class CacheLookup:
    status: CacheStatus
    value: dict[str, object] | None


def evidence_cache_key(kind: str, object_id: str) -> str:
    parameters_hash = sha256(
        json.dumps(
            {"kind": kind, "object_id": object_id},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"opercerta:evidence:v1:{kind}:{parameters_hash}"


class AsyncRedisClient(Protocol):
    def get(self, key: str) -> Awaitable[bytes | str | None]: ...

    def set(self, key: str, value: str, *, ex: int) -> Awaitable[object]: ...


class EvidenceCache(Protocol):
    async def lookup(self, key: str) -> CacheLookup: ...

    async def get(self, key: str) -> dict[str, object] | None: ...

    async def set(self, key: str, value: dict[str, object], ttl_seconds: int) -> None: ...


class NullEvidenceCache:
    async def lookup(self, key: str) -> CacheLookup:
        del key
        return CacheLookup(CacheStatus.BYPASS, None)

    async def get(self, key: str) -> dict[str, object] | None:
        return (await self.lookup(key)).value

    async def set(self, key: str, value: dict[str, object], ttl_seconds: int) -> None:
        del key, value, ttl_seconds


class RedisEvidenceCache:
    def __init__(
        self,
        client: AsyncRedisClient,
        observe: Callable[[str], None] = lambda outcome: None,
    ) -> None:
        self._client = client
        self._observe = observe

    def _record(self, outcome: str) -> None:
        try:
            self._observe(outcome)
        except Exception:
            pass

    async def lookup(self, key: str) -> CacheLookup:
        try:
            raw = await self._client.get(key)
            if raw is None:
                self._record("miss")
                return CacheLookup(CacheStatus.MISS, None)
            decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            value = json.loads(decoded)
            if not isinstance(value, dict):
                raise ValueError("cached evidence must be a JSON object")
            self._record("hit")
            return CacheLookup(CacheStatus.HIT, cast(dict[str, object], value))
        except Exception:
            self._record("error")
            return CacheLookup(CacheStatus.UNAVAILABLE, None)

    async def get(self, key: str) -> dict[str, object] | None:
        return (await self.lookup(key)).value

    async def set(self, key: str, value: dict[str, object], ttl_seconds: int) -> None:
        try:
            if ttl_seconds <= 0:
                raise ValueError("cache ttl must be positive")
            await self._client.set(
                key,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )
            self._record("write")
        except Exception:
            self._record("error")
