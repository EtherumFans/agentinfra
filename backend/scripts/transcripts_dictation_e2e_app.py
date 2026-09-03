"""Local-only ASGI target for the prerecorded dictation E2E.

This module is never imported by the production application. It replaces the
ASR boundary with one fixed, synthetic phrase so a real Uvicorn process can
exercise auth, recording persistence, synchronous/background transcription,
dictation punctuation, ordered keyterm forwarding and retrieval without native
models or patient audio.
"""

from __future__ import annotations

import os
import struct
import wave

if os.getenv("APP_ENV", "").strip().lower() != "local":
    raise RuntimeError("dictation E2E app requires APP_ENV=local")
if os.getenv("ICODER_E2E_ALLOW_SYNTHETIC_STT", "") != "1":
    raise RuntimeError("dictation E2E synthetic STT is not explicitly enabled")

from app.main import app  # noqa: E402
from app.services import stt_jobs, stt_service  # noqa: E402

_SYNTHETIC_DICTATION_TEXT = "患者主诉胸痛 逗号 持续三天 句号 左括号 房颤 右括号"
_SYNTHETIC_KEYTERM_TEXT = "房颤患者由Corti Health随访"
_EXPECTED_KEYTERMS = ("房颤", "Corti Health")
_SYNTHETIC_CHANNEL_TEXT = {1400: "医生询问房颤", -1400: "患者回答Corti Health"}
_SYNTHETIC_CHANNEL_SEGMENTS = {
    1400: (("医生询问", 0, 40), ("房颤", 50, 90)),
    -1400: (("患者回答", 0, 45), ("Corti Health", 50, 95)),
}


async def _synthetic_transcribe_bytes(
    audio_bytes: bytes,
    media_type: str,
    *,
    keyterms=(),
) -> tuple[str, str]:
    if media_type.split(";", 1)[0].strip().lower() not in {"audio/wav", "audio/x-wav"}:
        return "", "synthetic_e2e_requires_wav"
    if len(audio_bytes) < 44 or not audio_bytes.startswith(b"RIFF"):
        return "", "synthetic_e2e_invalid_wav"
    if keyterms:
        if tuple(keyterms) != _EXPECTED_KEYTERMS:
            return "", "synthetic_e2e_keyterms_mismatch"
        text = _SYNTHETIC_KEYTERM_TEXT
    else:
        text = _SYNTHETIC_DICTATION_TEXT
    stt_service._record_stt_inference_telemetry(
        provider="local_e2e_fixture",
        model="fixed_dictation_phrase_v1",
        latency_ms=0,
        status="complete",
        fallback_used=False,
        streaming=False,
    )
    return text, ""


async def _synthetic_transcribe_audio(
    audio_path: str,
    *,
    keyterms=(),
) -> tuple[str, str]:
    """Inspect the real mono outputs produced by the stereo WAV splitter."""
    if keyterms and tuple(keyterms) != _EXPECTED_KEYTERMS:
        return "", "synthetic_e2e_keyterms_mismatch"
    try:
        with wave.open(audio_path, "rb") as reader:
            if (
                reader.getnchannels() != 1
                or reader.getsampwidth() != 2
                or reader.getframerate() != 16000
            ):
                return "", "synthetic_e2e_invalid_mono_channel"
            frames = reader.readframes(reader.getnframes())
        samples = set(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    except (OSError, EOFError, wave.Error, struct.error):
        return "", "synthetic_e2e_invalid_mono_channel"
    if len(samples) != 1:
        return "", "synthetic_e2e_channel_crosstalk"
    text = _SYNTHETIC_CHANNEL_TEXT.get(next(iter(samples)))
    if text is None:
        return "", "synthetic_e2e_unknown_channel"
    stt_service._LAST_STT_SEGMENTS.set(
        tuple(
            stt_service.STTTranscriptSegment(text=value, start_ms=start, end_ms=end)
            for value, start, end in _SYNTHETIC_CHANNEL_SEGMENTS[next(iter(samples))]
        )
    )
    stt_service._record_stt_inference_telemetry(
        provider="local_e2e_fixture",
        model="fixed_stereo_channel_v1",
        latency_ms=0,
        status="complete",
        fallback_used=False,
        streaming=False,
    )
    return text, ""


stt_service.transcribe_bytes = _synthetic_transcribe_bytes
stt_service.transcribe_audio = _synthetic_transcribe_audio
stt_jobs.transcribe_bytes = _synthetic_transcribe_bytes
