"""Add generic approval binding columns for three business scenarios.

Revision ID: 0003_three_business_operations
Revises: 0002_inventory_replenishment
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_three_business_operations"
down_revision: str | Sequence[str] | None = "0002_inventory_replenishment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approvals",
        sa.Column("subject_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "approvals",
        sa.Column("binding_payload", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        """
        UPDATE approvals
        SET
            subject_evidence_id = inventory_evidence_id,
            binding_payload = jsonb_build_object(
                'scenario', 'inventory',
                'subject_evidence_id', inventory_evidence_id::text,
                'policy_evidence_id', policy_evidence_id::text,
                'rule_version', rule_version,
                'decision_facts_hash', decision_facts_hash,
                'plan_hash', plan_hash,
                'parameters', jsonb_build_object(
                    'kind', 'replenishment',
                    'recommended_quantity', recommended_quantity
                )
            )
        WHERE
            inventory_evidence_id IS NOT NULL
            AND policy_evidence_id IS NOT NULL
            AND rule_version IS NOT NULL
            AND decision_facts_hash IS NOT NULL
            AND plan_hash IS NOT NULL
            AND recommended_quantity IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("approvals", "binding_payload")
    op.drop_column("approvals", "subject_evidence_id")
