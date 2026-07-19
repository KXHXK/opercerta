from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from opercerta.application.scenario_registry import ScenarioRegistry
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.model_gateway import ModelGateway
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.workflow.replenishment_graph import (
    EvidenceGateway,
    ReplenishmentGraph,
    ReplenishmentState,
    build_replenishment_graph,
    build_replenishment_initial_state,
)

ControlledActionGraph = ReplenishmentGraph
ControlledActionState = ReplenishmentState


def build_controlled_action_initial_state(
    operation_id: UUID,
    request: OperationRequest,
    registry: ScenarioRegistry,
) -> ControlledActionState:
    registry.get(request)
    return build_replenishment_initial_state(operation_id, request)


def build_controlled_action_graph(
    checkpointer: object,
    operations: OperationRepository,
    evidence_repository: EvidenceRepository,
    gateway: EvidenceGateway,
    model_gateway: ModelGateway,
    clock: Callable[[], datetime],
    registry: ScenarioRegistry,
    *,
    approval_ttl_seconds: int = 300,
) -> ControlledActionGraph:
    del registry
    return build_replenishment_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        gateway,
        model_gateway,
        clock,
        approval_ttl_seconds=approval_ttl_seconds,
    )
