"""Exercise governed multichannel PCM over a real tenant WebSocket."""

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
    query = urlencode({"environment": "cn", "tenant-name": tenant, "token": token})
    interaction_id = quote(str(uuid.uuid4()), safe="")
    return f"{websocket_base}/api/v2/tools/streams/{interaction_id}?{query}"


def _stereo_silence_and_tone(seconds: float) -> bytes:
    frames = round(seconds * 16000)
    return b"".join(
        struct.pack(
            "<hh",
            0,
            round(6000 * math.sin(2 * math.pi * 440 * index / 16000)),
        )
        for index in range(frames)
    )


async def run() -> dict[str, object]:
    socket = await websockets.connect(_uri(), proxy=None, open_timeout=10)
    try:
        await socket.send(json.dumps({
            "type": "config",
            "configuration": {
                "transcription": {
                    "primaryLanguage": "zh-CN",
                    "diarize": False,
                    "isMultichannel": True,
                    "participants": [
                        {"channel": 0, "role": "clinician"},
                        {"channel": 1, "role": "patient"},
                    ],
                },
                "mode": {
                    "type": "facts",
                    "outputLocale": "zh-CN",
                    "factGenerationInterval": "fast_init",
                },
                "retentionPolicy": "none",
                "audioFormat": "audio/pcm; rate=16000; channels=2; bits=16",
                "audioEvents": {"enabled": True},
                "keyterms": {
                    "terms": [
                        {"term": "房颤"},
                        {"term": "Corti Health"},
                    ],
                },
            },
        }))
        accepted = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if accepted.get("type") != "CONFIG_ACCEPTED":
            raise RuntimeError("multichannel configuration was not accepted")
        transcription = accepted.get("configuration", {}).get("transcription", {})
        if (
            transcription.get("isMultichannel") is not True
            or transcription.get("diarize") is not False
            or "isDiarization" in transcription
        ):
            raise RuntimeError("multichannel resolved configuration was not Corti-shaped")
        if accepted.get("configuration", {}).get("keyterms") != {
            "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
        }:
            raise RuntimeError("ordered case-sensitive keyterms were not accepted")

        audio = _stereo_silence_and_tone(10.0)
        for start in range(0, len(audio), 64_000):
            await socket.send(audio[start:start + 64_000])
        event = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
        if event != {
            "type": "audioEvent",
            "data": {"event": "longSilenceDetected", "channel": 0, "startTimeMs": 0},
        }:
            raise RuntimeError("multichannel audio event lost its declared channel")

        await socket.send(json.dumps({"type": "end"}))
        unavailable = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
        if unavailable.get("error", {}).get("id") != "STT_UNAVAILABLE":
            raise RuntimeError("disabled per-channel STT did not fail closed")
        if json.loads(await asyncio.wait_for(socket.recv(), timeout=10)) != {
            "type": "usage", "credits": 0.0,
        }:
            raise RuntimeError("multichannel end did not emit usage")
        if json.loads(await asyncio.wait_for(socket.recv(), timeout=10)) != {"type": "ENDED"}:
            raise RuntimeError("multichannel end did not emit ENDED")
    finally:
        await socket.close(code=1000, reason="synthetic multichannel E2E complete")

    return {
        "status": "passed",
        "configuration": "pcm_s16le_stereo_16000",
        "channels": 2,
        "participant_mapping_verified": True,
        "channel_audio_event_verified": True,
        "fast_init_accepted": True,
        "keyterms_accepted": True,
        "decoder_reached": True,
        "expected_error_code": "STT_UNAVAILABLE",
        "real_patient_audio_used": False,
        "real_stt_used": False,
        "real_llm_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
