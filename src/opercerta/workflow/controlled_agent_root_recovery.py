from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from opercerta.domain.contracts import OperationRequest
from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.recovery import (
    TERMINAL_STATUSES,
    CheckpointPhase,
    OperationStatus,
    RecoveryAction,
    RecoveryFacts,
    choose_recovery_action,
)
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.workflow.inventory_agent_root_graph import (
    ControlledAgentRootGraph,
    build_controlled_agent_root_initial_state,
)


class ControlledAgentRootRecoveryCoordinator:
    """Recover the one root graph without selecting or chaining scenario graphs."""

    def __init__(
        self,
        graph: ControlledAgentRootGraph,
        operations: ReplenishmentOperationRepository,
    ) -> None:
        self._graph = graph
        self._operations = operations

    async def recover(self, operation_id: UUID) -> RecoveryAction:
        detail = await self._operations.load_detail(operation_id)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(operation_id)},
        }
        snapshot = await self._graph.aget_state(config)
        phase = self._phase(snapshot)
        status = OperationStatus(str(detail.status.value))
        self._validate(operation_id, detail.thread_id, status, snapshot, phase)
        action = choose_recovery_action(
            RecoveryFacts(
                status=status,
                checkpoint=phase,
                has_approval=getattr(detail, "approval", None) is not None,
                has_work_order=getattr(detail, "work_order", None) is not None,
            )
        )

        if action in {RecoveryAction.KEEP_WAITING, RecoveryAction.NO_OP}:
            return action
        if action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS:
            if status is not OperationStatus.RECEIVED:
                raise RecoveryStateConflict(
                    operation_id,
                    f"missing_root_checkpoint_for_{status.value}",
                )
            request = OperationRequest.model_validate(detail.snapshot.request)
            await self._graph.ainvoke(
                build_controlled_agent_root_initial_state(operation_id, request),
                config=config,
            )
            return action
        if action is RecoveryAction.RESUME_DECISION:
            approval = getattr(detail, "approval", None)
            if approval is None:
                raise RecoveryStateConflict(operation_id, "approval_locator_missing")
            await self._graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            return action

        await self._graph.ainvoke(None, config=config)
        return action

    @staticmethod
    def _phase(snapshot: Any) -> CheckpointPhase:
        if snapshot.created_at is None:
            return CheckpointPhase.MISSING
        if snapshot.interrupts or any(task.interrupts for task in snapshot.tasks):
            return CheckpointPhase.INTERRUPTED
        return CheckpointPhase.RUNNABLE

    @staticmethod
    def _validate(
        operation_id: UUID,
        thread_id: str,
        status: OperationStatus,
        snapshot: Any,
        phase: CheckpointPhase,
    ) -> None:
        if phase is CheckpointPhase.MISSING:
            return
        if not isinstance(snapshot.values, Mapping):
            raise RecoveryStateConflict(operation_id, "checkpoint_values_not_mapping")
        if snapshot.values.get("operation_id") != thread_id:
            raise RecoveryStateConflict(operation_id, "checkpoint_operation_id_mismatch")
        if status in TERMINAL_STATUSES and (snapshot.next or phase is CheckpointPhase.INTERRUPTED):
            raise RecoveryStateConflict(
                operation_id,
                "terminal_state_has_pending_checkpoint",
            )
