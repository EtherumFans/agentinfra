import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


def _client_with_transport(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_speech_to_text_batch_lifecycle_preserves_async_metadata():
    captured = []

    def handler(request):
        captured.append(request)
        if request.url.path.endswith("/recordings"):
            return httpx.Response(201, json={"recordingId": "rec-1"})
        return httpx.Response(
            202,
            json={"id": "tr-1", "recordingId": "rec-1", "status": "processing"},
            headers={"Location": "/status/tr-1"},
        )

    client = _client_with_transport(handler)
    try:
        recording = client.speech_to_text.upload_recording(
            "interaction/1", b"audio", "audio/flac"
        )
        transcript = client.speech_to_text.create_transcript(
            "interaction/1",
            recording["recordingId"],
            async_=True,
            is_dictation=True,
            spoken_punctuation=True,
            automatic_punctuation=False,
            is_multichannel=True,
            participants=[
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
            keyterms={"terms": [{"term": "房颤"}, {"term": "Corti Health"}]},
        )
    finally:
        client.close()

    assert str(captured[0].url).endswith("/interaction%2F1/recordings")
    assert captured[0].headers["content-type"] == "audio/flac"
    transcript_request = json.loads(captured[1].content)
    assert transcript_request["async"] is True
    assert transcript_request["isDictation"] is True
    assert transcript_request["spokenPunctuation"] is True
    assert transcript_request["automaticPunctuation"] is False
    assert transcript_request["isMultichannel"] is True
    assert transcript_request["participants"] == [
        {"channel": 0, "role": "doctor"},
        {"channel": 1, "role": "patient"},
    ]
    assert transcript_request["keyterms"] == {
        "terms": [{"term": "房颤"}, {"term": "Corti Health"}]
    }
    assert transcript.status_code == 202
    assert transcript.location == "/status/tr-1"


def test_speech_to_text_readiness_uses_content_free_status_route():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"production_ready": False})

    client = _client_with_transport(handler)
    try:
        assert client.speech_to_text.readiness()["production_ready"] is False
    finally:
        client.close()
    assert captured[0].url.path == "/api/v2/tools/stt/readiness"


def test_speech_to_text_rejects_unsupported_capabilities_before_transport():
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    try:
        with pytest.raises(ValueError, match="unsupported recording media type"):
            client.speech_to_text.upload_recording("i-1", b"audio", "application/json")
        with pytest.raises(ValueError, match="Chinese audio only"):
            client.speech_to_text.create_transcript(
                "i-1", "rec-1", primary_language="en-US"
            )
        with pytest.raises(ValueError, match="at most one participant"):
            client.speech_to_text.create_transcript(
                "i-1",
                "rec-1",
                participants=[
                    {"channel": 1, "role": "doctor"},
                    {"channel": 2, "role": "patient"},
                ],
            )
        with pytest.raises(ValueError, match="channels 0 and 1"):
            client.speech_to_text.create_transcript(
                "i-1",
                "rec-1",
                is_multichannel=True,
                participants=[{"channel": 0, "role": "doctor"}],
            )
        with pytest.raises(ValueError, match="1 to 50 characters"):
            client.speech_to_text.create_transcript(
                "i-1",
                "rec-1",
                keyterms={"terms": [{"term": "术" * 51}]},
            )
        with pytest.raises(ValueError, match="cannot exceed 1000 items"):
            client.speech_to_text.create_transcript(
                "i-1",
                "rec-1",
                keyterms={
                    "terms": [{"term": f"term-{index}"} for index in range(1001)]
                },
            )
    finally:
        client.close()


@pytest.mark.asyncio
async def test_realtime_session_rejects_unverified_language_before_importing_websockets():
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    try:
        with pytest.raises(ValueError, match="zh-CN only"):
            await client.speech_to_text.create_session_async(language="en-US")
    finally:
        client.close()


@pytest.mark.asyncio
async def test_realtime_session_waits_for_ready(monkeypatch):
    captured = {}

    class FakeWebSocket:
        async def send(self, value):
            captured["start"] = json.loads(value)

        async def recv(self):
            return json.dumps({
                "type": "ready", "language": "zh-CN", "maxSessionBytes": 33554432,
            })

        async def close(self):
            captured["closed"] = True

    async def connect(uri):
        captured["uri"] = uri
        return FakeWebSocket()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="tenant/token +")
    )
    try:
        session = await client.speech_to_text.create_session_async()
        assert isinstance(session, FakeWebSocket)
        assert captured["uri"].endswith("?token=tenant%2Ftoken%20%2B")
        assert captured["start"] == {
            "type": "start", "mimeType": "audio/webm;codecs=opus", "language": "zh-CN",
        }
        await session.close()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_realtime_connection_error_does_not_retain_token(monkeypatch):
    async def connect(uri):
        raise RuntimeError(f"failed {uri}")

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    token = "tenant-secret-token-value"
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token=token)
    )
    try:
        with pytest.raises(ConnectionError) as error:
            await client.speech_to_text.create_session_async()
        assert token not in str(error.value)
        assert error.value.__cause__ is None
    finally:
        client.close()
