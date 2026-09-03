"""Managed lifecycle for negotiated iCoDer real-time STT recovery."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import secrets
import struct
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Optional


_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_RESUME_PROTOCOL = "icoder.stt-resume.v1"
_RESUME_MODE = "client_replay"
_MAXIMUM_SESSION_BYTES = 32 * 1024 * 1024


def _safe_int(value: Any, *, minimum: int = 0) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    return value


class ManagedSttSessionError(ConnectionError):
    """PHI-safe managed WebSocket failure."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(f"iCoDer managed STT session failed ({code})")
        self.code = code
        self.retryable = retryable


def _parse_message(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except Exception:
        return {"type": "unknown"}
    if not isinstance(value, dict):
        return {"type": "unknown"}
    message_type = value.get("type")
    if message_type == "ready":
        result = {
            "type": "ready",
            "language": value.get("language")
            if isinstance(value.get("language"), str)
            else "zh-CN",
        }
        if isinstance(value.get("maxSessionBytes"), int):
            result["maxSessionBytes"] = value["maxSessionBytes"]
        for key in ("protocol", "resumeMode", "sessionId"):
            if isinstance(value.get(key), str):
                result[key] = value[key]
        if isinstance(value.get("resumeSupported"), bool):
            result["resumeSupported"] = value["resumeSupported"]
        next_sequence = _safe_int(value.get("nextAudioSequence"), minimum=1)
        if next_sequence is not None:
            result["nextAudioSequence"] = next_sequence
        return result
    if message_type == "audio_ack":
        sequence = _safe_int(value.get("sequence"), minimum=1)
        next_sequence = _safe_int(value.get("nextAudioSequence"), minimum=1)
        total_bytes = _safe_int(value.get("totalBytes"))
        if sequence is None or next_sequence is None or total_bytes is None:
            return {"type": "unknown"}
        return {
            "type": "audio_ack",
            "sequence": sequence,
            "nextAudioSequence": next_sequence,
            "totalBytes": total_bytes,
            "duplicate": value.get("duplicate") is True,
            **(
                {"sessionId": value["sessionId"]}
                if isinstance(value.get("sessionId"), str)
                else {}
            ),
        }
    if message_type in {"interim", "final"}:
        result = {
            "type": message_type,
            "text": value.get("text") if isinstance(value.get("text"), str) else "",
        }
        if message_type == "final":
            result["diarization"] = (
                value["diarization"] if isinstance(value.get("diarization"), list) else []
            )
        return result
    if message_type == "buffering":
        return {
            "type": "buffering",
            "bytes": value.get("bytes") if isinstance(value.get("bytes"), int) else 0,
        }
    if message_type == "pong":
        return {"type": "pong"}
    if message_type == "error":
        code = value.get("code")
        return {
            "type": "error",
            **({"code": code} if isinstance(code, str) and _SAFE_CODE.fullmatch(code) else {}),
        }
    return {"type": "unknown"}


class ManagedSttSession:
    """Typed events and bounded client-replay audio recovery."""

    def __init__(
        self,
        connect_factory: Callable[[str], Awaitable[Any]],
        url_factory: Callable[[], str],
        *,
        prepare_connection: Optional[Callable[[], Awaitable[None]]] = None,
        language: str = "zh-CN",
        mime_type: str = "audio/webm;codecs=opus",
        reconnect_attempts: int = 3,
        reconnect_initial_delay: float = 0.25,
        reconnect_max_delay: float = 2.0,
        setup_timeout: float = 5.0,
    ) -> None:
        if (
            not isinstance(reconnect_attempts, int)
            or isinstance(reconnect_attempts, bool)
            or reconnect_attempts < 0
        ):
            raise ValueError("reconnect_attempts must be a non-negative integer")
        if reconnect_initial_delay < 0 or reconnect_max_delay < reconnect_initial_delay:
            raise ValueError("reconnect delays are invalid")
        if setup_timeout <= 0:
            raise ValueError("setup_timeout must be positive")
        self._connect_factory = connect_factory
        self._url_factory = url_factory
        self._prepare_connection = prepare_connection
        self._language = language
        self._mime_type = mime_type
        self._session_id = f"stt_{secrets.token_hex(16)}"
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._setup_timeout = setup_timeout
        self._listeners: dict[str, set[Callable[[Any], Any]]] = {}
        self._messages: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        self._websocket: Any = None
        self._reader_task: Optional[asyncio.Task] = None
        self._ready_task: Optional[asyncio.Task] = None
        self._reconnects_used = 0
        self._generation = 0
        self._started = False
        self._manually_closed = False
        self._audio_sent = False
        self._end_sent = False
        self._resume_supported = False
        self._audio_frames: list[bytes] = []
        self._sent_audio_bytes = 0
        self._max_session_bytes = _MAXIMUM_SESSION_BYTES
        self._last_acknowledged_sequence = 0
        self._ready = False
        self._terminal_error: Optional[ManagedSttSessionError] = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    def on(self, event: str, handler: Callable[[Any], Any]) -> "ManagedSttSession":
        self._listeners.setdefault(event, set()).add(handler)
        return self

    def off(
        self, event: str, handler: Optional[Callable[[Any], Any]] = None
    ) -> "ManagedSttSession":
        if handler is None:
            self._listeners.pop(event, None)
        else:
            self._listeners.get(event, set()).discard(handler)
        return self

    async def connect(self, await_configuration: bool = True) -> "ManagedSttSession":
        if self._started:
            raise ManagedSttSessionError("already_started")
        self._started = True
        self._ready_task = asyncio.create_task(self._establish_with_reconnect(False))
        self._ready_task.add_done_callback(self._observe_ready_task)
        if await_configuration:
            await self._ready_task
        return self

    async def wait_for_ready(self) -> None:
        if self._ready:
            return
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._ready_task is None:
            raise ManagedSttSessionError("not_started")
        await self._ready_task
        if not self._ready:
            raise self._terminal_error or ManagedSttSessionError(
                "configuration_not_ready", True
            )

    async def send_audio(self, data: bytes | bytearray | memoryview) -> None:
        self._assert_ready()
        if not data:
            raise ValueError("audio cannot be empty")
        payload = bytes(data)
        if self._sent_audio_bytes + len(payload) > self._max_session_bytes:
            raise ValueError(
                f"audio exceeds the {self._max_session_bytes}-byte session limit"
            )
        self._audio_sent = True
        self._sent_audio_bytes += len(payload)
        if self._resume_supported:
            sequence = len(self._audio_frames) + 1
            frame = b"ICR1" + struct.pack(">I", sequence) + payload
            self._audio_frames.append(frame)
            await self._websocket.send(frame)
        else:
            await self._websocket.send(payload)

    async def request_interim(self) -> None:
        self._assert_ready()
        await self._websocket.send(json.dumps({"type": "interim"}))

    async def send_end(self) -> None:
        self._assert_ready()
        self._end_sent = True
        command = (
            {"type": "end", "lastAudioSequence": len(self._audio_frames)}
            if self._resume_supported
            else {"type": "end"}
        )
        await self._websocket.send(json.dumps(command))

    async def close(self) -> None:
        self._manually_closed = True
        self._ready = False
        if self._terminal_error is None:
            self._terminal_error = ManagedSttSessionError("client_closed")
        if self._websocket is not None:
            try:
                await self._websocket.close(code=1000, reason="client close")
            except TypeError:
                await self._websocket.close()
            except Exception:
                pass
        if self._reader_task and self._reader_task is not asyncio.current_task():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        await self._messages.put(None)

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            message = await self._messages.get()
            if message is None:
                return
            yield message

    def _assert_ready(self) -> None:
        if not self._ready or self._websocket is None:
            raise ManagedSttSessionError("configuration_not_ready", True)
        if self._end_sent:
            raise ManagedSttSessionError("session_already_ended")

    def _emit(self, event: str, payload: Any) -> None:
        for handler in tuple(self._listeners.get(event, set())):
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    asyncio.create_task(result)
            except Exception:
                continue

    def _observe_ready_task(self, task: asyncio.Task) -> None:
        """Retrieve background failures while preserving them for later awaits."""
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is None:
            return
        managed = (
            error
            if isinstance(error, ManagedSttSessionError)
            else ManagedSttSessionError("connection_failed", True)
        )
        self._terminal_error = managed
        if not self._manually_closed:
            self._emit("error", managed)

    async def _establish_with_reconnect(self, reconnect: bool) -> None:
        while not self._manually_closed:
            if reconnect:
                if (self._audio_sent or self._end_sent) and not self._resume_supported:
                    raise ManagedSttSessionError("audio_resume_unsupported")
                if self._reconnects_used >= self._reconnect_attempts:
                    raise ManagedSttSessionError("reconnect_exhausted")
                self._reconnects_used += 1
                delay = min(
                    self._reconnect_max_delay,
                    self._reconnect_initial_delay * (2 ** (self._reconnects_used - 1)),
                )
                self._emit("reconnecting", {
                    "attempt": self._reconnects_used,
                    "delay": delay,
                })
                if delay:
                    await asyncio.sleep(delay)
                if self._manually_closed:
                    return
            try:
                if self._prepare_connection is not None:
                    await self._prepare_connection()
                await self._establish_once()
                return
            except asyncio.CancelledError:
                raise
            except ManagedSttSessionError as error:
                if (
                    not error.retryable
                    or (self._audio_sent and not self._resume_supported)
                    or self._manually_closed
                ):
                    raise
                reconnect = True
            except Exception:
                reconnect = True

    async def _establish_once(self) -> None:
        self._generation += 1
        generation = self._generation
        self._ready = False
        try:
            websocket = await asyncio.wait_for(
                self._connect_factory(self._url_factory()),
                timeout=self._setup_timeout,
            )
            self._websocket = websocket
            self._emit("open", {"attempt": self._reconnects_used})
            await websocket.send(json.dumps({
                "type": "start",
                "protocol": _RESUME_PROTOCOL,
                "sessionId": self._session_id,
                "mimeType": self._mime_type,
                "language": self._language,
            }))
            raw = await asyncio.wait_for(websocket.recv(), timeout=self._setup_timeout)
            message = _parse_message(raw)
            self._emit("message", message)
            await self._messages.put(message)
            if message["type"] == "error":
                raise ManagedSttSessionError(message.get("code", "server_error"))
            if message["type"] != "ready":
                raise ManagedSttSessionError("configuration_not_ready")
            negotiated_resume = (
                message.get("protocol") == _RESUME_PROTOCOL
                and message.get("resumeSupported") is True
                and message.get("resumeMode") == _RESUME_MODE
                and message.get("sessionId") == self._session_id
            )
            if (self._audio_sent or self._end_sent) and not negotiated_resume:
                raise ManagedSttSessionError("audio_resume_unsupported")
            requested_sequence = (
                _safe_int(message.get("nextAudioSequence"), minimum=1)
                if negotiated_resume
                else None
            )
            if negotiated_resume and (
                requested_sequence is None
                or requested_sequence > len(self._audio_frames) + 1
            ):
                raise ManagedSttSessionError("invalid_resume_cursor")
            self._resume_supported = negotiated_resume
            advertised_limit = _safe_int(message.get("maxSessionBytes"), minimum=1)
            if advertised_limit is not None:
                self._max_session_bytes = min(
                    _MAXIMUM_SESSION_BYTES, advertised_limit
                )
            if self._sent_audio_bytes > self._max_session_bytes:
                raise ManagedSttSessionError("session_too_large")
            if negotiated_resume:
                assert requested_sequence is not None
                self._last_acknowledged_sequence = requested_sequence - 1
                for sequence, frame in enumerate(self._audio_frames, start=1):
                    if sequence >= requested_sequence:
                        await websocket.send(frame)
                if self._end_sent:
                    await websocket.send(json.dumps({
                        "type": "end",
                        "lastAudioSequence": len(self._audio_frames),
                    }))
            self._ready = True
            self._terminal_error = None
            self._emit("ready", message)
            self._reader_task = asyncio.create_task(self._reader(websocket, generation))
        except ManagedSttSessionError:
            await self._close_failed_socket()
            raise
        except asyncio.TimeoutError:
            await self._close_failed_socket()
            raise ManagedSttSessionError("setup_timeout", True) from None
        except asyncio.CancelledError:
            await self._close_failed_socket()
            raise
        except Exception:
            await self._close_failed_socket()
            raise ManagedSttSessionError("connection_failed", True) from None

    async def _reader(self, websocket: Any, generation: int) -> None:
        try:
            async for raw in websocket:
                if generation != self._generation:
                    return
                message = _parse_message(raw)
                self._emit("message", message)
                await self._messages.put(message)
                if message["type"] == "audio_ack":
                    if (
                        not self._resume_supported
                        or message.get("sessionId") != self._session_id
                        or message["sequence"] > len(self._audio_frames)
                        or message["nextAudioSequence"] < message["sequence"] + 1
                        or message["nextAudioSequence"] > len(self._audio_frames) + 1
                    ):
                        error = ManagedSttSessionError("invalid_audio_ack")
                        self._terminal_error = error
                        self._ready = False
                        self._manually_closed = True
                        self._emit("error", error)
                        try:
                            await websocket.close(
                                code=1002, reason="invalid audio acknowledgement"
                            )
                        except TypeError:
                            await websocket.close()
                        await self._messages.put(None)
                        return
                    self._last_acknowledged_sequence = max(
                        self._last_acknowledged_sequence,
                        message["nextAudioSequence"] - 1,
                    )
                elif message["type"] == "error":
                    self._emit(
                        "error",
                        ManagedSttSessionError(message.get("code", "server_error")),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            if generation != self._generation:
                return
            self._ready = False
            self._emit("close", {"code": self._safe_close_code(websocket)})
            if self._manually_closed:
                return
            if (self._audio_sent or self._end_sent) and not self._resume_supported:
                error = ManagedSttSessionError("audio_resume_unsupported")
                self._terminal_error = error
                self._emit("error", error)
                return
            self._ready_task = asyncio.create_task(self._recover())
            self._ready_task.add_done_callback(self._observe_ready_task)

    async def _recover(self) -> None:
        await self._establish_with_reconnect(True)

    async def _close_failed_socket(self) -> None:
        if self._websocket is None:
            return
        try:
            await self._websocket.close()
        except Exception:
            pass

    @staticmethod
    def _safe_close_code(websocket: Any) -> int:
        code = getattr(websocket, "close_code", None)
        return code if isinstance(code, int) else 1006
