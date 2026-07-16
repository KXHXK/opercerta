from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def test_inventory_replenishment_migration_upgrades_and_downgrades(
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

    try:
        command.downgrade(config, "0001_reliability_kernel")
        command.upgrade(config, "0001_reliability_kernel")
        assert "evidence" not in inspect(engine).get_table_names(schema="public")

        command.upgrade(config, "0002_inventory_replenishment")
        inspector = inspect(engine)
        assert "evidence" in inspector.get_table_names(schema="public")
        assert {
            "result_payload",
            "error_code",
            "approval_expires_at",
        } <= {column["name"] for column in inspector.get_columns("operations")}
        assert {
            "inventory_evidence_id",
            "policy_evidence_id",
            "rule_version",
            "decision_facts_hash",
            "plan_hash",
            "recommended_quantity",
        } <= {column["name"] for column in inspector.get_columns("approvals")}

        command.downgrade(config, "0001_reliability_kernel")
        assert "evidence" not in inspect(engine).get_table_names(schema="public")
    finally:
        command.upgrade(config, "head")
        engine.dispose()
