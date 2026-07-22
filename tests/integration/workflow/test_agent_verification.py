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
from opercerta.domain.errors import ApprovalSnapshotMismatch
from opercerta.domain.model_gateway import MockAgentModelGateway, MockModelGateway
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import approvals, operations, work_orders
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import (
    build_controlled_action_graph,
    build_controlled_action_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


class ScriptedVerifierModel(MockAgentModelGateway):
    def __init__(self, decision: str, *, propose_parameter_change: bool = False) -> None:
        self._decision = decision
        self._propose_parameter_change = propose_parameter_change
        self.verification_contexts: list[VerificationContext] = []

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        self.verification_contexts.append(context)
        payload = {
            "decision": self._decision,
            "reason": f"synthetic {self._decision} decision",
        }
        if self._propose_parameter_change:
            payload["proposed_plan"] = context.approved_plan.model_copy(
                update={
                    "parameters": {
                        "kind": "replenishment",
                        "recommended_quantity": 999,
                    }
                }
            )
        return VerificationDecision.model_validate(payload)


class EscalateThenProceedModel(MockAgentModelGateway):
    def __init__(self) -> None:
        self.verification_contexts: list[VerificationContext] = []

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        self.verification_contexts.append(context)
        decision = "escalate" if len(self.verification_contexts) == 1 else "proceed"
        return VerificationDecision(
            decision=decision,
            reason=f"synthetic {decision} decision",
        )


async def work_order_count(engine: AsyncEngine, operation_id: object) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                select(func.count())
                .select_from(work_orders)
                .where(work_orders.c.operation_id == operation_id)
            )
            or 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "verifier_decision",
        "propose_parameter_change",
        "expected_status",
        "expected_work_orders",
    ),
    [
        ("proceed", False, "completed", 1),
        ("abort", False, "aborted", 0),
        ("escalate", False, "needs_reapproval", 0),
        ("proceed", True, "needs_reapproval", 0),
    ],
)
async def test_approved_agent_plan_is_verified_before_any_write(
    verifier_decision: str,
    propose_parameter_change: bool,
    expected_status: str,
    expected_work_orders: int,
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="Create a controlled replenishment work order if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)
    model = ScriptedVerifierModel(
        verifier_decision,
        propose_parameter_change=propose_parameter_change,
    )
    config = {"configurable": {"thread_id": str(operation_id)}}

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
                agent_model_gateway=model,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approve the bound deterministic plan",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )

            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status.value == expected_status
        assert await work_order_count(engine, operation_id) == expected_work_orders
        assert len(model.verification_contexts) == 1
        context = model.verification_contexts[0]
        assert context.original_observations[0].evidence_ref != (
            context.refreshed_observations[0].evidence_ref
        )
        if verifier_decision == "escalate" or propose_parameter_change:
            assert detail.approval_binding != waiting.approval_binding
            assert detail.approval is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_reapproval_uses_a_new_cycle_and_old_binding_cannot_be_reused(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="Create a controlled replenishment work order if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=ObjectType.INVENTORY,
        object_id="SKU-LOW-001",
    )
    operation_id = await repository.create(request)
    model = EscalateThenProceedModel()
    config = {"configurable": {"thread_id": str(operation_id)}}

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
                agent_model_gateway=model,
            )
            await graph.ainvoke(
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
            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(first.id),
                        "decision": first.decision.value,
                    }
                ),
                config=config,
            )

            second_waiting = await repository.load_detail(operation_id)
            assert second_waiting.status.value == "needs_reapproval"
            assert second_waiting.approval_cycle == 2
            assert second_waiting.approval_binding is not None
            assert second_waiting.approval_binding != first_waiting.approval_binding
            with pytest.raises(ApprovalSnapshotMismatch):
                await ApprovalRepository(engine).submit_bound_once(
                    BoundApprovalCommand(
                        operation_id=operation_id,
                        approver_id="inventory.manager",
                        decision=ApprovalDecision.APPROVED,
                        reason="Attempt stale cycle one binding",
                        expected_binding=first_waiting.approval_binding,
                    ),
                    NOW,
                )

            second = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approve cycle two",
                    expected_binding=second_waiting.approval_binding,
                ),
                NOW,
            )
            assert second.approval_cycle == 2
            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(second.id),
                        "decision": second.decision.value,
                    }
                ),
                config=config,
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status.value == "completed"
        assert await work_order_count(engine, operation_id) == 1
        async with engine.connect() as connection:
            cycles = tuple(
                (
                    await connection.execute(
                        select(approvals.c.approval_cycle)
                        .where(approvals.c.operation_id == operation_id)
                        .order_by(approvals.c.approval_cycle)
                    )
                ).scalars()
            )
        assert cycles == (1, 2)
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id", "decision", "expected_status", "expected_count"),
    [
        (ObjectType.EQUIPMENT, "EQ-PUMP-001", "proceed", "completed", 1),
        (ObjectType.EQUIPMENT, "EQ-PUMP-001", "abort", "aborted", 0),
        (
            ObjectType.EQUIPMENT,
            "EQ-PUMP-001",
            "escalate",
            "needs_reapproval",
            0,
        ),
        (ObjectType.TASK, "TASK-BLOCKED-001", "proceed", "completed", 1),
        (ObjectType.TASK, "TASK-BLOCKED-001", "abort", "aborted", 0),
        (
            ObjectType.TASK,
            "TASK-BLOCKED-001",
            "escalate",
            "needs_reapproval",
            0,
        ),
    ],
)
async def test_equipment_and_task_use_the_same_post_approval_verifier(
    object_type: ObjectType,
    object_id: str,
    decision: str,
    expected_status: str,
    expected_count: int,
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    request = OperationRequest(
        message="Create the bounded scenario work order if required",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=object_type,
        object_id=object_id,
    )
    operation_id = await repository.create(request)
    model = ScriptedVerifierModel(decision)
    config = {"configurable": {"thread_id": str(operation_id)}}

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
                agent_model_gateway=model,
            )
            await graph.ainvoke(
                build_controlled_action_initial_state(
                    operation_id,
                    request,
                    build_default_scenario_registry(),
                ),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="scenario.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="Approve the deterministic scenario plan",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )
            await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert detail.status.value == expected_status
        assert await work_order_count(engine, operation_id) == expected_count
        assert len(model.verification_contexts) == 1
        assert model.verification_contexts[0].approved_plan.scenario.value == object_type.value
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
