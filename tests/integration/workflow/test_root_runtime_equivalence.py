from datetime import UTC, datetime
from uuid import UUID

import pytest
from langgraph.types import Command
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.application.scenario_runtime import binding_facts
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
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
from opercerta.workflow.inventory_agent_root_graph import (
    build_controlled_agent_root_graph,
    build_controlled_agent_root_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _config(operation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(operation_id)}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id"),
    [
        (ObjectType.INVENTORY, "SKU-LOW-001"),
        (ObjectType.EQUIPMENT, "EQ-PUMP-001"),
        (ObjectType.TASK, "TASK-BLOCKED-001"),
    ],
)
async def test_single_root_preserves_frozen_business_runtime_contract(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    object_type: ObjectType,
    object_id: str,
) -> None:
    repository = OperationRepository(engine)
    approvals = ApprovalRepository(engine)
    registry = build_default_scenario_registry()
    request = OperationRequest(
        message="调查异常, 并在确定性规则要求时创建受控工单",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=object_type,
        object_id=object_id,
    )
    legacy_id = await repository.create(request)
    root_id = await repository.create(request)
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)

    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            legacy = build_controlled_action_graph(
                saver,
                repository,
                EvidenceRepository(engine),
                gateway,
                MockModelGateway(),
                lambda: NOW,
                registry,
                agent_model_gateway=MockAgentModelGateway(),
            )
            root = build_controlled_agent_root_graph(
                MockAgentModelGateway(),
                gateway,
                clock=lambda: NOW,
                registry=registry,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )

            await legacy.ainvoke(
                build_controlled_action_initial_state(legacy_id, request, registry),
                config=_config(legacy_id),
            )
            await root.ainvoke(
                build_controlled_agent_root_initial_state(root_id, request),
                config=_config(root_id),
            )

            legacy_waiting = await repository.load_detail(legacy_id)
            root_waiting = await repository.load_detail(root_id)
            assert legacy_waiting.assessment == root_waiting.assessment
            assert legacy_waiting.plan is not None
            assert root_waiting.plan is not None
            assert legacy_waiting.plan.plan_hash == root_waiting.plan.plan_hash
            assert legacy_waiting.approval_binding is not None
            assert root_waiting.approval_binding is not None
            assert binding_facts(legacy_waiting.approval_binding) == binding_facts(
                root_waiting.approval_binding
            )

            legacy_approval = await approvals.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=legacy_id,
                    approver_id="equivalence.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准冻结业务契约对照执行",
                    expected_binding=legacy_waiting.approval_binding,
                ),
                NOW,
            )
            root_approval = await approvals.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=root_id,
                    approver_id="equivalence.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准冻结业务契约对照执行",
                    expected_binding=root_waiting.approval_binding,
                ),
                NOW,
            )
            await legacy.ainvoke(
                Command(
                    resume={
                        "approval_id": str(legacy_approval.id),
                        "decision": legacy_approval.decision.value,
                    }
                ),
                config=_config(legacy_id),
            )
            await root.ainvoke(
                Command(
                    resume={
                        "approval_id": str(root_approval.id),
                        "decision": root_approval.decision.value,
                    }
                ),
                config=_config(root_id),
            )
            await saver.adelete_thread(str(legacy_id))
            await saver.adelete_thread(str(root_id))

        legacy_done = await repository.load_detail(legacy_id)
        root_done = await repository.load_detail(root_id)
        assert legacy_done.status == root_done.status
        assert legacy_done.result is not None
        assert root_done.result is not None
        assert legacy_done.result.outcome == root_done.result.outcome
        assert legacy_done.work_order is not None
        assert root_done.work_order is not None
        assert legacy_done.work_order.payload == root_done.work_order.payload
        assert legacy_done.event_types == root_done.event_types
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operations).where(operations.c.id.in_((legacy_id, root_id)))
            )
