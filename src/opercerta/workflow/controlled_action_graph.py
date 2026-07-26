from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from opercerta.agent.tool_executor import ReadToolGateway
from opercerta.agent.trace_recorder import TraceRecorder
from opercerta.application.scenario_registry import ScenarioRegistry
from opercerta.domain.agent import AgentAnalysis
from opercerta.domain.contracts import ObjectType, OperationRequest
from opercerta.domain.model_gateway import AgentModelGateway, ModelGateway
from opercerta.domain.replenishment import OperationError
from opercerta.domain.work_orders import WorkOrderCommand, WorkOrderRecord, WorkOrderWriteResult
from opercerta.infrastructure.cache import EvidenceCache, NullEvidenceCache, evidence_cache_key
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.observation_gateway import CachedReadToolGateway
from opercerta.infrastructure.traced_tool_gateway import TracedControlledEvidenceGateway
from opercerta.observability.tracing import NOOP_TRACING, Tracing
from opercerta.workflow.agent_controlled_action_graph import (
    AgentInvestigationGraph,
    build_agent_investigation_graph,
    build_agent_investigation_initial_state,
)
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
from opercerta.workflow.task_recovery_graph import (
    TaskGateway,
    TaskRecoveryGraph,
    build_task_recovery_graph,
)

ControlledActionState = ReplenishmentState


class ControlledEvidenceGateway(
    EvidenceGateway,
    MaintenanceGateway,
    TaskGateway,
    ReadToolGateway,
    Protocol,
):
    pass


class CachedControlledEvidenceGateway:
    def __init__(
        self,
        delegate: ControlledEvidenceGateway,
        cache: EvidenceCache,
        ttl_seconds: int,
        tracing: Tracing,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._tracing = tracing

    @staticmethod
    def _key(kind: str, object_id: str) -> str:
        return evidence_cache_key(kind, object_id)

    async def _get(self, key: str, loader: Callable[[], Awaitable[object]]) -> object:
        with self._tracing.span("redis.evidence", {"component": "redis", "operation": "get"}):
            cached = await self._cache.get(key)
        if cached is not None:
            return cached
        loaded = await loader()
        if isinstance(loaded, BaseModel):
            payload = loaded.model_dump(mode="json")
        elif isinstance(loaded, dict):
            payload = loaded
        else:
            return loaded
        with self._tracing.span(
            "redis.evidence",
            {"component": "redis", "operation": "set"},
        ):
            await self._cache.set(key, payload, self._ttl_seconds)
        return loaded

    async def get_inventory(self, sku: str) -> object:
        return await self._get(
            self._key("inventory", sku),
            lambda: self._delegate.get_inventory(sku),
        )

    async def get_policy(self, sku: str) -> object:
        return await self._get(
            self._key("policy.inventory", sku),
            lambda: self._delegate.get_policy(sku),
        )

    async def get_equipment(self, equipment_id: str) -> object:
        return await self._get(
            self._key("equipment", equipment_id),
            lambda: self._delegate.get_equipment(equipment_id),
        )

    async def get_maintenance_policy(self, equipment_id: str) -> object:
        return await self._get(
            self._key("policy.equipment", equipment_id),
            lambda: self._delegate.get_maintenance_policy(equipment_id),
        )

    async def get_task(self, task_id: str) -> object:
        return await self._get(
            self._key("task", task_id),
            lambda: self._delegate.get_task(task_id),
        )

    async def get_task_recovery_policy(self, task_id: str) -> object:
        return await self._get(
            self._key("policy.task", task_id),
            lambda: self._delegate.get_task_recovery_policy(task_id),
        )

    async def create_work_order(
        self, command: WorkOrderCommand, *, plan_hash: str
    ) -> WorkOrderWriteResult:
        return await self._delegate.create_work_order(command, plan_hash=plan_hash)

    async def get_work_order(self, work_order_id: UUID) -> WorkOrderRecord:
        return await self._delegate.get_work_order(work_order_id)


class ControlledActionGraph:
    def __init__(
        self,
        inventory: ReplenishmentGraph,
        equipment: EquipmentMaintenanceGraph,
        task: TaskRecoveryGraph,
        operations: OperationRepository,
        tracing: Tracing,
        agent: AgentInvestigationGraph | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self._inventory = inventory
        self._equipment = equipment
        self._task = task
        self._operations = operations
        self._tracing = tracing
        self._agent = agent
        self._trace_recorder = trace_recorder

    async def ainvoke(
        self,
        value: ControlledActionState | Command[Any] | None,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        if self._agent is not None and isinstance(value, dict) and "request" in value:
            request = OperationRequest.model_validate(value["request"])
            agent_config: RunnableConfig = {
                "configurable": {
                    **config.get("configurable", {}),
                    "checkpoint_ns": "agent",
                }
            }
            agent_result = await self._agent.ainvoke(
                build_agent_investigation_initial_state(request),
                config=agent_config,
            )
            operation_id = UUID(str(value["operation_id"]))
            if self._trace_recorder is not None:
                await self._trace_recorder.capture_investigation(
                    operation_id,
                    request,
                    agent_result,
                )
            if agent_result["status"] != "completed":
                error = OperationError(
                    code=agent_result["error_code"] or "agent_investigation_failed",
                    message="Agent investigation failed before deterministic execution.",
                )
                await self._operations.mark_failed(operation_id, error)
                return {**value, "error": error.model_dump(mode="json")}
            analysis = AgentAnalysis.model_validate(agent_result["analysis"])
            value = cast(
                ControlledActionState,
                {**value, "agent_analysis": analysis.model_dump(mode="json")},
            )
        graph = await self._graph(value, config)
        scenario = (
            "inventory"
            if graph is self._inventory
            else "equipment"
            if graph is self._equipment
            else "task"
        )
        thread_id = str(config.get("configurable", {}).get("thread_id", ""))
        with self._tracing.span(
            "graph.invoke",
            {
                "component": "graph",
                "scenario": scenario,
                "thread_id": thread_id,
                "operation_id": thread_id,
            },
        ):
            result = cast(dict[str, Any], await graph.ainvoke(value, config=config))
        if self._trace_recorder is not None and thread_id:
            operation_id = UUID(thread_id)
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
                    cast(dict[str, object], result["verification"])
                    if isinstance(result.get("verification"), dict)
                    else None
                ),
                verification_route=(
                    str(result["verification_route"])
                    if result.get("verification_route") is not None
                    else None
                ),
                work_order=(
                    detail.work_order.model_dump(mode="json")
                    if detail.work_order is not None
                    else None
                ),
                result=(
                    detail.result.model_dump(mode="json") if detail.result is not None else None
                ),
                error_code=detail.error.code if detail.error is not None else None,
            )
        return result

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
    ) -> ReplenishmentGraph | EquipmentMaintenanceGraph | TaskRecoveryGraph:
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
        if request.object_type is ObjectType.TASK:
            return self._task
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
    cache: EvidenceCache | None = None,
    cache_ttl_seconds: int = 60,
    tracing: Tracing = NOOP_TRACING,
    parallel_evidence_reads: bool = True,
    approval_ttl_seconds: int = 300,
    agent_model_gateway: AgentModelGateway | None = None,
    knowledge_enabled: bool = False,
    knowledge_required: bool = False,
    trace_recorder: TraceRecorder | None = None,
) -> ControlledActionGraph:
    traced_gateway = TracedControlledEvidenceGateway(gateway, tracing)
    initial_gateway = CachedControlledEvidenceGateway(
        traced_gateway,
        cache or NullEvidenceCache(),
        cache_ttl_seconds,
        tracing,
    )
    inventory = build_replenishment_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        traced_gateway,
        model_gateway,
        clock,
        initial_gateway=initial_gateway,
        tracing=tracing,
        parallel_evidence_reads=parallel_evidence_reads,
        approval_ttl_seconds=approval_ttl_seconds,
        agent_model_gateway=agent_model_gateway,
    )
    equipment = build_equipment_maintenance_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        traced_gateway,
        model_gateway,
        clock,
        initial_gateway=initial_gateway,
        tracing=tracing,
        parallel_evidence_reads=parallel_evidence_reads,
        approval_ttl_seconds=approval_ttl_seconds,
        agent_model_gateway=agent_model_gateway,
    )
    task = build_task_recovery_graph(
        checkpointer,  # type: ignore[arg-type]
        operations,
        evidence_repository,
        traced_gateway,
        model_gateway,
        clock,
        initial_gateway=initial_gateway,
        tracing=tracing,
        parallel_evidence_reads=parallel_evidence_reads,
        approval_ttl_seconds=approval_ttl_seconds,
        agent_model_gateway=agent_model_gateway,
    )
    agent_gateway = CachedReadToolGateway(
        traced_gateway,
        cache or NullEvidenceCache(),
        ttl_seconds=cache_ttl_seconds,
        tracing=tracing,
    )
    agent = (
        build_agent_investigation_graph(
            agent_model_gateway,
            agent_gateway,
            checkpointer=checkpointer,
            registry=registry,
            clock=clock,
            knowledge_enabled=knowledge_enabled,
            knowledge_required=knowledge_required,
        )
        if agent_model_gateway is not None
        else None
    )
    return ControlledActionGraph(
        inventory,
        equipment,
        task,
        operations,
        tracing,
        agent,
        trace_recorder,
    )
