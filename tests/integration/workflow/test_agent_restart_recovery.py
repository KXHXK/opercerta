from datetime import UTC, datetime

import pytest
from langgraph.types import Command
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.agent import VerificationContext, VerificationDecision
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
from opercerta.domain.recovery import RecoveryAction
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations, work_orders
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from opercerta.workflow.controlled_action_recovery import ControlledActionRecoveryCoordinator
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


class EscalateThenProceedModel(MockAgentModelGateway):
    def __init__(self) -> None:
        self.verify_calls = 0

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        del context
        self.verify_calls += 1
        decision = "escalate" if self.verify_calls == 1 else "proceed"
        return VerificationDecision(
            decision=decision,
            reason=f"synthetic {decision} after restart",
        )


@pytest.mark.asyncio
async def test_missing_checkpoint_rebuilds_needs_reapproval_without_writing(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="Create a replenishment work order with verified approval",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)
    model = EscalateThenProceedModel()
    config = {"configurable": {"thread_id": str(operation_id)}}

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
                agent_model_gateway=model,
            )
            await graph_a.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config=config,
            )
            first_waiting = await repository.load_detail(operation_id)
            assert first_waiting.approval_binding is not None
            first = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approve cycle one",
                    expected_binding=first_waiting.approval_binding,
                ),
                NOW,
            )
            await graph_a.ainvoke(
                Command(
                    resume={
                        "approval_id": str(first.id),
                        "decision": first.decision.value,
                    }
                ),
                config=config,
            )
            escalated = await repository.load_detail(operation_id)
            assert escalated.status.value == "needs_reapproval"
            assert escalated.approval_binding is not None
            await saver_a.adelete_thread(str(operation_id))

        restart_model = EscalateThenProceedModel()
        restart_model.verify_calls = 1
        async with open_checkpointer(checkpoint_database_url) as saver_b:
            graph_b = build_controlled_action_graph(
                saver_b,
                repository,
                EvidenceRepository(engine),
                McpToolGateway(mcp_server.url, timeout_seconds=2),
                MockModelGateway(),
                lambda: NOW,
                build_default_scenario_registry(),
                agent_model_gateway=restart_model,
            )
            action = await ControlledActionRecoveryCoordinator(
                graph_b,
                repository,
            ).recover(operation_id)

            rebuilt = await repository.load_detail(operation_id)
            assert action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS
            assert rebuilt.status.value == "needs_reapproval"
            assert rebuilt.approval is None
            assert restart_model.verify_calls == 1
            async with engine.connect() as connection:
                count_before_second_approval = int(
                    await connection.scalar(
                        select(func.count())
                        .select_from(work_orders)
                        .where(work_orders.c.operation_id == operation_id)
                    )
                    or 0
                )
            assert count_before_second_approval == 0

            assert rebuilt.approval_binding is not None
            second = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approve rebuilt cycle two",
                    expected_binding=rebuilt.approval_binding,
                ),
                NOW,
            )
            resumed = await ControlledActionRecoveryCoordinator(
                graph_b,
                repository,
            ).recover(operation_id)
            await saver_b.adelete_thread(str(operation_id))

        completed = await repository.load_detail(operation_id)
        assert second.approval_cycle == 2
        assert resumed is RecoveryAction.RESUME_DECISION
        assert completed.status.value == "completed"
        assert completed.work_order is not None
        assert restart_model.verify_calls == 2
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
