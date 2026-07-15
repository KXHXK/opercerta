import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

operations = sa.Table(
    "operations",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("thread_id", sa.String(length=128), nullable=False),
    sa.Column("request_payload", postgresql.JSONB(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
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
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.UniqueConstraint("operation_id", name="uq_approvals_operation_id"),
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
