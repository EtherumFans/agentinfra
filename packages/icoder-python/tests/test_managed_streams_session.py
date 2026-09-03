import asyncio
import json
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from icoder_sdk import (
    ManagedStreamsSessionError,
    iCoDerClient,
    iCoDerConfig,
)


INTERACTION_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def configuration(**overrides):
    value = {
        "transcription": {
            "primaryLanguage": "zh-CN",
            "diarize": False,
            "isMultichannel": False,
            "participants": [{"channel": 0, "role": "multiple"}],
        },
        "mode": {"type": "facts", "outputLocale": "zh-CN"},
        "retentionPolicy": "none",
    }
    value.update(overrides)
    return value


class FakeWebSocket:
    def __init__(self, uri, behavior):
        self.uri = uri
        self.behavior = behavior
        self.sent = []
        self._incoming = asyncio.Queue()

    async def send(self, value):
        self.sent.append(value)
        await self.behavior(self, value)

    async def recv(self):
        value = await self._incoming.get()
        if value is None:
            raise ConnectionError("closed with private URI")
        return value

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self._incoming.get()
        if value is None:
            raise StopAsyncIteration
        return value

    async def close(self, code=1000, reason=""):
        await self._incoming.put(None)

    def server_message(self, value):
        self._incoming.put_nowait(json.dumps(value))

    def server_close(self):
        self._incoming.put_nowait(None)


def install_websockets(monkeypatch, behavior):
    instances = []

    async def connect(uri):
        websocket = FakeWebSocket(uri, behavior)
        instances.append(websocket)
        return websocket

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    return instances


async def accept_configuration(socket, value):
    if isinstance(value, str) and json.loads(value).get("type") == "config":
        message = json.loads(value)
        socket.server_message({
            "type": "CONFIG_ACCEPTED",
            "sessionId": SESSION_ID,
            "configuration": message["configuration"],
        })


def client():
    return iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test",
        access_token="tenant/token +",
    ))


@pytest.mark.asyncio
async def test_streams_connects_with_tenant_environment_token_and_config(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital cn",
            environment="cn",
            configuration=configuration(),
        )
        parsed = urlsplit(instances[0].uri)
        query = parse_qs(parsed.query)
        assert parsed.scheme == "wss"
        assert parsed.path.endswith(f"/api/v2/tools/streams/{INTERACTION_ID}")
        assert query == {
            "environment": ["cn"],
            "tenant-name": ["hospital cn"],
            "token": ["tenant/token +"],
        }
        assert json.loads(instances[0].sent[0]) == {
            "type": "config", "configuration": configuration(),
        }
        assert session.is_ready is True
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_yields_typed_messages_and_waits_for_ended(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(),
        )
        await session.send_audio(b"\x01\x02")
        await session.flush()
        await session.end()
        ended = asyncio.create_task(session.wait_ended())
        for message in (
            {"type": "transcript", "data": [{"transcript": "患者胸痛"}]},
            {"type": "facts", "fact": [{"text": "胸痛"}]},
            {"type": "flushed"},
            {"type": "delta_usage", "credits": 0},
            {"type": "usage", "credits": 0},
            {"type": "ENDED"},
        ):
            instances[0].server_message(message)
        await asyncio.wait_for(ended, 1)
        messages = session.messages()
        observed = [await messages.__anext__() for _ in range(7)]
        assert [item["type"] for item in observed] == [
            "CONFIG_ACCEPTED", "transcript", "facts", "flushed",
            "delta_usage", "usage", "ENDED",
        ]
        assert session.is_ended is True
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_accepts_recommended_pcm_and_validates_audio_events(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(
                audioFormat="audio/pcm; rate=16000; channels=1; bits=16",
                audioEvents={"enabled": True},
            ),
        )
        instances[0].server_message({
            "type": "audioEvent",
            "data": {"event": "longSilenceDetected", "channel": 0, "startTimeMs": 0},
        })
        instances[0].server_message({
            "type": "audioEvent",
            "data": {
                "event": "privateUnexpectedEvent",
                "channel": 0,
                "startTimeMs": 0,
                "text": "patient secret",
            },
        })
        messages = session.messages()
        assert (await messages.__anext__())["type"] == "CONFIG_ACCEPTED"
        assert await messages.__anext__() == {
            "type": "audioEvent",
            "data": {"event": "longSilenceDetected", "channel": 0, "startTimeMs": 0},
        }
        assert await messages.__anext__() == {"type": "unknown"}
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_bounds_chunk_and_aggregate_audio(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(),
        )
        with pytest.raises(ValueError, match="64000"):
            await session.send_audio(b"x" * 64_001)
        chunk = b"x" * 64_000
        for _ in range(524):
            await session.send_audio(chunk)
        with pytest.raises(ValueError, match="33554432"):
            await session.send_audio(chunk)
        assert len(instances[0].sent) == 525
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_rejects_unsupported_capability_before_connect(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(transcription={
                    "primaryLanguage": "zh-CN", "diarize": True,
                }),
            )
        assert caught.value.code == "diarization_not_available"
        assert instances == []
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_accepts_governed_multichannel_and_fast_init(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(
                transcription={
                    "primaryLanguage": "zh-CN",
                    "isMultichannel": True,
                    "participants": [
                        {"channel": 0, "role": "clinician"},
                        {"channel": 1, "role": "patient"},
                    ],
                },
                mode={
                    "type": "facts",
                    "outputLocale": "zh-CN",
                    "factGenerationInterval": "fast_init",
                },
                audioFormat="audio/pcm; rate=16000; channels=2; bits=16",
            ),
        )
        assert len(instances) == 1
        assert session.accepted_configuration["configuration"]["transcription"][
            "isMultichannel"
        ] is True
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_accepts_ordered_case_sensitive_keyterms(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    keyterms = {"terms": [{"term": "房颤"}, {"term": "Corti Health"}]}
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(keyterms=keyterms),
        )
        assert len(instances) == 1
        assert session.accepted_configuration["configuration"]["keyterms"] == keyterms
        await session.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keyterms", "expected_code"),
    [
        ({"terms": [{"term": "房颤"}] * 1001}, "keyterm_limit_exceeded"),
        ({"terms": [{"term": ""}]}, "keyterm_invalid"),
        ({"terms": [{"term": "x" * 51}]}, "keyterm_invalid"),
    ],
)
async def test_streams_bounds_keyterms_before_connect(
    monkeypatch,
    keyterms,
    expected_code,
):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(keyterms=keyterms),
            )
        assert caught.value.code == expected_code
        assert instances == []
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_rejects_incomplete_multichannel_mapping(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(
                    transcription={
                        "primaryLanguage": "zh-CN",
                        "isMultichannel": True,
                        "participants": [{"channel": 0, "role": "clinician"}],
                    },
                    audioFormat="audio/pcm; rate=16000; channels=2; bits=16",
                ),
            )
        assert caught.value.code == "multichannel_participants_must_match_channels"
        assert instances == []
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_rejects_wav_and_unknown_audio_formats_before_connect(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        for audio_format, expected_code in (
            ("audio/wav", "audio_format_not_supported"),
            ("audio/pcm", "audio_format_not_supported"),
            (
                "audio/pcm; rate=48000; channels=1; bits=16",
                "raw_pcm_profile_not_available",
            ),
            ("audio/mpeg; codecs=mp3", "audio_format_not_supported"),
        ):
            with pytest.raises(ManagedStreamsSessionError) as caught:
                await sdk.streams.connect_async(
                    interaction_id=INTERACTION_ID,
                    tenant_name="hospital",
                    configuration=configuration(audioFormat=audio_format),
                )
            assert caught.value.code == expected_code
        assert instances == []
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_audio_events_require_governed_pcm_before_connect(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(
                    audioFormat="audio/ogg",
                    audioEvents={"enabled": True},
                ),
            )
        assert caught.value.code == "audio_events_require_pcm"
        assert instances == []
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_configuration_denial_discards_server_reason(monkeypatch):
    async def deny(socket, value):
        if isinstance(value, str) and json.loads(value).get("type") == "config":
            socket.server_message({
                "type": "CONFIG_DENIED",
                "reason": "patient secret",
                "interactionId": INTERACTION_ID,
            })

    install_websockets(monkeypatch, deny)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(),
            )
        assert caught.value.code == "config_denied"
        assert "patient secret" not in str(caught.value)
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_fails_closed_after_audio_disconnect(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(),
        )
        terminal = asyncio.get_running_loop().create_future()
        session.on("error", lambda error: terminal.set_result(error) if not terminal.done() else None)
        await session.send_audio(b"\x01")
        ended = asyncio.create_task(session.wait_ended())
        instances[0].server_close()
        error = await asyncio.wait_for(terminal, 1)
        with pytest.raises(ManagedStreamsSessionError) as ended_error:
            await ended
        assert error.code == ended_error.value.code == "audio_resume_unsupported"
        assert error.retryable is False
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_resumes_only_flushed_retained_checkpoint(monkeypatch):
    connection_count = 0

    async def resume_behavior(socket, value):
        nonlocal connection_count
        if isinstance(value, str) and json.loads(value).get("type") == "config":
            connection_count += 1
            message = json.loads(value)
            socket.server_message({
                "type": "CONFIG_ACCEPTED",
                "sessionId": (
                    SESSION_ID
                    if connection_count == 1
                    else "33333333-3333-4333-8333-333333333333"
                ),
                "configuration": message["configuration"],
                "resumed": connection_count == 2,
                "restoredAudioBytes": 3 if connection_count == 2 else 0,
                "restoredTranscriptMessages": 1 if connection_count == 2 else 0,
                "restoredFactMessages": 1 if connection_count == 2 else 0,
            })

    instances = install_websockets(monkeypatch, resume_behavior)
    sdk = client()
    retained = configuration(retentionPolicy="retain")
    try:
        first = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=retained,
        )
        terminal = asyncio.get_running_loop().create_future()
        first.on(
            "error",
            lambda error: terminal.set_result(error) if not terminal.done() else None,
        )
        await first.send_audio(b"\x01\x02\x03")
        await first.flush()
        instances[0].server_message({"type": "flushed"})
        instances[0].server_message({"type": "delta_usage", "credits": 0})
        await asyncio.sleep(0)
        instances[0].server_close()
        error = await asyncio.wait_for(terminal, 1)
        assert error.code == "stream_resume_required"
        assert error.retryable is True

        resumed = await sdk.streams.resume_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=retained,
        )
        assert resumed.accepted_configuration == {
            "type": "CONFIG_ACCEPTED",
            "sessionId": "33333333-3333-4333-8333-333333333333",
            "configuration": retained,
            "resumed": True,
            "restoredAudioBytes": 3,
            "restoredTranscriptMessages": 1,
            "restoredFactMessages": 1,
        }
        await resumed.send_audio(b"\x04")
        assert instances[1].sent[1] == b"\x04"
        await resumed.close()
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_resume_requires_server_checkpoint_ack(monkeypatch):
    install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.resume_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(retentionPolicy="retain"),
            )
        assert caught.value.code == "stream_checkpoint_not_found"
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_rejects_malformed_acceptance(monkeypatch):
    async def malformed(socket, value):
        if isinstance(value, str) and json.loads(value).get("type") == "config":
            socket.server_message({
                "type": "CONFIG_ACCEPTED",
                "sessionId": "not-a-uuid",
                "configuration": configuration(),
                "secret": "patient secret",
            })

    install_websockets(monkeypatch, malformed)
    sdk = client()
    try:
        with pytest.raises(ManagedStreamsSessionError) as caught:
            await sdk.streams.connect_async(
                interaction_id=INTERACTION_ID,
                tenant_name="hospital",
                configuration=configuration(),
            )
        assert caught.value.code == "invalid_configuration_response"
        assert "patient secret" not in str(caught.value)
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_streams_runtime_error_exposes_only_stable_code(monkeypatch):
    instances = install_websockets(monkeypatch, accept_configuration)
    sdk = client()
    try:
        session = await sdk.streams.connect_async(
            interaction_id=INTERACTION_ID,
            tenant_name="hospital",
            configuration=configuration(),
        )
        terminal = asyncio.get_running_loop().create_future()
        session.on("error", lambda error: terminal.set_result(error) if not terminal.done() else None)
        instances[0].server_message({
            "type": "error",
            "error": {"id": "FACTS_UNAVAILABLE", "details": "patient secret"},
        })
        error = await asyncio.wait_for(terminal, 1)
        assert error.code == "FACTS_UNAVAILABLE"
        assert "patient secret" not in str(error)
        await session.close()
    finally:
        sdk.close()
