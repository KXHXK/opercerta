from typing import cast

from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.workflow.controlled_action_graph import ControlledActionGraph
from opercerta.workflow.replenishment_graph import ReplenishmentGraph
from opercerta.workflow.replenishment_recovery import (
    ReplenishmentRecoveryCoordinator,
)


class ControlledActionRecoveryCoordinator(ReplenishmentRecoveryCoordinator):
    """Compatibility boundary for scenario-neutral recovery."""

    def __init__(
        self,
        graph: ControlledActionGraph,
        operations: OperationRepository,
    ) -> None:
        super().__init__(cast(ReplenishmentGraph, graph), operations)
