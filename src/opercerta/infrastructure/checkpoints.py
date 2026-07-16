import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def checkpoint_dsn(database_url: SecretStr) -> SecretStr:
    parsed = make_url(database_url.get_secret_value())
    query = dict(parsed.query)
    query["options"] = "-c search_path=langgraph"
    passwordless = URL.create(
        drivername="postgresql",
        username=parsed.username,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
    ).render_as_string(hide_password=False)
    encoded_query = urlencode(query, doseq=True, quote_via=quote)
    return SecretStr(f"{passwordless}?{encoded_query}")


@asynccontextmanager
async def open_checkpointer(
    database_url: SecretStr,
    *,
    setup: bool = False,
) -> AsyncIterator["AsyncPostgresSaver"]:
    if os.environ.get("LANGGRAPH_STRICT_MSGPACK", "").lower() != "true":
        raise RuntimeError("LANGGRAPH_STRICT_MSGPACK must be true before checkpointer import")

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    parsed = make_url(database_url.get_secret_value())
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed.password is not None:
        os.environ["PGPASSWORD"] = parsed.password
    try:
        dsn = checkpoint_dsn(database_url)
        async with AsyncPostgresSaver.from_conn_string(dsn.get_secret_value()) as saver:
            if setup:
                await saver.setup()
            yield saver
    finally:
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword
