from __future__ import annotations

import asyncio
import io
import json
import os
import wave

import pytest

from app.config import settings
from app.services.prerecorded_media_decoder import (
    PrerecordedMediaDecoderError,
    decoded_prerecorded_multichannel_wavs,
    probe_prerecorded_multichannel_audio,
    prerecorded_media_decoder_snapshot,
    reset_prerecorded_media_decoder_state_for_tests,
)


@pytest.fixture(autouse=True)
def reset_decoder_state():
    reset_prerecorded_media_decoder_state_for_tests()
    yield
    reset_prerecorded_media_decoder_state_for_tests()


def _probe_payload(
    *,
    channels: int = 2,
    sample_rate: int = 48_000,
    duration: str = "1.25",
    codec: str = "flac",
    format_name: str = "flac",
) -> bytes:
    return json.dumps(
        {
            "streams": [
                {
                    "codec_name": codec,
                    "codec_type": "audio",
                    "channels": channels,
                    "sample_rate": str(sample_rate),
                    "duration": duration,
                }
            ],
            "format": {"format_name": format_name, "duration": duration},
        }
    ).encode()


@pytest.mark.asyncio
async def test_probe_is_exact_two_channel_content_free_and_credential_free(monkeypatch):
    audio = b"fLaC-private-clinical-audio"
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self, *, input):
            captured["input"] = input
            return _probe_payload(), b""

    async def create(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH", "ffprobe")
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.shutil.which",
        lambda value: value,
    )
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.asyncio.create_subprocess_exec",
        create,
    )
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "must-not-reach-media-process")

    info = await probe_prerecorded_multichannel_audio(audio, media_type="audio/flac")

    assert (info.channels, info.sample_rate, info.duration_ms) == (2, 48_000, 1_250)
    assert captured["input"] == audio
    assert audio.decode() not in " ".join(captured["args"])
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL
    assert "ICODER_CREDENTIAL_LLM" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["close_fds"] is True
    assert "-protocol_whitelist" in captured["args"]
    assert "stream=codec_name,codec_type,channels,sample_rate,duration:format=format_name,duration" in captured["args"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "media_type", "reason"),
    [
        (_probe_payload(channels=1), "audio/flac", "multichannel_channel_count_mismatch"),
        (_probe_payload(channels=3), "audio/flac", "multichannel_channel_count_mismatch"),
        (_probe_payload(duration="7200.1"), "audio/flac", "multichannel_media_duration_exceeded"),
        (_probe_payload(codec="mp3", format_name="mp3"), "audio/flac", "multichannel_media_type_mismatch"),
    ],
)
async def test_probe_rejects_channel_duration_and_declared_type_mismatch(
    monkeypatch,
    payload,
    media_type,
    reason,
):
    class Process:
        returncode = 0

        async def communicate(self, *, input):
            return payload, b""

    async def create(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH", "ffprobe")
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.shutil.which", lambda value: value
    )
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.asyncio.create_subprocess_exec", create
    )

    with pytest.raises(PrerecordedMediaDecoderError, match=reason):
        await probe_prerecorded_multichannel_audio(b"encoded", media_type=media_type)


@pytest.mark.asyncio
async def test_missing_probe_is_transient_and_never_spawns(monkeypatch):
    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH", "ffprobe")
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.shutil.which", lambda _value: None
    )

    with pytest.raises(PrerecordedMediaDecoderError) as raised:
        await probe_prerecorded_multichannel_audio(b"encoded", media_type="audio/flac")

    assert raised.value.reason == "multichannel_media_probe_unavailable"
    assert raised.value.transient is True


def _write_mono_wav(path: str, *, sample: int, frames: int = 320) -> None:
    with wave.open(path, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(sample.to_bytes(2, "little", signed=True) * frames)


@pytest.mark.asyncio
async def test_decode_writes_bounded_channels_and_context_cleans_paths(monkeypatch):
    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class ProbeProcess:
        returncode = 0

        async def communicate(self, *, input):
            return _probe_payload(), b""

    class DecoderProcess:
        returncode = 0

        def __init__(self, args):
            self.args = args

        async def communicate(self, *, input):
            wav_paths = [str(item) for item in self.args if str(item).endswith(".wav")]
            assert len(wav_paths) == 2
            _write_mono_wav(wav_paths[0], sample=1200)
            _write_mono_wav(wav_paths[1], sample=-1200)
            return None, None

    async def create(*args, **kwargs):
        captured.append((args, kwargs))
        return ProbeProcess() if str(args[0]).endswith("ffprobe") else DecoderProcess(args)

    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH", "ffprobe")
    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.shutil.which", lambda value: value
    )
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.asyncio.create_subprocess_exec", create
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-reach-media-process")

    observed_paths: tuple[str, str] | None = None
    async with decoded_prerecorded_multichannel_wavs(
        b"encoded-stereo", media_type="audio/flac"
    ) as decoded:
        observed_paths = decoded.channel_paths
        assert decoded.duration_ms == 20
        assert all(os.path.exists(path) for path in observed_paths)
        decoder_args, decoder_kwargs = captured[1]
        assert "channelmap=map=0|1:channel_layout=stereo" in " ".join(decoder_args)
        assert decoder_args.count("-map") == 2
        assert decoder_kwargs["stdout"] == asyncio.subprocess.DEVNULL
        assert decoder_kwargs["stderr"] == asyncio.subprocess.DEVNULL
        assert "DEEPSEEK_API_KEY" not in decoder_kwargs["env"]
        assert decoder_kwargs["close_fds"] is True
    assert observed_paths is not None
    assert all(not os.path.exists(path) for path in observed_paths)
    snapshot = prerecorded_media_decoder_snapshot()
    assert snapshot["complete"] == 1
    assert snapshot["active"] == 0


@pytest.mark.asyncio
async def test_decode_failure_removes_all_temporary_outputs(monkeypatch):
    observed_paths: list[str] = []

    class ProbeProcess:
        returncode = 0

        async def communicate(self, *, input):
            return _probe_payload(), b""

    class DecoderProcess:
        returncode = 1

        def __init__(self, args):
            observed_paths.extend(str(item) for item in args if str(item).endswith(".wav"))

        async def communicate(self, *, input):
            return None, None

    calls = 0

    async def create(*args, **_kwargs):
        nonlocal calls
        calls += 1
        return ProbeProcess() if calls == 1 else DecoderProcess(args)

    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH", "ffprobe")
    monkeypatch.setattr(settings, "ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.shutil.which", lambda value: value
    )
    monkeypatch.setattr(
        "app.services.prerecorded_media_decoder.asyncio.create_subprocess_exec", create
    )

    with pytest.raises(PrerecordedMediaDecoderError, match="multichannel_media_decode_failed"):
        async with decoded_prerecorded_multichannel_wavs(
            b"encoded-stereo", media_type="audio/flac"
        ):
            raise AssertionError("decode failure must not yield")
    assert len(observed_paths) == 2
    assert all(not os.path.exists(path) for path in observed_paths)
