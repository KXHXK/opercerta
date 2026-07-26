"""Add durable successor lineage to operational signals.

Revision ID: 0008_signal_successor_lineage
Revises: 0007_operational_signals
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_signal_successor_lineage"
down_revision: str | Sequence[str] | None = "0007_operational_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operational_signals",
        sa.Column(
            "predecessor_signal_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_signal_predecessor",
        "operational_signals",
        "operational_signals",
        ["predecessor_signal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_operational_signals_predecessor_signal_id",
        "operational_signals",
        ["predecessor_signal_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_operational_signals_predecessor_signal_id",
        "operational_signals",
        type_="unique",
    )
    op.drop_constraint(
        "fk_signal_predecessor",
        "operational_signals",
        type_="foreignkey",
    )
    op.drop_column("operational_signals", "predecessor_signal_id")
