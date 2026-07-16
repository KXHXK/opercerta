from typing import Any, TypedDict
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import JsonValue, SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.infrastructure.checkpoints import checkpoint_dsn, open_checkpointer


class ProbeState(TypedDict):
    operation_id: str
    payload: dict[str, JsonValue]


def build_probe_graph(checkpointer: Any) -> Any:
    def finish(_: ProbeState) -> dict[str, object]:
        return {}

    builder = StateGraph(ProbeState)
    builder.add_node("finish", finish)
    builder.add_edge(START, "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)


def test_checkpoint_dsn_is_secret_and_targets_langgraph_schema() -> None:
    source = SecretStr("postgresql+psycopg://user:password@127.0.0.1:55432/database")

    result = checkpoint_dsn(source)

    assert str(result) == "**********"
    raw = result.get_secret_value()
    assert raw.startswith("postgresql://")
    assert "postgresql+psycopg" not in raw
    assert "password" not in raw
    assert ":password@" not in raw
    assert "?options=-c%20search_path%3Dlanggraph" in raw
    assert "+search_path" not in raw


@pytest.mark.asyncio
async def test_setup_creates_saver_tables_only_in_langgraph(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    assert isinstance(checkpoint_database_url, SecretStr)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_name IN ('checkpoint_migrations', 'checkpoints', "
                    "'checkpoint_blobs', 'checkpoint_writes')"
                )
            )
        ).all()

    assert {schema for schema, _ in rows} == {"langgraph"}
    assert {name for _, name in rows} == {
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    }


@pytest.mark.asyncio
async def test_plain_json_checkpoint_survives_new_saver_instance(
    checkpoint_database_url: SecretStr,
) -> None:
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async with open_checkpointer(checkpoint_database_url) as saver_a:
        graph_a = build_probe_graph(saver_a)
        await graph_a.ainvoke(
            {
                "operation_id": thread_id,
                "payload": {"items": [1, True, None]},
            },
            config=config,
        )

    async with open_checkpointer(checkpoint_database_url) as saver_b:
        graph_b = build_probe_graph(saver_b)
        snapshot = await graph_b.aget_state(config)

        assert snapshot.values["operation_id"] == thread_id
        assert snapshot.values["payload"] == {"items": [1, True, None]}
        await saver_b.adelete_thread(thread_id)


@pytest.mark.asyncio
async def test_missing_strict_serializer_setting_is_rejected(
    checkpoint_database_url: SecretStr,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGGRAPH_STRICT_MSGPACK", raising=False)

    with pytest.raises(
        RuntimeError,
        match="LANGGRAPH_STRICT_MSGPACK must be true",
    ):
        async with open_checkpointer(checkpoint_database_url):
            pass
