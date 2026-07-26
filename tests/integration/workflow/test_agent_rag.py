from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.agent import AgentAnalysis
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.knowledge import build_knowledge_ingest_command
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
from opercerta.domain.recovery import OperationStatus
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.knowledge_repository import KnowledgeRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import knowledge_documents, operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
VECTOR = (1.0,) + (0.0,) * 511


@pytest.mark.asyncio
async def test_agent_cites_only_the_active_sop_for_its_scenario(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    knowledge = KnowledgeRepository(engine)
    inventory = await knowledge.ingest(
        build_knowledge_ingest_command(
            scenario=ScenarioKind.INVENTORY,
            slug="inventory-controlled-action-sop",
            version="1.0.0",
            title="库存补货受控操作 SOP",
            active=True,
            chunks=(("审批前核对库存。审批后重新取证。", VECTOR, {"section": "approval"}),),
        )
    )
    equipment = await knowledge.ingest(
        build_knowledge_ingest_command(
            scenario=ScenarioKind.EQUIPMENT,
            slug="equipment-controlled-action-sop",
            version="1.0.0",
            title="设备维修受控操作 SOP",
            active=True,
            chunks=(("维修前核对设备告警。", VECTOR, {"section": "alert"}),),
        )
    )
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="查询库存并依据适用 SOP 给出结论",
        requested_action=ActionType.QUERY,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_action_graph(
                saver,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=MockAgentModelGateway(),
                knowledge_enabled=True,
            )
            result = await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        analysis = AgentAnalysis.model_validate(result["agent_analysis"])
        assert [citation.document_id for citation in analysis.citations] == [inventory.document.id]
        assert equipment.document.id not in {
            citation.document_id for citation in analysis.citations
        }
        assert analysis.citations[0].safe_snippet == "审批前核对库存。审批后重新取证。"
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
            await connection.execute(delete(knowledge_documents))


@pytest.mark.asyncio
async def test_required_sop_failure_stops_before_business_action(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(knowledge_documents))
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="库存不足时创建受控补货工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_action_graph(
                saver,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=MockAgentModelGateway(),
                knowledge_enabled=True,
                knowledge_required=True,
            )
            result = await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert result["error"]["code"] == "knowledge_insufficient"
        assert detail.status is OperationStatus.FAILED
        assert detail.work_order is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_optional_sop_failure_degrades_to_structured_facts(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(knowledge_documents))
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="查询当前库存状态",
        requested_action=ActionType.QUERY,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_action_graph(
                saver,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=MockAgentModelGateway(),
                knowledge_enabled=True,
            )
            result = await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        analysis = AgentAnalysis.model_validate(result["agent_analysis"])
        detail = await repository.load_detail(operation_id)
        assert analysis.citations == ()
        assert detail.status is OperationStatus.COMPLETED
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
