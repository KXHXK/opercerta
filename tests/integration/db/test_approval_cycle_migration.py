from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def test_approval_cycle_migration_backfills_current_cycle_and_downgrades(
    database_url: SecretStr,
    monkeypatch: MonkeyPatch,
) -> None:
    parsed_url = make_url(database_url.get_secret_value())
    if parsed_url.password:
        monkeypatch.setenv("PGPASSWORD", parsed_url.password)
    passwordless_url = parsed_url.set(password=None)
    monkeypatch.setenv(
        "OPERCERTA_DATABASE_URL",
        passwordless_url.render_as_string(hide_password=False),
    )
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(passwordless_url)
    received_id = uuid4()
    awaiting_id = uuid4()
    approved_id = uuid4()

    try:
        command.downgrade(config, "0003_three_business_operations")
        with engine.begin() as connection:
            for operation_id, status in (
                (received_id, "received"),
                (awaiting_id, "awaiting_approval"),
                (approved_id, "resuming"),
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO operations (id, thread_id, request_payload, status)
                        VALUES (:id, :thread_id, CAST(:payload AS jsonb), :status)
                        """
                    ),
                    {
                        "id": operation_id,
                        "thread_id": str(operation_id),
                        "payload": '{"message":"approval cycle migration"}',
                        "status": status,
                    },
                )
            connection.execute(
                text(
                    """
                    INSERT INTO approvals (
                        id, operation_id, approver_id, decision, reason
                    ) VALUES (
                        :id, :operation_id, 'migration.approver', 'approved',
                        'historical approval'
                    )
                    """
                ),
                {"id": uuid4(), "operation_id": approved_id},
            )

        command.upgrade(config, "0004_approval_cycles")
        with engine.connect() as connection:
            cycles = dict(
                connection.execute(
                    text(
                        """
                        SELECT id, approval_cycle FROM operations
                        WHERE id IN (:received_id, :awaiting_id, :approved_id)
                        """
                    ),
                    {
                        "received_id": received_id,
                        "awaiting_id": awaiting_id,
                        "approved_id": approved_id,
                    },
                ).all()
            )
            approval_cycle = connection.execute(
                text("SELECT approval_cycle FROM approvals WHERE operation_id = :operation_id"),
                {"operation_id": approved_id},
            ).scalar_one()

        assert cycles == {received_id: 0, awaiting_id: 1, approved_id: 1}
        assert approval_cycle == 1
        assert {
            constraint["name"] for constraint in inspect(engine).get_unique_constraints("approvals")
        } == {"uq_approvals_operation_cycle"}

        command.downgrade(config, "0003_three_business_operations")
        assert "approval_cycle" not in {
            column["name"] for column in inspect(engine).get_columns("operations")
        }
        assert "approval_cycle" not in {
            column["name"] for column in inspect(engine).get_columns("approvals")
        }
    finally:
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM operations WHERE id IN (:a, :b, :c)"),
                {"a": received_id, "b": awaiting_id, "c": approved_id},
            )
        engine.dispose()
