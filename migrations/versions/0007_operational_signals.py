"""Add durable operational anomaly signals.

Revision ID: 0007_operational_signals
Revises: 0006_agent_trace
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_operational_signals"
down_revision: str | Sequence[str] | None = "0006_agent_trace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name="fk_operational_signals_operation_id_operations",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_signals"),
        sa.UniqueConstraint("dedup_key", name="uq_operational_signals_dedup_key"),
        sa.UniqueConstraint("operation_id", name="uq_operational_signals_operation_id"),
    )
    op.create_index(
        "ix_operational_signals_status_detected_at",
        "operational_signals",
        ["status", "detected_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_signals_status_detected_at",
        table_name="operational_signals",
    )
    op.drop_table("operational_signals")
