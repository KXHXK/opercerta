from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.agent import GoalContext, GoalEncoding
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
from opercerta.domain.recovery import OperationStatus, RecoveryAction
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from opercerta.workflow.controlled_action_recovery import (
    ControlledActionRecoveryCoordinator,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


class CountingMockAgentModelGateway(MockAgentModelGateway):
    def __init__(self) -> None:
        self.goal_calls = 0

    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        self.goal_calls += 1
        return await super().encode_goal(context)


@pytest.mark.asyncio
async def test_shared_entrypoint_preserves_inventory_no_action_result(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="查询正常库存并在需要时补货",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-NORMAL-001",
    )
    operation_id = await repository.create(request)
    agent_model = CountingMockAgentModelGateway()

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
                agent_model_gateway=agent_model,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status is OperationStatus.COMPLETED
        assert detail.result is not None
        assert detail.result.outcome == "replenishment_not_required"
        assert detail.approval is None
        assert detail.work_order is None
        assert agent_model.goal_calls == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_agent_analysis_flows_into_deterministic_approval_plan(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="库存不足时创建受控补货工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)
    agent_model = CountingMockAgentModelGateway()

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
                agent_model_gateway=agent_model,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status is OperationStatus.AWAITING_APPROVAL
        assert detail.plan is not None
        assert detail.plan.recommended_quantity == 18
        assert detail.plan.rationale == "由确定性 Policy Guard 计算动作参数。"
        assert detail.approval is None
        assert detail.work_order is None
        assert agent_model.goal_calls == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_restart_resumes_agent_backed_approval_without_rerunning_agent(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="库存不足时创建受控补货工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver_a:
            graph_a = build_controlled_action_graph(
                saver_a,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=CountingMockAgentModelGateway(),
            )
            await graph_a.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config={"configurable": {"thread_id": str(operation_id)}},
            )

        waiting = await repository.load_detail(operation_id)
        assert waiting.approval_binding is not None
        await ApprovalRepository(engine).submit_bound_once(
            BoundApprovalCommand(
                operation_id=operation_id,
                approver_id="inventory.manager",
                decision=ApprovalDecision.APPROVED,
                reason="批准已绑定的 Agent 补货计划",
                expected_binding=waiting.approval_binding,
            ),
            NOW,
        )

        restart_agent = CountingMockAgentModelGateway()
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_controlled_action_graph(
                saver_b,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=restart_agent,
            )
            action = await ControlledActionRecoveryCoordinator(
                graph_b,
                repository,
            ).recover(operation_id)
            await saver_b.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert action is RecoveryAction.RESUME_DECISION
        assert detail.status is OperationStatus.COMPLETED
        assert detail.work_order is not None
        assert restart_agent.goal_calls == 0
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
