import json

from opercerta.agent.trace_recorder import redact_trace_payload


def test_trace_redaction_removes_forbidden_keys_and_nested_secret_values() -> None:
    payload = {
        "summary": "已完成受控库存核验。",
        "authorization": "Bearer forbidden-token",
        "request": {
            "api_key": "forbidden-api-key",
            "prompt": "complete private prompt",
            "reasoning_content": "hidden chain of thought",
        },
        "tool": {
            "raw_body": "unfiltered tool response",
            "safe_summary": "库存低于补货点。",
        },
        "error": {
            "stack_trace": "Traceback: database password",
            "error_code": "knowledge_unavailable",
        },
    }

    redacted = redact_trace_payload(payload)
    serialized = json.dumps(redacted, ensure_ascii=False).lower()

    assert redacted["summary"] == "已完成受控库存核验。"
    assert redacted["tool"] == {"safe_summary": "库存低于补货点。"}
    assert redacted["error"] == {"error_code": "knowledge_unavailable"}
    for forbidden in (
        "authorization",
        "forbidden-token",
        "api_key",
        "forbidden-api-key",
        "complete private prompt",
        "reasoning_content",
        "hidden chain of thought",
        "raw_body",
        "unfiltered tool response",
        "stack_trace",
        "traceback",
        "password",
    ):
        assert forbidden not in serialized


def test_trace_redaction_bounds_depth_collection_size_and_text_length() -> None:
    payload = {
        "items": [{"safe": "x" * 2_000} for _ in range(100)],
        "deep": {"a": {"b": {"c": {"d": {"e": "too deep"}}}}},
    }

    redacted = redact_trace_payload(payload)

    assert len(redacted["items"]) == 50
    assert len(redacted["items"][0]["safe"]) == 1_000
    assert redacted["deep"] == {"a": {"b": {"c": "[truncated]"}}}
