from opercerta.observability.metrics import ApiMetrics


def test_metrics_use_isolated_registry_and_low_cardinality_labels() -> None:
    secret_operation_id = "2b971f65-1844-4f58-acbc-acdeef012345"
    metrics_a = ApiMetrics.create()
    metrics_b = ApiMetrics.create()

    metrics_a.observe_http(
        "GET",
        f"/api/v1/operations/{secret_operation_id}",
        404,
        0.125,
    )
    metrics_a.count_audit_event("unknown-user-controlled-event")

    rendered_a = metrics_a.render().decode()
    rendered_b = metrics_b.render().decode()

    assert 'route="unmatched"' in rendered_a
    assert 'event_type="other"' in rendered_a
    assert secret_operation_id not in rendered_a
    assert "unknown-user-controlled-event" not in rendered_a
    assert 'route="unmatched"' not in rendered_b
