import json
from collections.abc import Sequence
from typing import Protocol, TypeVar, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from opercerta.agent.prompt_registry import PromptId, PromptRegistry
from opercerta.domain.agent import (
    AgentAnalysis,
    AnalysisContext,
    FinalReport,
    GoalContext,
    GoalEncoding,
    InvestigationPlan,
    InvestigationStep,
    PlanningContext,
    PlanningMode,
    PlanningResult,
    ReadToolName,
    ReportingContext,
    VerificationContext,
    VerificationDecision,
)
from opercerta.infrastructure.model_gateway import ModelOutputInvalid

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def to_model_tool_name(name: ReadToolName) -> str:
    """Translate the stable domain tool ID to a provider-safe function name."""
    return name.value.replace(".", "_")


class AsyncRunnable(Protocol):
    async def ainvoke(self, value: object) -> object: ...


class AgentChatModel(Protocol):
    def bind_tools(self, tools: list[object]) -> AsyncRunnable: ...

    def with_structured_output(self, schema: type[object]) -> AsyncRunnable: ...


class LangChainOpenAIModelGateway:
    def __init__(self, *, model: AgentChatModel, prompts: PromptRegistry) -> None:
        self._model = model
        self._prompts = prompts

    @classmethod
    def from_openai_compatible(
        cls,
        *,
        base_url: str,
        model_name: str,
        api_key: SecretStr,
        prompts: PromptRegistry | None = None,
        timeout_seconds: float = 10.0,
        disable_thinking: bool = False,
    ) -> "LangChainOpenAIModelGateway":
        extra_body = {"thinking": {"type": "disabled"}} if disable_thinking else None
        model = ChatOpenAI(
            base_url=base_url,
            model=model_name,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
            extra_body=extra_body,
        )
        return cls(
            model=cast(AgentChatModel, model),
            prompts=prompts or PromptRegistry.packaged(),
        )

    async def encode_goal(self, context: GoalContext) -> GoalEncoding:
        return await self._invoke_structured(PromptId.PLANNER, context, GoalEncoding)

    async def plan(self, context: PlanningContext) -> PlanningResult:
        prompt = self._prompts.load(PromptId.PLANNER)
        wire_to_domain = {
            to_model_tool_name(definition.name): definition.name for definition in context.tools
        }
        if len(wire_to_domain) != len(context.tools):
            raise ValueError("model_tool_name_collision")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": to_model_tool_name(definition.name),
                    "description": definition.description,
                    "parameters": definition.input_schema,
                },
            }
            for definition in context.tools
        ]
        bound = self._model.bind_tools(cast(list[object], tools))
        response = await bound.ainvoke(self._messages(prompt.content, context))
        if not isinstance(response, AIMessage):
            raise ModelOutputInvalid

        allowed_names = {definition.name for definition in context.tools}
        if response.tool_calls:
            try:
                steps = tuple(
                    InvestigationStep(
                        tool_name=wire_to_domain[call["name"]],
                        arguments=call["args"],
                        purpose="执行模型提出的受控只读调查。",
                    )
                    for call in response.tool_calls
                )
                if any(step.tool_name not in allowed_names for step in steps):
                    raise ValueError("tool_not_exposed")
                plan = InvestigationPlan(
                    goal=context.goal,
                    steps=steps,
                    replan_count=context.replan_count,
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                raise ModelOutputInvalid from None
            return PlanningResult(mode=PlanningMode.NATIVE_TOOL_CALL, plan=plan)

        if not isinstance(response.content, str) or not response.content.strip():
            raise ModelOutputInvalid
        try:
            plan = InvestigationPlan.model_validate_json(response.content)
        except (ValueError, ValidationError):
            raise ModelOutputInvalid from None
        if any(step.tool_name not in allowed_names for step in plan.steps):
            raise ModelOutputInvalid
        return PlanningResult(mode=PlanningMode.STRUCTURED_PLAN, plan=plan)

    async def analyze(self, context: AnalysisContext) -> AgentAnalysis:
        return await self._invoke_structured(PromptId.ANALYST, context, AgentAnalysis)

    async def verify(self, context: VerificationContext) -> VerificationDecision:
        return await self._invoke_structured(
            PromptId.VERIFIER,
            context,
            VerificationDecision,
        )

    async def report(self, context: ReportingContext) -> FinalReport:
        return await self._invoke_structured(PromptId.REPORTER, context, FinalReport)

    async def _invoke_structured(
        self,
        prompt_id: PromptId,
        context: BaseModel,
        schema: type[StructuredModel],
    ) -> StructuredModel:
        prompt = self._prompts.load(prompt_id)
        runnable = self._model.with_structured_output(schema)
        response = await runnable.ainvoke(self._messages(prompt.content, context))
        try:
            return schema.model_validate(response)
        except ValidationError:
            raise ModelOutputInvalid from None

    @staticmethod
    def _messages(prompt: str, context: BaseModel) -> Sequence[BaseMessage]:
        return (
            SystemMessage(content=prompt),
            HumanMessage(
                content=json.dumps(
                    context.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
        )
