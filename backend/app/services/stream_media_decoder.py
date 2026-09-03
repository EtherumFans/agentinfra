"""Isolated, bounded decoder validation for streamed clinical audio.

Container signatures are necessary but not sufficient: malformed media can
carry a plausible header.  This module asks an external ffmpeg process to
decode exactly one audio frame under strict probe, thread, output and wall-time
bounds.  Audio is provided over stdin, stdout/stderr are discarded, and no
clinical bytes or decoder diagnostics enter application logs.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import threading
import weakref
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.config import settings
from app.services.stream_audio_format import parse_declared_stream_audio_format


class StreamMediaDecodeStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class StreamMediaDecodeResult:
    status: StreamMediaDecodeStatus


_limiter_lock = threading.Lock()
_limiters: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_metrics_lock = threading.Lock()
_metrics = {
    "attempts": 0,
    "active": 0,
    "maximum_active": 0,
    "valid": 0,
    "invalid": 0,
    "unavailable": 0,
    "timeout": 0,
    "busy": 0,
    "cancelled": 0,
}


def _validation_mode() -> str:
    mode = str(settings.ICODER_STREAM_MEDIA_VALIDATION_MODE or "").strip().casefold()
    return mode if mode in {"decoder", "header_only"} else "invalid"


def _resolve_decoder_path() -> str | None:
    configured = str(settings.ICODER_STREAM_MEDIA_DECODER_PATH or "").strip()
    if not configured or len(configured) > 512 or any(
        character in configured for character in ("\x00", "\r", "\n")
    ):
        return None
    candidate = Path(configured)
    if candidate.is_absolute():
        return str(candidate) if candidate.is_file() else None
    if candidate.name != configured or configured in {".", ".."}:
        return None
    return shutil.which(configured)


def _decoder_timeout_seconds() -> float:
    try:
        timeout = float(settings.ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS)
    except (TypeError, ValueError, OverflowError):
        return 3.0
    return timeout if 0.25 <= timeout <= 10.0 else 3.0


def _decoder_max_concurrency() -> int:
    try:
        value = int(settings.ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY)
    except (TypeError, ValueError, OverflowError):
        return 2
    return value if 1 <= value <= 16 else 2


def _decoder_queue_timeout_seconds() -> float:
    try:
        value = float(settings.ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS)
    except (TypeError, ValueError, OverflowError):
        return 0.5
    return value if 0.05 <= value <= 5.0 else 0.5


def _decoder_limiter() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    limit = _decoder_max_concurrency()
    with _limiter_lock:
        entry = _limiters.get(loop)
        if entry is None or entry[0] != limit:
            entry = (limit, asyncio.Semaphore(limit))
            _limiters[loop] = entry
        return entry[1]


def _record_attempt() -> None:
    with _metrics_lock:
        _metrics["attempts"] += 1


def _record_active(delta: int) -> None:
    with _metrics_lock:
        _metrics["active"] = max(0, _metrics["active"] + delta)
        _metrics["maximum_active"] = max(
            _metrics["maximum_active"],
            _metrics["active"],
        )


def _result(status: StreamMediaDecodeStatus) -> StreamMediaDecodeResult:
    with _metrics_lock:
        _metrics[status.value] += 1
    return StreamMediaDecodeResult(status)


def stream_media_decoder_snapshot() -> dict[str, object]:
    with _metrics_lock:
        counters = dict(_metrics)
    return {
        "schema": "icoder/stream-media-decoder-health/v1",
        "mode": _validation_mode(),
        "decoder_ready": _resolve_decoder_path() is not None,
        "maximum_concurrency": _decoder_max_concurrency(),
        "queue_timeout_seconds": _decoder_queue_timeout_seconds(),
        "decode_timeout_seconds": _decoder_timeout_seconds(),
        **counters,
    }


def reset_stream_media_decoder_state_for_tests() -> None:
    with _limiter_lock:
        _limiters.clear()
    with _metrics_lock:
        for key in _metrics:
            _metrics[key] = 0


def _decoder_environment(decoder: str) -> dict[str, str]:
    """Pass only process-runtime essentials, never application credentials."""

    environment = {"PATH": str(Path(decoder).resolve().parent)}
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    else:
        environment["LANG"] = "C"
        environment["LC_ALL"] = "C"
    return environment


async def _kill_and_wait(process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await asyncio.shield(process.wait())


async def validate_stream_audio_decode(
    audio: bytes,
    *,
    media_type: str,
) -> StreamMediaDecodeResult:
    """Decode one frame without retaining media or decoder output."""

    _record_attempt()
    if _validation_mode() == "header_only":
        return _result(StreamMediaDecodeStatus.VALID)
    if _validation_mode() != "decoder" or not audio or not media_type.startswith("audio/"):
        return _result(StreamMediaDecodeStatus.INVALID)

    decoder = _resolve_decoder_path()
    if decoder is None:
        return _result(StreamMediaDecodeStatus.UNAVAILABLE)

    input_arguments: list[str] = []
    if media_type.casefold().startswith("audio/pcm"):
        try:
            declared = parse_declared_stream_audio_format(media_type)
        except ValueError:
            return _result(StreamMediaDecodeStatus.INVALID)
        if (
            declared is None
            or declared.container != "pcm"
            or declared.rate != 16000
            or declared.channels is None
            or not 1 <= declared.channels <= 8
            or declared.bits != 16
            or declared.endian != "little"
            or declared.encoding != "sint"
        ):
            return _result(StreamMediaDecodeStatus.INVALID)
        input_arguments = [
            "-f", "s16le", "-ar", "16000", "-ac", str(declared.channels),
        ]

    limiter = _decoder_limiter()
    try:
        await asyncio.wait_for(
            limiter.acquire(),
            timeout=_decoder_queue_timeout_seconds(),
        )
    except asyncio.TimeoutError:
        return _result(StreamMediaDecodeStatus.BUSY)
    _record_active(1)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(asyncio.subprocess, "CREATE_NO_WINDOW", 0)
        if creation_flags == 0:
            import subprocess

            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    process = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                decoder,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "pipe",
                "-threads",
                "1",
                "-max_alloc",
                "67108864",
                "-probesize",
                "1048576",
                "-analyzeduration",
                "1000000",
                *input_arguments,
                "-i",
                "pipe:0",
                "-map",
                "0:a:0",
                "-frames:a",
                "1",
                "-vn",
                "-sn",
                "-dn",
                "-f",
                "null",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=_decoder_environment(decoder),
                close_fds=True,
                creationflags=creation_flags,
            )
        except (OSError, ValueError):
            return _result(StreamMediaDecodeStatus.UNAVAILABLE)

        try:
            await asyncio.wait_for(
                process.communicate(input=audio),
                timeout=_decoder_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            await _kill_and_wait(process)
            return _result(StreamMediaDecodeStatus.TIMEOUT)
        except (BrokenPipeError, ConnectionResetError):
            await process.wait()
        except asyncio.CancelledError:
            await _kill_and_wait(process)
            with _metrics_lock:
                _metrics["cancelled"] += 1
            raise

        return _result(
            StreamMediaDecodeStatus.VALID
            if process.returncode == 0
            else StreamMediaDecodeStatus.INVALID
        )
    finally:
        _record_active(-1)
        limiter.release()


__all__ = [
    "StreamMediaDecodeResult",
    "StreamMediaDecodeStatus",
    "reset_stream_media_decoder_state_for_tests",
    "stream_media_decoder_snapshot",
    "validate_stream_audio_decode",
]
