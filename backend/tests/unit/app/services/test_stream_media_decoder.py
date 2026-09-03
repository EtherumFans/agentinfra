from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from app.services.stream_media_decoder import (
    StreamMediaDecodeStatus,
    reset_stream_media_decoder_state_for_tests,
    stream_media_decoder_snapshot,
    validate_stream_audio_decode,
)


@pytest.fixture(autouse=True)
def reset_decoder_state():
    reset_stream_media_decoder_state_for_tests()
    yield
    reset_stream_media_decoder_state_for_tests()


@pytest.mark.asyncio
async def test_header_only_is_explicit_local_escape_hatch(monkeypatch):
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "header_only")
    result = await validate_stream_audio_decode(b"not decoded", media_type="audio/ogg")
    assert result.status == StreamMediaDecodeStatus.VALID


@pytest.mark.asyncio
async def test_missing_decoder_fails_closed_without_spawning(monkeypatch):
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "missing-ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: None)

    result = await validate_stream_audio_decode(b"OggS-data", media_type="audio/ogg")

    assert result.status == StreamMediaDecodeStatus.UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returncode", "expected"),
    [
        (0, StreamMediaDecodeStatus.VALID),
        (1, StreamMediaDecodeStatus.INVALID),
    ],
)
async def test_decoder_result_is_bounded_and_content_free(
    monkeypatch,
    returncode,
    expected,
):
    audio = b"OggS-private-clinical-audio"
    captured: dict[str, object] = {}

    class Process:
        def __init__(self):
            self.returncode = returncode

        async def communicate(self, *, input):
            captured["input"] = input

    async def create(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-secret-must-not-be-inherited")
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    result = await validate_stream_audio_decode(audio, media_type="audio/ogg")

    assert result.status == expected
    assert captured["input"] == audio
    assert audio.decode("ascii") not in " ".join(captured["args"])
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL
    assert "ICODER_CREDENTIAL_LLM" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["close_fds"] is True
    assert "-protocol_whitelist" in captured["args"]
    assert captured["args"].count("-frames:a") == 1


@pytest.mark.asyncio
async def test_recommended_pcm_profile_has_fixed_server_derived_decoder_arguments(monkeypatch):
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self, *, input):
            captured["input"] = input

    async def create(*args, **_kwargs):
        captured["args"] = args
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    result = await validate_stream_audio_decode(
        b"\x00\x00" * 4000,
        media_type=(
            "audio/pcm; rate=16000; channels=1; bits=16; "
            "endian=little; encoding=sint"
        ),
    )

    assert result.status == StreamMediaDecodeStatus.VALID
    args = captured["args"]
    input_index = args.index("-i")
    assert args[input_index - 6:input_index] == (
        "-f", "s16le", "-ar", "16000", "-ac", "1"
    )
    assert captured["input"] == b"\x00\x00" * 4000


@pytest.mark.asyncio
async def test_multichannel_pcm_uses_declared_bounded_channel_count(monkeypatch):
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self, *, input):
            captured["input"] = input

    async def create(*args, **_kwargs):
        captured["args"] = args
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    payload = b"\x00\x00\x01\x00" * 4000
    result = await validate_stream_audio_decode(
        payload,
        media_type=(
            "audio/pcm; rate=16000; channels=2; bits=16; "
            "endian=little; encoding=sint"
        ),
    )

    assert result.status == StreamMediaDecodeStatus.VALID
    args = captured["args"]
    input_index = args.index("-i")
    assert args[input_index - 6:input_index] == (
        "-f", "s16le", "-ar", "16000", "-ac", "2"
    )
    assert captured["input"] == payload


@pytest.mark.asyncio
async def test_decoder_timeout_kills_and_reaps_process(monkeypatch):
    state = {"killed": False, "waited": False}

    class Process:
        returncode = None

        async def communicate(self, *, input):
            await asyncio.Future()

        def kill(self):
            state["killed"] = True

        async def wait(self):
            state["waited"] = True

    async def create(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS", 0.25)
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    result = await validate_stream_audio_decode(b"OggS-data", media_type="audio/ogg")

    assert result.status == StreamMediaDecodeStatus.TIMEOUT
    assert state == {"killed": True, "waited": True}


@pytest.mark.asyncio
async def test_decoder_concurrency_is_bounded_and_queue_fails_busy(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    class Process:
        returncode = None

        async def communicate(self, *, input):
            started.set()
            await release.wait()
            self.returncode = 0

    async def create(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY", 1)
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    first_task = asyncio.create_task(
        validate_stream_audio_decode(b"OggS-first", media_type="audio/ogg")
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    second = await validate_stream_audio_decode(b"OggS-second", media_type="audio/ogg")
    release.set()
    first = await asyncio.wait_for(first_task, timeout=1)

    assert first.status == StreamMediaDecodeStatus.VALID
    assert second.status == StreamMediaDecodeStatus.BUSY
    snapshot = stream_media_decoder_snapshot()
    assert snapshot["maximum_active"] == 1
    assert snapshot["active"] == 0
    assert snapshot["busy"] == 1


@pytest.mark.asyncio
async def test_cancellation_kills_reaps_and_releases_capacity(monkeypatch):
    started = asyncio.Event()
    state = {"killed": False, "waited": False}

    class Process:
        returncode = None

        async def communicate(self, *, input):
            started.set()
            await asyncio.Future()

        def kill(self):
            state["killed"] = True

        async def wait(self):
            state["waited"] = True

    async def create(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY", 1)
    monkeypatch.setattr("app.services.stream_media_decoder.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("app.services.stream_media_decoder.asyncio.create_subprocess_exec", create)

    task = asyncio.create_task(
        validate_stream_audio_decode(b"OggS-cancel", media_type="audio/ogg")
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert state == {"killed": True, "waited": True}
    snapshot = stream_media_decoder_snapshot()
    assert snapshot["active"] == 0
    assert snapshot["cancelled"] == 1


@pytest.mark.asyncio
async def test_invalid_mode_or_media_type_never_spawns(monkeypatch):
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "unexpected")
    invalid_mode = await validate_stream_audio_decode(b"OggS", media_type="audio/ogg")
    monkeypatch.setattr(settings, "ICODER_STREAM_MEDIA_VALIDATION_MODE", "decoder")
    invalid_media = await validate_stream_audio_decode(b"OggS", media_type="text/plain")

    assert invalid_mode.status == StreamMediaDecodeStatus.INVALID
    assert invalid_media.status == StreamMediaDecodeStatus.INVALID
