import asyncio
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
import uvicorn
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.tools.catalog import SyntheticCatalog
from opercerta.tools.server import build_mcp_server

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


class FixedTestEmbeddingGateway:
    model_id = "fixed-test-embedding-v1"
    dimension = 512

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        vector = (1.0,) + (0.0,) * 511
        return tuple(vector for _ in texts)


@dataclass(frozen=True, slots=True)
class McpServerHarness:
    url: str
    catalog: SyntheticCatalog


def unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def wait_until_listening(port: int) -> None:
    for _ in range(100):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.02)
            continue
        writer.close()
        await writer.wait_closed()
        del reader
        return
    raise TimeoutError(f"MCP test server did not listen on port {port}")


@pytest_asyncio.fixture
async def mcp_server(engine: AsyncEngine) -> AsyncIterator[McpServerHarness]:
    catalog = SyntheticCatalog.load(
        ROOT / "data" / "synthetic" / "inventory.json",
        ROOT / "data" / "synthetic" / "replenishment_policies.json",
        equipment_path=ROOT / "data" / "synthetic" / "equipment.json",
        maintenance_policy_path=ROOT / "data" / "synthetic" / "maintenance_policies.json",
        task_path=ROOT / "data" / "synthetic" / "tasks.json",
        task_recovery_policy_path=ROOT / "data" / "synthetic" / "task_recovery_policies.json",
    )
    port = unused_loopback_port()
    mcp = build_mcp_server(
        catalog,
        engine,
        lambda: NOW,
        embedding_gateway=FixedTestEmbeddingGateway(),
        host="127.0.0.1",
        port=port,
    )
    config = uvicorn.Config(
        mcp.streamable_http_app(),
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        await wait_until_listening(port)
        yield McpServerHarness(
            url=f"http://127.0.0.1:{port}/mcp",
            catalog=catalog,
        )
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
