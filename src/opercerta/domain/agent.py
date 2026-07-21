from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
)

from opercerta.domain.contracts import ActionType
from opercerta.domain.scenarios import Digest, ScenarioKind, Version

SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
SafeIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SafeSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRequirement(StrEnum):
    SUBJECT = "subject"
    POLICY = "policy"
    KNOWLEDGE = "knowledge"


class ReadToolName(StrEnum):
    INVENTORY_SNAPSHOT = "inventory.get_snapshot"
    EQUIPMENT_STATUS = "equipment.get_status"
    TASK_STATUS = "task.get_status"
    POLICY_CONSTRAINTS = "policy.list_constraints"
    KNOWLEDGE_SEARCH = "knowledge.search_sop"


class IntentEnvelope(StrictAgentModel):
    goal: ActionType
    scenario: ScenarioKind
    object_id: SafeIdentifier
    trigger_reason: SafeSlug
    expected_action: SafeSlug


class GoalEncoding(StrictAgentModel):
    goal: ActionType
    scenario: ScenarioKind
    object_id: SafeIdentifier
    required_evidence: Annotated[tuple[EvidenceRequirement, ...], Field(min_length=1)]
    success_condition: SafeSlug
    uncertainties: tuple[SafeText, ...] = ()


class InvestigationStep(StrictAgentModel):
    tool_name: ReadToolName
    arguments: dict[str, JsonValue]
    purpose: SafeText


class InvestigationPlan(StrictAgentModel):
    goal: GoalEncoding
    steps: Annotated[tuple[InvestigationStep, ...], Field(min_length=1, max_length=4)]
    replan_count: Literal[0, 1]


class ToolCallProposal(StrictAgentModel):
    tool_call_id: SafeIdentifier
    tool_name: ReadToolName
    arguments: dict[str, JsonValue]


class ToolObservation(StrictAgentModel):
    tool_call_id: SafeIdentifier
    tool_name: ReadToolName
    arguments_hash: Digest
    status: Literal["ok", "error"]
    evidence_ref: UUID | None = None
    safe_summary: SafeText
    structured_payload: dict[str, JsonValue]


class KnowledgeCitation(StrictAgentModel):
    document_id: UUID
    chunk_id: UUID
    version: Version
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    safe_snippet: SafeText


class AgentAnalysis(StrictAgentModel):
    summary: SafeText
    recommendation: SafeText
    uncertainties: tuple[SafeText, ...] = ()
    citations: tuple[KnowledgeCitation, ...] = ()


class DecisionPlan(StrictAgentModel):
    scenario: ScenarioKind
    action: SafeSlug
    object_id: SafeIdentifier
    parameters: dict[str, JsonValue]
    decision_facts_hash: Digest
    plan_hash: Digest


class VerificationDecision(StrictAgentModel):
    decision: Literal["proceed", "abort", "escalate"]
    reason: SafeText


class FinalReport(StrictAgentModel):
    outcome: SafeSlug
    summary: SafeText
    evidence_refs: tuple[UUID, ...] = ()
    citations: tuple[KnowledgeCitation, ...] = ()


class AgentBudget(StrictAgentModel):
    max_model_calls: StrictPositiveInt
    max_tool_calls: StrictPositiveInt
    max_input_tokens: StrictPositiveInt
    timeout_seconds: StrictPositiveInt
    max_replans: Literal[1] = 1
