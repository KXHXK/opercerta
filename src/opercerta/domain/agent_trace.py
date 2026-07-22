from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

SafeTraceKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SafeNode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SafeReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class StrictTraceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTraceEventType(StrEnum):
    PERCEPTION = "perception"
    MODEL = "model"
    TOOL = "tool"
    RAG = "rag"
    RULE = "rule"
    HUMAN = "human"
    EXECUTION = "execution"
    FEEDBACK = "feedback"
    GUARDRAIL = "guardrail"


class AgentTraceActor(StrEnum):
    USER = "user"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    POLICY = "policy"
    HUMAN = "human"
    SYSTEM = "system"


class AgentTraceStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING = "waiting"


class AgentTraceCitationInput(StrictTraceModel):
    document_id: UUID
    chunk_id: UUID
    version: SafeReference
    rank: Annotated[int, Field(strict=True, ge=1, le=20)]
    score: Annotated[float, Field(ge=0.0, le=1.0)]


class AgentTraceCitationRecord(AgentTraceCitationInput):
    id: UUID
    event_id: UUID


class AgentTraceEventInput(StrictTraceModel):
    semantic_key: SafeTraceKey
    event_type: AgentTraceEventType
    actor_type: AgentTraceActor
    node: SafeNode
    status: AgentTraceStatus
    safe_input: dict[str, JsonValue] = Field(default_factory=dict)
    safe_output: dict[str, JsonValue] = Field(default_factory=dict)
    prompt_ref: SafeReference | None = None
    tool_ref: SafeReference | None = None
    error_code: SafeReference | None = None
    citations: tuple[AgentTraceCitationInput, ...] = ()
    started_at: datetime
    ended_at: datetime | None = None


class AgentTraceEventRecord(StrictTraceModel):
    id: UUID
    run_id: UUID
    sequence: Annotated[int, Field(strict=True, ge=1)]
    semantic_key: SafeTraceKey
    event_type: AgentTraceEventType
    actor_type: AgentTraceActor
    node: SafeNode
    status: AgentTraceStatus
    safe_input: dict[str, JsonValue]
    safe_output: dict[str, JsonValue]
    prompt_ref: SafeReference | None = None
    tool_ref: SafeReference | None = None
    error_code: SafeReference | None = None
    citations: tuple[AgentTraceCitationRecord, ...] = ()
    started_at: datetime
    ended_at: datetime | None = None


class AgentRunRecord(StrictTraceModel):
    id: UUID
    operation_id: UUID
    run_key: SafeTraceKey
    scenario: Literal["inventory", "equipment", "task"]
    status: AgentRunStatus
    model_mode: Literal["mock", "real"]
    initiated_by: SafeReference | None = None
    next_sequence: Annotated[int, Field(strict=True, ge=0)]
    started_at: datetime
    ended_at: datetime | None = None


class AgentTraceAppendResult(StrictTraceModel):
    event: AgentTraceEventRecord
    replayed: bool


class AgentTraceSnapshot(StrictTraceModel):
    run: AgentRunRecord
    events: tuple[AgentTraceEventRecord, ...]
