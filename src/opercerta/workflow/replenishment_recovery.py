from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot
from pydantic import JsonValue

from opercerta.domain.contracts import OperationRequest
from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.operation_state import ApprovalResume
from opercerta.domain.recovery import (
    TERMINAL_STATUSES,
    CheckpointPhase,
    OperationStatus,
    RecoveryAction,
    RecoveryFacts,
    choose_recovery_action,
)
from opercerta.domain.replenishment import (
    ApprovalBinding,
    EvidenceBundle,
    ReplenishmentPlan,
    build_approval_binding,
)
from opercerta.infrastructure.db.replenishment_operation_repository import (
    OperationDetail,
    ReplenishmentOperationRepository,
)
from opercerta.workflow.replenishment_graph import (
    ReplenishmentGraph,
    ReplenishmentState,
    build_replenishment_initial_state,
)


class ReplenishmentRecoveryCoordinator:
    def __init__(
        self,
        graph: ReplenishmentGraph,
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
        phase = self._checkpoint_phase(snapshot)
        self._validate_checkpoint(operation_id, detail, snapshot, phase)
        action = choose_recovery_action(
            RecoveryFacts(
                status=detail.status,
                checkpoint=phase,
                has_approval=detail.approval is not None,
                has_work_order=detail.work_order is not None,
            )
        )

        if action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS:
            await self._rebuild_from_business_facts(detail, config)
        elif action in {RecoveryAction.KEEP_WAITING, RecoveryAction.NO_OP}:
            return action
        elif action is RecoveryAction.RESUME_DECISION:
            await self._resume_persisted_decision(detail, config)
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
        detail: OperationDetail,
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
        if values.get("operation_id") != detail.thread_id:
            raise RecoveryStateConflict(
                operation_id,
                "checkpoint_operation_id_mismatch",
            )
        if detail.status in TERMINAL_STATUSES and (
            snapshot.next or phase is CheckpointPhase.INTERRUPTED
        ):
            raise RecoveryStateConflict(
                operation_id,
                "terminal_state_has_pending_checkpoint",
            )

    async def _rebuild_from_business_facts(
        self,
        detail: OperationDetail,
        config: RunnableConfig,
    ) -> None:
        if detail.status is OperationStatus.RECEIVED:
            await self._graph.ainvoke(
                build_replenishment_initial_state(
                    detail.operation_id,
                    self._request(detail),
                ),
                config=config,
            )
            return

        state = self._state_from_detail(detail)
        completed_node = self._completed_node_for(detail)
        await self._graph.aupdate_state(
            config,
            state,
            as_node=completed_node,
        )
        if detail.status is OperationStatus.RESUMING:
            await self._graph.ainvoke(None, config=config)
            await self._resume_persisted_decision(detail, config)
            return
        await self._graph.ainvoke(None, config=config)

    def _request(self, detail: OperationDetail) -> OperationRequest:
        return OperationRequest.model_validate(detail.snapshot.request)

    def _state_from_detail(self, detail: OperationDetail) -> ReplenishmentState:
        risk = detail.snapshot.risk
        approval_value: dict[str, JsonValue] | None = None
        if detail.approval is not None:
            approval_value = cast(
                dict[str, JsonValue],
                ApprovalResume(
                    approval_id=detail.approval.id,
                    decision=detail.approval.decision,
                ).model_dump(mode="json"),
            )

        binding_value = risk.get("approval_binding")
        if (
            binding_value is None
            and detail.status is OperationStatus.VALIDATING
            and detail.plan is not None
        ):
            if not isinstance(detail.plan, ReplenishmentPlan):
                raise RecoveryStateConflict(
                    detail.operation_id,
                    "non_replenishment_plan_in_replenishment_recovery",
                )
            bundle = EvidenceBundle.model_validate(risk.get("evidence"))
            binding_value = build_approval_binding(
                bundle,
                detail.plan,
            ).model_dump(mode="json")
        elif binding_value is not None:
            binding_value = ApprovalBinding.model_validate(binding_value).model_dump(mode="json")

        return ReplenishmentState(
            operation_id=detail.thread_id,
            request=detail.snapshot.request,
            evidence=cast(dict[str, JsonValue] | None, risk.get("evidence")),
            assessment=cast(dict[str, JsonValue] | None, risk.get("assessment")),
            plan=cast(
                dict[str, JsonValue] | None,
                detail.plan.model_dump(mode="json") if detail.plan is not None else None,
            ),
            approval_binding=binding_value,
            approval=approval_value,
            work_order=cast(
                dict[str, JsonValue] | None,
                detail.work_order.model_dump(mode="json")
                if detail.work_order is not None
                else None,
            ),
            result=cast(
                dict[str, JsonValue] | None,
                detail.result.model_dump(mode="json") if detail.result is not None else None,
            ),
            error=cast(
                dict[str, JsonValue] | None,
                detail.error.model_dump(mode="json") if detail.error is not None else None,
            ),
            replayed=False,
        )

    def _completed_node_for(self, detail: OperationDetail) -> str:
        if detail.status is OperationStatus.GATHERING_EVIDENCE:
            return "mark_gathering"
        if detail.status is OperationStatus.PLANNING:
            return "gather_evidence"
        if detail.status is OperationStatus.VALIDATING:
            return "record_low_plan" if detail.plan is not None else "record_normal_plan"
        if detail.status is OperationStatus.REPORTING:
            return "mark_reporting"
        if detail.status in {
            OperationStatus.AWAITING_APPROVAL,
            OperationStatus.RESUMING,
        }:
            return "prepare_approval"
        if detail.status is OperationStatus.EXECUTING:
            return "mark_executing"
        if detail.status is OperationStatus.VERIFYING:
            return "mark_verifying"
        raise RecoveryStateConflict(
            detail.operation_id,
            f"unsupported_missing_checkpoint_status_{detail.status.value}",
        )

    async def _resume_persisted_decision(
        self,
        detail: OperationDetail,
        config: RunnableConfig,
    ) -> None:
        if detail.approval is None:
            raise RecoveryStateConflict(
                detail.operation_id,
                "approval_locator_missing",
            )
        resume_command: Command[Any] = Command(
            resume={
                "approval_id": str(detail.approval.id),
                "decision": detail.approval.decision.value,
            }
        )
        await self._graph.ainvoke(resume_command, config=config)
