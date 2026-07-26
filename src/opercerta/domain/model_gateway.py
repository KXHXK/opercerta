from typing import Protocol

from opercerta.domain.agent import (
    AgentAnalysis,
    AgentDecisionContext,
    AgentTurn,
    AnalysisContext,
    FinalReport,
    GoalContext,
    GoalEncoding,
    InvestigationPlan,
    InvestigationStep,
    PlanningContext,
    PlanningMode,
    PlanningResult,
    ReportingContext,
    VerificationContext,
    VerificationDecision,
)
from opercerta.domain.maintenance import MaintenanceAssessment
from opercerta.domain.replenishment import (
    ModelPlanExplanation,
    ReplenishmentAssessment,
)
from opercerta.domain.task_recovery import TaskRecoveryAssessment

ScenarioAssessment = ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment


class ModelGateway(Protocol):
    async def explain_plan(
        self,
        assessment: ScenarioAssessment,
    ) -> ModelPlanExplanation:
        raise NotImplementedError


class AgentModelGateway(Protocol):
    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        raise NotImplementedError

    async def plan(self, context: PlanningContext) -> PlanningResult:
        raise NotImplementedError

    async def analyze(self, context: AnalysisContext) -> AgentAnalysis:
        raise NotImplementedError

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        raise NotImplementedError

    async def report(self, context: ReportingContext) -> FinalReport:
        raise NotImplementedError


class AgentLoopModelGateway(Protocol):
    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        raise NotImplementedError

    async def decide(self, context: AgentDecisionContext) -> AgentTurn:
        raise NotImplementedError

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        raise NotImplementedError


class MockModelGateway:
    async def explain_plan(
        self,
        assessment: ScenarioAssessment,
    ) -> ModelPlanExplanation:
        if isinstance(assessment, MaintenanceAssessment):
            return ModelPlanExplanation(
                summary=f"建议为设备 {assessment.equipment_id} 创建维修工单。",
                rationale="维修优先级由已验证设备证据和版本化规则确定。",
            )
        if isinstance(assessment, TaskRecoveryAssessment):
            return ModelPlanExplanation(
                summary=f"建议为任务 {assessment.task_id} 创建人工恢复工单。",
                rationale="恢复动作由已验证阻塞或逾期事实和版本化规则确定。",
            )
        return ModelPlanExplanation(
            summary=f"建议为 {assessment.sku} 创建补货计划。",
            rationale="数量由已验证库存事实和版本化规则确定。",
        )


class MockAgentModelGateway:
    """Deterministic offline model double that still exercises the Agent graph."""

    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        return GoalEncoding(
            goal=context.intent.goal,
            scenario=context.intent.scenario,
            object_id=context.intent.object_id,
            required_evidence=("subject", "policy"),
            success_condition=(
                "query_reported"
                if context.intent.goal.value == "query"
                else "approved_work_order_verified"
            ),
        )

    async def decide(self, context: AgentDecisionContext) -> AgentTurn:
        if context.tools:
            calls: list[dict[str, object]] = []
            for index, definition in enumerate(context.tools, start=1):
                properties = definition.input_schema.get("properties")
                if not isinstance(properties, dict):
                    raise ValueError("mock_tool_schema_invalid")
                arguments: dict[str, object] = {}
                for key, schema in properties.items():
                    if (
                        not isinstance(key, str)
                        or not isinstance(schema, dict)
                        or "const" not in schema
                    ):
                        raise ValueError("mock_tool_schema_invalid")
                    arguments[key] = schema["const"]
                calls.append(
                    {
                        "tool_call_id": f"mock-call-{context.tool_call_count + index}",
                        "tool_name": definition.name,
                        "arguments": arguments,
                        "purpose": "读取当前决策仍缺少的受控事实。",
                    }
                )
            return AgentTurn.model_validate({"kind": "tool_calls", "tool_calls": calls})

        return AgentTurn.model_validate(
            {
                "kind": "final_analysis",
                "finding": f"已核对 {context.goal.object_id} 的业务事实与规则。",
                "evidence_refs": [observation.tool_call_id for observation in context.observations],
                "missing_evidence": [],
                "recommended_action": (
                    "report_status" if context.goal.goal.value == "query" else "request_approval"
                ),
                "confidence_band": "high",
                "explanation": "最终动作参数和写权限仍由确定性规则与审批门禁控制。",
            }
        )

    async def plan(self, context: PlanningContext) -> PlanningResult:
        steps: list[InvestigationStep] = []
        completed = {item.tool_name for item in context.prior_observations}
        for definition in context.tools:
            if definition.name in completed:
                continue
            properties = definition.input_schema.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("mock_tool_schema_invalid")
            arguments: dict[str, object] = {}
            for key, schema in properties.items():
                if (
                    not isinstance(key, str)
                    or not isinstance(schema, dict)
                    or "const" not in schema
                ):
                    raise ValueError("mock_tool_schema_invalid")
                arguments[key] = schema["const"]
            steps.append(
                InvestigationStep.model_validate(
                    {
                        "tool_name": definition.name,
                        "arguments": arguments,
                        "purpose": "读取受控合成业务证据。",
                    }
                )
            )
        return PlanningResult(
            mode=PlanningMode.NATIVE_TOOL_CALL,
            plan=InvestigationPlan(
                goal=context.goal,
                steps=tuple(steps),
                replan_count=context.replan_count,
            ),
        )

    async def analyze(self, context: AnalysisContext) -> AgentAnalysis:
        return AgentAnalysis(
            summary=f"已核对 {context.goal.object_id} 的业务事实与规则。",
            recommendation="由确定性 Policy Guard 计算动作参数。",
        )

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        del context
        return VerificationDecision(
            decision="proceed",
            reason="批准后重新取证与绑定事实一致。",
        )

    async def report(self, context: ReportingContext) -> FinalReport:
        return FinalReport(
            outcome=context.outcome,
            summary="操作已按可信事实完成。",
            evidence_refs=context.evidence_refs,
            citations=context.citations,
        )
