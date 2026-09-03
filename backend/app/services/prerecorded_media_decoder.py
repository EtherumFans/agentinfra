"""Isolated, bounded decoding for prerecorded multichannel audio.

The API process never imports native codec libraries. Untrusted containers are
probed and decoded in separate ffprobe/ffmpeg processes with a minimal
credential-free environment, an explicit pipe/file protocol allowlist, one
worker thread, bounded concurrency and wall-clock deadlines. Only two mono PCM
WAV paths and content-free metadata cross the boundary.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import wave
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from app.config import settings


SUPPORTED_ENCODED_RECORDING_MEDIA_TYPES = frozenset(
    {
        "audio/ogg",
        "audio/webm",
        "audio/opus",
        "audio/vorbis",
        "audio/mpeg",
        "audio/mp3",
        "audio/mpeg3",
        "audio/flac",
        "audio/mp4",
        "audio/m4a",
    }
)

_MAX_INPUT_BYTES = 150 * 1024 * 1024
_MAX_PROBE_OUTPUT_BYTES = 16 * 1024
_OUTPUT_SAMPLE_RATE = 16_000
_OUTPUT_SAMPLE_WIDTH = 2
_EXPECTED_CHANNELS = 2
_DURATION_OVERREAD_MILLISECONDS = 250
_MAX_WAV_CONTAINER_OVERHEAD_BYTES = 4_096


@dataclass(frozen=True, slots=True)
class PrerecordedMediaInfo:
    channels: int
    sample_rate: int
    duration_ms: int | None
    codec_name: str
    format_name: str


@dataclass(frozen=True, slots=True)
class DecodedPrerecordedAudio:
    channel_paths: tuple[str, str]
    duration_ms: int


class PrerecordedMediaDecoderError(RuntimeError):
    """Content-free failure suitable for stable API/job classification."""

    def __init__(self, reason: str, *, transient: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.transient = transient


_limiter_lock = threading.Lock()
_limiters: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_metrics_lock = threading.Lock()
_metrics = {
    "probe_attempts": 0,
    "decode_attempts": 0,
    "active": 0,
    "maximum_active": 0,
    "complete": 0,
    "invalid": 0,
    "unavailable": 0,
    "timeout": 0,
    "busy": 0,
    "cancelled": 0,
}


def _bounded_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if minimum <= parsed <= maximum else default


def _decoder_timeout_seconds() -> float:
    return _bounded_float(
        settings.ICODER_TRANSCRIPTS_MEDIA_DECODER_TIMEOUT_SECONDS,
        default=120.0,
        minimum=5.0,
        maximum=600.0,
    )


def _probe_timeout_seconds() -> float:
    return _bounded_float(
        settings.ICODER_TRANSCRIPTS_MEDIA_PROBE_TIMEOUT_SECONDS,
        default=10.0,
        minimum=1.0,
        maximum=60.0,
    )


def _queue_timeout_seconds() -> float:
    return _bounded_float(
        settings.ICODER_TRANSCRIPTS_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS,
        default=1.0,
        minimum=0.05,
        maximum=10.0,
    )


def _max_duration_seconds() -> int:
    try:
        value = int(settings.ICODER_TRANSCRIPTS_MAX_DURATION_SECONDS)
    except (TypeError, ValueError, OverflowError):
        return 7_200
    return value if 1 <= value <= 7_200 else 7_200


def _max_concurrency() -> int:
    try:
        value = int(settings.ICODER_TRANSCRIPTS_MEDIA_DECODER_MAX_CONCURRENCY)
    except (TypeError, ValueError, OverflowError):
        return 2
    return value if 1 <= value <= 8 else 2


def _resolve_executable(configured_value: object, *, allowed_names: set[str]) -> str | None:
    configured = str(configured_value or "").strip()
    if not configured or len(configured) > 512 or any(
        character in configured for character in ("\x00", "\r", "\n")
    ):
        return None
    candidate = Path(configured)
    if candidate.is_absolute():
        return str(candidate) if candidate.is_file() else None
    if candidate.name != configured or configured.casefold() not in allowed_names:
        return None
    return shutil.which(configured)


def _resolve_decoder_path() -> str | None:
    return _resolve_executable(
        settings.ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH,
        allowed_names={"ffmpeg", "ffmpeg.exe"},
    )


def _resolve_probe_path() -> str | None:
    return _resolve_executable(
        settings.ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH,
        allowed_names={"ffprobe", "ffprobe.exe"},
    )


def _limiter() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    limit = _max_concurrency()
    with _limiter_lock:
        entry = _limiters.get(loop)
        if entry is None or entry[0] != limit:
            entry = (limit, asyncio.Semaphore(limit))
            _limiters[loop] = entry
        return entry[1]


def _record(name: str, amount: int = 1) -> None:
    with _metrics_lock:
        _metrics[name] = max(0, _metrics[name] + amount)
        if name == "active":
            _metrics["maximum_active"] = max(
                _metrics["maximum_active"], _metrics["active"]
            )


def prerecorded_media_decoder_snapshot() -> dict[str, object]:
    with _metrics_lock:
        counters = dict(_metrics)
    return {
        "schema": "icoder/prerecorded-media-decoder-health/v1",
        "decoder_ready": _resolve_decoder_path() is not None,
        "probe_ready": _resolve_probe_path() is not None,
        "maximum_concurrency": _max_concurrency(),
        "queue_timeout_seconds": _queue_timeout_seconds(),
        "probe_timeout_seconds": _probe_timeout_seconds(),
        "decode_timeout_seconds": _decoder_timeout_seconds(),
        "maximum_duration_seconds": _max_duration_seconds(),
        **counters,
    }


def reset_prerecorded_media_decoder_state_for_tests() -> None:
    with _limiter_lock:
        _limiters.clear()
    with _metrics_lock:
        for key in _metrics:
            _metrics[key] = 0


def _minimal_environment(executable: str) -> dict[str, str]:
    environment = {"PATH": str(Path(executable).resolve().parent)}
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    else:
        environment["LANG"] = "C"
        environment["LC_ALL"] = "C"
    return environment


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = getattr(asyncio.subprocess, "CREATE_NO_WINDOW", 0)
    if flags:
        return flags
    import subprocess

    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


async def _kill_and_wait(process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await asyncio.shield(process.wait())


async def _acquire_limiter() -> asyncio.Semaphore:
    limiter = _limiter()
    try:
        await asyncio.wait_for(limiter.acquire(), timeout=_queue_timeout_seconds())
    except asyncio.TimeoutError as exc:
        _record("busy")
        raise PrerecordedMediaDecoderError(
            "multichannel_media_decoder_busy", transient=True
        ) from exc
    _record("active")
    return limiter


def _normalized_media_type(media_type: str) -> str:
    return (media_type or "").split(";", 1)[0].strip().casefold()


def _validate_declared_container(
    media_type: str,
    *,
    codec_name: str,
    format_name: str,
) -> None:
    formats = {item.strip().casefold() for item in format_name.split(",") if item.strip()}
    codec = codec_name.casefold()
    valid = False
    if media_type == "audio/ogg":
        valid = "ogg" in formats and codec in {"opus", "vorbis", "flac"}
    elif media_type == "audio/webm":
        valid = bool(formats & {"matroska", "webm"}) and codec in {"opus", "vorbis"}
    elif media_type == "audio/opus":
        valid = "ogg" in formats and codec == "opus"
    elif media_type == "audio/vorbis":
        valid = "ogg" in formats and codec == "vorbis"
    elif media_type in {"audio/mpeg", "audio/mp3", "audio/mpeg3"}:
        valid = "mp3" in formats and codec == "mp3"
    elif media_type == "audio/flac":
        valid = "flac" in formats and codec == "flac"
    elif media_type in {"audio/mp4", "audio/m4a"}:
        valid = bool(formats & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}) and codec in {
            "aac",
            "mp3",
        }
    if not valid:
        raise PrerecordedMediaDecoderError("multichannel_media_type_mismatch")


def _parse_positive_int(value: object, *, reason: str) -> int:
    if isinstance(value, bool):
        raise PrerecordedMediaDecoderError(reason)
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PrerecordedMediaDecoderError(reason) from exc
    if parsed <= 0:
        raise PrerecordedMediaDecoderError(reason)
    return parsed


def _parse_duration_ms(*values: object) -> int | None:
    for value in values:
        if value in (None, "", "N/A"):
            continue
        try:
            seconds = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if seconds <= 0:
            raise PrerecordedMediaDecoderError("multichannel_media_duration_invalid")
        duration_ms = max(1, round(seconds * 1000))
        if duration_ms > _max_duration_seconds() * 1000:
            raise PrerecordedMediaDecoderError("multichannel_media_duration_exceeded")
        return duration_ms
    return None


async def probe_prerecorded_multichannel_audio(
    audio: bytes,
    *,
    media_type: str,
) -> PrerecordedMediaInfo:
    """Return bounded metadata for the first audio stream without decoding in-process."""

    _record("probe_attempts")
    normalized = _normalized_media_type(media_type)
    if normalized not in SUPPORTED_ENCODED_RECORDING_MEDIA_TYPES:
        _record("invalid")
        raise PrerecordedMediaDecoderError("multichannel_encoded_media_type_required")
    if not audio or len(audio) > _MAX_INPUT_BYTES:
        _record("invalid")
        raise PrerecordedMediaDecoderError("multichannel_media_size_invalid")
    probe = _resolve_probe_path()
    if probe is None:
        _record("unavailable")
        raise PrerecordedMediaDecoderError(
            "multichannel_media_probe_unavailable", transient=True
        )

    limiter = await _acquire_limiter()
    process = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                probe,
                "-v",
                "error",
                "-protocol_whitelist",
                "pipe",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,codec_type,channels,sample_rate,duration:format=format_name,duration",
                "-of",
                "json",
                "pipe:0",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=_minimal_environment(probe),
                close_fds=True,
                creationflags=_creation_flags(),
            )
        except (OSError, ValueError) as exc:
            _record("unavailable")
            raise PrerecordedMediaDecoderError(
                "multichannel_media_probe_unavailable", transient=True
            ) from exc
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(input=audio), timeout=_probe_timeout_seconds()
            )
        except asyncio.TimeoutError as exc:
            await _kill_and_wait(process)
            _record("timeout")
            raise PrerecordedMediaDecoderError(
                "multichannel_media_probe_timeout", transient=True
            ) from exc
        except asyncio.CancelledError:
            await _kill_and_wait(process)
            _record("cancelled")
            raise
        if process.returncode != 0 or not stdout or len(stdout) > _MAX_PROBE_OUTPUT_BYTES:
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_media_probe_failed")
        try:
            payload = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_media_probe_invalid") from exc
        streams = payload.get("streams") if isinstance(payload, dict) else None
        if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_audio_stream_missing")
        stream = streams[0]
        channels = _parse_positive_int(
            stream.get("channels"), reason="multichannel_channel_count_invalid"
        )
        if channels != _EXPECTED_CHANNELS:
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_channel_count_mismatch")
        sample_rate = _parse_positive_int(
            stream.get("sample_rate"), reason="multichannel_sample_rate_invalid"
        )
        codec_name = str(stream.get("codec_name") or "").strip().casefold()
        format_payload = payload.get("format")
        format_payload = format_payload if isinstance(format_payload, dict) else {}
        format_name = str(format_payload.get("format_name") or "").strip().casefold()
        if not codec_name or not format_name:
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_media_identity_missing")
        try:
            _validate_declared_container(
                normalized, codec_name=codec_name, format_name=format_name
            )
            duration_ms = _parse_duration_ms(
                stream.get("duration"), format_payload.get("duration")
            )
        except PrerecordedMediaDecoderError:
            _record("invalid")
            raise
        return PrerecordedMediaInfo(
            channels=channels,
            sample_rate=sample_rate,
            duration_ms=duration_ms,
            codec_name=codec_name,
            format_name=format_name,
        )
    finally:
        _record("active", -1)
        limiter.release()


def _new_channel_paths() -> tuple[str, str]:
    paths: list[str] = []
    try:
        for channel in range(_EXPECTED_CHANNELS):
            handle = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"-decoded-channel-{channel}.wav"
            )
            paths.append(handle.name)
            handle.close()
        return paths[0], paths[1]
    except Exception:
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def _remove_paths(paths: tuple[str, str]) -> None:
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass


def _inspect_decoded_channels(paths: tuple[str, str]) -> int:
    frame_counts: list[int] = []
    maximum_frames = _max_duration_seconds() * _OUTPUT_SAMPLE_RATE
    for path in paths:
        try:
            with wave.open(path, "rb") as reader:
                channels = reader.getnchannels()
                sample_rate = reader.getframerate()
                sample_width = reader.getsampwidth()
                frame_count = reader.getnframes()
                compression = reader.getcomptype()
        except (EOFError, OSError, wave.Error) as exc:
            raise PrerecordedMediaDecoderError("multichannel_decoded_wav_invalid") from exc
        if (
            channels != 1
            or sample_rate != _OUTPUT_SAMPLE_RATE
            or sample_width != _OUTPUT_SAMPLE_WIDTH
            or compression != "NONE"
            or frame_count <= 0
        ):
            raise PrerecordedMediaDecoderError("multichannel_decoded_pcm_invalid")
        if frame_count > maximum_frames:
            raise PrerecordedMediaDecoderError("multichannel_media_duration_exceeded")
        # FFmpeg may emit WAVEFORMATEXTENSIBLE/LIST chunks instead of the
        # canonical 44-byte PCM header. Bound payload bytes exactly and allow
        # only a small fixed amount of container metadata.
        maximum_bytes = (
            maximum_frames * _OUTPUT_SAMPLE_WIDTH
            + _MAX_WAV_CONTAINER_OVERHEAD_BYTES
        )
        if Path(path).stat().st_size > maximum_bytes:
            raise PrerecordedMediaDecoderError("multichannel_decoded_size_exceeded")
        frame_counts.append(frame_count)
    if frame_counts[0] != frame_counts[1]:
        raise PrerecordedMediaDecoderError("multichannel_channel_alignment_mismatch")
    return max(1, round(frame_counts[0] * 1000 / _OUTPUT_SAMPLE_RATE))


async def decode_prerecorded_multichannel_audio(
    audio: bytes,
    *,
    media_type: str,
) -> DecodedPrerecordedAudio:
    """Decode a declared two-channel container into two aligned mono PCM WAVs."""

    await probe_prerecorded_multichannel_audio(audio, media_type=media_type)
    _record("decode_attempts")
    decoder = _resolve_decoder_path()
    if decoder is None:
        _record("unavailable")
        raise PrerecordedMediaDecoderError(
            "multichannel_media_decoder_unavailable", transient=True
        )
    paths = _new_channel_paths()
    limiter = await _acquire_limiter()
    process = None
    try:
        maximum_seconds = _max_duration_seconds() + (
            _DURATION_OVERREAD_MILLISECONDS / 1000
        )
        filter_graph = (
            "[0:a:0]channelmap=map=0|1:channel_layout=stereo,"
            "aresample=16000,channelsplit=channel_layout=stereo[ch0][ch1]"
        )
        command = [
            decoder,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-protocol_whitelist",
            "pipe",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-max_alloc",
            "67108864",
            "-probesize",
            "8388608",
            "-analyzeduration",
            "10000000",
            "-i",
            "pipe:0",
            "-filter_complex",
            filter_graph,
        ]
        for channel, path in enumerate(paths):
            command.extend(
                [
                    "-map",
                    f"[ch{channel}]",
                    "-t",
                    f"{maximum_seconds:.3f}",
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                    "-vn",
                    "-sn",
                    "-dn",
                    "-ac",
                    "1",
                    "-ar",
                    str(_OUTPUT_SAMPLE_RATE),
                    "-sample_fmt",
                    "s16",
                    "-c:a",
                    "pcm_s16le",
                    "-f",
                    "wav",
                    path,
                ]
            )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=_minimal_environment(decoder),
                close_fds=True,
                creationflags=_creation_flags(),
            )
        except (OSError, ValueError) as exc:
            _record("unavailable")
            raise PrerecordedMediaDecoderError(
                "multichannel_media_decoder_unavailable", transient=True
            ) from exc
        try:
            await asyncio.wait_for(
                process.communicate(input=audio), timeout=_decoder_timeout_seconds()
            )
        except asyncio.TimeoutError as exc:
            await _kill_and_wait(process)
            _record("timeout")
            raise PrerecordedMediaDecoderError(
                "multichannel_media_decode_timeout", transient=True
            ) from exc
        except asyncio.CancelledError:
            await _kill_and_wait(process)
            _record("cancelled")
            raise
        if process.returncode != 0:
            _record("invalid")
            raise PrerecordedMediaDecoderError("multichannel_media_decode_failed")
        duration_ms = _inspect_decoded_channels(paths)
        _record("complete")
        return DecodedPrerecordedAudio(
            channel_paths=paths,
            duration_ms=duration_ms,
        )
    except Exception:
        _remove_paths(paths)
        raise
    finally:
        _record("active", -1)
        limiter.release()


@asynccontextmanager
async def decoded_prerecorded_multichannel_wavs(
    audio: bytes,
    *,
    media_type: str,
) -> AsyncIterator[DecodedPrerecordedAudio]:
    decoded = await decode_prerecorded_multichannel_audio(audio, media_type=media_type)
    try:
        yield decoded
    finally:
        _remove_paths(decoded.channel_paths)


__all__ = [
    "DecodedPrerecordedAudio",
    "PrerecordedMediaDecoderError",
    "PrerecordedMediaInfo",
    "SUPPORTED_ENCODED_RECORDING_MEDIA_TYPES",
    "decode_prerecorded_multichannel_audio",
    "decoded_prerecorded_multichannel_wavs",
    "prerecorded_media_decoder_snapshot",
    "probe_prerecorded_multichannel_audio",
    "reset_prerecorded_media_decoder_state_for_tests",
]
