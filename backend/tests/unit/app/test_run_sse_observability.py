from __future__ import annotations

import json

from app.services.run_sse_observability import RunSSEMetrics


def test_metrics_are_bounded_low_cardinality_and_evaluate_alerts():
    metrics = RunSSEMetrics(sample_limit=10)

    for index in range(20):
        metrics.connection_attempted()
        metrics.stream_started(resumed=True, recovery_seconds=3.0 + index / 100)
        metrics.event_emitted(2)
        metrics.stream_closed(
            reason="client_disconnected" if index < 3 else "terminal",
            duration_seconds=0.5 + index / 100,
        )
        metrics.token_renewed("audit_failed" if index < 2 else "success")

    metrics.rejected("patient-id-must-never-become-a-label")
    snapshot = metrics.snapshot()

    assert snapshot["scope"] == "single_api_process"
    assert snapshot["active_connections"] == 0
    assert snapshot["events_emitted_total"] == 40
    assert snapshot["rejections_by_reason"] == {"other": 1}
    assert snapshot["resume_recovery_seconds"]["observations_total"] == 20
    assert snapshot["resume_recovery_seconds"]["window_samples"] == 10
    states = {item["code"]: item["state"] for item in snapshot["alert_evaluation"]}
    assert states == {
        "SSE_UNEXPECTED_CLOSE_RATIO_HIGH": "firing",
        "SSE_TOKEN_RENEW_FAILURE_RATIO_HIGH": "firing",
        "SSE_RESUME_RECOVERY_P95_HIGH": "firing",
    }
    assert "patient-id-must-never-become-a-label" not in json.dumps(snapshot)


def test_unknown_close_and_renewal_outcomes_collapse_to_other():
    metrics = RunSSEMetrics()
    metrics.stream_started(resumed=False, recovery_seconds=None)
    metrics.stream_closed(reason="run-123", duration_seconds=0.1)
    metrics.token_renewed("tenant-123")

    snapshot = metrics.snapshot()
    assert snapshot["stream_closes_by_reason"] == {"other": 1}
    assert snapshot["token_renewals_by_outcome"] == {"other_failure": 1}
