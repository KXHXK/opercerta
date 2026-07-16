from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot

from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.operation_state import RecoveryView
from opercerta.domain.recovery import (
    TERMINAL_STATUSES,
    CheckpointPhase,
    RecoveryAction,
    RecoveryFacts,
    choose_recovery_action,
)
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.workflow.reliability_graph import ReliabilityGraph, build_initial_state


class RecoveryCoordinator:
    def __init__(
        self,
        graph: ReliabilityGraph,
        operation_states: OperationStateRepository,
    ) -> None:
        self._graph = graph
        self._operation_states = operation_states

    async def recover(self, operation_id: UUID) -> RecoveryAction:
        view = await self._operation_states.load_recovery_view(operation_id)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(operation_id)},
        }
        snapshot = await self._graph.aget_state(config)
        phase = self._checkpoint_phase(snapshot)
        self._validate_checkpoint(operation_id, view, snapshot, phase)
        action = choose_recovery_action(
            RecoveryFacts(
                status=view.status,
                checkpoint=phase,
                has_approval=view.approval_id is not None,
                has_work_order=view.work_order_id is not None,
            )
        )

        if action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS:
            await self._graph.ainvoke(build_initial_state(view), config=config)
        elif action in {RecoveryAction.KEEP_WAITING, RecoveryAction.NO_OP}:
            return action
        elif action is RecoveryAction.RESUME_DECISION:
            if view.approval_id is None or view.decision is None:
                raise RecoveryStateConflict(operation_id, "approval_locator_missing")
            resume_command: Command[Any] = Command(
                resume={
                    "approval_id": str(view.approval_id),
                    "decision": view.decision.value,
                }
            )
            await self._graph.ainvoke(
                resume_command,
                config=config,
            )
        else:
            await self._graph.ainvoke(None, config=config)

        return action

    def _checkpoint_phase(self, snapshot: StateSnapshot) -> CheckpointPhase:
        if snapshot.created_at is None:
            return CheckpointPhase.MISSING
        if snapshot.interrupts or any(task.interrupts for task in snapshot.tasks):
            return CheckpointPhase.INTERRUPTED
        return CheckpointPhase.RUNNABLE

    def _validate_checkpoint(
        self,
        operation_id: UUID,
        view: RecoveryView,
        snapshot: StateSnapshot,
        phase: CheckpointPhase,
    ) -> None:
        if phase is CheckpointPhase.MISSING:
            return
        if not isinstance(snapshot.values, Mapping):
            raise RecoveryStateConflict(
                operation_id,
                "checkpoint_values_not_mapping",
            )
        values: Mapping[str, Any] = snapshot.values
        if values.get("operation_id") != view.thread_id:
            raise RecoveryStateConflict(
                operation_id,
                "checkpoint_operation_id_mismatch",
            )
        if view.status in TERMINAL_STATUSES and (
            snapshot.next or phase is CheckpointPhase.INTERRUPTED
        ):
            raise RecoveryStateConflict(
                operation_id,
                "terminal_state_has_pending_checkpoint",
            )
