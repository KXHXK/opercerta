"""Allow versioned reapproval while retaining prior decisions.

Revision ID: 0004_approval_cycles
Revises: 0003_three_business_operations
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_approval_cycles"
down_revision: str | Sequence[str] | None = "0003_three_business_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operations",
        sa.Column(
            "approval_cycle",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "approvals",
        sa.Column(
            "approval_cycle",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE operations
        SET approval_cycle = 1
        WHERE status = 'awaiting_approval'
           OR EXISTS (
                SELECT 1 FROM approvals
                WHERE approvals.operation_id = operations.id
           )
        """
    )
    op.drop_constraint("uq_approvals_operation_id", "approvals", type_="unique")
    op.create_unique_constraint(
        "uq_approvals_operation_cycle",
        "approvals",
        ["operation_id", "approval_cycle"],
    )
    op.create_check_constraint(
        "ck_operations_approval_cycle_non_negative",
        "operations",
        "approval_cycle >= 0",
    )
    op.create_check_constraint(
        "ck_approvals_approval_cycle_positive",
        "approvals",
        "approval_cycle >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_approvals_approval_cycle_positive",
        "approvals",
        type_="check",
    )
    op.drop_constraint(
        "ck_operations_approval_cycle_non_negative",
        "operations",
        type_="check",
    )
    op.drop_constraint("uq_approvals_operation_cycle", "approvals", type_="unique")
    op.create_unique_constraint(
        "uq_approvals_operation_id",
        "approvals",
        ["operation_id"],
    )
    op.drop_column("approvals", "approval_cycle")
    op.drop_column("operations", "approval_cycle")
