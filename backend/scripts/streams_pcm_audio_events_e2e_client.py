"""Exercise governed PCM audio health events over a real tenant WebSocket."""

from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import uuid
from urllib.parse import quote, urlencode

import websockets


def _uri() -> str:
    base_url = os.environ.get("ICODER_E2E_STREAMS_BASE_URL", "")
    tenant = os.environ.get("ICODER_E2E_TENANT_NAME", "")
    token = os.environ.get("ICODER_E2E_ACCESS_TOKEN", "")
    if not base_url or not tenant or not token:
        raise RuntimeError("missing isolated Streams E2E environment")
    websocket_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    query = urlencode({
        "environment": "cn",
        "tenant-name": tenant,
        "token": token,
    })
    interaction_id = quote(str(uuid.uuid4()), safe="")
    return f"{websocket_base}/api/v2/tools/streams/{interaction_id}?{query}"


def _tone(seconds: float, *, amplitude: int = 6000) -> bytes:
    rate = 16000
    return b"".join(
        struct.pack(
            "<h",
            round(amplitude * math.sin(2 * math.pi * 440 * index / rate)),
        )
        for index in range(round(seconds * rate))
    )


async def _send_bounded(socket, payload: bytes) -> None:
    for start in range(0, len(payload), 64_000):
        await socket.send(payload[start:start + 64_000])


async def _receive_event(socket, expected: str, start_time_ms: int) -> None:
    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
    if message != {
        "type": "audioEvent",
        "data": {"event": expected, "channel": 0, "startTimeMs": start_time_ms},
    }:
        raise RuntimeError("PCM audio health event did not match the governed contract")


async def run() -> dict[str, object]:
    socket = await websockets.connect(_uri(), proxy=None, open_timeout=10)
    try:
        await socket.send(json.dumps({
            "type": "config",
            "configuration": {
                "transcription": {
                    "primaryLanguage": "zh-CN",
                    "diarize": False,
                    "isMultichannel": False,
                    "participants": [{"channel": 0, "role": "multiple"}],
                },
                "mode": {"type": "transcription"},
                "retentionPolicy": "none",
                "audioFormat": "audio/pcm; rate=16000; channels=1; bits=16",
                "audioEvents": {"enabled": True},
            },
        }))
        accepted = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if accepted.get("type") != "CONFIG_ACCEPTED":
            raise RuntimeError("PCM audio health configuration was not accepted")

        silence = b"\x00\x00" * (16000 * 10)
        await _send_bounded(socket, silence)
        await _receive_event(socket, "longSilenceDetected", 0)

        await _send_bounded(socket, _tone(0.25))
        await _receive_event(socket, "longSilenceRecovered", 10000)

        await _send_bounded(socket, struct.pack("<h", 32767) * 16000)
        await _receive_event(socket, "speechQualityIssueDetected", 10250)

        await _send_bounded(socket, _tone(1.0))
        await _receive_event(socket, "speechQualityIssueRecovered", 11250)

        # Finish the stream so this scenario also proves that the exact
        # governed PCM profile passes the isolated decoder and reaches the
        # STT adapter. The E2E server deliberately disables local STT, so the
        # expected outcome is an explicit availability error followed by the
        # normal Corti-compatible usage/end sequence.
        await socket.send(json.dumps({"type": "end"}))
        unavailable = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
        error = unavailable.get("error") if isinstance(unavailable, dict) else None
        if (
            not isinstance(error, dict)
            or error.get("id") != "STT_UNAVAILABLE"
            or error.get("status") != 503
        ):
            raise RuntimeError("PCM end did not fail closed at the disabled STT adapter")
        usage = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if usage != {"type": "usage", "credits": 0.0}:
            raise RuntimeError("PCM end did not emit the expected usage message")
        ended = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if ended != {"type": "ENDED"}:
            raise RuntimeError("PCM end did not emit ENDED after usage")
    finally:
        await socket.close(code=1000, reason="synthetic audio health E2E complete")

    return {
        "status": "passed",
        "configuration": "pcm_s16le_mono_16000",
        "events": [
            "longSilenceDetected",
            "longSilenceRecovered",
            "speechQualityIssueDetected",
            "speechQualityIssueRecovered",
        ],
        "audio_event_count": 4,
        "event_payload_content_free": True,
        "decoder_reached": True,
        "asr_adapter_reached": True,
        "expected_error_code": "STT_UNAVAILABLE",
        "retention_reached": False,
        "real_patient_audio_used": False,
        "real_stt_used": False,
        "real_llm_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
