"""Real uploaded-recording lifecycle for the Corti-compatible STT API."""

from __future__ import annotations

import io
import struct
import sys
import uuid
import wave

import pytest


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def _interaction() -> str:
    return f"real-stt-{uuid.uuid4()}"


def _stereo_pcm_wav(*, frames: int = 320) -> bytes:
    interleaved = [sample for _ in range(frames) for sample in (1200, -1200)]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(struct.pack("<" + "h" * len(interleaved), *interleaved))
    return buffer.getvalue()


def test_unknown_stt_resources_never_materialize_protocol_fixtures_by_default(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    monkeypatch.delenv("ICODER_ENABLE_PROTOCOL_FIXTURES", raising=False)
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)

    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    ).json() == {"recordings": []}
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/"
    ).json() == {"transcripts": []}
    recording = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/not-created"
    )
    transcript = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/not-created"
    )
    create = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": "not-created", "primaryLanguage": "zh-CN"},
    )

    assert recording.status_code == 404
    assert transcript.status_code == 404
    assert create.status_code == 404


def test_protocol_fixtures_cannot_be_enabled_in_cloud(monkeypatch):
    from app.api.v2_tools_stt import _protocol_fixtures_enabled

    monkeypatch.setenv("APP_ENV", "cloud")
    monkeypatch.setenv("ICODER_ENABLE_PROTOCOL_FIXTURES", "1")

    assert _protocol_fixtures_enabled() is False


def test_protocol_fixtures_cannot_be_enabled_outside_pytest(monkeypatch):
    from app.api.v2_tools_stt import _protocol_fixtures_enabled

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ICODER_ENABLE_PROTOCOL_FIXTURES", "1")
    pytest_module = sys.modules.pop("pytest", None)
    try:
        assert _protocol_fixtures_enabled() is False
    finally:
        if pytest_module is not None:
            sys.modules["pytest"] = pytest_module


def test_stt_readiness_is_scoped_and_truthful(icoder_client):
    response = icoder_client.get("/api/v2/tools/stt/readiness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified_languages"] == ["zh-CN"]
    assert body["durable_job_state"] is True
    assert body["restart_recovery"] is True
    assert body["queue_backend"] == "in_process"
    assert body["horizontally_scalable_queue"] is False
    assert body["live_health_verified"] is False
    assert body["production_ready"] is False
    assert body["maximum_recording_bytes"] == 150 * 1024 * 1024
    assert "encrypted_text" not in response.text.lower()


def test_uploaded_audio_round_trips_and_creates_non_synthetic_transcript(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    audio = b"RIFF" + b"\x00" * 128

    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=audio,
        headers={"Content-Type": "audio/wav"},
    )
    assert upload.status_code == 201, upload.text
    recording_id = upload.json()["recordingId"]
    assert recording_id.startswith(f"{interaction_id}-rec-")

    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert listed.status_code == 200
    assert listed.json() == {"recordings": [recording_id]}

    fetched = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert fetched.status_code == 200
    assert fetched.content == audio
    assert fetched.headers["content-type"].startswith("audio/wav")
    assert fetched.headers["cache-control"] == "no-store"

    observed: dict[str, object] = {}

    async def fake_transcribe_bytes(content: bytes, media_type: str):
        observed["content"] = content
        observed["media_type"] = media_type
        return "患者主诉胸疼，建议进一步评估。", ""

    monkeypatch.setattr(
        "app.services.stt_service.transcribe_bytes",
        fake_transcribe_bytes,
    )
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "replacements": [{"find": "胸疼", "replace": "胸痛"}],
        },
    )
    assert created.status_code == 201, created.text
    transcript = created.json()
    transcript_id = transcript["id"]
    assert transcript["status"] == "completed"
    assert transcript["recordingId"] == recording_id
    assert transcript["transcripts"][0]["text"] == "患者主诉胸痛，建议进一步评估。"
    assert transcript["metadata"]["participantsRoles"] is None
    assert "stub" not in transcript["transcripts"][0]["text"].lower()
    assert observed == {"content": audio, "media_type": "audio/wav"}

    listed_transcripts = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/?full=true"
    )
    assert listed_transcripts.status_code == 200
    items = listed_transcripts.json()["transcripts"]
    assert [item["id"] for item in items] == [transcript_id]
    assert items[0]["transcript"]["transcripts"][0]["text"].startswith("患者主诉胸痛")

    status = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert status.status_code == 200
    assert status.json() == {"status": "completed"}

    deleted_transcript = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert deleted_transcript.status_code == 204
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/"
    ).json() == {"transcripts": []}

    deleted_recording = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert deleted_recording.status_code == 204
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    ).json() == {"recordings": []}


def test_requested_replacements_are_case_insensitive(icoder_client, monkeypatch):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "Take BID and bid after meals.", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "replacements": [{"find": "BID", "replace": "每日两次"}],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "Take 每日两次 and 每日两次 after meals."


def test_prerecorded_keyterms_are_forwarded_ordered_and_case_sensitive(
    icoder_client,
    monkeypatch,
):
    from app.services.stt_artifact_repository import stt_artifact_repository

    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]
    observed: dict[str, object] = {}

    async def transcribe(_content: bytes, _media_type: str, *, keyterms):
        observed["keyterms"] = keyterms
        return "房颤患者由Corti Health随访。", ""

    persisted: list[dict] = []
    original_put = stt_artifact_repository.put_transcript

    async def capture_request_data(db, **kwargs):
        persisted.append(dict(kwargs.get("request_data") or {}))
        return await original_put(db, **kwargs)

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    monkeypatch.setattr(stt_artifact_repository, "put_transcript", capture_request_data)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "keyterms": {
                "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
            },
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "房颤患者由Corti Health随访。"
    assert observed["keyterms"] == ("房颤", "Corti Health")
    assert persisted[-1]["keyterms"] == ["房颤", "Corti Health"]


def test_prerecorded_stereo_channels_are_persisted_and_returned_with_roles(
    icoder_client,
    monkeypatch,
):
    from app.services.stt_service import STTChannelTranscript

    interaction_id = _interaction()
    stereo = _stereo_pcm_wav()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=stereo,
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]
    observed: dict[str, object] = {}

    async def transcribe(content, media_type, *, expected_channels, keyterms):
        observed.update(
            content=content,
            media_type=media_type,
            expected_channels=expected_channels,
            keyterms=keyterms,
        )
        return (
            [
                STTChannelTranscript(0, "医生询问房颤 句号", 0, 20),
                STTChannelTranscript(1, "患者回答Corti Health", 0, 20),
            ],
            "",
            {
                "schema": "icoder/stt-inference-telemetry/v1",
                "provider": "funasr",
                "model": "iic/paraformer@v2.0.4",
                "latency_ms": 12,
                "status": "complete",
                "fallback_used": False,
                "streaming": False,
            },
        )

    monkeypatch.setattr(
        "app.services.stt_service.transcribe_multichannel_bytes_with_telemetry",
        transcribe,
    )
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "spokenPunctuation": True,
            "keyterms": {"terms": [{"term": "房颤"}, {"term": "Corti Health"}]},
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["metadata"]["participantsRoles"] == [
        {"channel": 0, "role": "doctor"},
        {"channel": 1, "role": "patient"},
    ]
    assert payload["transcripts"] == [
        {
            "channel": 0,
            "participant": 0,
            "speakerId": -1,
            "text": "医生询问房颤。",
            "start": 0,
            "end": 20,
        },
        {
            "channel": 1,
            "participant": 1,
            "speakerId": -1,
            "text": "患者回答Corti Health",
            "start": 0,
            "end": 20,
        },
    ]
    assert observed == {
        "content": stereo,
        "media_type": "audio/wav",
        "expected_channels": 2,
        "keyterms": ("房颤", "Corti Health"),
    }
    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/?full=true"
    ).json()["transcripts"]
    assert listed[0]["transcript"]["transcripts"] == payload["transcripts"]
    assert listed[0]["transcriptSample"] == "医生询问房颤。\n患者回答Corti Health"


@pytest.mark.parametrize("request_flag", ["isDictation", "spokenPunctuation"])
def test_dictation_punctuation_is_explicit_and_chinese_localized(
    icoder_client,
    monkeypatch,
    request_flag,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "患者主诉胸痛 逗号 持续三天 句号 左括号 房颤 右括号", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            request_flag: True,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "患者主诉胸痛，持续三天。（房颤）"


@pytest.mark.parametrize(
    "punctuation_fields",
    [
        {"isDictation": True, "spokenPunctuation": False},
        {"isDictation": True, "automaticPunctuation": True},
    ],
)
def test_current_punctuation_fields_override_legacy_is_dictation(
    icoder_client,
    monkeypatch,
    punctuation_fields,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "患者胸痛 句号", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            **punctuation_fields,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "患者胸痛 句号"


def test_spoken_punctuation_overrides_disabled_automatic_punctuation(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "患者胸痛 句号", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "spokenPunctuation": True,
            "automaticPunctuation": False,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "患者胸痛。"


def test_dictation_punctuation_is_not_applied_without_opt_in(icoder_client, monkeypatch):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "患者问号待确认", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": recording_id, "primaryLanguage": "zh-CN"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["transcripts"][0]["text"] == "患者问号待确认"


def test_sync_transcript_persists_content_free_runtime_telemetry(
    icoder_client,
    monkeypatch,
):
    from app.services import stt_service
    from app.services.stt_artifact_repository import stt_artifact_repository

    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]
    captured = []

    async def transcribe(_content: bytes, _media_type: str):
        stt_service._record_stt_inference_telemetry(
            provider="funasr",
            model="iic/paraformer@v2.0.4",
            latency_ms=9,
            status="complete",
            fallback_used=False,
            streaming=False,
        )
        return "去标识化转写", ""

    original = stt_artifact_repository.set_transcript_runtime_telemetry

    async def capture(db, row, telemetry):
        captured.append(dict(telemetry))
        await original(db, row, telemetry)

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", transcribe)
    monkeypatch.setattr(
        stt_artifact_repository,
        "set_transcript_runtime_telemetry",
        capture,
    )

    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": recording_id, "primaryLanguage": "zh-CN"},
    )

    assert response.status_code == 201, response.text
    assert captured == [{
        "schema": "icoder/stt-inference-telemetry/v1",
        "provider": "funasr",
        "model": "iic/paraformer@v2.0.4",
        "latency_ms": 9,
        "status": "complete",
        "fallback_used": False,
        "streaming": False,
    }]
    assert "去标识化转写" not in str(captured)


@pytest.mark.parametrize(
    ("unsupported_payload", "expected_feature"),
    [
        ({"diarize": True}, "diarize"),
        ({"automaticPunctuation": False}, "automaticPunctuation=false"),
        (
            {
                "participants": [
                    {"channel": 1, "role": "doctor"},
                    {"channel": 2, "role": "patient"},
                ]
            },
            "participants>1",
        ),
    ],
)
def test_unimplemented_stt_features_fail_explicitly(
    icoder_client,
    unsupported_payload,
    expected_feature,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            **unsupported_payload,
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["type"] == "unsupported_stt_feature"
    assert expected_feature in detail["unsupported"]
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/"
    ).json() == {"transcripts": []}


@pytest.mark.parametrize(
    "participants",
    [
        [],
        [{"channel": 0, "role": "doctor"}],
        [
            {"channel": 0, "role": "doctor"},
            {"channel": 0, "role": "patient"},
        ],
        [
            {"channel": 1, "role": "doctor"},
            {"channel": 2, "role": "patient"},
        ],
    ],
)
def test_multichannel_requires_exact_participants_for_channels_zero_and_one(
    icoder_client,
    participants,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=_stereo_pcm_wav(),
        headers={"Content-Type": "audio/wav"},
    )
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "participants": participants,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["type"] == "invalid_multichannel_configuration"


def test_multichannel_rejects_non_stereo_or_non_pcm_wav_before_asr(icoder_client):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"not-a-valid-stereo-wav",
        headers={"Content-Type": "audio/wav"},
    )
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["type"] == "invalid_multichannel_audio"


def test_encoded_multichannel_is_probed_then_returns_phrase_timestamps(
    icoder_client,
    monkeypatch,
):
    from app.services.stt_service import STTChannelTranscript

    interaction_id = _interaction()
    encoded = b"synthetic-lossless-stereo"
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=encoded,
        headers={"Content-Type": "audio/flac"},
    )
    assert upload.status_code == 201, upload.text
    observed: dict[str, object] = {}

    async def validate(content, media_type, *, expected_channels):
        observed["validated"] = (content, media_type, expected_channels)
        return object()

    async def transcribe(content, media_type, *, expected_channels, keyterms):
        observed["transcribed"] = (content, media_type, expected_channels, keyterms)
        return (
            [
                STTChannelTranscript(0, "医生第一句", 120, 860),
                STTChannelTranscript(0, "医生第二句", 940, 1710),
                STTChannelTranscript(1, "患者回答", 300, 1480),
            ],
            "",
            {},
        )

    monkeypatch.setattr(
        "app.services.stt_service.validate_prerecorded_multichannel_audio",
        validate,
    )
    monkeypatch.setattr(
        "app.services.stt_service.transcribe_multichannel_bytes_with_telemetry",
        transcribe,
    )
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
        },
    )

    assert response.status_code == 201, response.text
    assert [
        (row["channel"], row["participant"], row["speakerId"], row["start"], row["end"])
        for row in response.json()["transcripts"]
    ] == [
        (0, 0, -1, 120, 860),
        (0, 0, -1, 940, 1710),
        (1, 1, -1, 300, 1480),
    ]
    assert observed == {
        "validated": (encoded, "audio/flac", 2),
        "transcribed": (encoded, "audio/flac", 2, ()),
    }


def test_encoded_multichannel_probe_unavailable_is_retryable_503(
    icoder_client,
    monkeypatch,
):
    from app.services.prerecorded_media_decoder import PrerecordedMediaDecoderError

    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"synthetic-encoded-stereo",
        headers={"Content-Type": "audio/ogg"},
    )

    async def unavailable(*_args, **_kwargs):
        raise PrerecordedMediaDecoderError(
            "multichannel_media_probe_unavailable", transient=True
        )

    monkeypatch.setattr(
        "app.services.stt_service.validate_prerecorded_multichannel_audio",
        unavailable,
    )
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "requestid": response.json()["detail"]["requestid"],
        "status": 503,
        "type": "stt_media_decoder_unavailable",
        "detail": "The isolated prerecorded media decoder is temporarily unavailable.",
        "reason": "multichannel_media_probe_unavailable",
    }


@pytest.mark.parametrize(
    "media_type",
    ["audio/opus", "audio/vorbis", "audio/mp3", "audio/mpeg3", "audio/flac", "audio/m4a"],
)
def test_recording_upload_accepts_current_corti_audio_media_types(icoder_client, media_type):
    interaction_id = _interaction()
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"declared-audio-container",
        headers={"Content-Type": media_type},
    )

    assert response.status_code == 201, response.text


def test_recording_upload_rejects_non_audio_media_type(icoder_client, monkeypatch):
    monkeypatch.delenv("ICODER_ENABLE_PROTOCOL_FIXTURES", raising=False)
    interaction_id = _interaction()
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b'{"not":"audio"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["type"] == "unsupported_media_type"
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    ).json() == {"recordings": []}


def test_recording_upload_rejects_declared_oversize_before_reading_body(icoder_client):
    interaction_id = _interaction()
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"small-body",
        headers={
            "Content-Type": "audio/wav",
            "Content-Length": str(150 * 1024 * 1024 + 1),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["type"] == "recording_too_large"


def test_transcript_request_schema_enforces_documented_limits(icoder_client):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    too_many = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "replacements": [
                {"find": f"term-{index}", "replace": "x"}
                for index in range(1001)
            ],
        },
    )
    empty_find = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "replacements": [{"find": "", "replace": "x"}],
        },
    )
    too_many_keyterms = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "keyterms": {
                "terms": [{"term": f"term-{index}"} for index in range(1001)],
            },
        },
    )
    oversized_keyterm = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "keyterms": {"terms": [{"term": "术" * 51}]},
        },
    )

    assert too_many.status_code == 422
    assert empty_find.status_code == 422
    assert too_many_keyterms.status_code == 422
    assert oversized_keyterm.status_code == 422


def test_real_transcription_fails_closed_when_engine_is_unavailable(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"not-real-audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def unavailable(_content: bytes, _media_type: str):
        return "", "FunASR and Whisper are unavailable"

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", unavailable)
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": recording_id, "primaryLanguage": "zh-CN"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["type"] == "stt_unavailable"
    assert icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/"
    ).json() == {"transcripts": []}


def test_real_pipeline_rejects_language_it_does_not_support(icoder_client):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": recording_id, "primaryLanguage": "en"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["type"] == "unsupported_language"


def test_async_transcription_uses_persisted_job_and_location_header(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"async-audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    observed = {}

    async def transcribe(_content: bytes, _media_type: str, *, keyterms):
        observed["keyterms"] = keyterms
        return "异步转录完成 句号", ""

    monkeypatch.setattr("app.services.stt_jobs.transcribe_bytes", transcribe)
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "async": True,
            "isDictation": True,
            "keyterms": {
                "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
            },
        },
    )

    assert created.status_code == 202, created.text
    transcript_id = created.json()["id"]
    assert created.json()["status"] == "processing"
    assert created.headers["location"].endswith(f"/{transcript_id}/status")

    status = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert status.json() == {"status": "completed"}
    transcript = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    ).json()
    assert transcript["transcripts"][0]["text"] == "异步转录完成。"
    assert observed["keyterms"] == ("房颤", "Corti Health")


def test_async_multichannel_transcription_preserves_channel_attribution(
    icoder_client,
    monkeypatch,
):
    from app.services.stt_service import STTChannelTranscript

    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=_stereo_pcm_wav(),
        headers={"Content-Type": "audio/wav"},
    )
    observed: dict[str, object] = {}

    async def transcribe(content, media_type, *, expected_channels, keyterms):
        observed.update(
            media_type=media_type,
            expected_channels=expected_channels,
            keyterms=keyterms,
        )
        return (
            [
                STTChannelTranscript(0, "医生异步声道", 0, 20),
                STTChannelTranscript(1, "患者异步声道", 0, 20),
            ],
            "",
            {},
        )

    monkeypatch.setattr(
        "app.services.stt_jobs.transcribe_multichannel_bytes_with_telemetry",
        transcribe,
    )
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "async": True,
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
        },
    )

    assert created.status_code == 202, created.text
    fetched = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{created.json()['id']}"
    ).json()
    assert [(row["channel"], row["participant"], row["text"]) for row in fetched["transcripts"]] == [
        (0, 0, "医生异步声道"),
        (1, 1, "患者异步声道"),
    ]
    assert observed == {
        "media_type": "audio/wav",
        "expected_channels": 2,
        "keyterms": (),
    }


def test_async_current_punctuation_field_overrides_legacy_dictation(
    icoder_client,
    monkeypatch,
):
    interaction_id = _interaction()
    upload = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"async-audio",
        headers={"Content-Type": "audio/wav"},
    )
    recording_id = upload.json()["recordingId"]

    async def transcribe(_content: bytes, _media_type: str):
        return "异步转录完成 句号", ""

    monkeypatch.setattr("app.services.stt_jobs.transcribe_bytes", transcribe)
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={
            "recordingId": recording_id,
            "primaryLanguage": "zh-CN",
            "async": True,
            "isDictation": True,
            "spokenPunctuation": False,
        },
    )

    assert created.status_code == 202, created.text
    transcript_id = created.json()["id"]
    transcript = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    ).json()
    assert transcript["transcripts"][0]["text"] == "异步转录完成 句号"
