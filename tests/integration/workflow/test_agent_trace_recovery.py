from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.agent.trace_recorder import TraceRecorder
from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.agent import AgentAnalysis, GoalEncoding, ReadToolName, ToolObservation
from opercerta.domain.agent_trace import AgentRunStatus
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.knowledge import KnowledgeSearchEvidence, KnowledgeSearchResult
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.agent_trace_repository import AgentTraceRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.agent_controlled_action_graph import build_agent_investigation_initial_state
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from opercerta.workflow.controlled_action_recovery import ControlledActionRecoveryCoordinator
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
GRAPH_NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
mcp_server = _mcp_server_fixture


@pytest.mark.asyncio
async def test_investigation_trace_replay_does_not_duplicate_business_events(
    engine: AsyncEngine,
) -> None:
    request = OperationRequest(
        message="查询 SKU-LOW-001 当前库存状态",
        requested_action=ActionType.QUERY,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await OperationRepository(engine).create(request)
    repository = AgentTraceRepository(engine)
    recorder = TraceRecorder(repository, clock=lambda: NOW, model_mode="mock")
    state = build_agent_investigation_initial_state(request)
    state.update(
        {
            "goal": GoalEncoding(
                goal=ActionType.QUERY,
                scenario=ScenarioKind.INVENTORY,
                object_id="SKU-LOW-001",
                required_evidence=("subject", "policy"),
                success_condition="report_inventory_status",
            ).model_dump(mode="json"),
            "plan": None,
            "analysis": AgentAnalysis(
                summary="库存事实已核验。",
                recommendation="返回只读状态并保持零工单。",
            ).model_dump(mode="json"),
            "status": "completed",
            "error_code": None,
        }
    )

    try:
        first = await recorder.capture_investigation(operation_id, request, state)
        replay = await recorder.capture_investigation(operation_id, request, state)
        snapshot = await repository.load_snapshot(operation_id)

        assert first.id == replay.id
        assert snapshot.run.status is AgentRunStatus.COMPLETED
        assert [event.semantic_key for event in snapshot.events] == [
            "perception:intent",
            "model:goal",
            "model:analysis",
            "feedback:investigation_terminal",
        ]
        assert [event.sequence for event in snapshot.events] == [1, 2, 3, 4]
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_rag_observation_persists_only_safe_citation_refs(engine: AsyncEngine) -> None:
    request = OperationRequest(
        message="查询 SKU-LOW-001 当前库存状态",
        requested_action=ActionType.QUERY,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await OperationRepository(engine).create(request)
    repository = AgentTraceRepository(engine)
    recorder = TraceRecorder(repository, clock=lambda: NOW, model_mode="mock")
    state = build_agent_investigation_initial_state(request)
    document_id = uuid4()
    chunk_id = uuid4()
    evidence = KnowledgeSearchEvidence(
        evidence_id=uuid4(),
        scenario=ScenarioKind.INVENTORY,
        query="库存补货审批步骤",
        embedding_model="BAAI/bge-small-zh-v1.5",
        results=(
            KnowledgeSearchResult(
                document_id=document_id,
                chunk_id=chunk_id,
                scenario=ScenarioKind.INVENTORY,
                slug="inventory-replenishment-sop",
                version="1.0.0",
                title="库存补货审批 SOP",
                chunk_index=0,
                content="批准前核对库存事实与规则版本。",
                metadata={"section": "approval"},
                score=0.75,
            ),
        ),
    )
    observation = ToolObservation(
        tool_call_id="call-r0-s2",
        tool_name=ReadToolName.KNOWLEDGE_SEARCH,
        arguments_hash="a" * 64,
        status="ok",
        evidence_ref=evidence.evidence_id,
        safe_summary="已取得当前场景 SOP 引用。",
        structured_payload=evidence.model_dump(mode="json"),
    )
    state.update(
        {
            "goal": GoalEncoding(
                goal=ActionType.QUERY,
                scenario=ScenarioKind.INVENTORY,
                object_id="SKU-LOW-001",
                required_evidence=("subject", "policy", "knowledge"),
                success_condition="report_inventory_status",
            ).model_dump(mode="json"),
            "observations": [observation.model_dump(mode="json")],
            "analysis": AgentAnalysis(
                summary="库存事实与 SOP 已核验。",
                recommendation="返回只读状态。",
            ).model_dump(mode="json"),
            "status": "completed",
        }
    )

    try:
        await recorder.capture_investigation(operation_id, request, state)
        snapshot = await repository.load_snapshot(operation_id)
        rag = next(event for event in snapshot.events if event.event_type.value == "rag")

        assert rag.tool_ref == "knowledge.search_sop"
        assert len(rag.citations) == 1
        assert rag.citations[0].document_id == document_id
        assert rag.citations[0].chunk_id == chunk_id
        assert rag.citations[0].version == "1.0.0"
        assert rag.citations[0].score == pytest.approx(0.75)
        assert "content" not in rag.safe_output
        assert "structured_payload" not in rag.safe_output
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_real_agent_graph_rebuild_replays_trace_without_duplicate_events(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    request = OperationRequest(
        message="为 SKU-LOW-001 生成补货工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operations_repository = OperationRepository(engine)
    operation_id = await operations_repository.create(request)
    trace_repository = AgentTraceRepository(engine)
    recorder = TraceRecorder(trace_repository, clock=lambda: NOW, model_mode="mock")
    registry = build_default_scenario_registry()
    config = {"configurable": {"thread_id": str(operation_id)}}

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_controlled_action_graph(
                saver_a,
                operations_repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: GRAPH_NOW,
                registry,
                agent_model_gateway=MockAgentModelGateway(),
                trace_recorder=recorder,
            )
            await graph_a.ainvoke(
                build_controlled_action_initial_state(operation_id, request, registry),
                config=config,
            )
            before = await trace_repository.load_snapshot(operation_id)
            await saver_a.adelete_thread(str(operation_id))

        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_controlled_action_graph(
                saver_b,
                operations_repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: GRAPH_NOW,
                registry,
                agent_model_gateway=MockAgentModelGateway(),
                trace_recorder=recorder,
            )
            await ControlledActionRecoveryCoordinator(
                graph_b,
                operations_repository,
            ).recover(operation_id)
            after = await trace_repository.load_snapshot(operation_id)
            await saver_b.adelete_thread(str(operation_id))

        assert before.run.status is AgentRunStatus.AWAITING_HUMAN
        assert after.run.status is AgentRunStatus.AWAITING_HUMAN
        assert [event.id for event in after.events] == [event.id for event in before.events]
        assert [event.sequence for event in after.events] == list(range(1, len(after.events) + 1))
        assert {
            "perception",
            "model",
            "tool",
            "rule",
            "human",
            "feedback",
        } <= {event.event_type.value for event in after.events}
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
