import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from opercerta.agent.trace_recorder import TraceRecorder
from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.domain.approvals import BoundApprovalCommand
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.errors import DependencyUnavailable, RecoveryStateConflict
from opercerta.domain.replenishment import OperationError
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.workflow.inventory_agent_root_graph import (
    ControlledAgentRootGraph,
    build_controlled_agent_root_initial_state,
)

LOGGER = logging.getLogger(__name__)


class RootRecovery(Protocol):
    async def recover(self, operation_id: UUID) -> object: ...


class ControlledAgentRootRunner:
    """Application adapter for the one LangGraph that owns an operation lifecycle."""

    def __init__(
        self,
        graph: ControlledAgentRootGraph,
        approvals: ApprovalRepository,
        operations: ReplenishmentOperationRepository,
        recovery: RootRecovery,
        expiry: ApprovalExpiryService,
        clock: Callable[[], datetime],
        *,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self._graph = graph
        self._approvals = approvals
        self._operations = operations
        self._recovery = recovery
        self._expiry = expiry
        self._clock = clock
        self._trace_recorder = trace_recorder

    async def start(self, request: OperationRequest) -> UUID:
        operation_id = await self._operations.create(request)
        try:
            result = await self._graph.ainvoke(
                build_controlled_agent_root_initial_state(operation_id, request),
                config=self._config(operation_id),
            )
            await self._capture(operation_id, request, result)
        except Exception:
            try:
                await self._operations.mark_failed(
                    operation_id,
                    OperationError(
                        code=DependencyUnavailable.code,
                        message=(
                            "Operation dependency failed before the root graph "
                            "reached a safe state."
                        ),
                    ),
                )
            except Exception:
                LOGGER.error(
                    "operation failure transition unavailable",
                    extra={"operation_id": str(operation_id)},
                )
            raise
        return operation_id

    async def submit_approval(
        self,
        command: BoundApprovalCommand,
        now: datetime | None = None,
    ) -> UUID:
        approval_time = now if now is not None else self._clock()
        self._require_aware(approval_time)
        approval = await self._approvals.submit_bound_once(command, approval_time)
        result = await self._graph.ainvoke(
            Command(
                resume={
                    "approval_id": str(approval.id),
                    "decision": approval.decision.value,
                }
            ),
            config=self._config(command.operation_id),
        )
        detail = await self._operations.load_detail(command.operation_id)
        await self._capture(
            command.operation_id,
            OperationRequest.model_validate(detail.snapshot.request),
            result,
        )
        return command.operation_id

    async def recover_all(self) -> list[UUID]:
        await self.expire_due()
        recovered: list[UUID] = []
        for operation_id in await self._operations.list_recoverable_ids():
            try:
                await self._recovery.recover(operation_id)
                detail = await self._operations.load_detail(operation_id)
                snapshot = await self._graph.aget_state(self._config(operation_id))
                values = snapshot.values
                if isinstance(values, dict):
                    await self._capture(
                        operation_id,
                        OperationRequest.model_validate(detail.snapshot.request),
                        cast(dict[str, Any], values),
                    )
            except RecoveryStateConflict:
                await self._operations.mark_failed(
                    operation_id,
                    OperationError(
                        code=RecoveryStateConflict.code,
                        message=("Business facts conflict with the saved root graph checkpoint."),
                    ),
                )
            except Exception:
                LOGGER.exception(
                    "controlled agent root recovery deferred",
                    extra={"operation_id": str(operation_id)},
                )
                continue
            recovered.append(operation_id)
        return recovered

    async def expire_due(self) -> list[UUID]:
        self._require_aware(self._clock())
        return await self._expiry.expire_due()

    @staticmethod
    def _config(operation_id: UUID) -> RunnableConfig:
        return {"configurable": {"thread_id": str(operation_id)}}

    async def _capture(
        self,
        operation_id: UUID,
        request: OperationRequest,
        state: dict[str, Any],
    ) -> None:
        if self._trace_recorder is None:
            return
        await self._trace_recorder.capture_investigation(operation_id, request, state)
        detail = await self._operations.load_detail(operation_id)
        approval_payload = (
            {
                "id": str(detail.approval.id),
                "approver_id": detail.approval.approver_id,
                "decision": detail.approval.decision.value,
            }
            if detail.approval is not None
            else None
        )
        await self._trace_recorder.capture_operation_outcome(
            operation_id,
            status=detail.status.value,
            approval_cycle=detail.approval_cycle,
            approval=approval_payload,
            verification=(
                cast(dict[str, object], state["verification"])
                if isinstance(state.get("verification"), dict)
                else None
            ),
            verification_route=(
                str(state["verification_route"])
                if state.get("verification_route") is not None
                else None
            ),
            work_order=(
                detail.work_order.model_dump(mode="json") if detail.work_order is not None else None
            ),
            result=(detail.result.model_dump(mode="json") if detail.result is not None else None),
            error_code=detail.error.code if detail.error is not None else None,
        )

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
