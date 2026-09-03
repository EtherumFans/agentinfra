import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig, ManagedSttSessionError


class FakeWebSocket:
    def __init__(self, uri, behavior, index):
        self.uri = uri
        self.behavior = behavior
        self.index = index
        self.sent = []
        self.close_code = None
        self._incoming = asyncio.Queue()

    async def send(self, value):
        self.sent.append(value)
        await self.behavior(self, value, self.index)

    async def recv(self):
        value = await self._incoming.get()
        if value is None:
            raise ConnectionError("closed")
        return value

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self._incoming.get()
        if value is None:
            raise StopAsyncIteration
        return value

    async def close(self, code=1000, reason=""):
        self.close_code = code
        await self._incoming.put(None)

    def server_message(self, value):
        self._incoming.put_nowait(json.dumps(value))

    def server_close(self, code=1006):
        self.close_code = code
        self._incoming.put_nowait(None)


def install_websockets(monkeypatch, behavior):
    instances = []

    async def connect(uri):
        socket = FakeWebSocket(uri, behavior, len(instances) + 1)
        instances.append(socket)
        return socket

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    return instances


async def ready_on_start(socket, value, _index):
    if isinstance(value, str) and json.loads(value).get("type") == "start":
        start = json.loads(value)
        socket.server_message({
            "type": "ready", "language": "zh-CN", "maxSessionBytes": 33554432,
            "protocol": "icoder.stt-resume.v1", "resumeSupported": True,
            "resumeMode": "client_replay", "sessionId": start["sessionId"],
            "nextAudioSequence": 1,
        })


async def legacy_ready_on_start(socket, value, _index):
    if isinstance(value, str) and json.loads(value).get("type") == "start":
        socket.server_message({
            "type": "ready", "language": "zh-CN", "maxSessionBytes": 33554432,
        })


async def eventually(predicate, attempts=50):
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition did not become true")


@pytest.mark.asyncio
async def test_managed_stt_waits_for_ready_and_yields_typed_messages(monkeypatch):
    instances = install_websockets(monkeypatch, ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="tenant/token +",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=0,
        )
        instances[0].server_message({
            "type": "final", "text": "患者主诉胸痛", "diarization": [{"speaker": 0}],
        })
        messages = session.messages()
        first = await messages.__anext__()
        second = await messages.__anext__()
        await session.send_audio(b"\x01\x02")
        await session.request_interim()
        await session.send_end()

        assert first["type"] == "ready"
        assert second == {
            "type": "final", "text": "患者主诉胸痛", "diarization": [{"speaker": 0}],
        }
        assert session.is_ready is True
        assert instances[0].uri.endswith("?token=tenant%2Ftoken%20%2B")
        assert instances[0].sent[1][:8] == b"ICR1\x00\x00\x00\x01"
        assert instances[0].sent[1][8:] == b"\x01\x02"
        assert json.loads(instances[0].sent[2]) == {"type": "interim"}
        assert json.loads(instances[0].sent[3]) == {
            "type": "end", "lastAudioSequence": 1,
        }
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_reconnects_before_audio(monkeypatch):
    instances = install_websockets(monkeypatch, ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=1,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
        )
        events = []
        session.on("reconnecting", events.append)
        instances[0].server_close()
        await eventually(lambda: len(instances) == 2 and session.is_ready)

        assert events == [{"attempt": 1, "delay": 0}]
        assert json.loads(instances[1].sent[0])["type"] == "start"
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_replays_audio_after_disconnect(monkeypatch):
    instances = install_websockets(monkeypatch, ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=3,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
        )
        await session.send_audio(b"\x01\x02")
        original_frame = instances[0].sent[1]
        instances[0].server_close()
        await eventually(lambda: len(instances) == 2 and session.is_ready)

        assert instances[1].sent[1] == original_frame
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_replays_end_after_disconnect(monkeypatch):
    instances = install_websockets(monkeypatch, ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=1,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
        )
        await session.send_audio(b"\x07")
        await session.send_end()
        instances[0].server_close()
        await eventually(lambda: len(instances) == 2 and session.is_ready)

        assert instances[1].sent[1][8:] == b"\x07"
        assert json.loads(instances[1].sent[2]) == {
            "type": "end", "lastAudioSequence": 1,
        }
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_refuses_post_audio_reconnect_to_legacy_server(monkeypatch):
    instances = install_websockets(monkeypatch, legacy_ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=3,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
        )
        terminal = asyncio.get_running_loop().create_future()
        session.on(
            "error",
            lambda error: terminal.set_result(error) if not terminal.done() else None,
        )
        await session.send_audio(b"\x01")
        instances[0].server_close()
        error = await asyncio.wait_for(terminal, timeout=1)

        assert isinstance(error, ManagedSttSessionError)
        assert error.code == "audio_resume_unsupported"
        assert len(instances) == 1
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_parses_ack_and_enforces_advertised_limit(monkeypatch):
    async def bounded_ready(socket, value, _index):
        if not isinstance(value, str) or json.loads(value).get("type") != "start":
            return
        start = json.loads(value)
        socket.server_message({
            "type": "ready", "language": "zh-CN", "maxSessionBytes": 2,
            "protocol": "icoder.stt-resume.v1", "resumeSupported": True,
            "resumeMode": "client_replay", "sessionId": start["sessionId"],
            "nextAudioSequence": 1,
        })

    instances = install_websockets(monkeypatch, bounded_ready)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=0,
        )
        await session.send_audio(b"\x01\x02")
        start = json.loads(instances[0].sent[0])
        instances[0].server_message({
            "type": "audio_ack", "sequence": 1, "nextAudioSequence": 2,
            "totalBytes": 2, "duplicate": False, "sessionId": start["sessionId"],
        })
        await eventually(lambda: session._last_acknowledged_sequence == 1)
        with pytest.raises(ValueError, match="2-byte session limit"):
            await session.send_audio(b"\x03")
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_terminates_on_invalid_acknowledgement(monkeypatch):
    instances = install_websockets(monkeypatch, ready_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    terminal = asyncio.get_running_loop().create_future()
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=1,
        )
        session.on(
            "error",
            lambda error: terminal.set_result(error) if not terminal.done() else None,
        )
        await session.send_audio(b"\x01")
        instances[0].server_message({
            "type": "audio_ack", "sequence": 1, "nextAudioSequence": 2,
            "totalBytes": 1, "duplicate": False,
            "sessionId": "stt_wrong_session_identifier_0000",
        })

        error = await asyncio.wait_for(terminal, timeout=1)
        assert error.code == "invalid_audio_ack"
        assert session.is_ready is False
        assert instances[0].close_code == 1002
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_wait_rejects_when_reconnect_budget_is_exhausted(
    monkeypatch,
):
    async def first_ready_then_close(socket, value, index):
        if not isinstance(value, str) or json.loads(value).get("type") != "start":
            return
        if index == 1:
            socket.server_message({"type": "ready", "language": "zh-CN"})
        else:
            socket.server_close()

    instances = install_websockets(monkeypatch, first_ready_then_close)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=1,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
        )
        instances[0].server_close()
        await eventually(lambda: len(instances) == 2)

        with pytest.raises(ManagedSttSessionError) as captured:
            await session.wait_for_ready()
        assert captured.value.code == "reconnect_exhausted"
        assert session.is_ready is False
        assert len(instances) == 2
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_managed_stt_configuration_error_discards_free_text(monkeypatch):
    async def deny_on_start(socket, value, _index):
        if isinstance(value, str) and json.loads(value).get("type") == "start":
            socket.server_message({
                "type": "error",
                "code": "unsupported_language",
                "message": "patient secret from upstream",
            })

    install_websockets(monkeypatch, deny_on_start)
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test", access_token="token",
    ))
    try:
        with pytest.raises(ManagedSttSessionError) as captured:
            await client.speech_to_text.connect_managed_session_async(
                reconnect_attempts=0,
            )
        assert captured.value.code == "unsupported_language"
        assert "patient secret" not in str(captured.value)
        assert not hasattr(captured.value, "uri")
    finally:
        client.close()
