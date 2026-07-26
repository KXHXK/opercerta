from typing import cast

from pydantic import BaseModel, JsonValue, ValidationError

from opercerta.agent.tool_executor import ReadToolGateway, ReadToolResult
from opercerta.domain.agent import CacheStatus, ReadToolName
from opercerta.domain.errors import InvalidAgentToolArguments
from opercerta.domain.knowledge import KnowledgeSearchEvidence
from opercerta.domain.maintenance import EquipmentEvidence, MaintenancePolicyEvidence
from opercerta.domain.replenishment import InventoryEvidence, PolicyEvidence
from opercerta.domain.task_recovery import TaskEvidence, TaskRecoveryPolicyEvidence
from opercerta.domain.work_orders import canonical_payload_json
from opercerta.infrastructure.cache import EvidenceCache, evidence_cache_key
from opercerta.observability.tracing import Tracing


class CachedReadToolGateway:
    """Cache-aside adapter for every model-visible read tool."""

    def __init__(
        self,
        delegate: ReadToolGateway,
        cache: EvidenceCache,
        *,
        ttl_seconds: int,
        tracing: Tracing,
        bypass_cache: bool = False,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("cache ttl must be positive")
        self._delegate = delegate
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._tracing = tracing
        self._bypass_cache = bypass_cache

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> ReadToolResult:
        if self._bypass_cache:
            return ReadToolResult(
                evidence=await self._load(name, arguments),
                cache_status=CacheStatus.BYPASS,
            )

        key = self._key(name, arguments)
        with self._tracing.span(
            "redis.evidence",
            {"component": "redis", "operation": "lookup"},
        ):
            lookup = await self._cache.lookup(key)
        if lookup.value is not None:
            cached = self._restore(name, arguments, lookup.value)
            if cached is not None:
                return ReadToolResult(evidence=cached, cache_status=CacheStatus.HIT)

        evidence = await self._load(name, arguments)
        with self._tracing.span(
            "redis.evidence",
            {"component": "redis", "operation": "set"},
        ):
            await self._cache.set(
                key,
                cast(dict[str, object], evidence.model_dump(mode="json")),
                self._ttl_seconds,
            )
        return ReadToolResult(evidence=evidence, cache_status=lookup.status)

    async def _load(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> BaseModel:
        result = await self._delegate.read_agent_tool(name, arguments)
        if isinstance(result, ReadToolResult):
            return result.evidence
        return result

    @staticmethod
    def _key(name: ReadToolName, arguments: dict[str, JsonValue]) -> str:
        kind, object_id = CachedReadToolGateway._identity(name, arguments)
        return evidence_cache_key(kind, object_id)

    @staticmethod
    def _identity(
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> tuple[str, str]:
        if name is ReadToolName.INVENTORY_SNAPSHOT:
            return "inventory", CachedReadToolGateway._string(arguments, "sku")
        if name is ReadToolName.EQUIPMENT_STATUS:
            return "equipment", CachedReadToolGateway._string(arguments, "equipment_id")
        if name is ReadToolName.TASK_STATUS:
            return "task", CachedReadToolGateway._string(arguments, "task_id")
        if name is ReadToolName.POLICY_CONSTRAINTS:
            action = arguments.get("action")
            mapping = {
                "replenish_inventory": ("policy.inventory", "sku"),
                "repair_equipment": ("policy.equipment", "equipment_id"),
                "recover_task": ("policy.task", "task_id"),
            }
            selected = mapping.get(action) if isinstance(action, str) else None
            if selected is None:
                raise InvalidAgentToolArguments
            kind, key = selected
            return kind, CachedReadToolGateway._string(arguments, key)
        if name is ReadToolName.KNOWLEDGE_SEARCH:
            return "knowledge", canonical_payload_json(arguments)
        raise InvalidAgentToolArguments

    @staticmethod
    def _string(arguments: dict[str, JsonValue], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise InvalidAgentToolArguments
        return value

    @staticmethod
    def _restore(
        name: ReadToolName,
        arguments: dict[str, JsonValue],
        payload: dict[str, object],
    ) -> BaseModel | None:
        model: type[BaseModel]
        if name is ReadToolName.INVENTORY_SNAPSHOT:
            model = InventoryEvidence
        elif name is ReadToolName.EQUIPMENT_STATUS:
            model = EquipmentEvidence
        elif name is ReadToolName.TASK_STATUS:
            model = TaskEvidence
        elif name is ReadToolName.KNOWLEDGE_SEARCH:
            model = KnowledgeSearchEvidence
        elif name is ReadToolName.POLICY_CONSTRAINTS:
            action = arguments.get("action")
            policy_models: dict[str, type[BaseModel]] = {
                "replenish_inventory": PolicyEvidence,
                "repair_equipment": MaintenancePolicyEvidence,
                "recover_task": TaskRecoveryPolicyEvidence,
            }
            model = policy_models.get(str(action), BaseModel)
            if model is BaseModel:
                raise InvalidAgentToolArguments
        else:
            raise InvalidAgentToolArguments
        try:
            return model.model_validate(payload)
        except ValidationError:
            return None
