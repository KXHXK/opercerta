from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.types import Command
from pydantic import BaseModel, JsonValue, SecretStr
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
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.tools.catalog import SyntheticCatalog
from opercerta.workflow.inventory_agent_root_graph import (
    build_controlled_agent_root_graph,
    build_controlled_agent_root_initial_state,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import mcp_server as _mcp_server_fixture

mcp_server = _mcp_server_fixture

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


@pytest.fixture
def catalog() -> SyntheticCatalog:
    return SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
        equipment_path=ROOT / "data" / "synthetic" / "equipment.json",
        maintenance_policy_path=ROOT / "data" / "synthetic" / "maintenance_policies.json",
        task_path=ROOT / "data" / "synthetic" / "tasks.json",
        task_recovery_policy_path=ROOT / "data" / "synthetic" / "task_recovery_policies.json",
    )


class ScenarioReadGateway:
    def __init__(self, catalog: SyntheticCatalog) -> None:
        self._catalog = catalog
        self.calls: list[ReadToolName] = []

    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> BaseModel:
        self.calls.append(name)
        if name is ReadToolName.EQUIPMENT_STATUS:
            return self._catalog.equipment_status(str(arguments["equipment_id"]), NOW)
        if name is ReadToolName.TASK_STATUS:
            return self._catalog.task_status(str(arguments["task_id"]), NOW)
        if name is ReadToolName.POLICY_CONSTRAINTS:
            action = str(arguments["action"])
            if action == "repair_equipment":
                return self._catalog.maintenance_policy_constraints(
                    str(arguments["equipment_id"]), NOW
                )
            return self._catalog.task_recovery_policy_constraints(str(arguments["task_id"]), NOW)
        raise AssertionError(f"unexpected tool: {name}")


class ScenarioTurnModel:
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
        if len(context.observations) == 2:
            return AgentTurn.model_validate(
                {
                    "kind": "final_analysis",
                    "finding": "业务事实和适用规则均已核验。",
                    "evidence_refs": [item.tool_call_id for item in context.observations],
                    "missing_evidence": [],
                    "recommended_action": (
                        "report_status" if context.goal.goal == "query" else "request_approval"
                    ),
                    "confidence_band": "high",
                    "explanation": "由确定性规则根据已验证事实形成结论。",
                }
            )
        if not context.observations:
            tool_name = {
                ScenarioKind.EQUIPMENT: "equipment.get_status",
                ScenarioKind.TASK: "task.get_status",
            }[context.goal.scenario]
            subject_key = {
                ScenarioKind.EQUIPMENT: "equipment_id",
                ScenarioKind.TASK: "task_id",
            }[context.goal.scenario]
            arguments = {subject_key: context.goal.object_id}
        else:
            action = {
                ScenarioKind.EQUIPMENT: "repair_equipment",
                ScenarioKind.TASK: "recover_task",
            }[context.goal.scenario]
            subject_key = {
                ScenarioKind.EQUIPMENT: "equipment_id",
                ScenarioKind.TASK: "task_id",
            }[context.goal.scenario]
            tool_name = "policy.list_constraints"
            arguments = {
                "action": action,
                subject_key: context.goal.object_id,
            }
        return AgentTurn.model_validate(
            {
                "kind": "tool_calls",
                "tool_calls": [
                    {
                        "tool_call_id": f"call-{len(context.observations) + 1}",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "purpose": "读取当前场景仍缺少的受控事实。",
                    }
                ],
            }
        )

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        return VerificationDecision(decision="proceed", reason="事实与审批绑定一致。")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id", "expected_subject_tool"),
    [
        ("equipment", "EQ-PUMP-001", ReadToolName.EQUIPMENT_STATUS),
        ("task", "TASK-BLOCKED-001", ReadToolName.TASK_STATUS),
    ],
)
async def test_equipment_and_task_queries_share_the_root_graph_topology(
    catalog: SyntheticCatalog,
    object_type: str,
    object_id: str,
    expected_subject_tool: ReadToolName,
) -> None:
    controlled_request = OperationRequest(
        message="调查业务异常",
        requested_action="query",
        object_type=object_type,
        object_id=object_id,
    )
    gateway = ScenarioReadGateway(catalog)
    graph = build_controlled_agent_root_graph(
        ScenarioTurnModel(), gateway, clock=lambda: NOW, enabled=True
    )

    result = await graph.ainvoke(
        build_controlled_agent_root_initial_state(uuid4(), controlled_request)
    )

    assert result["status"] == "query_completed"
    assert gateway.calls == [expected_subject_tool, ReadToolName.POLICY_CONSTRAINTS]
    assert result["model_call_count"] == 4
    assert result["tool_call_count"] == 2


class CrossScenarioModel(ScenarioTurnModel):
    async def decide(self, context: AgentDecisionContext) -> AgentTurn:
        return AgentTurn.model_validate(
            {
                "kind": "tool_calls",
                "tool_calls": [
                    {
                        "tool_call_id": "cross-scenario",
                        "tool_name": "inventory.get_snapshot",
                        "arguments": {"sku": "SKU-LOW-001"},
                        "purpose": "尝试读取不相关业务事实。",
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_equipment_goal_rejects_cross_scenario_inventory_tool(
    catalog: SyntheticCatalog,
) -> None:
    controlled_request = OperationRequest(
        message="调查设备异常",
        requested_action="query",
        object_type="equipment",
        object_id="EQ-PUMP-001",
    )
    graph = build_controlled_agent_root_graph(
        CrossScenarioModel(),
        ScenarioReadGateway(catalog),
        clock=lambda: NOW,
        enabled=True,
    )

    result = await graph.ainvoke(
        build_controlled_agent_root_initial_state(uuid4(), controlled_request)
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "tool_policy_violation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id", "expected_payload_keys"),
    [
        (
            "equipment",
            "EQ-PUMP-001",
            {
                "kind",
                "equipment_id",
                "alert_code",
                "priority",
                "approved_plan_hash",
            },
        ),
        (
            "task",
            "TASK-BLOCKED-001",
            {
                "kind",
                "task_id",
                "blocker_code",
                "retry_count",
                "recovery_action",
                "approved_plan_hash",
            },
        ),
    ],
)
async def test_equipment_and_task_approved_paths_share_human_and_write_nodes(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    object_type: str,
    object_id: str,
    expected_payload_keys: set[str],
) -> None:
    repository = OperationRepository(engine)
    approval_repository = ApprovalRepository(engine)
    controlled_request = OperationRequest(
        message="调查异常并在规则要求时创建工单",
        requested_action="create_work_order",
        object_type=object_type,
        object_id=object_id,
    )
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_agent_root_graph(
                ScenarioTurnModel(),
                gateway,
                clock=lambda: NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            waiting_state = await graph.ainvoke(
                build_controlled_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting_state["status"] == "awaiting_approval"
            assert waiting.approval_binding is not None
            approval = await approval_repository.submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="scenario.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准受控场景工单。",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
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

        detail = await repository.load_detail(operation_id)
        assert completed["status"] == "completed", completed["error_code"]
        assert completed["verification_route"] == "proceed"
        assert detail.status.value == "completed"
        assert detail.work_order is not None
        assert set(detail.work_order.payload) == expected_payload_keys
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id"),
    [
        ("equipment", "EQ-PUMP-001"),
        ("task", "TASK-BLOCKED-001"),
    ],
)
async def test_equipment_and_task_rejections_finish_without_work_orders(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    object_type: str,
    object_id: str,
) -> None:
    repository = OperationRepository(engine)
    controlled_request = OperationRequest(
        message="调查异常并在规则要求时创建工单",
        requested_action="create_work_order",
        object_type=object_type,
        object_id=object_id,
    )
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_agent_root_graph(
                ScenarioTurnModel(),
                gateway,
                clock=lambda: NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_controlled_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="scenario.manager",
                    decision=ApprovalDecision.REJECTED,
                    reason="拒绝本次受控工单。",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
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

        detail = await repository.load_detail(operation_id)
        assert rejected["status"] == "rejected"
        assert detail.status.value == "rejected"
        assert detail.work_order is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id"),
    [
        ("equipment", "EQ-MUTABLE-001"),
        ("task", "TASK-MUTABLE-001"),
    ],
)
async def test_equipment_and_task_fact_drift_require_reapproval_without_writing(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    object_type: str,
    object_id: str,
) -> None:
    repository = OperationRepository(engine)
    controlled_request = OperationRequest(
        message="调查异常并在规则要求时创建工单",
        requested_action="create_work_order",
        object_type=object_type,
        object_id=object_id,
    )
    operation_id = await repository.create(controlled_request)
    config = {"configurable": {"thread_id": str(operation_id)}}
    gateway = McpToolGateway(mcp_server.url, timeout_seconds=2)
    try:
        async with open_checkpointer(checkpoint_database_url) as saver:
            graph = build_controlled_agent_root_graph(
                ScenarioTurnModel(),
                gateway,
                clock=lambda: NOW,
                checkpointer=saver,
                enabled=True,
                operations=repository,
                action_gateway=gateway,
                refresh_gateway=gateway,
            )
            await graph.ainvoke(
                build_controlled_agent_root_initial_state(operation_id, controlled_request),
                config=config,
            )
            waiting = await repository.load_detail(operation_id)
            assert waiting.approval_binding is not None
            approval = await ApprovalRepository(engine).submit_bound_once(
                BoundApprovalCommand(
                    operation_id=operation_id,
                    approver_id="scenario.manager",
                    decision=ApprovalDecision.APPROVED,
                    reason="批准原始计划。",
                    expected_binding=waiting.approval_binding,
                ),
                NOW,
            )
            if object_type == "equipment":
                mcp_server.catalog.replace_equipment(
                    object_id,
                    state="offline",
                    alert_code="MOTOR_OVERHEAT",
                    severity="critical",
                    last_heartbeat=NOW - timedelta(minutes=1),
                )
            else:
                mcp_server.catalog.replace_task(
                    object_id,
                    state="blocked",
                    due_at=NOW + timedelta(minutes=10),
                    last_progress_at=NOW - timedelta(minutes=5),
                    blocker_code="LOCK_CONTENTION",
                    retry_count=2,
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
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
