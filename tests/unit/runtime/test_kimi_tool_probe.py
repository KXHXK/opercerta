import json
import sys

from scripts import probe_kimi_tool_call
from scripts.probe_kimi_tool_call import (
    MODEL_TOOL_NAME,
    build_dry_run_report,
    main,
    safe_probe_result,
)


def test_dry_run_report_declares_checks_without_network_or_secrets() -> None:
    report = build_dry_run_report()
    serialized = json.dumps(report, ensure_ascii=False)

    assert report["mode"] == "dry_run"
    assert report["network_called"] is False
    assert report["allowed_tools"] == ["inventory.get_snapshot"]
    assert "tool_call" in report["checks"]
    assert "tool_result_continuation" in report["checks"]
    assert "api_key" not in serialized
    assert "authorization" not in serialized.lower()
    assert "prompt" not in serialized.lower()


def test_probe_uses_provider_safe_wire_name_but_reports_domain_tool_id() -> None:
    assert MODEL_TOOL_NAME == "inventory_get_snapshot"
    assert build_dry_run_report()["allowed_tools"] == ["inventory.get_snapshot"]


def test_safe_real_probe_summary_excludes_raw_model_content() -> None:
    report = safe_probe_result(
        provider="moonshot-compatible",
        model="configured-model",
        planning_mode="native_tool_call",
        first_tool_name="inventory.get_snapshot",
        continuation_received=True,
        elapsed_ms=125,
    )

    assert report == {
        "mode": "real",
        "provider": "moonshot-compatible",
        "model": "configured-model",
        "planning_mode": "native_tool_call",
        "first_tool_name": "inventory.get_snapshot",
        "continuation_received": True,
        "elapsed_ms": 125,
    }


def test_missing_real_configuration_fails_without_traceback_or_secret(
    monkeypatch,
    capsys,
) -> None:
    for name in (
        "OPERCERTA_MODEL_BASE_URL",
        "OPERCERTA_MODEL_NAME",
        "OPERCERTA_MODEL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["probe_kimi_tool_call.py", "--real"])

    assert main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "mode": "real",
        "status": "failed",
        "error_code": "probe_failed",
    }


def test_provider_exception_is_reduced_to_safe_error(
    monkeypatch,
    capsys,
) -> None:
    async def fail() -> dict[str, object]:
        raise OSError("sensitive-provider-detail")

    monkeypatch.setattr(probe_kimi_tool_call, "run_real_probe", fail)
    monkeypatch.setattr(sys, "argv", ["probe_kimi_tool_call.py", "--real"])

    assert main() == 1
    output = capsys.readouterr().out
    assert "sensitive-provider-detail" not in output
    assert json.loads(output)["error_code"] == "probe_failed"
