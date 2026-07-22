from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def test_agent_knowledge_migration_upgrades_downgrades_and_reupgrades(
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
        command.downgrade(config, "0004_approval_cycles")
        command.upgrade(config, "0005_agent_knowledge")

        inspector = inspect(engine)
        assert {"knowledge_documents", "knowledge_chunks"} <= set(
            inspector.get_table_names(schema="public")
        )
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("knowledge_documents")
        } == {"uq_knowledge_documents_scenario_slug_version"}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("knowledge_chunks")
        } == {
            "uq_knowledge_chunks_document_index",
            "uq_knowledge_chunks_document_content_hash",
        }
        with engine.connect() as connection:
            extension_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
            embedding_type = connection.execute(
                text(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    WHERE c.relname = 'knowledge_chunks'
                      AND a.attname = 'embedding'
                    """
                )
            ).scalar_one()
        assert extension_version
        assert embedding_type == "vector(512)"

        command.downgrade(config, "0004_approval_cycles")
        downgraded = inspect(engine)
        assert "knowledge_documents" not in downgraded.get_table_names(schema="public")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                ).scalar_one()
                == 0
            )

        command.upgrade(config, "0005_agent_knowledge")
        assert {"knowledge_documents", "knowledge_chunks"} <= set(
            inspect(engine).get_table_names(schema="public")
        )
    finally:
        command.upgrade(config, "head")
        engine.dispose()
