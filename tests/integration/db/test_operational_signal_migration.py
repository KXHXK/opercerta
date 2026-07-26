from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_operational_signals_schema_is_present(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        columns = await connection.run_sync(
            lambda sync: {
                column["name"] for column in inspect(sync).get_columns("operational_signals")
            }
        )
        unique_constraints = await connection.run_sync(
            lambda sync: {
                item["name"] for item in inspect(sync).get_unique_constraints("operational_signals")
            }
        )

    assert "operational_signals" in table_names
    assert {
        "id",
        "dedup_key",
        "signal_type",
        "object_type",
        "object_id",
        "source",
        "severity",
        "reason_code",
        "facts_hash",
        "facts",
        "status",
        "operation_id",
        "predecessor_signal_id",
        "detected_at",
        "updated_at",
        "resolved_at",
    } <= columns
    assert "uq_operational_signals_dedup_key" in unique_constraints
    assert "uq_operational_signals_operation_id" in unique_constraints
    assert "uq_operational_signals_predecessor_signal_id" in unique_constraints


def test_signal_successor_migration_downgrades_and_reupgrades(
    migrated_database_url: SecretStr,
    monkeypatch: MonkeyPatch,
) -> None:
    parsed_url = make_url(migrated_database_url.get_secret_value())
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
        command.downgrade(config, "0007_operational_signals")
        assert "predecessor_signal_id" not in {
            column["name"] for column in inspect(engine).get_columns("operational_signals")
        }

        command.upgrade(config, "0008_signal_successor_lineage")
        assert "predecessor_signal_id" in {
            column["name"] for column in inspect(engine).get_columns("operational_signals")
        }

        command.downgrade(config, "0007_operational_signals")
        command.upgrade(config, "0008_signal_successor_lineage")
        assert "uq_operational_signals_predecessor_signal_id" in {
            item["name"] for item in inspect(engine).get_unique_constraints("operational_signals")
        }
    finally:
        command.upgrade(config, "head")
        engine.dispose()
