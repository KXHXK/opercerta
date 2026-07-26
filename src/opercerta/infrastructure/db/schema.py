import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

knowledge_documents = sa.Table(
    "knowledge_documents",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("scenario", sa.String(length=16), nullable=False),
    sa.Column("slug", sa.String(length=128), nullable=False),
    sa.Column("version", sa.String(length=64), nullable=False),
    sa.Column("title", sa.String(length=200), nullable=False),
    sa.Column("checksum", sa.String(length=64), nullable=False),
    sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "scenario",
        "slug",
        "version",
        name="uq_knowledge_documents_scenario_slug_version",
    ),
    sa.CheckConstraint(
        "scenario IN ('inventory', 'equipment', 'task')",
        name="ck_knowledge_documents_scenario",
    ),
    sa.CheckConstraint(
        "checksum ~ '^[0-9a-f]{64}$'",
        name="ck_knowledge_documents_checksum",
    ),
)

knowledge_chunks = sa.Table(
    "knowledge_chunks",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "document_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("chunk_index", sa.Integer(), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("content_hash", sa.String(length=64), nullable=False),
    sa.Column("embedding", Vector(512), nullable=False),
    sa.Column(
        "metadata",
        postgresql.JSONB(),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "document_id",
        "chunk_index",
        name="uq_knowledge_chunks_document_index",
    ),
    sa.UniqueConstraint(
        "document_id",
        "content_hash",
        name="uq_knowledge_chunks_document_content_hash",
    ),
    sa.CheckConstraint(
        "chunk_index >= 0",
        name="ck_knowledge_chunks_index_non_negative",
    ),
    sa.CheckConstraint(
        "length(btrim(content)) > 0",
        name="ck_knowledge_chunks_content_non_empty",
    ),
    sa.CheckConstraint(
        "content_hash ~ '^[0-9a-f]{64}$'",
        name="ck_knowledge_chunks_content_hash",
    ),
)

operations = sa.Table(
    "operations",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("thread_id", sa.String(length=128), nullable=False),
    sa.Column("request_payload", postgresql.JSONB(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("result_payload", postgresql.JSONB()),
    sa.Column("error_code", sa.String(length=64)),
    sa.Column("approval_expires_at", sa.DateTime(timezone=True)),
    sa.Column(
        "approval_cycle",
        sa.Integer(),
        server_default=sa.text("0"),
        nullable=False,
    ),
    sa.Column(
        "next_audit_sequence",
        sa.BigInteger(),
        server_default=sa.text("0"),
        nullable=False,
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint("thread_id", name="uq_operations_thread_id"),
    sa.CheckConstraint(
        "approval_cycle >= 0",
        name="ck_operations_approval_cycle_non_negative",
    ),
)

operational_signals = sa.Table(
    "operational_signals",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("dedup_key", sa.String(length=200), nullable=False),
    sa.Column("signal_type", sa.String(length=32), nullable=False),
    sa.Column("object_type", sa.String(length=16), nullable=False),
    sa.Column("object_id", sa.String(length=64), nullable=False),
    sa.Column("source", sa.String(length=64), nullable=False),
    sa.Column("severity", sa.String(length=16), nullable=False),
    sa.Column("reason_code", sa.String(length=64), nullable=False),
    sa.Column("facts_hash", sa.String(length=64), nullable=False),
    sa.Column("facts", postgresql.JSONB(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "predecessor_signal_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operational_signals.id", ondelete="RESTRICT"),
    ),
    sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("dedup_key", name="uq_operational_signals_dedup_key"),
    sa.UniqueConstraint("operation_id", name="uq_operational_signals_operation_id"),
    sa.UniqueConstraint(
        "predecessor_signal_id",
        name="uq_operational_signals_predecessor_signal_id",
    ),
    sa.CheckConstraint(
        "signal_type IN ('inventory_shortage', 'equipment_attention', 'task_blocked')",
        name="ck_operational_signals_type",
    ),
    sa.CheckConstraint(
        "object_type IN ('inventory', 'equipment', 'task')",
        name="ck_operational_signals_object_type",
    ),
    sa.CheckConstraint(
        "severity IN ('low', 'medium', 'high')",
        name="ck_operational_signals_severity",
    ),
    sa.CheckConstraint(
        "status IN ('open', 'investigating', 'resolved', 'attention_required')",
        name="ck_operational_signals_status",
    ),
    sa.CheckConstraint(
        "facts_hash ~ '^[0-9a-f]{64}$'",
        name="ck_operational_signals_facts_hash",
    ),
)

agent_runs = sa.Table(
    "agent_runs",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("run_key", sa.String(length=160), nullable=False),
    sa.Column("scenario", sa.String(length=16), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("model_mode", sa.String(length=16), nullable=False),
    sa.Column("initiated_by", sa.String(length=128)),
    sa.Column("next_sequence", sa.BigInteger(), server_default="0", nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint(
        "operation_id",
        "run_key",
        name="uq_agent_runs_operation_run_key",
    ),
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
)

agent_trace_events = sa.Table(
    "agent_trace_events",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "run_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("sequence", sa.BigInteger(), nullable=False),
    sa.Column("semantic_key", sa.String(length=160), nullable=False),
    sa.Column("event_type", sa.String(length=32), nullable=False),
    sa.Column("actor_type", sa.String(length=32), nullable=False),
    sa.Column("node", sa.String(length=128), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("safe_input", postgresql.JSONB(), server_default="{}", nullable=False),
    sa.Column("safe_output", postgresql.JSONB(), server_default="{}", nullable=False),
    sa.Column("prompt_ref", sa.String(length=256)),
    sa.Column("tool_ref", sa.String(length=256)),
    sa.Column("error_code", sa.String(length=256)),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint(
        "run_id",
        "sequence",
        name="uq_agent_trace_events_run_sequence",
    ),
    sa.UniqueConstraint(
        "run_id",
        "semantic_key",
        name="uq_agent_trace_events_run_semantic_key",
    ),
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
    sa.CheckConstraint(
        "sequence >= 1",
        name="ck_agent_trace_events_sequence_positive",
    ),
)

agent_trace_citations = sa.Table(
    "agent_trace_citations",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "event_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agent_trace_events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("version", sa.String(length=64), nullable=False),
    sa.Column("rank", sa.Integer(), nullable=False),
    sa.Column("score", sa.Float(), nullable=False),
    sa.UniqueConstraint(
        "event_id",
        "rank",
        name="uq_agent_trace_citations_event_rank",
    ),
    sa.UniqueConstraint(
        "event_id",
        "chunk_id",
        name="uq_agent_trace_citations_event_chunk",
    ),
    sa.CheckConstraint(
        "rank >= 1",
        name="ck_agent_trace_citations_rank_positive",
    ),
    sa.CheckConstraint(
        "score >= 0.0 AND score <= 1.0",
        name="ck_agent_trace_citations_score_range",
    ),
)

approvals = sa.Table(
    "approvals",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("approver_id", sa.String(length=128), nullable=False),
    sa.Column("decision", sa.String(length=16), nullable=False),
    sa.Column("reason", sa.String(length=1_000), nullable=False),
    sa.Column(
        "approval_cycle",
        sa.Integer(),
        server_default=sa.text("1"),
        nullable=False,
    ),
    sa.Column("inventory_evidence_id", postgresql.UUID(as_uuid=True)),
    sa.Column("policy_evidence_id", postgresql.UUID(as_uuid=True)),
    sa.Column("rule_version", sa.String(length=128)),
    sa.Column("decision_facts_hash", sa.String(length=64)),
    sa.Column("plan_hash", sa.String(length=64)),
    sa.Column("recommended_quantity", sa.BigInteger()),
    sa.Column("subject_evidence_id", postgresql.UUID(as_uuid=True)),
    sa.Column("binding_payload", postgresql.JSONB()),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "operation_id",
        "approval_cycle",
        name="uq_approvals_operation_cycle",
    ),
    sa.CheckConstraint(
        "approval_cycle >= 1",
        name="ck_approvals_approval_cycle_positive",
    ),
)

evidence = sa.Table(
    "evidence",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_type", sa.String(length=32), nullable=False),
    sa.Column("source_tool", sa.String(length=128), nullable=False),
    sa.Column("source_version", sa.String(length=128), nullable=False),
    sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("content", postgresql.JSONB(), nullable=False),
    sa.Column("content_hash", sa.String(length=64), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "operation_id",
        "evidence_id",
        name="uq_evidence_operation_evidence_id",
    ),
)

work_orders = sa.Table(
    "work_orders",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("idempotency_key", sa.String(length=128), nullable=False),
    sa.Column("payload", postgresql.JSONB(), nullable=False),
    sa.Column("payload_hash", sa.String(length=64), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint("operation_id", name="uq_work_orders_operation_id"),
    sa.UniqueConstraint("idempotency_key", name="uq_work_orders_idempotency_key"),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "operation_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("sequence", sa.BigInteger(), nullable=False),
    sa.Column("event_type", sa.String(length=64), nullable=False),
    sa.Column("payload", postgresql.JSONB(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "operation_id",
        "sequence",
        name="uq_audit_events_operation_sequence",
    ),
)
