import json
from collections.abc import Awaitable, Callable
from typing import Protocol, cast


class AsyncRedisClient(Protocol):
    def get(self, key: str) -> Awaitable[bytes | str | None]: ...

    def set(self, key: str, value: str, *, ex: int) -> Awaitable[object]: ...


class EvidenceCache(Protocol):
    async def get(self, key: str) -> dict[str, object] | None: ...

    async def set(self, key: str, value: dict[str, object], ttl_seconds: int) -> None: ...


class NullEvidenceCache:
    async def get(self, key: str) -> dict[str, object] | None:
        del key
        return None

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

    async def get(self, key: str) -> dict[str, object] | None:
        try:
            raw = await self._client.get(key)
            if raw is None:
                self._record("miss")
                return None
            decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            value = json.loads(decoded)
            if not isinstance(value, dict):
                raise ValueError("cached evidence must be a JSON object")
            self._record("hit")
            return cast(dict[str, object], value)
        except Exception:
            self._record("error")
            return None

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
