import json

import httpx
import pytest

from icoder_sdk import (
    RunEventRetentionError,
    RunEventStreamError,
    iCoDerClient,
    iCoDerConfig,
)


def _client(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.test", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_run_text_sends_versioned_documents_and_upstream_results():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"agent_id": "agent", "run_id": "run-1"})

    client = _client(handler)
    try:
        client.runs.run_text(
            "principal-diagnosis-review",
            "primary",
            purpose_of_use="treatment",
            documents=[{
                "document_id": "admission",
                "document_version": "v2",
                "normalization": "NFKC",
                "text": "ＡＢ",
            }],
            upstream_results=[{
                "agent_id": "diagnosis-extractor",
                "run_id": "upstream-run",
                "schema_ref": "icoder/DiagnosisExtractionOutput/v6",
                "attestation": "signed-upstream-result",
                "result": {"diagnoses": [{"icd10_cn_code": "I21.0"}]},
            }],
        )
    finally:
        client.close()

    assert captured["input"]["documents"][0]["document_version"] == "v2"
    assert captured["input"]["upstream_results"][0]["agent_id"] == "diagnosis-extractor"
    assert captured["input"]["upstream_results"][0]["attestation"] == "signed-upstream-result"
    assert captured["purpose_of_use"] == "treatment"


def test_run_status_cancel_and_signed_event_stream_contracts():
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.raw_path.decode().split("?", 1)[0]
        if path.endswith("/events"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                content=(
                    b'data: {"name":"run.provider","payload":{},"meta":{}}\n\n'
                    b': keepalive\n\n'
                    b'data: {"name":"run.completion","payload":{},"meta":{}}\n\n'
                    b'data: {"name":"stream.completed","payload":{},"meta":{}}\n\n'
                ),
            )
        if path.endswith("/cancel"):
            assert json.loads(request.content) == {"reason": "operator request"}
            return httpx.Response(202, json={
                "run_id": "run/id",
                "outcome": "RECORDED_ONLY",
                "status": "RUNNING",
                "message": "request recorded",
            })
        return httpx.Response(200, json={
            "run_id": "run/id",
            "status": "RUNNING",
            "terminal": False,
            "agent_id": "note-completeness-agent",
            "trace_id": "trace-1",
            "runtime_mode": "default",
            "latency_ms": 12,
            "cost_amount": 0.01,
            "cost_currency": "CNY",
            "error": False,
        })

    client = _client(handler)
    try:
        status = client.runs.get("run/id")
        cancellation = client.runs.cancel("run/id", "operator request")
        events = list(client.runs.stream_events(
            "run/id", "signed token+value", last_event_id="event-previous"
        ))
    finally:
        client.close()

    assert status["terminal"] is False
    assert cancellation["outcome"] == "RECORDED_ONLY"
    assert [event["name"] for event in events] == [
        "run.provider", "run.completion", "stream.completed"
    ]
    assert calls[0].url.raw_path.decode() == "/api/v1/runs/run%2Fid"
    assert calls[1].url.raw_path.decode() == "/api/v1/runs/run%2Fid/cancel"
    assert calls[2].url.params["token"] == "signed token+value"
    assert calls[2].headers["Accept"] == "text/event-stream"
    assert calls[2].headers["Last-Event-ID"] == "event-previous"


def test_run_event_stream_errors_are_sanitized():
    client = _client(lambda request: httpx.Response(401, json={"secret": "details"}))
    try:
        with pytest.raises(RunEventStreamError) as captured:
            list(client.runs.stream_events("run-1", "signed-secret-token"))
    finally:
        client.close()
    assert captured.value.http_status == 401
    assert "signed-secret-token" not in str(captured.value)

    client = _client(lambda request: httpx.Response(200, json={"not": "sse"}))
    try:
        with pytest.raises(RunEventStreamError):
            list(client.runs.stream_events("run-1", "token"))
        with pytest.raises(ValueError, match="trace_token is required"):
            list(client.runs.stream_events("run-1", ""))
        with pytest.raises(ValueError, match="last_event_id is malformed"):
            list(client.runs.stream_events(
                "run-1", "token", last_event_id="x" * 129
            ))
    finally:
        client.close()


def test_resilient_stream_reconnects_from_last_event_id():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"name":"run.ingest","payload":{},'
                    b'"meta":{"event_id":"event-1"}}\n\n'
                ),
            )
        assert request.headers["Last-Event-ID"] == "event-1"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"name":"run.completion","payload":{},'
                b'"meta":{"event_id":"event-2"}}\n\n'
                b'data: {"name":"stream.completed","payload":{},"meta":{}}\n\n'
            ),
        )

    client = _client(handler)
    try:
        events = list(client.runs.stream_events_resilient(
            "run-1",
            "trace-token",
            max_attempts=3,
            initial_delay=0,
            max_delay=0,
            jitter_ratio=0,
        ))
    finally:
        client.close()
    assert [event["name"] for event in events] == [
        "run.ingest", "run.completion", "stream.completed"
    ]
    assert len(calls) == 2


def test_resilient_stream_renews_only_on_401():
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.raw_path.decode().split("?", 1)[0]
        if path.endswith("/trace-token"):
            return httpx.Response(200, json={
                "run_id": "run-1",
                "trace_token": "renewed-token",
                "expires_at": 9999999999,
                "events_url": "/api/v1/runs/run-1/events",
                "trace_url": "/api/v1/runs/run-1/trace",
            })
        if request.url.params["token"] == "expired-token":
            return httpx.Response(401)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"name":"stream.completed","payload":{},"meta":{}}\n\n',
        )

    client = _client(handler)
    try:
        events = list(client.runs.stream_events_resilient(
            "run-1",
            "expired-token",
            max_attempts=2,
            initial_delay=0,
            max_delay=0,
            jitter_ratio=0,
        ))
    finally:
        client.close()
    assert events[-1]["name"] == "stream.completed"
    assert [request.url.raw_path.decode().split("?", 1)[0] for request in calls] == [
        "/api/v1/runs/run-1/events",
        "/api/v1/runs/run-1/trace-token",
        "/api/v1/runs/run-1/events",
    ]
    assert calls[-1].url.params["token"] == "renewed-token"


def test_resilient_stream_does_not_retry_cursor_errors():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(409)

    client = _client(handler)
    try:
        with pytest.raises(RunEventStreamError) as captured:
            list(client.runs.stream_events_resilient(
                "run-1", "token", max_attempts=4,
                initial_delay=0, max_delay=0,
            ))
    finally:
        client.close()
    assert captured.value.http_status == 409
    assert calls == 1


def test_resilient_stream_exposes_sanitized_retention_expiry_without_retry():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(410, json={
            "detail": {
                "code": "SSE_CURSOR_EXPIRED",
                "retention_days": 90,
                "message": "must not be retained by the SDK",
                "raw_clinical_text": "must not escape",
            },
        })

    client = _client(handler)
    try:
        with pytest.raises(RunEventRetentionError) as captured:
            list(client.runs.stream_events_resilient(
                "run-1", "token", max_attempts=4,
                initial_delay=0, max_delay=0,
            ))
    finally:
        client.close()
    assert captured.value.http_status == 410
    assert captured.value.error_code == "SSE_CURSOR_EXPIRED"
    assert captured.value.retention_days == 90
    assert "raw_clinical_text" not in str(captured.value)
    assert calls == 1


def test_stream_reads_bounded_unbuffered_error_body_before_safe_parsing():
    payload = json.dumps({
        "detail": {
            "code": "SSE_TRACE_EXPIRED",
            "retention_days": 90,
            "raw_clinical_text": "must not escape",
        },
    }).encode()

    def handler(request):
        return httpx.Response(
            410,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(payload),
        )

    client = _client(handler)
    try:
        with pytest.raises(RunEventRetentionError) as captured:
            list(client.runs.stream_events("run-1", "token"))
    finally:
        client.close()

    assert captured.value.error_code == "SSE_TRACE_EXPIRED"
    assert captured.value.retention_days == 90
    assert "raw_clinical_text" not in str(captured.value)
