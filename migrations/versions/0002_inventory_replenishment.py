"""Persist inventory-replenishment evidence and terminal facts.

Revision ID: 0002_inventory_replenishment
Revises: 0001_reliability_kernel
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_inventory_replenishment"
down_revision: str | Sequence[str] | None = "0001_reliability_kernel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name="fk_evidence_operation_id_operations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.UniqueConstraint(
            "operation_id",
            "evidence_id",
            name="uq_evidence_operation_evidence_id",
        ),
    )
    op.add_column("operations", sa.Column("result_payload", postgresql.JSONB()))
    op.add_column("operations", sa.Column("error_code", sa.String(length=64)))
    op.add_column(
        "operations",
        sa.Column("approval_expires_at", sa.DateTime(timezone=True)),
    )
    for name, column in (
        ("inventory_evidence_id", postgresql.UUID(as_uuid=True)),
        ("policy_evidence_id", postgresql.UUID(as_uuid=True)),
        ("rule_version", sa.String(length=128)),
        ("decision_facts_hash", sa.String(length=64)),
        ("plan_hash", sa.String(length=64)),
        ("recommended_quantity", sa.BigInteger()),
    ):
        op.add_column("approvals", sa.Column(name, column, nullable=True))


def downgrade() -> None:
    for name in (
        "recommended_quantity",
        "plan_hash",
        "decision_facts_hash",
        "rule_version",
        "policy_evidence_id",
        "inventory_evidence_id",
    ):
        op.drop_column("approvals", name)
    op.drop_column("operations", "approval_expires_at")
    op.drop_column("operations", "error_code")
    op.drop_column("operations", "result_payload")
    op.drop_table("evidence")
