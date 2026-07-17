from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.tools.catalog import SyntheticCatalog
from opercerta.tools.server import build_mcp_server


def create_mcp_app(
    catalog: SyntheticCatalog,
    engine: AsyncEngine,
    clock: Callable[[], datetime],
    *,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    mcp_app = build_mcp_server(catalog, engine, clock).streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        try:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        finally:
            if on_shutdown is not None:
                await on_shutdown()

    app = FastAPI(title="OperCerta MCP", lifespan=lifespan)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready"},
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})

    app.mount("/", mcp_app)
    return app
