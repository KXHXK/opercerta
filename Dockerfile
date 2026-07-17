FROM python:3.12.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY migrations ./migrations
COPY data ./data
COPY alembic.ini ./

RUN groupadd --gid 10001 opercerta \
    && useradd --uid 10001 --gid 10001 --create-home opercerta

USER opercerta
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH=/app/src
