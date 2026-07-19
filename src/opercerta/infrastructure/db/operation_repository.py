from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)


class OperationRepository(ReplenishmentOperationRepository):
    """Compatibility boundary while scenario-neutral persistence is extracted."""
