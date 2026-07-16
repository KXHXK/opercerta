from datetime import UTC, datetime
from uuid import UUID

import pytest

from opercerta.application.approval_expiry import ApprovalExpiryService

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
FIRST_ID = UUID("10000000-0000-4000-8000-000000000001")
SECOND_ID = UUID("20000000-0000-4000-8000-000000000002")


class FakeOperationRepository:
    def __init__(self) -> None:
        self.list_calls: list[tuple[datetime, int]] = []
        self.mark_calls: list[tuple[UUID, datetime]] = []
        self.due_ids = [FIRST_ID, SECOND_ID]
        self.mark_results = {
            FIRST_ID: True,
            SECOND_ID: False,
        }

    async def list_due_approval_ids(
        self,
        now: datetime,
        limit: int,
    ) -> list[UUID]:
        self.list_calls.append((now, limit))
        return self.due_ids[:limit]

    async def mark_expired(self, operation_id: UUID, now: datetime) -> bool:
        self.mark_calls.append((operation_id, now))
        return self.mark_results[operation_id]


def fixed_clock(calls: list[datetime]) -> datetime:
    calls.append(NOW)
    return NOW


@pytest.mark.asyncio
async def test_expire_operation_passes_exact_clock_value_to_repository() -> None:
    repository = FakeOperationRepository()
    clock_calls: list[datetime] = []
    service = ApprovalExpiryService(
        repository=repository,
        clock=lambda: fixed_clock(clock_calls),
    )

    assert await service.expire_operation(FIRST_ID) is True
    assert clock_calls == [NOW]
    assert repository.mark_calls == [(FIRST_ID, NOW)]
    assert repository.list_calls == []


@pytest.mark.asyncio
async def test_expire_due_uses_one_clock_read_and_returns_only_committed_expiries() -> None:
    repository = FakeOperationRepository()
    clock_calls: list[datetime] = []
    service = ApprovalExpiryService(
        repository=repository,
        clock=lambda: fixed_clock(clock_calls),
    )

    expired_ids = await service.expire_due(limit=2)

    assert expired_ids == [FIRST_ID]
    assert clock_calls == [NOW]
    assert repository.list_calls == [(NOW, 2)]
    assert repository.mark_calls == [
        (FIRST_ID, NOW),
        (SECOND_ID, NOW),
    ]
