#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export COMPOSE_FILE=compose.release.yaml
export OPERCERTA_HTTP_PORT="${OPERCERTA_HTTP_PORT:-18080}"
export OPERCERTA_HTTPS_PORT="${OPERCERTA_HTTPS_PORT:-18443}"
export OPERCERTA_PUBLIC_ADDRESS="${OPERCERTA_PUBLIC_ADDRESS:-http://localhost}"
export OPERCERTA_API_URL="http://localhost:${OPERCERTA_HTTP_PORT}"

cleanup() {
  status=$?
  if [[ "$status" -ne 0 ]]; then
    docker compose ps || true
    docker compose logs --no-color --tail=40 caddy api || true
    curl --silent --show-error --include "${OPERCERTA_API_URL}/health/ready" || true
  fi
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

docker compose up --build -d
python3 -c "from scripts.verify_compose import wait_for_ready; wait_for_ready(60)"

curl --fail --silent --show-error "${OPERCERTA_API_URL}/" | grep --quiet "OperCerta"
python3 scripts/verify_compose.py
docker compose restart api mcp
python3 scripts/verify_compose.py --recovery-only

metrics_content_type="$(curl --fail --silent --show-error --head "${OPERCERTA_API_URL}/metrics" | tr -d '\r' | grep -i '^Content-Type:')"
[[ "$metrics_content_type" == *"text/html"* ]]
docker compose ps
