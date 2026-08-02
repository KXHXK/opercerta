from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.agent import (
    AgentDecisionContext,
    AgentTurn,
    GoalContext,
    GoalEncoding,
    ReadToolName,
    VerificationContext,
    VerificationDecision,
)
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.replenishment import ReplenishmentPlan
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.tools.catalog import SyntheticCatalog
from opercerta.workflow.inventory_agent_root_graph import (
    build_inventory_agent_root_graph,
    build_inventory_agent_root_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
MCP_NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
OPERATION_ID = UUID("80000000-0000-4000-8000-000000000026")


@pytest.fixture(scope="module")
def catalog() -> SyntheticCatalog:
    return SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
        equipment_path=ROOT / "data" / "synthetic" / "equipment.json",
        maintenance_policy_path=ROOT / "data" / "synthetic" / "maintenance_policies.json",
        task_path=ROOT / "data" / "synthetic" / "tasks.json",
        task_recovery_policy_path=ROOT / "data" / "synthetic" / "task_recovery_policies.json",
    )


class InventoryReadGateway:
    def __init__(self, catalog: SyntheticCatalog) -> None:
        self._catalog = catalog
        self.calls: list[ReadToolName] = []

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, object],
    ) -> BaseModel:
        self.calls.append(name)
        if name is ReadToolName.INVENTORY_SNAPSHOT:
            return self._catalog.inventory_snapshot(str(arguments["sku"]), NOW)
        if name is ReadToolName.POLICY_CONSTRAINTS:
            return self._catalog.policy_constraints(str(arguments["sku"]), NOW)
        raise AssertionError(f"unexpected tool: {name}")


class SequentialTurnModel:
    def __init__(
        self,
        *,
        finish_early: bool = False,
        forbidden_write: bool = False,
        bogus_evidence_refs: bool = False,
    ) -> None:
        self.contexts: list[AgentDecisionContext] = []
        self._finish_early = finish_early
        self._forbidden_write = forbidden_write
        self._bogus_evidence_refs = bogus_evidence_refs

    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        return GoalEncoding(
            goal=context.intent.goal,
            scenario=context.intent.scenario,
            object_id=context.intent.object_id,
            required_evidence=("subject", "policy"),
            success_condition=(
                "query_reported" if context.intent.goal == "query" else "approval_requested"
            ),
        )

    async def decide(self, context: AgentDecisionContext) -> AgentTurn:
        self.contexts.append(context)
        if self._forbidden_write:
            return AgentTurn.model_validate(
                {
                    "kind": "tool_calls",
                    "tool_calls": [
                        {
                            "tool_call_id": "call-write",
                            "tool_name": "work_order.create",
                            "arguments": {"sku": context.goal.object_id},
                            "purpose": "非法绕过审批。",
                        }
                    ],
                }
            )
        if self._finish_early or len(context.observations) == 2:
            return AgentTurn.model_validate(
                {
                    "kind": "final_analysis",
                    "finding": "库存事实与规则已核对。",
                    "evidence_refs": (
                        ["model-invented-ref"]
                        if self._bogus_evidence_refs
                        else [item.tool_call_id for item in context.observations]
                    ),
                    "missing_evidence": [],
                    "recommended_action": (
                        "report_status" if context.goal.goal == "query" else "request_approval"
                    ),
                    "confidence_band": "high",
                    "explanation": "将结构化事实交给确定性 Policy Guard。",
                }
            )
        if not context.observations:
            tool_name = "inventory.get_snapshot"
            arguments = {"sku": context.goal.object_id}
        else:
            tool_name = "policy.list_constraints"
            arguments = {
                "action": "replenish_inventory",
                "sku": context.goal.object_id,
            }
        return AgentTurn.model_validate(
            {
                "kind": "tool_calls",
                "tool_calls": [
                    {
                        "tool_call_id": f"call-{len(context.observations) + 1}",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "purpose": "读取下一项尚缺的受控事实。",
                    }
                ],
            }
        )

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        assert all(
            observation.cache_status.value == "bypass"
            for observation in context.refreshed_observations
        )
        return VerificationDecision(
            decision="proceed",
            reason="批准后新鲜事实与审批绑定一致。",
        )


class FailingVerifierModel(SequentialTurnModel):
    async def verify(self, context: VerificationContext) -> VerificationDecision:
        raise RuntimeError("model_provider_unavailable")


def request(action: str, object_id: str = "SKU-LOW-001") -> OperationRequest:
    return OperationRequest(
        message="调查库存异常",
        requested_action=action,
        object_type="inventory",
        object_id=object_id,
    )


@pytest.mark.asyncio
async def test_query_observation_returns_to_model_before_next_decision(
    catalog: SyntheticCatalog,
) -> None:
    model = SequentialTurnModel()
    gateway = InventoryReadGateway(catalog)
    graph = build_inventory_agent_root_graph(
        model,
        gateway,
        clock=lambda: NOW,
        enabled=True,
    )

    result = await graph.ainvoke(
        build_inventory_agent_root_initial_state(OPERATION_ID, request("query")),
        config={"configurable": {"thread_id": str(OPERATION_ID)}},
    )

    assert result["status"] == "query_completed"
    assert [len(context.observations) for context in model.contexts] == [0, 1, 2]
    assert gateway.calls == [
        ReadToolName.INVENTORY_SNAPSHOT,
        ReadToolName.POLICY_CONSTRAINTS,
    ]
    assert result["model_call_count"] == 4  # goal encoding plus three decisions
    assert result["tool_call_count"] == 2
    assert result["decision_plan"] is None


@pytest.mark.asyncio
async def test_verified_observations_deterministically_bind_final_evidence_refs(
    catalog: SyntheticCatalog,
) -> None:
    model = SequentialTurnModel(bogus_evidence_refs=True)
    gateway = InventoryReadGateway(catalog)
    graph = build_inventory_agent_root_graph(
        model,
        gateway,
        clock=lambda: NOW,
        enabled=True,
    )

    result = await graph.ainvoke(
        build_inventory_agent_root_initial_state(OPERATION_ID, request("query")),
        config={"configurable": {"thread_id": str(OPERATION_ID)}},
    )

    assert result["status"] == "query_completed"
    assert set(result["final_analysis"]["evidence_refs"]) == {"call-1", "call-2"}


@pytest.mark.asyncio
async def test_create_path_interrupts_for_approval_on_the_same_thread(
    catalog: SyntheticCatalog,
) -> None:
    model = SequentialTurnModel()
    checkpointer = InMemorySaver()
    gateway = InventoryReadGateway(catalog)
    graph = build_inventory_agent_root_graph(
        model,
        gateway,
        clock=lambda: NOW,
        checkpointer=checkpointer,
        enabled=True,
    )
    config = {"configurable": {"thread_id": str(OPERATION_ID)}}

    result = await graph.ainvoke(
        build_inventory_agent_root_initial_state(
            OPERATION_ID,
            request("create_work_order"),
        ),
        config=config,
    )
    snapshot = await graph.aget_state(config)

    assert result["status"] == "awaiting_approval"
    assert result["decision_plan"] is not None
    assert result["__interrupt__"]
    assert snapshot.config["configurable"]["thread_id"] == str(OPERATION_ID)
    assert snapshot.next == ("approval_interrupt",)


@pytest.mark.asyncio
async def test_final_analysis_before_required_observations_fails_closed(
    catalog: SyntheticCatalog,
) -> None:
    gateway = InventoryReadGateway(catalog)
    graph = build_inventory_agent_root_graph(
        SequentialTurnModel(finish_early=True),
        gateway,
        clock=lambda: NOW,
        enabled=True,
    )

    result = await graph.ainvoke(
        build_inventory_agent_root_initial_state(OPERATION_ID, request("query"))
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "required_evidence_incomplete"
    assert gateway.calls == []


def test_write_tool_cannot_enter_the_agent_turn_contract() -> None:
    with pytest.raises(ValidationError):
        AgentTurn.model_validate(
            {
                "kind": "tool_calls",
                "tool_calls": [
                    {
                        "tool_call_id": "call-write",
                        "tool_name": "work_order.create",
                        "arguments": {"sku": "SKU-LOW-001"},
                        "purpose": "非法绕过审批。",
                    }
                ],
            }
        )


def test_single_root_candidate_is_disabled_unless_explicitly_enabled(
    catalog: SyntheticCatalog,
) -> None:
    with pytest.raises(RuntimeError, match="single_root_inventory_feature_disabled"):
        build_inventory_agent_root_graph(
            SequentialTurnModel(),
            InventoryReadGateway(catalog),
            clock=lambda: NOW,
        )


@pytest.mark.asyncio
async def test_create_interrupt_is_persisted_by_postgres_checkpointer(
    catalog: SyntheticCatalog,
    checkpoint_database_url: SecretStr,
) -> None:
    config = {"configurable": {"thread_id": str(OPERATION_ID)}}
    async with open_checkpointer(checkpoint_database_url) as saver:
        graph = build_inventory_agent_root_graph(
            SequentialTurnModel(),
            InventoryReadGateway(catalog),
            clock=lambda: NOW,
            checkpointer=saver,
            enabled=True,
        )

        result = await graph.ainvoke(
            build_inventory_agent_root_initial_state(
                OPERATION_ID,
                request("create_work_order"),
            ),
            config=config,
        )
        snapshot = await graph.aget_state(config)
        await saver.adelete_thread(str(OPERATION_ID))

    assert result["status"] == "awaiting_approval"
    assert snapshot.next == ("approval_interrupt",)
    assert snapshot.values["operation_id"] == str(OPERATION_ID)


@pytest.mark.asyncio
async def test_approved_inventory_root_completes_one_idempotent_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = request("create_work_order")
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_inventory_agent_root_graph(
                SequentialTurnModel(),
                gateway,
                clock=lambda: MCP_NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            waiting = await graph.ainvoke(
                build_inventory_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            detail = await repository.load_detail(operation_id)
            assert waiting["status"] == "awaiting_approval"
            assert detail.status.value == "awaiting_approval"
            assert detail.approval_binding is not None

            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准受控补货。",
                    expected_binding=detail.approval_binding,
                ),
                MCP_NOW,
            )
            completed = await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            await saver.adelete_thread(str(operation_id))

        final_detail = await repository.load_detail(operation_id)
        assert completed["status"] == "completed", (
            completed["status"],
            completed["error_code"],
            completed["verification_route"],
            completed["work_order"],
        )
        assert completed["verification_route"] == "proceed"
        assert completed["replayed"] is False
        assert final_detail.status.value == "completed"
        assert final_detail.work_order is not None
        assert final_detail.result is not None
        assert final_detail.result.work_order_id == final_detail.work_order.id
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_inventory_fact_drift_starts_a_new_approval_cycle_without_writing(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = request("create_work_order", "SKU-MUTABLE-001")
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_inventory_agent_root_graph(
                SequentialTurnModel(),
                gateway,
                clock=lambda: MCP_NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_inventory_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            first_waiting = await repository.load_detail(operation_id)
            assert first_waiting.approval_binding is not None
            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准原始补货计划。",
                    expected_binding=first_waiting.approval_binding,
                ),
                MCP_NOW,
            )
            mcp_server.catalog.replace_inventory(
                "SKU-MUTABLE-001",
                on_hand_quantity=18,
                reserved_quantity=8,
            )
            reapproval = await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            snapshot = await graph.aget_state(config)
            await saver.adelete_thread(str(operation_id))

        detail = await repository.load_detail(operation_id)
        assert reapproval["status"] == "needs_reapproval"
        assert snapshot.next == ("approval_interrupt",)
        assert detail.status.value == "needs_reapproval"
        assert detail.work_order is None
        assert isinstance(detail.plan, ReplenishmentPlan)
        assert detail.plan.recommended_quantity == 20
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_prewritten_inventory_work_order_is_replayed_after_checkpoint_gap(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = request("create_work_order")
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_inventory_agent_root_graph(
                SequentialTurnModel(),
                gateway,
                clock=lambda: MCP_NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_inventory_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            assert isinstance(waiting.plan, ReplenishmentPlan)
            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准受控补货。",
                    expected_binding=waiting.approval_binding,
                ),
                MCP_NOW,
            )
            prewritten = await gateway.create_work_order(
                WorkOrderCommand(
                    operation_id=operation_id,
                    payload={
                        "approved_plan_hash": waiting.plan.plan_hash,
                        "quantity": waiting.plan.recommended_quantity,
                        "sku": waiting.plan.sku,
                    },
                ),
                plan_hash=waiting.plan.plan_hash,
            )
            assert prewritten.replayed is False

            completed = await graph.ainvoke(
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
        assert completed["status"] == "completed"
        assert completed["replayed"] is True
        assert detail.work_order is not None
        assert detail.work_order.id == prewritten.work_order.id
        assert detail.event_types.count("work_order_created") == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_verifier_model_failure_cannot_bypass_deterministic_write_guard(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = request("create_work_order")
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_inventory_agent_root_graph(
                FailingVerifierModel(),
                gateway,
                clock=lambda: MCP_NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_inventory_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准受控补货。",
                    expected_binding=waiting.approval_binding,
                ),
                MCP_NOW,
            )
            failed = await graph.ainvoke(
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
        assert failed["status"] == "failed"
        assert failed["error_code"] == "approval_snapshot_mismatch"
        assert detail.status.value == "failed"
        assert detail.work_order is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_rejected_inventory_root_finishes_without_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = request("create_work_order")
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_inventory_agent_root_graph(
                SequentialTurnModel(),
                gateway,
                clock=lambda: MCP_NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_inventory_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            detail = await repository.load_detail(operation_id)
            assert detail.approval_binding is not None
            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="inventory.manager",
                    decision=ApprovalDecision.REJECTED,
                    reason="拒绝本次补货。",
                    expected_binding=detail.approval_binding,
                ),
                MCP_NOW,
            )
            rejected = await graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(approval.id),
                        "decision": approval.decision.value,
                    }
                ),
                config=config,
            )
            await saver.adelete_thread(str(operation_id))

        final_detail = await repository.load_detail(operation_id)
        assert rejected["status"] == "rejected"
        assert final_detail.status.value == "rejected"
        assert final_detail.work_order is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
