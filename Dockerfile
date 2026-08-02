FROM python:3.12.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --offline

COPY migrations ./migrations
COPY data ./data
COPY scripts ./scripts
COPY alembic.ini ./

RUN groupadd --gid 10001 opercerta \
    && useradd --uid 10001 --gid 10001 --create-home opercerta \
    && install -d -o opercerta -g opercerta /home/opercerta/.cache \
    && install -d -o opercerta -g opercerta /home/opercerta/.cache/fastembed

USER opercerta
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH=/app/src
