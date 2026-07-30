#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

print_compose_diagnostics() {
  local status="$?"
  if [[ "${status}" -eq 0 ]]; then
    return
  fi

  printf '\n[%s] Runtime bootstrap failed; collecting Compose diagnostics\n' "$(date '+%H:%M:%S')" >&2
  docker compose ps >&2 || true
  docker compose logs --no-color --tail=200 postgres bootstrap mcp api 2>&1 \
    | sed -E \
        -e 's#(postgresql[^:[:space:]]*://[^:[:space:]]+:)[^@[:space:]]+@#\1***@#g' \
        -e 's#(OPERCERTA_MODEL_API_KEY=)[^[:space:]]+#\1***#Ig' >&2 \
    || true
  exit "${status}"
}

trap print_compose_diagnostics ERR

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${project_root}"

[[ "$(uname -s)" == "Linux" ]] || fail "This script must run inside Ubuntu WSL2."
grep -qi microsoft /proc/sys/kernel/osrelease || fail "A WSL2 kernel was not detected."
command -v docker >/dev/null || fail "Docker is missing. Run bootstrap_wsl_environment.sh first."
docker info >/dev/null || fail "Docker is unavailable to this user. Reopen Ubuntu after joining the docker group."
command -v python3 >/dev/null || fail "The Ubuntu python3 command is required for smoke verification."

if ! git config --global --get-all safe.directory 2>/dev/null | grep -Fxq "${project_root}"; then
  log "Trusting only this Windows-owned repository path for WSL Git"
  git config --global --add safe.directory "${project_root}"
fi

if [[ ! -f .env.compose ]]; then
  log "Generating ignored local-only Compose credentials"
  umask 077
  db_password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  jwt_signing_key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat >.env.compose <<EOF
POSTGRES_USER=opercerta
POSTGRES_PASSWORD=${db_password}
POSTGRES_DB=opercerta
OPERCERTA_DATABASE_URL=postgresql+psycopg://opercerta:${db_password}@postgres:5432/opercerta
OPERCERTA_MCP_URL=http://mcp:8001/mcp
OPERCERTA_MCP_TIMEOUT_SECONDS=2
OPERCERTA_APPROVAL_TTL_SECONDS=300
OPERCERTA_MODEL_MODE=mock
OPERCERTA_REDIS_URL=redis://redis:6379/0
OPERCERTA_CACHE_ENABLED=true
OPERCERTA_CACHE_TTL_SECONDS=60
OPERCERTA_MODEL_BASE_URL=https://api.openai.com/v1
OPERCERTA_MODEL_NAME=mock
OPERCERTA_MODEL_API_KEY=not-used-in-mock-mode
OPERCERTA_MODEL_THINKING_MODE=default
OPERCERTA_MODEL_TIMEOUT_SECONDS=90
OPERCERTA_OTLP_ENABLED=false
OPERCERTA_KNOWLEDGE_ENABLED=true
OPERCERTA_KNOWLEDGE_REQUIRED=false
OPERCERTA_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
OPERCERTA_JWT_SIGNING_KEY=${jwt_signing_key}
OPERCERTA_JWT_ISSUER=opercerta-local-demo
OPERCERTA_JWT_AUDIENCE=opercerta-api
OPERCERTA_JWT_TTL_SECONDS=300
OPERCERTA_DEMO_TOKEN_ENABLED=true
OPERCERTA_METRICS_ENABLED=false
LANGGRAPH_STRICT_MSGPACK=true
PORT=8080
MCP_PORT=8001
OPERCERTA_API_BIND=127.0.0.1
EOF
  if ! chmod 600 .env.compose 2>/dev/null; then
    log "NTFS DrvFs does not expose POSIX chmod; relying on Windows ACLs and Git ignore"
  fi
else
  log "Preserving existing ignored .env.compose"
fi

grep -Eq '(^|=)CHANGE_ME' .env.compose && \
  fail ".env.compose still contains a CHANGE_ME placeholder."
git check-ignore -q .env.compose || fail ".env.compose is not ignored by Git."

log "Validating the resolved Compose configuration"
docker compose config --quiet

log "Building and starting PostgreSQL/pgvector, Redis, bootstrap, MCP, and FastAPI"
docker compose up --build -d --wait --wait-timeout 900

log "Running the complete three-business Agent Compose verification"
python3 scripts/verify_agent_compose.py

log "Restarting API and MCP, then proving persisted recovery"
docker compose restart api mcp
docker compose up -d --wait --wait-timeout 300
python3 scripts/verify_agent_compose.py --recovery-only

log "Final service state"
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
printf '\n\nOperCerta local Compose runtime verification completed.\n'
