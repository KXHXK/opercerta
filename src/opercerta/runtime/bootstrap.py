import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from opercerta.infrastructure.checkpoints import open_checkpointer

ROOT = Path(__file__).resolve().parents[3]


class BootstrapSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    database_url: SecretStr = Field(validation_alias="OPERCERTA_DATABASE_URL")


def upgrade_database() -> None:
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


async def setup_checkpointer(database_url: SecretStr) -> None:
    async with open_checkpointer(database_url, setup=True):
        pass


def main(settings: BootstrapSettings | None = None) -> None:
    active_settings = settings or BootstrapSettings()
    upgrade_database()
    asyncio.run(setup_checkpointer(active_settings.database_url))


if __name__ == "__main__":
    main()
