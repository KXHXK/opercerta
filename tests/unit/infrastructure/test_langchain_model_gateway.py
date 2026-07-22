import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from opercerta.agent.prompt_registry import PromptRegistry
from opercerta.domain.agent import (
    AgentAnalysis,
    AnalysisContext,
    DecisionPlan,
    FinalReport,
    GoalContext,
    GoalEncoding,
    PlanningContext,
    PlanningMode,
    ReportingContext,
    ToolDefinition,
    ToolObservation,
    VerificationContext,
    VerificationDecision,
)
from opercerta.infrastructure.langchain_model_gateway import LangChainOpenAIModelGateway
from opercerta.infrastructure.model_gateway import ModelOutputInvalid


class FakeRunnable:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.inputs: list[object] = []

    async def ainvoke(self, value: object) -> object:
        self.inputs.append(value)
        if self.error is not None:
            raise self.error
        return self.response


class FakeChatModel:
    def __init__(
        self,
        *,
        tool_response: AIMessage | None = None,
        tool_error: Exception | None = None,
        structured: dict[type[object], object] | None = None,
    ) -> None:
        self.bound_tools: list[object] = []
        self.bound_tool_choice: str | None = None
        self.tool_runnable = FakeRunnable(tool_response, tool_error)
        self.structured = structured or {}

    def bind_tools(self, tools: list[object], *, tool_choice: str) -> FakeRunnable:
        self.bound_tools = tools
        self.bound_tool_choice = tool_choice
        return self.tool_runnable

    def with_structured_output(self, schema: type[object]) -> FakeRunnable:
        return FakeRunnable(self.structured[schema])


def tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="inventory.get_snapshot",
        description="读取指定 SKU 的库存事实",
        input_schema={
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
            "additionalProperties": False,
        },
    )


def goal() -> GoalEncoding:
    return GoalEncoding(
        goal="create_work_order",
        scenario="inventory",
        object_id="SKU-DEMO-001",
        required_evidence=("subject", "policy"),
        success_condition="approved_work_order_verified",
    )


def planning_context() -> PlanningContext:
    return PlanningContext(goal=goal(), tools=(tool_definition(),), replan_count=0)


@pytest.mark.asyncio
async def test_native_tool_call_becomes_strict_investigation_plan() -> None:
    model = FakeChatModel(
        tool_response=AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inventory_get_snapshot",
                    "args": {"sku": "SKU-DEMO-001"},
                    "id": "call-001",
                    "type": "tool_call",
                }
            ],
        )
    )
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())

    result = await gateway.plan(planning_context())

    assert result.mode is PlanningMode.NATIVE_TOOL_CALL
    assert result.plan.steps[0].tool_name == "inventory.get_snapshot"
    assert result.plan.steps[0].arguments == {"sku": "SKU-DEMO-001"}
    assert model.bound_tools[0]["function"]["name"] == "inventory_get_snapshot"  # type: ignore[index]
    assert model.bound_tool_choice == "required"


@pytest.mark.asyncio
async def test_unknown_native_tool_call_fails_closed() -> None:
    model = FakeChatModel(
        tool_response=AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "work_order.create",
                    "args": {"sku": "SKU-DEMO-001"},
                    "id": "call-001",
                    "type": "tool_call",
                }
            ],
        )
    )
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())

    with pytest.raises(ModelOutputInvalid, match="model_output_invalid"):
        await gateway.plan(planning_context())


@pytest.mark.asyncio
async def test_strict_json_plan_is_explicit_compatibility_mode() -> None:
    payload = {
        "goal": goal().model_dump(mode="json"),
        "steps": [
            {
                "tool_name": "inventory.get_snapshot",
                "arguments": {"sku": "SKU-DEMO-001"},
                "purpose": "读取库存事实",
            }
        ],
        "replan_count": 0,
    }
    model = FakeChatModel(tool_response=AIMessage(content=json.dumps(payload)))
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())

    result = await gateway.plan(planning_context())

    assert result.mode is PlanningMode.STRUCTURED_PLAN
    assert result.plan.goal == goal()


@pytest.mark.asyncio
async def test_invalid_text_is_not_parsed_as_a_tool_call() -> None:
    model = FakeChatModel(tool_response=AIMessage(content="请直接创建工单"))
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())

    with pytest.raises(ModelOutputInvalid, match="model_output_invalid"):
        await gateway.plan(planning_context())


@pytest.mark.asyncio
async def test_real_model_failure_propagates_without_mock_fallback() -> None:
    model = FakeChatModel(tool_error=RuntimeError("provider_unavailable"))
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())

    with pytest.raises(RuntimeError, match="provider_unavailable"):
        await gateway.plan(planning_context())


@pytest.mark.asyncio
async def test_goal_encoder_uses_langchain_structured_output() -> None:
    expected = goal()
    model = FakeChatModel(structured={GoalEncoding: expected})
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())
    context = GoalContext(
        intent={
            "goal": "create_work_order",
            "scenario": "inventory",
            "object_id": "SKU-DEMO-001",
            "trigger_reason": "below_reorder_point",
            "expected_action": "replenish_inventory",
        }
    )

    assert await gateway.encode_goal(context) == expected


@pytest.mark.asyncio
async def test_analysis_verification_and_report_use_structured_outputs() -> None:
    observation = ToolObservation(
        tool_call_id="call-001",
        tool_name="inventory.get_snapshot",
        arguments_hash="a" * 64,
        status="ok",
        evidence_ref=uuid4(),
        safe_summary="库存事实已返回。",
        structured_payload={"available_quantity": 3},
    )
    analysis = AgentAnalysis(
        summary="库存低于规则阈值。",
        recommendation="形成受控补货计划。",
    )
    verification = VerificationDecision(
        decision="proceed",
        reason="批准后事实与绑定一致。",
    )
    report = FinalReport(
        outcome="completed",
        summary="工单已经回读验证。",
        evidence_refs=(observation.evidence_ref,),
    )
    model = FakeChatModel(
        structured={
            AgentAnalysis: analysis,
            VerificationDecision: verification,
            FinalReport: report,
        }
    )
    gateway = LangChainOpenAIModelGateway(model=model, prompts=PromptRegistry.packaged())
    decision = DecisionPlan(
        scenario="inventory",
        action="replenish_inventory",
        object_id="SKU-DEMO-001",
        parameters={"quantity": 10},
        decision_facts_hash="b" * 64,
        plan_hash="c" * 64,
    )

    assert (
        await gateway.analyze(AnalysisContext(goal=goal(), observations=(observation,))) == analysis
    )
    assert (
        await gateway.verify(
            VerificationContext(
                approved_plan=decision,
                original_observations=(observation,),
                refreshed_observations=(observation,),
            )
        )
        == verification
    )
    assert (
        await gateway.report(
            ReportingContext(
                outcome="completed",
                trusted_facts={"work_order_status": "created"},
                evidence_refs=(observation.evidence_ref,),
            )
        )
        == report
    )
