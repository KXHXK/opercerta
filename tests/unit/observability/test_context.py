import asyncio
from uuid import UUID

import pytest

from opercerta.observability.context import (
    current_request_id,
    new_request_id,
    request_context,
)


def test_new_request_id_is_uuid4() -> None:
    request_id = new_request_id()
    parsed = UUID(request_id)

    assert parsed.version == 4
    assert str(parsed) == request_id


@pytest.mark.asyncio
async def test_request_context_is_isolated_and_restored() -> None:
    async def observe(request_id: str) -> str | None:
        with request_context(request_id):
            await asyncio.sleep(0)
            return current_request_id()

    observed = await asyncio.gather(observe("request-a"), observe("request-b"))

    assert observed == ["request-a", "request-b"]
    assert current_request_id() is None
