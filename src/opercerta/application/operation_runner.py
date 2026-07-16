import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.domain.approvals import BoundApprovalCommand
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.replenishment import OperationError
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.workflow.replenishment_graph import (
    ReplenishmentGraph,
    build_replenishment_initial_state,
)
from opercerta.workflow.replenishment_recovery import (
    ReplenishmentRecoveryCoordinator,
)

LOGGER = logging.getLogger(__name__)


class OperationRunner:
    def __init__(
        self,
        graph: ReplenishmentGraph,
        approvals: ApprovalRepository,
        operations: ReplenishmentOperationRepository,
        recovery: ReplenishmentRecoveryCoordinator,
        expiry: ApprovalExpiryService,
        clock: Callable[[], datetime],
    ) -> None:
        self._graph = graph
        self._approvals = approvals
        self._operations = operations
        self._recovery = recovery
        self._expiry = expiry
        self._clock = clock

    async def start(self, request: OperationRequest) -> UUID:
        operation_id = await self._operations.create(request)
        await self._graph.ainvoke(
            build_replenishment_initial_state(operation_id, request),
            config=self._config(operation_id),
        )
        return operation_id

    async def submit_approval(
        self,
        command: BoundApprovalCommand,
        now: datetime,
    ) -> UUID:
        self._require_aware(now)
        approval = await self._approvals.submit_bound_once(command, now)
        resume_command: Command[Any] = Command(
            resume={
                "approval_id": str(approval.id),
                "decision": approval.decision.value,
            }
        )
        await self._graph.ainvoke(
            resume_command,
            config=self._config(command.operation_id),
        )
        return command.operation_id

    async def recover_all(self) -> list[UUID]:
        await self.expire_due()
        recovered: list[UUID] = []
        for operation_id in await self._operations.list_recoverable_ids():
            try:
                await self._recovery.recover(operation_id)
            except RecoveryStateConflict:
                await self._operations.mark_failed(
                    operation_id,
                    OperationError(
                        code=RecoveryStateConflict.code,
                        message="Business facts conflict with the saved workflow checkpoint.",
                    ),
                )
            except Exception:
                LOGGER.exception(
                    "replenishment recovery deferred",
                    extra={"operation_id": str(operation_id)},
                )
                continue
            recovered.append(operation_id)
        return recovered

    async def expire_due(self) -> list[UUID]:
        self._require_aware(self._clock())
        return await self._expiry.expire_due()

    def _config(self, operation_id: UUID) -> RunnableConfig:
        return {"configurable": {"thread_id": str(operation_id)}}

    def _require_aware(self, value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
