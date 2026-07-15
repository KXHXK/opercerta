import os
from pathlib import Path

import pytest
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[2]


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
