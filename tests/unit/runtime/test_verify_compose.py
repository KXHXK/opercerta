from scripts.verify_compose import api_request_timeout_seconds, decode_response_body


def test_compose_smoke_decodes_json_and_tolerates_empty_proxy_startup_response() -> None:
    assert decode_response_body(b'{"status":"ready"}') == {"status": "ready"}
    assert decode_response_body(b"") is None
    assert decode_response_body(b"Bad Gateway") is None


def test_compose_smoke_uses_bounded_configurable_api_timeout(monkeypatch) -> None:
    monkeypatch.delenv("OPERCERTA_API_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert api_request_timeout_seconds() == 10.0

    monkeypatch.setenv("OPERCERTA_API_REQUEST_TIMEOUT_SECONDS", "75")
    assert api_request_timeout_seconds() == 75.0

    monkeypatch.setenv("OPERCERTA_API_REQUEST_TIMEOUT_SECONDS", "999")
    assert api_request_timeout_seconds() == 600.0
