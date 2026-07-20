"""Measure one declared OperCerta performance cell without inventing unavailable data."""

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path
from statistics import median
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return ordered[index]


def request_json(url: str, method: str, payload: dict[str, Any]) -> tuple[int, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def metrics_text(api_url: str) -> str:
    with urlopen(f"{api_url}/metrics", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("metrics endpoint is unavailable")
        return response.read().decode("utf-8")


def metric_total(text: str, metric_name: str, label: str | None = None) -> float:
    total = 0.0
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(metric_name):
            continue
        if label is not None and label not in line:
            continue
        total += float(line.rsplit(" ", 1)[1])
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--scenario", choices=("inventory", "equipment", "task"), required=True)
    parser.add_argument("--cache-mode", choices=("enabled", "disabled"), required=True)
    parser.add_argument("--tool-mode", choices=("parallel", "sequential"), required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")

    account_status, account = request_json(
        f"{args.api_url}/api/v1/auth/demo-token",
        "POST",
        {"account": "operator"},
    )
    if account_status != 200:
        raise SystemExit("demo token endpoint is unavailable")
    token = account["access_token"]
    metrics_before = metrics_text(args.api_url)
    object_ids = {
        "inventory": "SKU-NORMAL-001",
        "equipment": "EQ-FAN-001",
        "task": "TASK-NORMAL-001",
    }
    durations: list[float] = []
    failures = 0
    completed_operations = 0
    for _ in range(args.repetitions):
        started = time.perf_counter()
        request = Request(
            f"{args.api_url}/api/v1/operations",
            data=json.dumps(
                {
                    "message": f"performance query {args.scenario}",
                    "requested_action": "query",
                    "object_type": args.scenario,
                    "object_id": object_ids[args.scenario],
                }
            ).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                body = json.loads(response.read())
                completed = response.status == 202 and body.get("status") == "completed"
                completed_operations += int(completed)
                failures += int(not completed)
        except (HTTPError, OSError):
            failures += 1
        durations.append((time.perf_counter() - started) * 1000)

    metrics_after = metrics_text(args.api_url)
    tool_calls = metric_total(metrics_after, "opercerta_mcp_tool_calls_total") - metric_total(
        metrics_before, "opercerta_mcp_tool_calls_total"
    )
    cache_hits = metric_total(
        metrics_after,
        "opercerta_cache_events_total",
        'outcome="hit"',
    ) - metric_total(
        metrics_before,
        "opercerta_cache_events_total",
        'outcome="hit"',
    )

    report = {
        "environment": {"platform": platform.platform(), "commit": git_commit()},
        "scenario": args.scenario,
        "cache_mode": args.cache_mode,
        "tool_mode": args.tool_mode,
        "repetitions": args.repetitions,
        "median_ms": round(median(durations), 3),
        "p50_ms": round(percentile(durations, 0.50), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "error_rate": failures / args.repetitions,
        "completed_operations": completed_operations,
        "tool_calls": int(tool_calls),
        "cache_hits": int(cache_hits),
        "model_usage": {
            "calls": 0,
            "tokens": 0,
            "reason": "query path does not call the model",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
