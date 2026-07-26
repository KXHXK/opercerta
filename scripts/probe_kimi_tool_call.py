"""Probe an OpenAI-compatible Kimi endpoint without printing secrets or model text."""

import argparse
import asyncio
import json
import os
from time import monotonic
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from opercerta.domain.agent import ReadToolName
from opercerta.infrastructure.langchain_model_gateway import to_model_tool_name

DOMAIN_TOOL_NAME = ReadToolName.INVENTORY_SNAPSHOT
MODEL_TOOL_NAME = to_model_tool_name(DOMAIN_TOOL_NAME)


class ProbeReport(TypedDict):
    mode: str
    provider: str
    model: str
    planning_mode: str
    first_tool_name: str
    continuation_received: bool
    elapsed_ms: int


def build_dry_run_report() -> dict[str, object]:
    return {
        "mode": "dry_run",
        "network_called": False,
        "allowed_tools": ["inventory.get_snapshot"],
        "checks": ["tool_call", "json_arguments", "tool_result_continuation"],
    }


def safe_probe_result(
    *,
    provider: str,
    model: str,
    planning_mode: str,
    first_tool_name: str,
    continuation_received: bool,
    elapsed_ms: int,
) -> ProbeReport:
    return {
        "mode": "real",
        "provider": provider,
        "model": model,
        "planning_mode": planning_mode,
        "first_tool_name": first_tool_name,
        "continuation_received": continuation_received,
        "elapsed_ms": elapsed_ms,
    }


async def run_real_probe() -> ProbeReport:
    base_url = os.environ["OPERCERTA_MODEL_BASE_URL"]
    model_name = os.environ["OPERCERTA_MODEL_NAME"]
    api_key = SecretStr(os.environ["OPERCERTA_MODEL_API_KEY"])
    disable_thinking = os.environ.get("OPERCERTA_MODEL_THINKING_MODE", "disabled") == "disabled"
    extra_body = {"thinking": {"type": "disabled"}} if disable_thinking else None
    model = ChatOpenAI(
        base_url=base_url,
        model=model_name,
        api_key=api_key,
        timeout=20.0,
        max_retries=0,
        extra_body=extra_body,
    )
    tool = {
        "type": "function",
        "function": {
            "name": MODEL_TOOL_NAME,
            "description": "读取指定 SKU 的合成库存事实",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"],
                "additionalProperties": False,
            },
        },
    }
    bound = model.bind_tools([tool])
    messages = [
        SystemMessage(content="只调用提供的只读库存工具。不得提出写操作。"),
        HumanMessage(content="请核对 SKU-DEMO-001 的库存事实。"),
    ]
    started = monotonic()
    first = await bound.ainvoke(messages)
    if not isinstance(first, AIMessage) or len(first.tool_calls) != 1:
        raise ValueError("native_tool_call_missing")
    call = first.tool_calls[0]
    if call["name"] != MODEL_TOOL_NAME or call["args"] != {"sku": "SKU-DEMO-001"}:
        raise ValueError("native_tool_call_invalid")
    continuation = await bound.ainvoke(
        [
            *messages,
            first,
            ToolMessage(
                content=json.dumps(
                    {"sku": "SKU-DEMO-001", "available_quantity": 3},
                    separators=(",", ":"),
                ),
                tool_call_id=call["id"],
            ),
        ]
    )
    return safe_probe_result(
        provider="openai-compatible",
        model=model_name,
        planning_mode="native_tool_call",
        first_tool_name=DOMAIN_TOOL_NAME.value,
        continuation_received=isinstance(continuation, AIMessage),
        elapsed_ms=int((monotonic() - started) * 1_000),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--real", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(build_dry_run_report(), ensure_ascii=False, sort_keys=True))
        return 0
    try:
        report = asyncio.run(run_real_probe())
    except Exception:
        print(json.dumps({"mode": "real", "status": "failed", "error_code": "probe_failed"}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
