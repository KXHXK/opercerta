from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]


def test_reliability_kernel_migration_creates_required_schema(
    database_url: SecretStr,
    monkeypatch: MonkeyPatch,
) -> None:
    raw_database_url = database_url.get_secret_value()
    monkeypatch.setenv("OPERCERTA_DATABASE_URL", raw_database_url)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

    engine = create_engine(raw_database_url)
    try:
        inspector = inspect(engine)
        assert {
            "operations",
            "approvals",
            "work_orders",
            "audit_events",
        } <= set(inspector.get_table_names(schema="public"))
        assert "langgraph" in inspector.get_schema_names()
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("approvals")
        } == {"uq_approvals_operation_id"}
    finally:
        engine.dispose()
