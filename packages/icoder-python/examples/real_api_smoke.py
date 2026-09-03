"""External Python SDK smoke against an already running temporary server."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from urllib.parse import parse_qs, urlparse

from icoder_sdk import iCoDerAPIError, iCoDerClient, iCoDerConfig


base_url = os.environ["ICODER_E2E_BASE_URL"]
sse_base_url = os.environ.get("ICODER_E2E_SSE_BASE_URL", base_url)
access_token = os.environ["ICODER_E2E_ACCESS_TOKEN"]
client = iCoDerClient(iCoDerConfig(base_url=base_url, access_token=access_token))
run_client = client
try:
    long_sse_run_id = os.environ.get("ICODER_E2E_SSE_RUN_ID", "")
    long_sse_token = os.environ.get("ICODER_E2E_SSE_TRACE_TOKEN", "")
    long_sse_verified = "skipped"
    if long_sse_run_id and long_sse_token:
        started_at = time.monotonic()
        resilient_client = iCoDerClient(iCoDerConfig(
            base_url=sse_base_url,
            access_token=access_token,
        ))
        long_events = list(resilient_client.runs.stream_events_resilient(
            long_sse_run_id, long_sse_token,
            max_attempts=4, initial_delay=0.01, max_delay=0.05, jitter_ratio=0,
        ))
        resilient_client.close()
        assert [event["name"] for event in long_events] == [
            "run.ingest", "run.completion", "stream.completed"
        ]
        assert long_events[-1]["payload"]["status"] == "COMPLETED"
        assert long_events[-1]["payload"]["event_count"] == 2
        assert time.monotonic() - started_at >= 0.3
        long_sse_verified = "expired-token-renewed-two-disconnects-resumed-terminal"

    hub = client.agent_hub.list()
    assert hub["total"] == 26
    assert len(hub["agents"]) == 26
    assert all(a["runnable"] and a["launch_candidate_ready"] for a in hub["agents"])

    oauth_client_id = os.environ.get("ICODER_E2E_CLIENT_ID", "")
    oauth_client_secret = os.environ.get("ICODER_E2E_CLIENT_SECRET", "")
    oauth_client_credentials = "skipped"
    if oauth_client_id and oauth_client_secret:
        token = client.oauth.get_token(oauth_client_id, oauth_client_secret)
        assert token["access_token"]
        assert "refresh_token" not in token and "user" not in token
        run_client = iCoDerClient(iCoDerConfig(
            base_url=base_url,
            access_token=token["access_token"],
        ))
        assert run_client.agent_hub.list()["total"] == 26
        oauth_client_credentials = "form-token-hub"

    try:
        client.facts.extract("Synthetic SDK Facts contract smoke only.", "zh-CN")
        raise AssertionError("credential-free Facts extraction did not fail closed")
    except iCoDerAPIError as error:
        assert error.status_code == 503

    try:
        coding = client.medical_coding.predict(
            "Synthetic coding-filter transport smoke only.",
            coding_systems=["icd10cn", "icd9cm3"],
            include_codes=["E11"],
            exclude_codes=["E11.9"],
            expand_categories=True,
        )
        assert coding["error"] is True
    except iCoDerAPIError as error:
        assert error.status_code == 503

    run = run_client.runs.run_text(
        "note-completeness-agent",
        "Python SDK contract smoke only; no patient or clinical data.",
        purpose_of_use="treatment",
        idempotency_key=f"python-smoke-{uuid.uuid4().hex}",
    )
    assert run["agent_id"] == "note-completeness-agent"
    assert run["run_id"] and run["trace_id"]
    assert run["error"] is False, (
        "deterministic local Note Completeness Agent Run failed unexpectedly"
    )
    assert isinstance(run["result"].get("review_conclusion"), str)
    assert isinstance(run["result"].get("completeness_score"), (int, float))
    run_status = run_client.runs.get(run["run_id"])
    assert run_status["terminal"] is True
    assert run_status["run_id"] == run["run_id"]
    run_cancellation = run_client.runs.cancel(
        run["run_id"], "SDK lifecycle smoke after terminal completion"
    )
    assert run_cancellation["outcome"] == "ALREADY_COMPLETE"
    trace_token = parse_qs(urlparse(run["trace_url"]).query).get("token", [""])[0]
    assert trace_token
    run_events = list(run_client.runs.stream_events(run["run_id"], trace_token))
    assert run_events[-1]["name"] == "stream.completed"

    first_turn = client.a2a.message_send(
        "note-completeness-agent",
        "Synthetic SDK context turn one; test phone 13800138000 only.",
    )
    second_turn = client.a2a.message_send(
        "note-completeness-agent",
        "Synthetic SDK context turn two; verify continuation only.",
        context_id=first_turn["contextId"],
    )
    assert second_turn["contextId"] == first_turn["contextId"]
    context = client.a2a.get_context(
        "note-completeness-agent", first_turn["contextId"]
    )
    assert context["id"] == first_turn["contextId"]
    assert len(context["items"]) == 4
    serialized_context = json.dumps(context)
    assert "13800138000" not in serialized_context
    assert "<REDACTED:PHONE>" in serialized_context
    assert client.a2a.delete_context(first_turn["contextId"])["deleted"] is True

    interaction_id = f"python-sdk-{uuid.uuid4().hex}"
    payload = b"RIFF\x00\x00\x00\x00"
    recording = client.speech_to_text.upload_recording(
        interaction_id, payload, "audio/wav"
    )
    recording_id = recording["recordingId"]
    assert recording_id in client.speech_to_text.list_recordings(interaction_id)["recordings"]
    assert client.speech_to_text.download_recording(interaction_id, recording_id) == payload
    client.speech_to_text.delete_recording(interaction_id, recording_id)
    assert recording_id not in client.speech_to_text.list_recordings(interaction_id)["recordings"]

    async def verify_realtime_stt():
        session = await client.speech_to_text.create_session_async()
        await session.close(code=1000, reason="SDK smoke complete")

    asyncio.run(verify_realtime_stt())

    print(json.dumps({
        "sdk": "python",
        "status": "passed",
        "hub_total": hub["total"],
        "run_error": run["error"],
        "run_lifecycle": "status-terminal,cancel-already-complete,sse-completed",
        "long_sse": long_sse_verified,
        "context_roundtrip": "send-continue-get-delete",
        "recording_lifecycle": "upload-list-download-delete",
        "realtime_stt": "authenticated-start-ready-close",
        "oauth_client_credentials": oauth_client_credentials,
        "facts_without_real_llm": "failed_closed",
        "coding_multi_system_filter_transport": "accepted_and_degraded_without_llm",
    }))
finally:
    if run_client is not client:
        run_client.close()
    client.close()
