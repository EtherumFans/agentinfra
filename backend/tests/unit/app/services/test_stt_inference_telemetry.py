from __future__ import annotations

import io
import json
import os
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock
import wave

import pytest

from app.models.stt_artifact import STTTranscript
from app.services import stt_service
from app.services.phi_encryption import encrypt_phi
from app.services.stt_artifact_repository import stt_artifact_repository


def _stereo_pcm_wav(*, frames: int = 320) -> bytes:
    interleaved = [sample for _ in range(frames) for sample in (1200, -1200)]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(struct.pack("<" + "h" * len(interleaved), *interleaved))
    return buffer.getvalue()


class _Model:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error

    def generate(self, **kwargs):
        assert kwargs["language"] == "zh"
        if self.error:
            raise self.error
        return self.result


class _CapturingModel(_Model):
    def __init__(self, result=None):
        super().__init__(result=result)
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return super().generate(**kwargs)


@pytest.mark.asyncio
async def test_batch_stt_returns_content_free_actual_engine_telemetry(monkeypatch):
    monkeypatch.setattr(
        stt_service, "_get_stt_model",
        lambda: _Model([{"text": "去标识化转写"}]),
    )
    monkeypatch.setattr(stt_service, "_load_terms", lambda: [])
    monkeypatch.setattr(stt_service, "_fuzzy_correct", lambda text, **_: text)
    monkeypatch.setattr(stt_service, "_restore_punctuation", lambda text: text)

    text, error, telemetry = await stt_service.transcribe_bytes_with_telemetry(
        b"RIFF-test-audio", "audio/wav"
    )

    assert text == "去标识化转写"
    assert error == ""
    assert telemetry["schema"] == "icoder/stt-inference-telemetry/v1"
    assert telemetry["provider"] == "funasr"
    assert telemetry["model"].endswith("@v2.0.4")
    assert telemetry["status"] == "complete"
    assert telemetry["fallback_used"] is False
    assert telemetry["streaming"] is False
    assert isinstance(telemetry["latency_ms"], int)
    assert "去标识化转写" not in json.dumps(telemetry, ensure_ascii=False)
    assert "audio" not in telemetry


@pytest.mark.asyncio
async def test_batch_stt_forwards_ordered_case_sensitive_keyterms_to_funasr(monkeypatch):
    model = _CapturingModel([{"text": "房颤复诊"}])
    monkeypatch.setattr(stt_service, "_get_stt_model", lambda: model)
    monkeypatch.setattr(stt_service, "_load_terms", lambda: [])
    monkeypatch.setattr(stt_service, "_fuzzy_correct", lambda text, **_: text)
    monkeypatch.setattr(stt_service, "_restore_punctuation", lambda text: text)

    text, error, telemetry = await stt_service.transcribe_bytes_with_telemetry(
        b"RIFF-test-audio",
        "audio/wav",
        keyterms=("房颤", "Corti Health"),
    )

    assert (text, error) == ("房颤复诊", "")
    assert model.kwargs["hotword"] == ["房颤", "Corti Health"]
    assert model.kwargs["sentence_timestamp"] is True
    assert "房颤" not in json.dumps(telemetry, ensure_ascii=False)


@pytest.mark.asyncio
async def test_batch_stt_preserves_valid_phrase_timestamps_in_milliseconds(monkeypatch):
    model = _CapturingModel(
        [
            {
                "text": "医生询问。患者回答。",
                "sentence_info": [
                    {"text": "医生询问。", "start": 120, "end": 860},
                    {"text": "患者回答。", "start": 940, "end": 1710},
                ],
            }
        ]
    )
    monkeypatch.setattr(stt_service, "_get_stt_model", lambda: model)
    monkeypatch.setattr(stt_service, "_load_terms", lambda: [])
    monkeypatch.setattr(stt_service, "_fuzzy_correct", lambda text, **_: text)
    monkeypatch.setattr(stt_service, "_restore_punctuation", lambda text: text)

    text, error = await stt_service.transcribe_audio("synthetic.wav")

    assert (text, error) == ("医生询问。患者回答。", "")
    assert [
        (item.text, item.start_ms, item.end_ms)
        for item in stt_service.get_stt_transcript_segments()
    ] == [
        ("医生询问。", 120, 860),
        ("患者回答。", 940, 1710),
    ]


@pytest.mark.asyncio
async def test_multichannel_uses_phrase_rows_when_provider_timestamps_are_valid(monkeypatch):
    call = 0

    async def transcribe_channel(_path: str):
        nonlocal call
        call += 1
        if call == 1:
            stt_service._LAST_STT_SEGMENTS.set(
                (
                    stt_service.STTTranscriptSegment("医生一", 0, 6),
                    stt_service.STTTranscriptSegment("医生二", 8, 15),
                )
            )
            return "医生一医生二", ""
        stt_service._LAST_STT_SEGMENTS.set(
            (stt_service.STTTranscriptSegment("患者一", 2, 18),)
        )
        return "患者一", ""

    monkeypatch.setattr(stt_service, "transcribe_audio", transcribe_channel)
    rows, error, _telemetry = await stt_service.transcribe_multichannel_bytes_with_telemetry(
        _stereo_pcm_wav(), "audio/wav"
    )

    assert error == ""
    assert [(row.channel, row.text, row.start_ms, row.end_ms) for row in rows] == [
        (0, "医生一", 0, 6),
        (0, "医生二", 8, 15),
        (1, "患者一", 2, 18),
    ]


@pytest.mark.asyncio
async def test_multichannel_pcm_wav_is_split_and_transcribed_with_bounded_telemetry(
    monkeypatch,
):
    observed_paths: list[str] = []
    observed_samples: list[set[int]] = []

    async def transcribe_channel(path: str, *, keyterms):
        observed_paths.append(path)
        assert keyterms == ("房颤", "Corti Health")
        with wave.open(path, "rb") as reader:
            assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
                1,
                2,
                16000,
            )
            frames = reader.readframes(reader.getnframes())
        samples = set(struct.unpack("<" + "h" * (len(frames) // 2), frames))
        observed_samples.append(samples)
        stt_service._record_stt_inference_telemetry(
            provider="funasr",
            model="iic/paraformer@v2.0.4",
            latency_ms=7,
            status="complete",
            fallback_used=False,
            streaming=False,
        )
        return ("医生声道" if samples == {1200} else "患者声道"), ""

    monkeypatch.setattr(stt_service, "transcribe_audio", transcribe_channel)
    rows, error, telemetry = await stt_service.transcribe_multichannel_bytes_with_telemetry(
        _stereo_pcm_wav(),
        "audio/wav",
        expected_channels=2,
        keyterms=("房颤", "Corti Health"),
    )

    assert error == ""
    assert [(row.channel, row.text, row.start_ms, row.end_ms) for row in rows] == [
        (0, "医生声道", 0, 20),
        (1, "患者声道", 0, 20),
    ]
    assert observed_samples == [{1200}, {-1200}]
    assert telemetry == {
        "schema": "icoder/stt-inference-telemetry/v1",
        "provider": "funasr",
        "model": "iic/paraformer@v2.0.4",
        "latency_ms": 14,
        "status": "complete",
        "fallback_used": False,
        "streaming": False,
    }
    assert all(not os.path.exists(path) for path in observed_paths)


@pytest.mark.parametrize(
    ("audio", "media_type", "reason"),
    [
        (b"encoded", "audio/mpeg", "multichannel_pcm_wav_required"),
        (b"not-a-wav", "audio/wav", "multichannel_wav_invalid"),
    ],
)
def test_multichannel_audio_format_failures_are_explicit(audio, media_type, reason):
    with pytest.raises(ValueError, match=reason):
        stt_service.inspect_multichannel_pcm_wav(audio, media_type)


@pytest.mark.asyncio
async def test_batch_stt_failure_records_engine_without_error_or_audio_content(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        stt_service, "_get_stt_model",
        lambda: _Model(error=RuntimeError("patient-audio-canary")),
    )

    text, error, telemetry = await stt_service.transcribe_bytes_with_telemetry(
        b"patient-audio-canary", "audio/wav"
    )

    assert text == ""
    assert error == "Local STT transcription failed."
    assert "patient-audio-canary" not in caplog.text
    assert telemetry["provider"] == "funasr"
    assert telemetry["status"] == "failed"
    serialized = json.dumps(telemetry, ensure_ascii=False)
    assert "patient-audio-canary" not in serialized
    assert "error" not in telemetry


@pytest.mark.asyncio
async def test_repository_persists_only_bounded_stt_telemetry_allowlist():
    row = STTTranscript(
        organization_id="org-test",
        owner_id="user-test",
        interaction_id="interaction-test",
        transcript_id="transcript-test",
        recording_id="recording-test",
        encrypted_request_json=encrypt_phi(json.dumps({"primaryLanguage": "zh-CN"})),
        participant_roles_json="[]",
        status="processing",
    )
    db = SimpleNamespace(flush=AsyncMock())

    await stt_artifact_repository.set_transcript_runtime_telemetry(
        db,
        row,
        {
            "schema": "icoder/stt-inference-telemetry/v1",
            "provider": "funasr",
            "model": "iic/paraformer@v2.0.4",
            "latency_ms": 42,
            "status": "complete",
            "fallback_used": False,
            "streaming": False,
            "transcript_text": "不得持久化的临床正文",
            "error_detail": "不得持久化的错误正文",
        },
    )

    stored = stt_artifact_repository.request_data(row)["_runtimeTelemetry"]
    assert stored == {
        "schema": "icoder/stt-inference-telemetry/v1",
        "provider": "funasr",
        "model": "iic/paraformer@v2.0.4",
        "status": "complete",
        "latency_ms": 42,
        "fallback_used": False,
        "streaming": False,
    }
    db.flush.assert_awaited_once()
