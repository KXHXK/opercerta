from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import JsonValue

from opercerta.domain.agent import (
    AgentAnalysis,
    GoalEncoding,
    InvestigationPlan,
    ReadToolName,
    ToolObservation,
)
from opercerta.domain.agent_trace import (
    AgentRunRecord,
    AgentRunStatus,
    AgentTraceActor,
    AgentTraceCitationInput,
    AgentTraceEventInput,
    AgentTraceEventType,
    AgentTraceStatus,
)
from opercerta.domain.contracts import ActionType, OperationRequest
from opercerta.domain.knowledge import KnowledgeSearchEvidence
from opercerta.domain.scenarios import ScenarioKind

_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "prompt",
        "full_prompt",
        "prompt_text",
        "system_prompt",
        "messages",
        "reasoning_content",
        "chain_of_thought",
        "stack_trace",
        "stacktrace",
        "traceback",
        "raw_body",
        "raw_tool_body",
        "raw_response",
    }
)
_MAX_DEPTH = 4
_MAX_ITEMS = 50
_MAX_TEXT = 1_000


def redact_trace_payload(payload: Mapping[str, object]) -> dict[str, JsonValue]:
    sanitized = _sanitize(payload, depth=0)
    if not isinstance(sanitized, dict):
        raise TypeError("trace payload must be an object")
    return sanitized


def _sanitize(value: object, *, depth: int) -> JsonValue:
    if depth >= _MAX_DEPTH:
        return "[truncated]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for raw_key, item in list(value.items())[:_MAX_ITEMS]:
            key = str(raw_key)[:128]
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                continue
            result[key] = _sanitize(item, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_sanitize(item, depth=depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return str(value)[:_MAX_TEXT]


class TraceRecorder:
    def __init__(
        self,
        repository: object,
        *,
        clock: Callable[[], datetime],
        model_mode: str,
    ) -> None:
        from opercerta.infrastructure.db.agent_trace_repository import AgentTraceRepository

        if not isinstance(repository, AgentTraceRepository):
            raise TypeError("AgentTraceRepository is required")
        if model_mode not in {"mock", "real"}:
            raise ValueError("model_mode must be mock or real")
        self._repository = repository
        self._clock = clock
        self._model_mode = cast(Literal["mock", "real"], model_mode)

    async def capture_investigation(
        self,
        operation_id: UUID,
        request: OperationRequest,
        state: Mapping[str, object],
    ) -> AgentRunRecord:
        if request.object_type is None:
            raise ValueError("trace scenario is required")
        now = self._clock()
        run = await self._repository.start_run(
            operation_id=operation_id,
            scenario=ScenarioKind(request.object_type.value),
            model_mode=self._model_mode,
            run_key="primary",
            started_at=now,
        )
        intent_payload = state.get("intent")
        await self._append(
            run.id,
            semantic_key="perception:intent",
            event_type=AgentTraceEventType.PERCEPTION,
            actor_type=AgentTraceActor.USER,
            node="intent_envelope",
            safe_input={
                "requested_action": request.requested_action.value
                if request.requested_action is not None
                else None,
                "object_type": request.object_type.value,
                "object_id": request.object_id,
            },
            safe_output=intent_payload if isinstance(intent_payload, Mapping) else {},
        )
        goal_payload = state.get("goal")
        if isinstance(goal_payload, Mapping):
            goal = GoalEncoding.model_validate(goal_payload)
            await self._append(
                run.id,
                semantic_key="model:goal",
                event_type=AgentTraceEventType.MODEL,
                actor_type=AgentTraceActor.MODEL,
                node="encode_goal",
                safe_input={"intent_ref": "perception:intent"},
                safe_output=goal.model_dump(mode="json"),
                prompt_ref="goal_encoder:v1",
            )
        plan_payload = state.get("plan")
        if isinstance(plan_payload, Mapping):
            plan = InvestigationPlan.model_validate(plan_payload)
            await self._append(
                run.id,
                semantic_key=f"model:plan:r{plan.replan_count}",
                event_type=AgentTraceEventType.MODEL,
                actor_type=AgentTraceActor.MODEL,
                node="plan_investigation",
                safe_input={"goal_ref": "model:goal", "replan_count": plan.replan_count},
                safe_output={
                    "steps": [
                        {
                            "tool_name": step.tool_name.value,
                            "purpose": step.purpose,
                        }
                        for step in plan.steps
                    ]
                },
                prompt_ref="investigation_planner:v1",
            )
        raw_observations = state.get("observations", [])
        observation_values: Sequence[object] = (
            raw_observations
            if isinstance(raw_observations, Sequence)
            and not isinstance(raw_observations, str | bytes | bytearray)
            else ()
        )
        for raw_observation in observation_values:
            if not isinstance(raw_observation, Mapping):
                continue
            observation = ToolObservation.model_validate(raw_observation)
            is_rag = observation.tool_name is ReadToolName.KNOWLEDGE_SEARCH
            citations: tuple[AgentTraceCitationInput, ...] = ()
            if is_rag and observation.status == "ok":
                evidence = KnowledgeSearchEvidence.model_validate(observation.structured_payload)
                citations = tuple(
                    AgentTraceCitationInput(
                        document_id=item.document_id,
                        chunk_id=item.chunk_id,
                        version=item.version,
                        rank=index,
                        score=max(0.0, min(1.0, item.score)),
                    )
                    for index, item in enumerate(evidence.results, start=1)
                )
            await self._append(
                run.id,
                semantic_key=f"observation:{observation.tool_call_id}",
                event_type=(AgentTraceEventType.RAG if is_rag else AgentTraceEventType.TOOL),
                actor_type=AgentTraceActor.TOOL,
                node="execute_read_tools",
                status=(
                    AgentTraceStatus.COMPLETED
                    if observation.status == "ok"
                    else AgentTraceStatus.FAILED
                ),
                safe_input={
                    "tool_name": observation.tool_name.value,
                    "arguments_hash": observation.arguments_hash,
                },
                safe_output={
                    "status": observation.status,
                    "evidence_ref": str(observation.evidence_ref)
                    if observation.evidence_ref is not None
                    else None,
                    "safe_summary": observation.safe_summary,
                    "error_code": observation.structured_payload.get("error_code"),
                },
                tool_ref=observation.tool_name.value,
                citations=citations,
                error_code=(
                    str(observation.structured_payload.get("error_code"))
                    if observation.status == "error"
                    and isinstance(observation.structured_payload.get("error_code"), str)
                    else None
                ),
            )
        analysis_payload = state.get("analysis")
        if not isinstance(analysis_payload, Mapping):
            analysis_payload = state.get("agent_analysis")
        if isinstance(analysis_payload, Mapping):
            analysis = AgentAnalysis.model_validate(analysis_payload)
            await self._append(
                run.id,
                semantic_key="model:analysis",
                event_type=AgentTraceEventType.MODEL,
                actor_type=AgentTraceActor.MODEL,
                node="analyze_observations",
                safe_input={"observation_count": len(observation_values)},
                safe_output={
                    "summary": analysis.summary,
                    "recommendation": analysis.recommendation,
                    "uncertainties": list(analysis.uncertainties),
                    "citation_count": len(analysis.citations),
                },
                prompt_ref="observation_analyst:v1",
            )
        if state.get("assessment") is not None or state.get("decision_plan") is not None:
            await self._append(
                run.id,
                semantic_key="rule:policy_guard",
                event_type=AgentTraceEventType.RULE,
                actor_type=AgentTraceActor.POLICY,
                node="calculate_policy_facts",
                safe_input={"analysis_ref": "model:analysis"},
                safe_output={
                    "assessment_present": state.get("assessment") is not None,
                    "decision_plan_present": state.get("decision_plan") is not None,
                },
            )
        failed = state.get("status") == "failed"
        if failed:
            await self._append(
                run.id,
                semantic_key="guardrail:terminal",
                event_type=AgentTraceEventType.GUARDRAIL,
                actor_type=AgentTraceActor.POLICY,
                node="mark_failed",
                status=AgentTraceStatus.BLOCKED,
                safe_input={},
                safe_output={"blocked": True},
                error_code=str(state.get("error_code") or "agent_investigation_failed"),
            )
        await self._append(
            run.id,
            semantic_key="feedback:investigation_terminal",
            event_type=AgentTraceEventType.FEEDBACK,
            actor_type=AgentTraceActor.SYSTEM,
            node="investigation_terminal",
            status=AgentTraceStatus.FAILED if failed else AgentTraceStatus.COMPLETED,
            safe_input={},
            safe_output={"status": state.get("status", "failed")},
            error_code=str(state.get("error_code")) if failed and state.get("error_code") else None,
        )
        run_status = AgentRunStatus.FAILED if failed else AgentRunStatus.COMPLETED
        if request.requested_action is ActionType.CREATE_WORK_ORDER and not failed:
            run_status = AgentRunStatus.RUNNING
        await self._repository.finish_run(run.id, run_status, self._clock())
        return await self._repository.load_run(run.id)

    async def capture_operation_outcome(
        self,
        operation_id: UUID,
        *,
        status: str,
        approval_cycle: int,
        approval: Mapping[str, object] | None,
        verification: Mapping[str, object] | None,
        verification_route: str | None,
        work_order: Mapping[str, object] | None,
        result: Mapping[str, object] | None,
        error_code: str | None,
    ) -> AgentRunRecord:
        snapshot = await self._repository.load_snapshot(operation_id)
        run_id = snapshot.run.id
        if status in {"awaiting_approval", "needs_reapproval"}:
            run_status = AgentRunStatus.AWAITING_HUMAN
        elif status in {"completed", "rejected", "aborted", "expired"}:
            run_status = AgentRunStatus.COMPLETED
        elif status == "failed":
            run_status = AgentRunStatus.FAILED
        else:
            run_status = AgentRunStatus.RUNNING
        if approval is not None:
            approval_id = str(approval.get("id", "unknown"))
            await self._append(
                run_id,
                semantic_key=f"human:approval:{approval_id}",
                event_type=AgentTraceEventType.HUMAN,
                actor_type=AgentTraceActor.HUMAN,
                node="approval_decision",
                safe_input={"approval_cycle": approval_cycle},
                safe_output={
                    "approval_id": approval_id,
                    "decision": approval.get("decision"),
                    "approver_id": approval.get("approver_id"),
                },
            )
        if verification is not None:
            decision = str(verification.get("decision", "unknown"))
            route = verification_route or "unknown"
            verification_cycle = (
                max(1, approval_cycle - 1) if status == "needs_reapproval" else approval_cycle
            )
            await self._append(
                run_id,
                semantic_key=f"model:verification:{verification_cycle}",
                event_type=AgentTraceEventType.MODEL,
                actor_type=AgentTraceActor.MODEL,
                node="verify_current_facts",
                safe_input={"approval_cycle": verification_cycle},
                safe_output={
                    "decision": decision,
                    "route": route,
                    "summary": "批准后已绕过缓存重新取证并完成 Verifier 复核。",
                },
                prompt_ref="verifier:v1",
            )
            await self._append(
                run_id,
                semantic_key=f"guardrail:binding_verification:{verification_cycle}",
                event_type=AgentTraceEventType.GUARDRAIL,
                actor_type=AgentTraceActor.POLICY,
                node="verify_approval_binding",
                status=(
                    AgentTraceStatus.COMPLETED if route == "proceed" else AgentTraceStatus.BLOCKED
                ),
                safe_input={
                    "approval_cycle": verification_cycle,
                    "verifier_decision": decision,
                },
                safe_output={
                    "binding_valid": route == "proceed",
                    "route": route,
                    "summary": (
                        "审批绑定与最新事实一致。允许进入幂等写入。"
                        if route == "proceed"
                        else "最新事实未通过执行护栏。已阻止直接写入。"
                    ),
                },
            )
        if status in {"awaiting_approval", "needs_reapproval"}:
            await self._append(
                run_id,
                semantic_key=f"human:approval_requested:{approval_cycle}",
                event_type=AgentTraceEventType.HUMAN,
                actor_type=AgentTraceActor.HUMAN,
                node="request_approval",
                status=AgentTraceStatus.WAITING,
                safe_input={"approval_cycle": approval_cycle},
                safe_output={"operation_status": status},
            )
        if status == "completed":
            await self._append(
                run_id,
                semantic_key="execution:operation_terminal",
                event_type=AgentTraceEventType.EXECUTION,
                actor_type=AgentTraceActor.SYSTEM,
                node="execute_controlled_action",
                safe_input={"approval_cycle": approval_cycle},
                safe_output={
                    "work_order_id": work_order.get("id") if work_order is not None else None,
                    "result_outcome": result.get("outcome") if result is not None else None,
                },
            )
        if status in {"completed", "rejected", "aborted", "expired", "failed"}:
            await self._append(
                run_id,
                semantic_key="feedback:operation_terminal",
                event_type=AgentTraceEventType.FEEDBACK,
                actor_type=AgentTraceActor.SYSTEM,
                node="operation_terminal",
                status=(
                    AgentTraceStatus.FAILED if status == "failed" else AgentTraceStatus.COMPLETED
                ),
                safe_input={},
                safe_output={"operation_status": status},
                error_code=error_code,
            )
        await self._repository.finish_run(run_id, run_status, self._clock())
        return await self._repository.load_run(run_id)

    async def _append(
        self,
        run_id: UUID,
        *,
        semantic_key: str,
        event_type: AgentTraceEventType,
        actor_type: AgentTraceActor,
        node: str,
        safe_input: Mapping[str, object],
        safe_output: Mapping[str, object],
        status: AgentTraceStatus = AgentTraceStatus.COMPLETED,
        prompt_ref: str | None = None,
        tool_ref: str | None = None,
        error_code: str | None = None,
        citations: tuple[AgentTraceCitationInput, ...] = (),
    ) -> None:
        now = self._clock()
        await self._repository.append_event(
            run_id,
            AgentTraceEventInput(
                semantic_key=semantic_key,
                event_type=event_type,
                actor_type=actor_type,
                node=node,
                status=status,
                safe_input=redact_trace_payload(safe_input),
                safe_output=redact_trace_payload(safe_output),
                prompt_ref=prompt_ref,
                tool_ref=tool_ref,
                error_code=error_code,
                citations=citations,
                started_at=now,
                ended_at=now,
            ),
        )
