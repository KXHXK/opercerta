from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import BigInteger, DateTime, String, create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector

ROOT = Path(__file__).resolve().parents[3]


def column_map(inspector: Inspector, table_name: str) -> dict[str, dict[str, object]]:
    return {
        str(column["name"]): column for column in inspector.get_columns(table_name, schema="public")
    }


def assert_nullable_type(
    column: dict[str, object],
    expected_type: type[object],
    *,
    length: int | None = None,
    timezone: bool | None = None,
) -> None:
    assert column["nullable"] is True
    column_type = column["type"]
    assert isinstance(column_type, expected_type)
    if length is not None:
        assert getattr(column_type, "length", None) == length
    if timezone is not None:
        assert getattr(column_type, "timezone", None) is timezone


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
        baseline_inspector = inspect(engine)
        baseline_operation_columns = set(column_map(baseline_inspector, "operations"))
        baseline_approval_columns = set(column_map(baseline_inspector, "approvals"))
        assert "evidence" not in baseline_inspector.get_table_names(schema="public")

        command.upgrade(config, "0002_inventory_replenishment")
        inspector = inspect(engine)
        assert "evidence" in inspector.get_table_names(schema="public")
        operation_columns = column_map(inspector, "operations")
        approval_columns = column_map(inspector, "approvals")
        assert set(operation_columns) == baseline_operation_columns | {
            "result_payload",
            "error_code",
            "approval_expires_at",
        }
        assert set(approval_columns) == baseline_approval_columns | {
            "inventory_evidence_id",
            "policy_evidence_id",
            "rule_version",
            "decision_facts_hash",
            "plan_hash",
            "recommended_quantity",
        }
        assert_nullable_type(operation_columns["result_payload"], postgresql.JSONB)
        assert_nullable_type(operation_columns["error_code"], String, length=64)
        assert_nullable_type(
            operation_columns["approval_expires_at"],
            DateTime,
            timezone=True,
        )
        assert_nullable_type(
            approval_columns["inventory_evidence_id"],
            postgresql.UUID,
        )
        assert_nullable_type(
            approval_columns["policy_evidence_id"],
            postgresql.UUID,
        )
        assert_nullable_type(approval_columns["rule_version"], String, length=128)
        assert_nullable_type(
            approval_columns["decision_facts_hash"],
            String,
            length=64,
        )
        assert_nullable_type(approval_columns["plan_hash"], String, length=64)
        assert_nullable_type(approval_columns["recommended_quantity"], BigInteger)

        evidence_columns = column_map(inspector, "evidence")
        assert set(evidence_columns) == {
            "id",
            "operation_id",
            "evidence_id",
            "evidence_type",
            "source_tool",
            "source_version",
            "captured_at",
            "expires_at",
            "content",
            "content_hash",
            "created_at",
        }
        for column_name in evidence_columns:
            assert evidence_columns[column_name]["nullable"] is False
        assert isinstance(evidence_columns["id"]["type"], postgresql.UUID)
        assert isinstance(evidence_columns["operation_id"]["type"], postgresql.UUID)
        assert isinstance(evidence_columns["evidence_id"]["type"], postgresql.UUID)
        for column_name, length in (
            ("evidence_type", 32),
            ("source_tool", 128),
            ("source_version", 128),
            ("content_hash", 64),
        ):
            assert isinstance(evidence_columns[column_name]["type"], String)
            assert getattr(evidence_columns[column_name]["type"], "length", None) == length
        for column_name in ("captured_at", "expires_at", "created_at"):
            assert isinstance(evidence_columns[column_name]["type"], DateTime)
            assert getattr(evidence_columns[column_name]["type"], "timezone", None) is True
        assert isinstance(evidence_columns["content"]["type"], postgresql.JSONB)

        primary_key = inspector.get_pk_constraint("evidence", schema="public")
        assert primary_key["name"] == "pk_evidence"
        assert primary_key["constrained_columns"] == ["id"]
        unique_constraints = inspector.get_unique_constraints("evidence", schema="public")
        assert {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in unique_constraints
        } == {
            (
                "uq_evidence_operation_evidence_id",
                ("operation_id", "evidence_id"),
            )
        }
        foreign_keys = inspector.get_foreign_keys("evidence", schema="public")
        assert len(foreign_keys) == 1
        foreign_key = foreign_keys[0]
        assert foreign_key["name"] == "fk_evidence_operation_id_operations"
        assert foreign_key["constrained_columns"] == ["operation_id"]
        assert foreign_key["referred_schema"] in {None, "public"}
        assert foreign_key["referred_table"] == "operations"
        assert foreign_key["referred_columns"] == ["id"]
        assert foreign_key["options"] == {"ondelete": "CASCADE"}

        command.downgrade(config, "0001_reliability_kernel")
        downgraded_inspector = inspect(engine)
        assert set(column_map(downgraded_inspector, "operations")) == (baseline_operation_columns)
        assert set(column_map(downgraded_inspector, "approvals")) == (baseline_approval_columns)
        assert "evidence" not in downgraded_inspector.get_table_names(schema="public")
    finally:
        command.upgrade(config, "head")
        engine.dispose()
