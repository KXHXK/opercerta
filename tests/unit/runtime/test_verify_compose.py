from scripts.verify_compose import decode_response_body


def test_compose_smoke_decodes_json_and_tolerates_empty_proxy_startup_response() -> None:
    assert decode_response_body(b'{"status":"ready"}') == {"status": "ready"}
    assert decode_response_body(b"") is None
    assert decode_response_body(b"Bad Gateway") is None
