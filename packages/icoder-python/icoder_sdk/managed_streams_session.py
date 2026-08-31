"""Managed Corti-compatible Streams WebSocket session."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Optional


_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_AUDIO_BYTES = 32 * 1024 * 1024
_MAX_CHUNK_BYTES = 64_000
_STREAM_AUDIO_FORMATS = {
    "audio/ogg": "ogg", "audio/webm": "webm", "audio/opus": "ogg",
    "audio/vorbis": "ogg", "audio/mpeg": "mpeg", "audio/mp3": "mpeg",
    "audio/mpeg3": "mpeg", "audio/flac": "flac", "audio/mp4": "mp4",
    "audio/m4a": "mp4",
    "audio/pcm": "pcm",
}
_STREAM_AUDIO_CODECS = {"flac", "opus", "vorbis"}
_STREAM_AUDIO_EVENTS = {
    "speechQualityIssueDetected", "speechQualityIssueRecovered",
    "longSilenceDetected", "longSilenceRecovered",
}
_CONFIG_FAILURES = {
    "CONFIG_DENIED", "CONFIG_MISSING", "CONFIG_NOT_PROVIDED",
    "CONFIG_ALREADY_RECEIVED",
}


class ManagedStreamsSessionError(ConnectionError):
    """PHI-safe Streams failure containing only a stable code."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(f"iCoDer managed Streams session failed ({code})")
        self.code = code
        self.retryable = retryable


def _record(value: Any) -> Optional[dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _parse_message(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except Exception:
        return {"type": "unknown"}
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        return {"type": "unknown"}
    message_type = value["type"]
    if message_type == "CONFIG_ACCEPTED":
        try:
            session_id = str(uuid.UUID(str(value.get("sessionId", ""))))
        except (ValueError, TypeError, AttributeError):
            return {"type": "unknown"}
        configuration = _record(value.get("configuration"))
        if configuration is None:
            return {"type": "unknown"}
        counters = (
            value.get("restoredAudioBytes", 0),
            value.get("restoredTranscriptMessages", 0),
            value.get("restoredFactMessages", 0),
        )
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in counters
        ):
            return {"type": "unknown"}
        return {
            "type": "CONFIG_ACCEPTED",
            "sessionId": session_id,
            "configuration": configuration,
            "resumed": value.get("resumed") is True,
            "restoredAudioBytes": counters[0],
            "restoredTranscriptMessages": counters[1],
            "restoredFactMessages": counters[2],
        }
    if message_type in _CONFIG_FAILURES:
        return {"type": message_type}
    if message_type == "transcript" and isinstance(value.get("data"), list):
        return {"type": "transcript", "data": [x for x in value["data"] if isinstance(x, dict)]}
    if message_type == "facts" and isinstance(value.get("fact"), list):
        return {"type": "facts", "fact": [x for x in value["fact"] if isinstance(x, dict)]}
    if message_type == "audioEvent":
        data = _record(value.get("data")) or {}
        event = data.get("event")
        channel = data.get("channel")
        start_time = data.get("startTimeMs")
        if (
            event in _STREAM_AUDIO_EVENTS
            and isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 15
            and isinstance(start_time, int) and not isinstance(start_time, bool) and start_time >= 0
        ):
            return {
                "type": "audioEvent",
                "data": {"event": event, "channel": channel, "startTimeMs": start_time},
            }
        return {"type": "unknown"}
    if message_type in {"flushed", "ENDED"}:
        return {"type": message_type}
    if message_type in {"delta_usage", "usage"}:
        credits = value.get("credits")
        if isinstance(credits, (int, float)) and not isinstance(credits, bool) and credits >= 0:
            return {"type": message_type, "credits": float(credits)}
        return {"type": "unknown"}
    if message_type == "error":
        error = _record(value.get("error")) or {}
        code = error.get("id")
        return {
            "type": "error",
            **({"code": code} if isinstance(code, str) and _SAFE_CODE.fullmatch(code) else {}),
        }
    return {"type": "unknown"}


def _validate_configuration(configuration: dict[str, Any]) -> None:
    transcription = _record(configuration.get("transcription")) or {}
    language = transcription.get("primaryLanguage")
    if not isinstance(language, str) or not language.lower().startswith("zh"):
        raise ManagedStreamsSessionError("unsupported_primary_language")
    if transcription.get("diarize") is True or transcription.get("isDiarization") is True:
        raise ManagedStreamsSessionError("diarization_not_available")
    mode = _record(configuration.get("mode")) or {}
    if mode.get("type") not in {"facts", "transcription"}:
        raise ManagedStreamsSessionError("mode_not_available")
    if mode.get("type") == "facts" and not isinstance(mode.get("outputLocale"), str):
        raise ManagedStreamsSessionError("output_locale_required")
    keyterms = _record(configuration.get("keyterms")) or {}
    terms = keyterms.get("terms") or []
    if not isinstance(terms, list) or len(terms) > 1000:
        raise ManagedStreamsSessionError("keyterm_limit_exceeded")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("term"), str)
        or not 1 <= len(item["term"]) <= 50
        for item in terms
    ):
        raise ManagedStreamsSessionError("keyterm_invalid")
    audio_format = configuration.get("audioFormat")
    audio_profile: tuple[str, Optional[int]] | None = None
    if audio_format is not None:
        audio_profile = _validate_audio_format(audio_format)
    audio_events = _record(configuration.get("audioEvents")) or {}
    if audio_events.get("enabled") is True and (
        audio_profile is None or audio_profile[0] != "pcm"
    ):
        raise ManagedStreamsSessionError("audio_events_require_pcm")
    participants = transcription.get("participants") or []
    participant_channels = {
        item.get("channel") for item in participants if isinstance(item, dict)
    }
    if transcription.get("isMultichannel") is True:
        channels = audio_profile[1] if audio_profile and audio_profile[0] == "pcm" else None
        if channels is None or channels < 2:
            raise ManagedStreamsSessionError("multichannel_pcm_format_required")
        if participant_channels != set(range(channels)):
            raise ManagedStreamsSessionError("multichannel_participants_must_match_channels")
    else:
        if audio_profile and audio_profile[0] == "pcm" and audio_profile[1] != 1:
            raise ManagedStreamsSessionError("multichannel_flag_required")
        if any(channel != 0 for channel in participant_channels):
            raise ManagedStreamsSessionError("mono_participant_channel_required")


def _validate_audio_format(value: Any) -> tuple[str, Optional[int]]:
    if not isinstance(value, str):
        raise ManagedStreamsSessionError("audio_format_not_supported")
    parts = [part.strip() for part in value.split(";")]
    mime = parts[0].lower()
    container = _STREAM_AUDIO_FORMATS.get(mime)
    if container is None:
        raise ManagedStreamsSessionError("audio_format_not_supported")
    if container == "pcm":
        parameters: dict[str, str] = {}
        for parameter in parts[1:]:
            match = re.fullmatch(
                r'(rate|channels|bits|endian|encoding)\s*=\s*"?([^"\s]+)"?',
                parameter,
                re.IGNORECASE,
            )
            key = match.group(1).lower() if match else ""
            if not match or key in parameters:
                raise ManagedStreamsSessionError("audio_format_not_supported")
            parameters[key] = match.group(2).lower()
        if not {"rate", "channels", "bits"}.issubset(parameters):
            raise ManagedStreamsSessionError("audio_format_not_supported")
        try:
            channels = int(parameters["channels"])
        except (TypeError, ValueError, OverflowError):
            raise ManagedStreamsSessionError("raw_pcm_profile_not_available") from None
        if (
            parameters["rate"] != "16000"
            or not 1 <= channels <= 8
            or parameters["bits"] != "16"
            or parameters.get("endian", "little") != "little"
            or parameters.get("encoding", "sint") != "sint"
        ):
            raise ManagedStreamsSessionError("raw_pcm_profile_not_available")
        return container, channels
    codec: Optional[str] = None
    for parameter in parts[1:]:
        match = re.fullmatch(r'codecs\s*=\s*"?([^"\s]+)"?', parameter, re.IGNORECASE)
        candidate = match.group(1).lower() if match else ""
        if not match or candidate not in _STREAM_AUDIO_CODECS or codec is not None:
            raise ManagedStreamsSessionError("audio_format_not_supported")
        codec = candidate
    if codec is not None and container not in {"ogg", "webm"}:
        raise ManagedStreamsSessionError("audio_format_not_supported")
    implied = {"audio/opus": "opus", "audio/vorbis": "vorbis"}.get(mime)
    if implied is not None and codec is not None and codec != implied:
        raise ManagedStreamsSessionError("audio_format_not_supported")
    return container, None


class ManagedStreamsSession:
    """Typed, bounded Streams session that fails closed after audio loss."""

    def __init__(
        self,
        connect_factory: Callable[[str], Awaitable[Any]],
        url_factory: Callable[[], str],
        *,
        configuration: dict[str, Any],
        setup_timeout: float = 10.0,
        require_checkpoint_resume: bool = False,
    ) -> None:
        _validate_configuration(configuration)
        if setup_timeout <= 0 or setup_timeout > 60:
            raise ValueError("setup_timeout must be greater than 0 and at most 60")
        self._connect_factory = connect_factory
        self._url_factory = url_factory
        self._configuration = configuration
        self._setup_timeout = setup_timeout
        self._require_checkpoint_resume = require_checkpoint_resume
        self._listeners: dict[str, set[Callable[[Any], Any]]] = {}
        self._messages: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        self._websocket: Any = None
        self._reader_task: Optional[asyncio.Task] = None
        self._ended_future: Optional[asyncio.Future[None]] = None
        self._ready = False
        self._ended = False
        self._end_sent = False
        self._audio_bytes = 0
        self._durable_audio_bytes = 0
        self._accepted_configuration: Optional[dict[str, Any]] = None
        self._terminal_error: Optional[ManagedStreamsSessionError] = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_ended(self) -> bool:
        return self._ended

    @property
    def accepted_configuration(self) -> Optional[dict[str, Any]]:
        return dict(self._accepted_configuration) if self._accepted_configuration else None

    def on(self, event: str, handler: Callable[[Any], Any]) -> "ManagedStreamsSession":
        self._listeners.setdefault(event, set()).add(handler)
        return self

    def off(self, event: str, handler: Optional[Callable[[Any], Any]] = None) -> "ManagedStreamsSession":
        if handler is None:
            self._listeners.pop(event, None)
        else:
            self._listeners.get(event, set()).discard(handler)
        return self

    async def connect(self) -> "ManagedStreamsSession":
        if self._websocket is not None:
            raise ManagedStreamsSessionError("already_started")
        try:
            websocket = await asyncio.wait_for(
                self._connect_factory(self._url_factory()),
                timeout=self._setup_timeout,
            )
            self._websocket = websocket
            await websocket.send(json.dumps({
                "type": "config", "configuration": self._configuration,
            }))
            raw = await asyncio.wait_for(websocket.recv(), timeout=self._setup_timeout)
            message = _parse_message(raw)
            await self._messages.put(message)
            self._emit("message", message)
            if message["type"] in _CONFIG_FAILURES:
                raise ManagedStreamsSessionError(message["type"].lower())
            if message["type"] != "CONFIG_ACCEPTED":
                raise ManagedStreamsSessionError("invalid_configuration_response")
            if self._require_checkpoint_resume and not message["resumed"]:
                raise ManagedStreamsSessionError("stream_checkpoint_not_found")
            self._accepted_configuration = dict(message)
            self._audio_bytes = int(message["restoredAudioBytes"])
            self._durable_audio_bytes = self._audio_bytes
            self._ready = True
            self._emit("ready", message)
            self._reader_task = asyncio.create_task(self._reader())
            return self
        except ManagedStreamsSessionError:
            await self._close_socket()
            raise
        except asyncio.TimeoutError:
            await self._close_socket()
            raise ManagedStreamsSessionError("setup_timeout", True) from None
        except Exception:
            await self._close_socket()
            raise ManagedStreamsSessionError("connection_failed", True) from None

    async def send_audio(self, data: bytes | bytearray | memoryview) -> None:
        self._assert_writable()
        payload = bytes(data)
        if not payload:
            raise ValueError("audio cannot be empty")
        if len(payload) > _MAX_CHUNK_BYTES:
            raise ValueError("audio chunk exceeds 64000 bytes")
        if self._audio_bytes + len(payload) > _MAX_AUDIO_BYTES:
            raise ValueError(f"audio exceeds the {_MAX_AUDIO_BYTES}-byte session limit")
        self._audio_bytes += len(payload)
        await self._websocket.send(payload)

    async def flush(self) -> None:
        self._assert_writable()
        await self._websocket.send(json.dumps({"type": "flush"}))

    async def end(self) -> None:
        self._assert_writable()
        self._end_sent = True
        await self._websocket.send(json.dumps({"type": "end"}))

    async def wait_ended(self) -> None:
        if self._ended:
            return
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._ended_future is None:
            self._ended_future = asyncio.get_running_loop().create_future()
        await self._ended_future

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            message = await self._messages.get()
            if message is None:
                return
            yield message

    async def close(self) -> None:
        self._ready = False
        await self._close_socket()
        if self._reader_task and self._reader_task is not asyncio.current_task():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        await self._messages.put(None)

    async def _reader(self) -> None:
        try:
            async for raw in self._websocket:
                message = _parse_message(raw)
                await self._messages.put(message)
                self._emit("message", message)
                if message["type"] == "flushed":
                    self._durable_audio_bytes = self._audio_bytes
                if message["type"] == "error":
                    self._emit("error", ManagedStreamsSessionError(message.get("code", "server_error")))
                elif message["type"] == "ENDED":
                    self._ended = True
                    self._ready = False
                    if self._ended_future is not None and not self._ended_future.done():
                        self._ended_future.set_result(None)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self._ready = False
            if not self._ended:
                safely_checkpointed = (
                    self._configuration.get("retentionPolicy") == "retain"
                    and self._audio_bytes > 0
                    and self._durable_audio_bytes == self._audio_bytes
                )
                error = ManagedStreamsSessionError(
                    (
                        "stream_resume_required"
                        if safely_checkpointed
                        else "audio_resume_unsupported"
                        if self._audio_bytes
                        else "stream_interrupted"
                    ),
                    retryable=safely_checkpointed or self._audio_bytes == 0,
                )
                self._terminal_error = error
                self._emit("error", error)
                if self._ended_future is not None and not self._ended_future.done():
                    self._ended_future.set_exception(error)
            await self._messages.put(None)

    def _assert_writable(self) -> None:
        if not self._ready or self._websocket is None:
            raise ManagedStreamsSessionError("configuration_not_ready", True)
        if self._end_sent:
            raise ManagedStreamsSessionError("session_already_ended")

    def _emit(self, event: str, payload: Any) -> None:
        for handler in tuple(self._listeners.get(event, set())):
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    asyncio.create_task(result)
            except Exception:
                continue

    async def _close_socket(self) -> None:
        if self._websocket is None:
            return
        try:
            await self._websocket.close(code=1000, reason="client close")
        except TypeError:
            await self._websocket.close()
        except Exception:
            pass
