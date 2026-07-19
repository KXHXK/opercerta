from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from opercerta.application.scenario_registry import ScenarioRegistry
from opercerta.domain.contracts import ObjectType, OperationRequest
from opercerta.domain.model_gateway import ModelGateway
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.workflow.equipment_maintenance_graph import (
    EquipmentMaintenanceGraph,
    MaintenanceGateway,
    build_equipment_maintenance_graph,
)
from opercerta.workflow.replenishment_graph import (
    EvidenceGateway,
    ReplenishmentGraph,
    ReplenishmentState,
    build_replenishment_graph,
    build_replenishment_initial_state,
)

ControlledActionState = ReplenishmentState


class ControlledEvidenceGateway(EvidenceGateway, MaintenanceGateway, Protocol):
    pass


class ControlledActionGraph:
    def __init__(
        self,
        inventory: ReplenishmentGraph,
        equipment: EquipmentMaintenanceGraph,
        operations: OperationRepository,
    ) -> None:
        self._inventory = inventory
        self._equipment = equipment
        self._operations = operations

    async def ainvoke(
        self,
        value: ControlledActionState | Command[Any] | None,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        graph = await self._graph(value, config)
        return cast(dict[str, Any], await graph.ainvoke(value, config=config))

    async def aget_state(self, config: RunnableConfig) -> Any:
        graph = await self._graph(None, config)
        return await graph.aget_state(config)

    async def aupdate_state(
        self,
        config: RunnableConfig,
        values: ControlledActionState,
        *,
        as_node: str,
    ) -> Any:
        graph = await self._graph(values, config)
        return await graph.aupdate_state(config, values, as_node=as_node)

    async def _graph(
        self,
        value: ControlledActionState | Command[Any] | None,
        config: RunnableConfig,
    ) -> ReplenishmentGraph | EquipmentMaintenanceGraph:
        if isinstance(value, dict) and "request" in value:
            request = OperationRequest.model_validate(value["request"])
        else:
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id is None:
                raise ValueError("thread_id is required")
            detail = await self._operations.load_detail(UUID(str(thread_id)))
            request = OperationRequest.model_validate(detail.snapshot.request)
        if request.object_type is ObjectType.INVENTORY:
            return self._inventory
        if request.object_type is ObjectType.EQUIPMENT:
            return self._equipment
        raise ValueError("unsupported controlled action object type")


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
    gateway: ControlledEvidenceGateway,
    model_gateway: ModelGateway,
    clock: Callable[[], datetime],
    registry: ScenarioRegistry,
    *,
    approval_ttl_seconds: int = 300,
) -> ControlledActionGraph:
    inventory = build_replenishment_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        gateway,
        model_gateway,
        clock,
        approval_ttl_seconds=approval_ttl_seconds,
    )
    equipment = build_equipment_maintenance_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        gateway,
        model_gateway,
        clock,
        approval_ttl_seconds=approval_ttl_seconds,
    )
    del registry
    return ControlledActionGraph(inventory, equipment, operations)
