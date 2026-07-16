from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)


class ApprovalExpiryService:
    def __init__(
        self,
        repository: ReplenishmentOperationRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._clock = clock

    async def expire_operation(self, operation_id: UUID) -> bool:
        return await self._repository.mark_expired(operation_id, self._clock())

    async def expire_due(self, limit: int = 100) -> list[UUID]:
        now = self._clock()
        due_ids = await self._repository.list_due_approval_ids(now, limit)
        expired_ids: list[UUID] = []
        for operation_id in due_ids:
            if await self._repository.mark_expired(operation_id, now):
                expired_ids.append(operation_id)
        return expired_ids
