"""Current Corti Streams contract and iCoDer safety-boundary tests."""

from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import threading
import time
import uuid
from queue import Empty, Queue
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_TEST_MODE", "1")

TENANT = "test-org"
ENVIRONMENT = "cn"
TOKEN = "test-signed-token-replaced-by-auth-adapter"


def _interaction_id() -> str:
    return str(uuid.uuid4())


def _url(interaction_id: str) -> str:
    return (
        f"/api/v2/tools/streams/{interaction_id}"
        f"?environment={ENVIRONMENT}&tenant-name={TENANT}&token={TOKEN}"
    )


def _config(
    *,
    mode: str = "transcription",
    retention: str = "none",
    **configuration_overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "config",
        "configuration": {
            "transcription": {
                "primaryLanguage": "zh-CN",
                "diarize": False,
                "isMultichannel": False,
                "participants": [{"channel": 0, "role": "multiple"}],
            },
            "mode": {"type": mode},
            "retentionPolicy": retention,
        },
    }
    if mode == "facts":
        payload["configuration"]["mode"]["outputLocale"] = "zh-CN"
    payload["configuration"].update(configuration_overrides)
    return payload


@pytest.fixture
def icoder_client(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.api.v2_tools_streams import _StreamPrincipal
    from app.main import app
    from app.services.ambient_processing import (
        ExtractedStreamFact,
        StreamFactExtraction,
    )
    from app.services.stream_media_decoder import (
        StreamMediaDecodeResult,
        StreamMediaDecodeStatus,
    )
    from fastapi.testclient import TestClient

    async def authenticated(token: str, tenant_name: str, environment: str):
        assert token == TOKEN
        assert tenant_name == TENANT
        assert environment == ENVIRONMENT
        return _StreamPrincipal(
            organization_id=TENANT,
            owner_id="test-user",
            username="tester",
            tenant_names=frozenset({TENANT}),
            token_type="access",
        )

    async def deterministic_asr(audio, *, media_type, primary_language):
        assert media_type == "audio/ogg"
        assert primary_language == "zh-CN"
        return f"患者主诉胸痛，已接收{len(audio)}字节音频。", ""

    async def deterministic_facts(transcript, *, output_language):
        assert transcript.startswith("患者主诉胸痛")
        assert output_language == "zh-CN"
        return StreamFactExtraction(
            facts=(ExtractedStreamFact("chief-complaint", "患者胸痛。"),),
            usage={"total_tokens": 20, "provider": "test-provider"},
        )

    async def no_audit(*_args, **_kwargs):
        return None

    async def decodable_media(audio, *, media_type):
        assert audio.startswith(b"OggS")
        assert media_type == "audio/ogg"
        return StreamMediaDecodeResult(StreamMediaDecodeStatus.VALID)

    active_leases: dict[tuple[str, str, str], str] = {}

    async def acquire_lease(scope, session_id, **_kwargs):
        key = (scope.organization_id, scope.owner_id, scope.interaction_id)
        if key in active_leases:
            return False
        active_leases[key] = session_id
        return True

    async def renew_lease(scope, session_id, **_kwargs):
        key = (scope.organization_id, scope.owner_id, scope.interaction_id)
        return active_leases.get(key) == session_id

    async def release_lease(scope, session_id, **_kwargs):
        key = (scope.organization_id, scope.owner_id, scope.interaction_id)
        if active_leases.get(key) != session_id:
            return False
        active_leases.pop(key, None)
        return True

    monkeypatch.setattr("app.api.v2_tools_streams._authenticate_stream", authenticated)
    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", deterministic_asr)
    monkeypatch.setattr(
        "app.api.v2_tools_streams.extract_stream_facts_with_usage",
        deterministic_facts,
    )
    monkeypatch.setattr("app.api.v2_tools_streams._audit_state", no_audit)
    monkeypatch.setattr(
        "app.api.v2_tools_streams.validate_stream_audio_decode",
        decodable_media,
    )
    monkeypatch.setattr("app.api.v2_tools_streams._acquire_stream_lease", acquire_lease)
    monkeypatch.setattr("app.api.v2_tools_streams._renew_stream_lease", renew_lease)
    monkeypatch.setattr("app.api.v2_tools_streams._release_stream_lease", release_lease)
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def _drive(
    client,
    *,
    audio_chunks: int,
    mode: str = "transcription",
    retention: str = "none",
    controls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    received_q: Queue = Queue()
    stop = threading.Event()
    thread: threading.Thread | None = None
    with client.websocket_connect(_url(_interaction_id())) as ws:
        def reader():
            while not stop.is_set():
                try:
                    received_q.put(json.loads(ws.receive_text()))
                except Exception:
                    return

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        ws.send_text(json.dumps(_config(mode=mode, retention=retention)))
        for index in range(audio_chunks):
            ws.send_bytes(
                (b"OggS" + b"\x00" * 60) if index == 0 else b"\x00" * 64
            )
        for control in controls or []:
            ws.send_text(json.dumps(control))
        ws.send_text(json.dumps({"type": "end"}))

        received: list[dict[str, Any]] = []
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                message = received_q.get(timeout=0.1)
            except Empty:
                continue
            received.append(message)
            if message.get("type") == "ENDED":
                break
        stop.set()
    if thread is not None:
        thread.join(timeout=2.0)
        if thread.is_alive():
            raise AssertionError("stream response reader did not terminate")
    return received


def _wait_for_stream_release(interaction_id: str) -> None:
    from app.api.v2_tools_streams import _active_streams

    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not any(key[2] == interaction_id for key in _active_streams):
            return
        time.sleep(0.01)
    raise AssertionError("stream connection did not release its local ownership")


def test_config_accepted_echoes_session_and_resolved_defaults(icoder_client):
    messages = _drive(icoder_client, audio_chunks=1)
    accepted = messages[0]
    assert accepted["type"] == "CONFIG_ACCEPTED"
    assert str(uuid.UUID(accepted["sessionId"])) == accepted["sessionId"]
    assert accepted["configuration"]["retentionPolicy"] == "none"
    assert accepted["configuration"]["transcription"]["diarize"] is False
    assert accepted["configuration"]["audioEvents"] == {"enabled": False}
    assert accepted["configuration"]["keyterms"] == {"terms": []}
    assert accepted["resumed"] is False
    assert accepted["restoredAudioBytes"] == 0
    assert accepted["restoredTranscriptMessages"] == 0
    assert accepted["restoredFactMessages"] == 0


def test_health_exposes_only_content_free_decoder_capacity(icoder_client):
    payload = icoder_client.get("/api/health").json()["stream_media_decoder"]
    assert payload["schema"] == "icoder/stream-media-decoder-health/v1"
    assert payload["maximum_concurrency"] >= 1
    assert payload["active"] >= 0
    assert "path" not in payload
    assert "audio" not in payload


def test_transcripts_are_final_mono_and_not_fabricated(icoder_client):
    messages = _drive(icoder_client, audio_chunks=60)
    transcripts = [message for message in messages if message.get("type") == "transcript"]
    assert len(transcripts) >= 2
    for message in transcripts:
        row = message["data"][0]
        assert row["final"] is True
        assert row["speakerId"] == -1
        assert row["participant"] == {"channel": 0}
        assert row["time"]["end"] < 10
        assert "患者主诉胸痛" in row["transcript"]


def test_facts_are_provider_grounded_uuid_shaped_and_deduplicated(icoder_client):
    messages = _drive(icoder_client, audio_chunks=100, mode="facts")
    facts = [message for message in messages if message.get("type") == "facts"]
    assert len(facts) == 1
    row = facts[0]["fact"][0]
    assert str(uuid.UUID(row["id"])) == row["id"]
    assert row["text"] == "患者胸痛。"
    assert row["group"] == "chief-complaint"
    assert row["groupId"] == ""
    assert row["source"] == "core"
    assert row["updatedAt"]


def test_flush_emits_flushed_then_truthful_delta_usage_and_keeps_stream_open(icoder_client):
    messages = _drive(
        icoder_client,
        audio_chunks=10,
        mode="facts",
        controls=[{"type": "flush"}],
    )
    types = [message.get("type") for message in messages]
    flushed = types.index("flushed")
    assert types[flushed + 1] == "delta_usage"
    assert messages[flushed + 1]["credits"] == 0.0
    assert types.index("usage") > flushed
    assert types.index("ENDED") > types.index("usage")


def test_end_does_not_reprocess_audio_already_processed_by_flush(
    icoder_client,
    monkeypatch,
):
    calls = 0

    async def counted_asr(audio, *, media_type, primary_language):
        nonlocal calls
        calls += 1
        assert media_type == "audio/ogg"
        assert primary_language == "zh-CN"
        return f"患者主诉胸痛，已接收{len(audio)}字节音频。", ""

    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", counted_asr)
    messages = _drive(
        icoder_client,
        audio_chunks=1,
        controls=[{"type": "flush"}],
    )

    assert messages[-1]["type"] == "ENDED"
    assert calls == 1


def test_end_emits_usage_before_ended_without_invented_credits(icoder_client):
    messages = _drive(icoder_client, audio_chunks=10)
    types = [message.get("type") for message in messages]
    assert types[-2:] == ["usage", "ENDED"]
    assert messages[-2]["credits"] == 0.0


def test_fails_closed_without_asr_output(icoder_client, monkeypatch):
    async def unavailable_asr(*_args, **_kwargs):
        return "", "ASR model unavailable and contains private detail"

    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", unavailable_asr)
    messages = _drive(icoder_client, audio_chunks=1)
    assert not [message for message in messages if message.get("type") == "transcript"]
    errors = [message for message in messages if message.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0]["error"]["id"] == "STT_UNAVAILABLE"
    assert "private detail" not in errors[0]["error"]["details"]
    assert [message["type"] for message in messages[-2:]] == ["usage", "ENDED"]


@pytest.mark.parametrize(
    ("mutate", "expected_reason"),
    [
        (lambda cfg: cfg["transcription"].update({"primaryLanguage": "en-US"}), "unsupported_primary_language"),
        (lambda cfg: cfg["transcription"].update({"diarize": True}), "diarization_not_available"),
        (
            lambda cfg: cfg["transcription"].update({"isMultichannel": True}),
            "multichannel_pcm_format_required",
        ),
        (
            lambda cfg: (
                cfg["transcription"].update({
                    "isMultichannel": True,
                    "participants": [{"channel": 0, "role": "clinician"}],
                }),
                cfg.update({
                    "audioFormat": "audio/pcm; rate=16000; channels=2; bits=16"
                }),
            ),
            "multichannel_participants_must_match_channels",
        ),
        (lambda cfg: cfg.update({"audioEvents": {"enabled": True}}), "audio_events_require_pcm"),
        (lambda cfg: cfg.update({"audioFormat": "audio/wav"}), "audio_format_not_supported"),
        (
            lambda cfg: cfg.update({
                "audioFormat": "audio/pcm; rate=48000; channels=1; bits=16"
            }),
            "raw_pcm_profile_not_available",
        ),
        (lambda cfg: cfg.update({"unknownClinicalOption": True}), "configuration_schema_invalid"),
    ],
)
def test_unsupported_or_unknown_capabilities_fail_during_config(
    icoder_client,
    mutate,
    expected_reason,
):
    payload = _config()
    mutate(payload["configuration"])
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        denied = json.loads(ws.receive_text())
        assert denied["type"] == "CONFIG_DENIED"
        assert denied["reason"] == expected_reason
        assert str(uuid.UUID(denied["interactionId"])) == denied["interactionId"]


def test_duplicate_configuration_is_explicitly_rejected(icoder_client):
    interaction_id = _interaction_id()
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        payload = _config()
        ws.send_text(json.dumps(payload))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_text(json.dumps(payload))
        duplicate = json.loads(ws.receive_text())
        assert duplicate["type"] == "CONFIG_ALREADY_RECEIVED"
        assert duplicate["interactionId"] == interaction_id


def test_keyterm_schema_accepts_exact_limits_and_rejects_overflow():
    from app.api.v2_tools_streams import _validate_config

    valid = _config(keyterms={
        "terms": [{"term": "x" * 50} for _ in range(1000)],
    })
    parsed, reason = _validate_config(valid)
    assert parsed is not None
    assert reason == ""
    assert len(parsed.configuration.keyterms.terms) == 1000

    too_many = _config(keyterms={
        "terms": [{"term": "房颤"} for _ in range(1001)],
    })
    assert _validate_config(too_many) == (None, "configuration_schema_invalid")

    too_long = _config(keyterms={"terms": [{"term": "x" * 51}]})
    assert _validate_config(too_long) == (None, "configuration_schema_invalid")


def test_declared_pcm_multichannel_is_deinterleaved_and_attributed(
    icoder_client,
    monkeypatch,
):
    from app.services.stream_media_decoder import (
        StreamMediaDecodeResult,
        StreamMediaDecodeStatus,
    )

    observed: list[tuple[bytes, str]] = []

    async def decoder(audio, *, media_type):
        assert audio == struct.pack("<hhhh", 100, 200, 300, 400)
        assert "channels=2" in media_type
        return StreamMediaDecodeResult(StreamMediaDecodeStatus.VALID)

    async def channel_asr(audio, *, media_type, primary_language):
        observed.append((audio, media_type))
        assert primary_language == "zh-CN"
        assert "channels=1" in media_type
        return ("医生问诊" if audio == struct.pack("<hh", 100, 300) else "患者回答"), ""

    monkeypatch.setattr("app.api.v2_tools_streams.validate_stream_audio_decode", decoder)
    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", channel_asr)
    payload = _config(
        audioFormat="audio/pcm; rate=16000; channels=2; bits=16",
    )
    payload["configuration"]["transcription"].update({
        "isMultichannel": True,
        "participants": [
            {"channel": 0, "role": "clinician"},
            {"channel": 1, "role": "patient"},
        ],
    })
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        accepted = json.loads(ws.receive_text())
        assert accepted["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(struct.pack("<hhhh", 100, 200, 300, 400))
        ws.send_text(json.dumps({"type": "end"}))
        transcript = json.loads(ws.receive_text())
        assert transcript["type"] == "transcript"
        assert [row["participant"] for row in transcript["data"]] == [
            {"channel": 0}, {"channel": 1},
        ]
        assert [row["speakerId"] for row in transcript["data"]] == [-1, -1]
        assert [row["transcript"] for row in transcript["data"]] == [
            "医生问诊", "患者回答",
        ]
        assert json.loads(ws.receive_text())["type"] == "usage"
        assert json.loads(ws.receive_text())["type"] == "ENDED"
    assert [audio for audio, _ in observed] == [
        struct.pack("<hh", 100, 300),
        struct.pack("<hh", 200, 400),
    ]


def test_keyterms_are_accepted_and_forwarded_to_each_channel(
    icoder_client,
    monkeypatch,
):
    from app.services.stream_media_decoder import (
        StreamMediaDecodeResult,
        StreamMediaDecodeStatus,
    )

    observed = []

    async def decoder(_audio, *, media_type):
        assert "channels=2" in media_type
        return StreamMediaDecodeResult(StreamMediaDecodeStatus.VALID)

    async def channel_asr(
        audio,
        *,
        media_type,
        primary_language,
        keyterms,
    ):
        observed.append((audio, media_type, primary_language, keyterms))
        return "房颤复诊", ""

    monkeypatch.setattr("app.api.v2_tools_streams.validate_stream_audio_decode", decoder)
    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", channel_asr)
    payload = _config(audioFormat="audio/pcm; rate=16000; channels=2; bits=16")
    payload["configuration"]["transcription"].update({
        "isMultichannel": True,
        "participants": [
            {"channel": 0, "role": "clinician"},
            {"channel": 1, "role": "patient"},
        ],
    })
    payload["configuration"]["keyterms"] = {
        "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
    }
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        accepted = json.loads(ws.receive_text())
        assert accepted["type"] == "CONFIG_ACCEPTED"
        assert accepted["configuration"]["keyterms"] == payload["configuration"]["keyterms"]
        ws.send_bytes(struct.pack("<hhhh", 100, 200, 300, 400))
        ws.send_text(json.dumps({"type": "end"}))
        assert json.loads(ws.receive_text())["type"] == "transcript"
        assert json.loads(ws.receive_text())["type"] == "usage"
        assert json.loads(ws.receive_text())["type"] == "ENDED"

    assert len(observed) == 2
    assert all(item[3] == ("房颤", "Corti Health") for item in observed)


def test_fast_init_schedule_matches_documented_initial_cadence():
    from app.api.v2_tools_streams import _fact_generation_interval_seconds

    assert [_fact_generation_interval_seconds(index, "fast_init") for index in range(4)] == [
        10.0, 20.0, 26.0, 38.0,
    ]
    assert _fact_generation_interval_seconds(100, "fast_init") == 60.0
    assert _fact_generation_interval_seconds(0, "fixed") == 60.0


def test_multichannel_checkpoint_roundtrip_preserves_channel_state():
    from app.api.v2_tools_streams import (
        _StreamPrincipal,
        _StreamState,
        _apply_checkpoint_state,
        _checkpoint_state_payload,
    )
    from app.schemas.v2_tools_streams import StreamConfigMessage

    payload = _config(
        retention="retain",
        audioFormat="audio/pcm; rate=16000; channels=2; bits=16",
    )
    payload["configuration"]["transcription"].update({
        "isMultichannel": True,
        "participants": [
            {"channel": 0, "role": "clinician"},
            {"channel": 1, "role": "patient"},
        ],
    })
    principal = _StreamPrincipal(
        organization_id=TENANT,
        owner_id="test-user",
        username="tester",
        tenant_names=frozenset({TENANT}),
        token_type="access",
    )
    original = _StreamState(
        interaction_id=_interaction_id(),
        session_id=str(uuid.uuid4()),
        principal=principal,
        configuration=StreamConfigMessage.model_validate(payload),
    )
    audio = struct.pack("<hhhh", 100, 200, 300, 400)
    original.audio_buffer = bytearray(audio)
    original.audio_bytes = len(audio)
    original.last_processed_bytes = len(audio)
    original.transcript_seq = 1
    original.channel_transcript_text = {0: "医生问诊", 1: "患者回答"}
    original.transcript_text = "[clinician] 医生问诊\n[patient] 患者回答"
    checkpoint = _checkpoint_state_payload(original)

    restored = _StreamState(
        interaction_id=original.interaction_id,
        session_id=str(uuid.uuid4()),
        principal=principal,
        configuration=original.configuration,
    )
    _apply_checkpoint_state(restored, checkpoint, audio)

    assert restored.channel_transcript_text == {0: "医生问诊", 1: "患者回答"}
    assert restored.transcript_text == original.transcript_text
    assert restored.transcript_seq == 1


def test_duplicate_active_stream_for_same_principal_is_rejected(icoder_client):
    interaction_id = _interaction_id()
    with icoder_client.websocket_connect(_url(interaction_id)) as first:
        first.send_text(json.dumps(_config()))
        assert json.loads(first.receive_text())["type"] == "CONFIG_ACCEPTED"
        with pytest.raises(WebSocketDisconnect) as caught:
            with icoder_client.websocket_connect(_url(interaction_id)):
                pass
        assert caught.value.code == 4409


def test_cross_worker_lease_conflict_is_rejected_before_acceptance(
    icoder_client,
    monkeypatch,
):
    async def lease_conflict(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        "app.api.v2_tools_streams._acquire_stream_lease", lease_conflict
    )
    with pytest.raises(WebSocketDisconnect) as caught:
        with icoder_client.websocket_connect(_url(_interaction_id())):
            pass
    assert caught.value.code == 4409


def test_stream_fails_closed_when_lease_store_is_unavailable(
    icoder_client,
    monkeypatch,
):
    async def lease_store_unavailable(*_args, **_kwargs):
        raise RuntimeError("private database connection detail")

    monkeypatch.setattr(
        "app.api.v2_tools_streams._acquire_stream_lease", lease_store_unavailable
    )
    with pytest.raises(WebSocketDisconnect) as caught:
        with icoder_client.websocket_connect(_url(_interaction_id())):
            pass
    assert caught.value.code == 1013
    assert "private database" not in caught.value.reason


def test_stream_fails_closed_when_lease_is_lost_before_end(
    icoder_client,
    monkeypatch,
):
    calls = 0

    async def lease_then_lost(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return calls == 1

    async def no_release(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        "app.api.v2_tools_streams._acquire_stream_lease", lease_then_lost
    )
    monkeypatch.setattr(
        "app.api.v2_tools_streams._renew_stream_lease", lease_then_lost
    )
    monkeypatch.setattr(
        "app.api.v2_tools_streams._release_stream_lease", no_release
    )
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(_config()))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_text(json.dumps({"type": "end"}))
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "STREAM_COORDINATION_LOST"
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 1013


def test_invalid_token_is_rejected_before_websocket_acceptance():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    url = (
        f"/api/v2/tools/streams/{_interaction_id()}"
        "?environment=cn&tenant-name=missing&token=not-a-jwt"
    )
    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(url):
            pass
    assert caught.value.code == 4401


def test_audio_chunk_and_total_buffer_are_bounded(icoder_client, monkeypatch):
    interaction_id = _interaction_id()
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config()))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"x" * 64_001)
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "AUDIO_CHUNK_TOO_LARGE"

    monkeypatch.setenv("ICODER_STREAM_MAX_AUDIO_BYTES", "16")
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(_config()))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"x" * 17)
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "AUDIO_TOO_LARGE"


def test_declared_audio_format_mismatch_fails_closed(icoder_client):
    payload = _config(audioFormat="audio/mpeg")
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"OggS" + b"\x00" * 60)
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "AUDIO_FORMAT_MISMATCH"
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 4400


def test_unknown_short_audio_is_rejected_on_end(icoder_client):
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(_config()))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"ICODER")
        ws.send_text(json.dumps({"type": "end"}))
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "AUDIO_FORMAT_INVALID"
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 4400


def test_pcm_audio_events_are_typed_deterministic_and_content_free(
    icoder_client,
    monkeypatch,
):
    audits: list[tuple[str, dict[str, Any]]] = []

    async def capture_audit(_state, action, **kwargs):
        audits.append((action, kwargs.get("details") or {}))

    monkeypatch.setattr("app.api.v2_tools_streams._audit_state", capture_audit)
    payload = _config(
        audioFormat="audio/pcm; rate=16000; channels=1; bits=16",
        audioEvents={"enabled": True},
    )
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        accepted = json.loads(ws.receive_text())
        assert accepted["type"] == "CONFIG_ACCEPTED"

        silence = b"\x00\x00" * (16000 * 10)
        for start in range(0, len(silence), 64_000):
            ws.send_bytes(silence[start:start + 64_000])
        detected = json.loads(ws.receive_text())
        assert detected == {
            "type": "audioEvent",
            "data": {
                "event": "longSilenceDetected",
                "channel": 0,
                "startTimeMs": 0,
            },
        }

        tone = b"".join(
            struct.pack(
                "<h",
                round(6000 * math.sin(2 * math.pi * 440 * index / 16000)),
            )
            for index in range(4000)
        )
        ws.send_bytes(tone)
        recovered = json.loads(ws.receive_text())
        assert recovered["type"] == "audioEvent"
        assert recovered["data"] == {
            "event": "longSilenceRecovered",
            "channel": 0,
            "startTimeMs": 10000,
        }

    event_audits = [details for action, details in audits if action == "stt.stream.audio_event"]
    assert [item["event"] for item in event_audits] == [
        "longSilenceDetected", "longSilenceRecovered",
    ]
    assert all(set(item) == {
        "event", "channel", "start_time_ms", "audio_event_count",
    } for item in event_audits)


def test_pcm_final_frame_alignment_fails_before_decoder_or_asr(
    icoder_client,
    monkeypatch,
):
    calls = {"decoder": 0, "asr": 0}

    async def decoder(*_args, **_kwargs):
        calls["decoder"] += 1
        raise AssertionError("decoder must not run for a partial PCM frame")

    async def asr(*_args, **_kwargs):
        calls["asr"] += 1
        raise AssertionError("ASR must not run for a partial PCM frame")

    monkeypatch.setattr("app.api.v2_tools_streams.validate_stream_audio_decode", decoder)
    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", asr)
    payload = _config(audioFormat="audio/pcm; rate=16000; channels=1; bits=16")
    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(payload))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"\x00\x00\x01")
        ws.send_text(json.dumps({"type": "end"}))
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == "AUDIO_FORMAT_INVALID"
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 4400
    assert calls == {"decoder": 0, "asr": 0}


@pytest.mark.parametrize(
    ("decode_status", "expected_error", "expected_close"),
    [
        ("invalid", "AUDIO_DECODE_INVALID", 4400),
        ("timeout", "AUDIO_VALIDATION_TIMEOUT", 1013),
        ("unavailable", "AUDIO_VALIDATION_UNAVAILABLE", 1013),
        ("busy", "AUDIO_VALIDATION_BUSY", 1013),
    ],
)
def test_isolated_decoder_failure_never_reaches_asr_or_retention(
    icoder_client,
    monkeypatch,
    decode_status,
    expected_error,
    expected_close,
):
    from app.services.stream_media_decoder import (
        StreamMediaDecodeResult,
        StreamMediaDecodeStatus,
    )

    calls = {"asr": 0, "retention": 0}

    async def decoder(*_args, **_kwargs):
        return StreamMediaDecodeResult(StreamMediaDecodeStatus(decode_status))

    async def asr(*_args, **_kwargs):
        calls["asr"] += 1
        return "unexpected", ""

    async def retention(*_args, **_kwargs):
        calls["retention"] += 1

    async def initialize_without_checkpoint(_state):
        # This decoder-isolation contract does not exercise the checkpoint
        # repository. Avoid coupling its parametrized websocket teardown to
        # SQLite writer scheduling from neighboring full-suite cases.
        return None

    monkeypatch.setattr("app.api.v2_tools_streams.validate_stream_audio_decode", decoder)
    monkeypatch.setattr("app.api.v2_tools_streams.transcribe_stream_audio", asr)
    monkeypatch.setattr("app.api.v2_tools_streams._persist_recording", retention)
    monkeypatch.setattr(
        "app.api.v2_tools_streams._resume_or_initialize_checkpoint",
        initialize_without_checkpoint,
    )

    with icoder_client.websocket_connect(_url(_interaction_id())) as ws:
        ws.send_text(json.dumps(_config(retention="retain")))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"OggS" + b"\x00" * 60)
        ws.send_text(json.dumps({"type": "end"}))
        error = json.loads(ws.receive_text())
        assert error["error"]["id"] == expected_error
        assert "OggS" not in error["error"]["details"]
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == expected_close

    assert calls == {"asr": 0, "retention": 0}


def test_retain_persists_exact_transcript_and_recording(icoder_client, monkeypatch):
    persisted: dict[str, Any] = {}

    async def persist_transcript(state, segment):
        persisted["transcript"] = segment.model_dump(mode="json")
        persisted["transcript_scope"] = state.scope

    async def persist_recording(state):
        persisted["recording"] = bytes(state.audio_buffer)
        persisted["recording_scope"] = state.scope

    monkeypatch.setattr("app.api.v2_tools_streams._persist_transcript", persist_transcript)
    monkeypatch.setattr("app.api.v2_tools_streams._persist_recording", persist_recording)
    messages = _drive(icoder_client, audio_chunks=1, retention="retain")
    transcript = next(message for message in messages if message.get("type") == "transcript")
    assert persisted["transcript"]["transcript"] == transcript["data"][0]["transcript"]
    assert persisted["recording"] == b"OggS" + b"\x00" * 60
    assert persisted["transcript_scope"] == persisted["recording_scope"]
    assert persisted["recording_scope"]["organization_id"] == TENANT


def test_retained_unfinished_stream_resumes_audio_transcript_and_facts(
    icoder_client,
    monkeypatch,
):
    from app.database import AsyncSessionLocal
    from app.models.stt_artifact import (
        STTStreamCheckpoint,
        STTStreamCheckpointChunk,
    )
    from app.services.clinical_fact_repository import clinical_fact_repository
    from app.services.stt_artifact_repository import stt_artifact_repository
    from sqlalchemy import func, select

    interaction_id = _interaction_id()
    audits: list[tuple[str, dict[str, Any]]] = []

    async def capture_audit(_state, action, **kwargs):
        audits.append((action, kwargs.get("details") or {}))

    monkeypatch.setattr("app.api.v2_tools_streams._audit_state", capture_audit)
    first_chunk = b"OggS" + b"\x00" * 60
    second_chunk = b"\x00" * 64

    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config(mode="facts", retention="retain")))
        first_accepted = json.loads(ws.receive_text())
        assert first_accepted["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(first_chunk)
        ws.send_text(json.dumps({"type": "flush"}))
        first_messages = []
        while True:
            message = json.loads(ws.receive_text())
            first_messages.append(message)
            if message.get("type") == "delta_usage":
                break
        assert any(message.get("type") == "transcript" for message in first_messages)
        assert any(message.get("type") == "facts" for message in first_messages)
        ws.close(code=1001)

    _wait_for_stream_release(interaction_id)
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config(mode="facts", retention="retain")))
        second_accepted = json.loads(ws.receive_text())
        assert second_accepted["type"] == "CONFIG_ACCEPTED"
        assert second_accepted["sessionId"] != first_accepted["sessionId"]
        assert second_accepted["resumed"] is True
        assert second_accepted["restoredAudioBytes"] == len(first_chunk)
        assert second_accepted["restoredTranscriptMessages"] == 1
        assert second_accepted["restoredFactMessages"] == 1
        ws.send_bytes(second_chunk)
        ws.send_text(json.dumps({"type": "end"}))
        second_messages = []
        while True:
            message = json.loads(ws.receive_text())
            second_messages.append(message)
            if message.get("type") == "ENDED":
                break

    configured = [details for action, details in audits if action == "stt.stream.configured"]
    assert [item["checkpoint_resumed"] for item in configured] == [False, True]
    assert configured[1]["restored_audio_bytes"] == len(first_chunk)
    assert configured[1]["restored_transcript_messages"] == 1
    assert configured[1]["restored_fact_messages"] == 1

    async def inspect_retained_state():
        async with AsyncSessionLocal() as db:
            checkpoints = await db.scalar(select(func.count()).select_from(
                STTStreamCheckpoint
            ).where(STTStreamCheckpoint.interaction_id == interaction_id))
            chunks = await db.scalar(select(func.count()).select_from(
                STTStreamCheckpointChunk
            ).where(STTStreamCheckpointChunk.interaction_id == interaction_id))
            recordings = await stt_artifact_repository.list_recordings(
                db,
                organization_id=TENANT,
                owner_id="test-user",
                interaction_id=interaction_id,
            )
            transcripts = await stt_artifact_repository.list_transcripts(
                db,
                organization_id=TENANT,
                owner_id="test-user",
                interaction_id=interaction_id,
            )
            facts = await clinical_fact_repository.list(
                db,
                organization_id=TENANT,
                owner_id="test-user",
                interaction_id=interaction_id,
            )
            return checkpoints, chunks, recordings, transcripts, facts

    checkpoints, chunks, recordings, transcripts, facts = asyncio.run(
        inspect_retained_state()
    )
    assert checkpoints == 0
    assert chunks == 0
    assert len(recordings) == 1
    assert stt_artifact_repository.recording_content(recordings[0]) == (
        first_chunk + second_chunk
    )
    assert len(transcripts) == 2
    assert len(facts) == 1


def test_retained_resume_rejects_changed_configuration(icoder_client):
    interaction_id = _interaction_id()
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config(retention="retain")))
        assert json.loads(ws.receive_text())["type"] == "CONFIG_ACCEPTED"
        ws.send_bytes(b"OggS" + b"\x00" * 60)
        ws.send_text(json.dumps({"type": "flush"}))
        while json.loads(ws.receive_text()).get("type") != "delta_usage":
            pass
        ws.close(code=1001)

    _wait_for_stream_release(interaction_id)
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config(mode="facts", retention="retain")))
        denied = json.loads(ws.receive_text())
        assert denied == {
            "type": "CONFIG_DENIED",
            "reason": "stream_checkpoint_configuration_mismatch",
            "interactionId": interaction_id,
        }
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 4409


def test_retained_stream_requires_encryption_key(icoder_client, monkeypatch):
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY", raising=False)
    interaction_id = _interaction_id()
    with icoder_client.websocket_connect(_url(interaction_id)) as ws:
        ws.send_text(json.dumps(_config(retention="retain")))
        denied = json.loads(ws.receive_text())
        assert denied == {
            "type": "CONFIG_DENIED",
            "reason": "stream_checkpoint_encryption_required",
            "interactionId": interaction_id,
        }
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_text()
        assert caught.value.code == 4403
