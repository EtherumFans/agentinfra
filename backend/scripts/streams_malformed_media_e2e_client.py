"""Prove that a plausible Ogg/Opus header cannot bypass decoder validation."""

from __future__ import annotations

import asyncio
import json
import os
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
                "retentionPolicy": "retain",
                "audioFormat": "audio/ogg; codecs=opus",
            },
        }))
        accepted = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if accepted.get("type") != "CONFIG_ACCEPTED":
            raise RuntimeError("malformed-media configuration was not accepted")

        # The header probe accepts this shape, but it is not a decodable Ogg
        # page. No patient or human audio is used.
        await socket.send(b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 64)
        await socket.send(json.dumps({"type": "end"}))
        error = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if (error.get("error") or {}).get("id") != "AUDIO_DECODE_INVALID":
            raise RuntimeError("malformed media did not fail at the isolated decoder")
        try:
            await socket.recv()
        except websockets.ConnectionClosed as closed:
            if closed.code != 4400:
                raise RuntimeError("malformed media closed with an unexpected code") from None
        else:
            raise RuntimeError("malformed media stream did not close")
    finally:
        await socket.close()

    return {
        "status": "passed",
        "plausible_header_rejected_by_decoder": True,
        "error_code": "AUDIO_DECODE_INVALID",
        "close_code": 4400,
        "asr_reached": False,
        "retention_reached": False,
        "real_audio_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
