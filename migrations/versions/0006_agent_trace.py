"""Add durable redacted Agent Trace runs, events, and citations.

Revision ID: 0006_agent_trace
Revises: 0005_agent_knowledge
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_agent_trace"
down_revision: str | Sequence[str] | None = "0005_agent_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_key", sa.String(length=160), nullable=False),
        sa.Column("scenario", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_mode", sa.String(length=16), nullable=False),
        sa.Column("initiated_by", sa.String(length=128), nullable=True),
        sa.Column("next_sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scenario IN ('inventory', 'equipment', 'task')",
            name="ck_agent_runs_scenario",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'awaiting_human', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "model_mode IN ('mock', 'real')",
            name="ck_agent_runs_model_mode",
        ),
        sa.CheckConstraint(
            "next_sequence >= 0",
            name="ck_agent_runs_next_sequence_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name="fk_agent_runs_operation_id_operations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint(
            "operation_id",
            "run_key",
            name="uq_agent_runs_operation_run_key",
        ),
    )
    op.create_table(
        "agent_trace_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("semantic_key", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("node", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("safe_input", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("safe_output", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("prompt_ref", sa.String(length=256), nullable=True),
        sa.Column("tool_ref", sa.String(length=256), nullable=True),
        sa.Column("error_code", sa.String(length=256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('perception', 'model', 'tool', 'rag', 'rule', 'human', "
            "'execution', 'feedback', 'guardrail')",
            name="ck_agent_trace_events_type",
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'agent', 'model', 'tool', 'policy', 'human', 'system')",
            name="ck_agent_trace_events_actor",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'blocked', 'waiting')",
            name="ck_agent_trace_events_status",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_agent_trace_events_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_trace_events_run_id_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_trace_events"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_trace_events_run_sequence"),
        sa.UniqueConstraint(
            "run_id",
            "semantic_key",
            name="uq_agent_trace_events_run_semantic_key",
        ),
    )
    op.create_table(
        "agent_trace_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_agent_trace_citations_rank_positive"),
        sa.CheckConstraint(
            "score >= 0.0 AND score <= 1.0",
            name="ck_agent_trace_citations_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["agent_trace_events.id"],
            name="fk_agent_trace_citations_event_id_events",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_trace_citations"),
        sa.UniqueConstraint("event_id", "rank", name="uq_agent_trace_citations_event_rank"),
        sa.UniqueConstraint(
            "event_id",
            "chunk_id",
            name="uq_agent_trace_citations_event_chunk",
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_trace_citations")
    op.drop_table("agent_trace_events")
    op.drop_table("agent_runs")
