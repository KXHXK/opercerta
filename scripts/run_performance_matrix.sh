#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

output_dir="${1:-tmp/performance}"
repetitions="${OPERCERTA_PERFORMANCE_REPETITIONS:-5}"
cache_modes="${OPERCERTA_PERFORMANCE_CACHE_MODES:-disabled enabled}"
tool_modes="${OPERCERTA_PERFORMANCE_TOOL_MODES:-parallel sequential}"
scenarios="${OPERCERTA_PERFORMANCE_SCENARIOS:-inventory equipment task}"

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

export OPERCERTA_METRICS_ENABLED=true
export OPERCERTA_CACHE_ENABLED=false
export OPERCERTA_TOOL_MODE=parallel

docker compose up --build -d >/dev/null
python3 -c "from scripts.verify_compose import wait_for_ready; wait_for_ready()"
mkdir -p "$output_dir"

for cache_mode in $cache_modes; do
  if [[ "$cache_mode" == "enabled" ]]; then
    export OPERCERTA_CACHE_ENABLED=true
  else
    export OPERCERTA_CACHE_ENABLED=false
  fi

  for tool_mode in $tool_modes; do
    export OPERCERTA_TOOL_MODE="$tool_mode"
    docker compose up -d --force-recreate api >/dev/null
    python3 -c "from scripts.verify_compose import wait_for_ready; wait_for_ready()"
    docker compose exec -T redis redis-cli FLUSHDB >/dev/null

    for scenario in $scenarios; do
      python3 scripts/run_performance_matrix.py \
        --scenario "$scenario" \
        --cache-mode "$cache_mode" \
        --tool-mode "$tool_mode" \
        --repetitions "$repetitions" \
        --output "$output_dir/$cache_mode-$tool_mode-$scenario.json"
      if [[ "${OPERCERTA_PERFORMANCE_CAPTURE_METRICS:-false}" == "true" ]]; then
        curl --fail --silent http://127.0.0.1:8080/metrics \
          >"$output_dir/$cache_mode-$tool_mode-$scenario.prom"
      fi
    done
  done
done
