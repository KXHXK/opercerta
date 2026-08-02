#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.local ]]; then
  echo ".env.local is required" >&2
  exit 2
fi

while IFS='=' read -r key value; do
  value="${value%$'\r'}"
  case "$key" in
    OPERCERTA_MODEL_MODE|OPERCERTA_MODEL_BASE_URL|OPERCERTA_MODEL_NAME|OPERCERTA_MODEL_API_KEY|OPERCERTA_MODEL_THINKING_MODE|OPERCERTA_MODEL_TIMEOUT_SECONDS)
      export "$key=$value"
      ;;
  esac
done < .env.local

for name in OPERCERTA_MODEL_BASE_URL OPERCERTA_MODEL_NAME OPERCERTA_MODEL_API_KEY; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name is required" >&2
    exit 2
  fi
done
if [[ "${OPERCERTA_MODEL_MODE:-}" != "real" ]]; then
  echo "OPERCERTA_MODEL_MODE must be real" >&2
  exit 2
fi

export COMPOSE_FILE=compose.release.yaml
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-opercerta-real-model-eval}"
export OPERCERTA_HTTP_PORT="${OPERCERTA_HTTP_PORT:-18082}"
export OPERCERTA_HTTPS_PORT="${OPERCERTA_HTTPS_PORT:-18445}"
export OPERCERTA_PUBLIC_ADDRESS="${OPERCERTA_PUBLIC_ADDRESS:-http://localhost}"
export OPERCERTA_API_URL="http://localhost:${OPERCERTA_HTTP_PORT}"
export OPERCERTA_MCP_TIMEOUT_SECONDS="${OPERCERTA_REAL_MODEL_MCP_TIMEOUT_SECONDS:-30}"
export OPERCERTA_API_REQUEST_TIMEOUT_SECONDS="${OPERCERTA_REAL_MODEL_API_TIMEOUT_SECONDS:-120}"
export OPERCERTA_MODEL_TIMEOUT_SECONDS="${OPERCERTA_MODEL_TIMEOUT_SECONDS:-90}"
export OPERCERTA_MODEL_THINKING_MODE="${OPERCERTA_MODEL_THINKING_MODE:-disabled}"

output="${1:-tmp/evals/opercerta-real-model-v1-report.json}"
case_id="${2:-}"

if command -v uv >/dev/null 2>&1; then
  PYTHON_RUNNER=(uv run --frozen --no-sync python)
else
  PYTHON_RUNNER=(python3)
fi

cleanup() {
  status=$?
  if [[ "$status" -ne 0 ]]; then
    docker compose ps || true
    docker compose logs --no-color --tail=40 api mcp caddy || true
  fi
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

if [[ "${OPERCERTA_EVAL_SKIP_BUILD:-false}" == "true" ]]; then
  docker compose up --no-build -d
else
  docker compose up --build -d
fi
"${PYTHON_RUNNER[@]}" -c "from scripts.verify_compose import wait_for_ready; wait_for_ready(90)"
evaluation_args=(--output "$output")
if [[ -n "$case_id" ]]; then
  evaluation_args+=(--case-id "$case_id")
fi
"${PYTHON_RUNNER[@]}" -m scripts.run_real_model_quality_evaluation "${evaluation_args[@]}"
