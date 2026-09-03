from __future__ import annotations

import logging

from app.services.access_log_privacy import (
    UvicornAccessLogPrivacyFilter,
    redact_request_target,
)


def test_request_target_redaction_removes_all_query_and_fragment_values() -> None:
    target = (
        "/api/v1/runs/run-1/events?token=secret-value&patient=张三"
        "#never-log-this"
    )

    assert redact_request_target(target) == "/api/v1/runs/run-1/events"


def test_request_target_redaction_hides_actor_bound_download_grant() -> None:
    target = (
        "/api/v2/agentic/artifact-objects/download/"
        "grant-12345678-1234-4abc-8def-1234567890ab?ignored=1"
    )

    assert redact_request_target(target).endswith("/download/[grant-redacted]")


def test_uvicorn_access_filter_rewrites_request_line_argument() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:10000",
            "GET",
            "/api/v2/agentic/artifact-objects/download/"
            "grant-12345678-1234-4abc-8def-1234567890ab?token=must-not-log",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert UvicornAccessLogPrivacyFilter().filter(record) is True
    rendered = record.getMessage()
    assert "must-not-log" not in rendered
    assert "12345678" not in rendered
    assert "/download/[grant-redacted]" in rendered
