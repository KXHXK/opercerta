import asyncio
import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _database_url() -> SecretStr:
    configured = os.getenv("OPERCERTA_DATABASE_URL")
    if configured:
        return SecretStr(configured)

    local_env = ROOT / ".env.local"
    if local_env.is_file():
        for raw_line in local_env.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = raw_line.partition("=")
            if name == "OPERCERTA_DATABASE_URL" and separator and value:
                return SecretStr(value)

    pytest.fail("OPERCERTA_DATABASE_URL is not configured for integration tests")


@pytest.fixture(scope="session")
def database_url() -> SecretStr:
    return _database_url()


@pytest.fixture(scope="session")
def migrated_database_url(database_url: SecretStr) -> SecretStr:
    parsed_url = make_url(database_url.get_secret_value())
    password = SecretStr(parsed_url.password) if parsed_url.password else None
    passwordless_url = parsed_url.set(password=None).render_as_string(hide_password=False)
    original_database_url = os.environ.get("OPERCERTA_DATABASE_URL")
    original_pgpassword = os.environ.get("PGPASSWORD")
    os.environ["OPERCERTA_DATABASE_URL"] = passwordless_url
    if password is not None:
        os.environ["PGPASSWORD"] = password.get_secret_value()
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        if original_database_url is None:
            os.environ.pop("OPERCERTA_DATABASE_URL", None)
        else:
            os.environ["OPERCERTA_DATABASE_URL"] = original_database_url
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword
    return database_url
