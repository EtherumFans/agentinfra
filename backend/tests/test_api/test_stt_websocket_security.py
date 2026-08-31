"""Security and bounded-memory contract for the real-time STT WebSocket."""

from __future__ import annotations

import inspect
import logging
import os
import struct
import sys
from types import ModuleType, SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.oauth import _create_oauth_token
from app.middleware.auth import create_access_token, create_refresh_token


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def _access_token(*, org_id: str = "org_default1") -> str:
    return create_access_token(
        "u-test-bypass",
        "test-user",
        "admin",
        org_id=org_id,
    )


def _receive_until(websocket, message_type: str) -> dict:
    for _ in range(4):
        message = websocket.receive_json()
        if message.get("type") == message_type:
            return message
    raise AssertionError(f"WebSocket did not emit {message_type}")


def _resume_frame(sequence: int, payload: bytes) -> bytes:
    return b"ICR1" + struct.pack(">I", sequence) + payload


@pytest.mark.parametrize("token", ["", "not-a-token"])
def test_stt_websocket_rejects_missing_or_invalid_token(icoder_client, token):
    suffix = f"?token={token}" if token else ""
    with pytest.raises(WebSocketDisconnect) as caught:
        with icoder_client.websocket_connect(f"/ws/speech-to-text{suffix}"):
            pass
    assert caught.value.code == 4401


def test_stt_websocket_rejects_refresh_token_and_missing_org(icoder_client):
    refresh = create_refresh_token("u-test-bypass", org_id="org_default1")
    missing_org = _access_token(org_id="")
    for token, expected_code in ((refresh, 4401), (missing_org, 4403)):
        with pytest.raises(WebSocketDisconnect) as caught:
            with icoder_client.websocket_connect(
                f"/ws/speech-to-text?token={token}"
            ):
                pass
        assert caught.value.code == expected_code


def test_stt_websocket_enforces_machine_client_scope(icoder_client):
    denied = _create_oauth_token(
        "client-1", "api:read", "owner-1", 300, org_id="org_default1"
    )
    allowed = _create_oauth_token(
        "client-1", "transcribe", "owner-1", 300, org_id="org_default1"
    )

    with pytest.raises(WebSocketDisconnect) as caught:
        with icoder_client.websocket_connect(
            f"/ws/speech-to-text?token={denied}"
        ):
            pass
    assert caught.value.code == 4403

    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={allowed}"
    ) as websocket:
        websocket.send_bytes(b"before-start")
        assert websocket.receive_json()["code"] == "session_not_started"


def test_stt_websocket_requires_start_before_audio(icoder_client):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_bytes(b"audio-before-start")
        assert websocket.receive_json()["code"] == "session_not_started"


@pytest.mark.parametrize(
    ("start", "expected_code"),
    [
        ({"type": "start", "language": "en-US", "mimeType": "audio/webm"}, "unsupported_language"),
        ({"type": "start", "language": "zh-CN", "mimeType": "application/json"}, "unsupported_media_type"),
    ],
)
def test_stt_websocket_rejects_unverified_language_and_media(
    icoder_client,
    start,
    expected_code,
):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json(start)
        assert websocket.receive_json()["code"] == expected_code
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_stt_websocket_advertises_and_enforces_memory_limit(icoder_client, monkeypatch):
    monkeypatch.setattr("app.api.websocket._MAX_STT_WEBSOCKET_BYTES", 4)
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "language": "zh-CN",
            "mimeType": "audio/webm;codecs=opus",
        })
        ready = websocket.receive_json()
        assert ready == {"type": "ready", "language": "zh-CN", "maxSessionBytes": 4}
        websocket.send_bytes(b"12345")
        error = _receive_until(websocket, "error")
        assert error["code"] == "session_too_large"
        with pytest.raises(WebSocketDisconnect) as caught:
            websocket.receive_json()
        assert caught.value.code == 1009


def test_stt_websocket_resume_protocol_acknowledges_and_deduplicates_audio(
    icoder_client,
    monkeypatch,
):
    captured_audio: list[bytes] = []

    async def capture(audio, _mime):
        captured_audio.append(audio)
        return "", "synthetic-disabled-engine"

    monkeypatch.setattr("app.api.websocket._transcribe_audio", capture)
    token = _access_token()
    session_id = "session_0123456789abcdef"
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "protocol": "icoder.stt-resume.v1",
            "sessionId": session_id,
            "language": "zh-CN",
            "mimeType": "audio/webm;codecs=opus",
        })
        assert websocket.receive_json() == {
            "type": "ready",
            "language": "zh-CN",
            "maxSessionBytes": 32 * 1024 * 1024,
            "protocol": "icoder.stt-resume.v1",
            "resumeSupported": True,
            "resumeMode": "client_replay",
            "sessionId": session_id,
            "nextAudioSequence": 1,
        }

        websocket.send_bytes(_resume_frame(1, b"first-"))
        first_ack = _receive_until(websocket, "audio_ack")
        assert first_ack["sequence"] == 1
        assert first_ack["nextAudioSequence"] == 2
        assert first_ack["totalBytes"] == 6
        assert first_ack["duplicate"] is False

        websocket.send_bytes(_resume_frame(1, b"must-not-duplicate"))
        duplicate_ack = _receive_until(websocket, "audio_ack")
        assert duplicate_ack["sequence"] == 1
        assert duplicate_ack["nextAudioSequence"] == 2
        assert duplicate_ack["totalBytes"] == 6
        assert duplicate_ack["duplicate"] is True

        websocket.send_bytes(_resume_frame(2, b"second"))
        second_ack = _receive_until(websocket, "audio_ack")
        assert second_ack["sequence"] == 2
        assert second_ack["nextAudioSequence"] == 3
        assert second_ack["totalBytes"] == 12

        websocket.send_json({"type": "end", "lastAudioSequence": 2})
        assert _receive_until(websocket, "error")["code"] == "transcription_failed"

    assert captured_audio == [b"first-second"]


def test_stt_websocket_resume_protocol_rejects_sequence_gap(icoder_client):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "protocol": "icoder.stt-resume.v1",
            "sessionId": "session_0123456789abcdef",
            "language": "zh-CN",
            "mimeType": "audio/webm",
        })
        websocket.receive_json()
        websocket.send_bytes(_resume_frame(2, b"gap"))
        error = websocket.receive_json()
        assert error["code"] == "audio_sequence_gap"
        assert error["nextAudioSequence"] == 1
        with pytest.raises(WebSocketDisconnect) as caught:
            websocket.receive_json()
        assert caught.value.code == 4400


@pytest.mark.parametrize(
    ("protocol", "session_id", "expected_code"),
    [
        ("unknown.v1", "session_0123456789abcdef", "unsupported_resume_protocol"),
        ("icoder.stt-resume.v1", "short", "invalid_resume_session"),
    ],
)
def test_stt_websocket_rejects_invalid_resume_negotiation(
    icoder_client,
    protocol,
    session_id,
    expected_code,
):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "protocol": protocol,
            "sessionId": session_id,
            "language": "zh-CN",
            "mimeType": "audio/webm",
        })
        assert websocket.receive_json()["code"] == expected_code
        with pytest.raises(WebSocketDisconnect) as caught:
            websocket.receive_json()
        assert caught.value.code == 4400


def test_stt_websocket_resume_limit_counts_payload_not_frame_header(
    icoder_client,
    monkeypatch,
):
    monkeypatch.setattr("app.api.websocket._MAX_STT_WEBSOCKET_BYTES", 3)
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "protocol": "icoder.stt-resume.v1",
            "sessionId": "session_0123456789abcdef",
            "language": "zh-CN",
            "mimeType": "audio/webm",
        })
        assert websocket.receive_json()["maxSessionBytes"] == 3
        websocket.send_bytes(_resume_frame(1, b"123"))
        assert _receive_until(websocket, "audio_ack")["totalBytes"] == 3
        websocket.send_bytes(_resume_frame(2, b"4"))
        assert _receive_until(websocket, "error")["code"] == "session_too_large"
        with pytest.raises(WebSocketDisconnect) as caught:
            websocket.receive_json()
        assert caught.value.code == 1009


def test_stt_websocket_resume_end_requires_complete_sequence(icoder_client):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "protocol": "icoder.stt-resume.v1",
            "sessionId": "session_0123456789abcdef",
            "language": "zh-CN",
            "mimeType": "audio/webm",
        })
        websocket.receive_json()
        websocket.send_bytes(_resume_frame(1, b"audio"))
        _receive_until(websocket, "audio_ack")
        websocket.send_json({"type": "end", "lastAudioSequence": 0})
        error = _receive_until(websocket, "error")
        assert error["code"] == "audio_sequence_incomplete"
        assert error["nextAudioSequence"] == 2


def test_stt_websocket_end_without_audio_is_explicit_and_safe(icoder_client):
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "language": "zh-CN",
            "mimeType": "audio/webm;codecs=opus",
        })
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "end"})
        assert websocket.receive_json() == {
            "type": "error",
            "code": "no_audio",
            "message": "No audio was received.",
        }


def test_stt_websocket_discards_transcriber_failure_detail(
    icoder_client,
    monkeypatch,
):
    async def unavailable(_audio, _mime):
        return "", "patient-secret-from-local-engine"

    monkeypatch.setattr("app.api.websocket._transcribe_audio", unavailable)
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "language": "zh-CN",
            "mimeType": "audio/webm",
        })
        websocket.receive_json()
        websocket.send_bytes(b"synthetic-audio")
        websocket.send_json({"type": "end"})
        error = _receive_until(websocket, "error")

    assert error == {
        "type": "error",
        "code": "transcription_failed",
        "message": "Transcription failed.",
    }
    assert "patient-secret" not in str(error)


def test_stt_websocket_discards_unhandled_exception_detail(
    icoder_client,
    monkeypatch,
    caplog,
):
    async def crash(_audio, _mime):
        raise RuntimeError("patient-secret-from-native-engine")

    monkeypatch.setattr("app.api.websocket._transcribe_audio", crash)
    caplog.set_level(logging.ERROR, logger="app.api.websocket")
    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "language": "zh-CN",
            "mimeType": "audio/wav",
        })
        websocket.receive_json()
        websocket.send_bytes(b"synthetic-audio")
        websocket.send_json({"type": "end"})
        error = _receive_until(websocket, "error")

    assert error == {
        "type": "error",
        "code": "internal_error",
        "message": "Real-time STT session failed.",
    }
    assert "patient-secret" not in caplog.text


def test_stt_websocket_removes_diarization_audio_after_native_failure(
    icoder_client,
    monkeypatch,
    caplog,
):
    async def transcribe(_audio, _mime):
        return "去标识化转写", ""

    captured_paths: list[str] = []

    def fail_diarization(path):
        assert os.path.exists(path)
        captured_paths.append(path)
        raise RuntimeError("patient-secret-from-diarizer")

    fake_module = ModuleType("app.services.speaker_diarizer")
    fake_module.speaker_diarizer = SimpleNamespace(diarize=fail_diarization)
    monkeypatch.setitem(sys.modules, "app.services.speaker_diarizer", fake_module)
    monkeypatch.setattr("app.api.websocket._transcribe_audio", transcribe)
    caplog.set_level(logging.WARNING, logger="app.api.websocket")

    token = _access_token()
    with icoder_client.websocket_connect(
        f"/ws/speech-to-text?token={token}"
    ) as websocket:
        websocket.send_json({
            "type": "start",
            "language": "zh-CN",
            "mimeType": "audio/wav",
        })
        websocket.receive_json()
        websocket.send_bytes(b"synthetic-audio")
        websocket.send_json({"type": "end"})
        final = _receive_until(websocket, "final")

    assert final == {
        "type": "final",
        "text": "去标识化转写",
        "diarization": [],
    }
    assert len(captured_paths) == 1
    assert not os.path.exists(captured_paths[0])
    assert "patient-secret" not in caplog.text


def test_realtime_stt_has_no_implicit_public_provider_fallback():
    from app.api import websocket as websocket_module

    source = inspect.getsource(websocket_module)
    assert "recognize_google" not in source
    assert "speech_recognition" not in source


@pytest.mark.asyncio
async def test_disabled_local_stt_returns_before_audio_tempfile_or_native_load(
    monkeypatch,
):
    from app.api import websocket as websocket_module
    from app.config import settings

    monkeypatch.setattr(settings, "ICODER_ENABLE_LOCAL_STT", False)

    def forbidden_tempfile(*_args, **_kwargs):
        raise AssertionError("disabled local STT must not materialize clinical audio")

    monkeypatch.setattr(websocket_module.tempfile, "NamedTemporaryFile", forbidden_tempfile)
    for transcriber in (
        websocket_module._transcribe_audio,
        websocket_module._transcribe_streaming,
    ):
        text, error = await transcriber(b"synthetic-audio", "audio/wav")
        assert text == ""
        assert error == "No approved local STT engine is enabled."
