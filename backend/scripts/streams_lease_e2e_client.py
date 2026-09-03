"""Drive a two-worker Streams lease conflict and crash-recovery scenario."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode

import websockets


def _uri(base_url: str, interaction_id: str, tenant: str, token: str) -> str:
    websocket_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    query = urlencode({
        "environment": "cn",
        "tenant-name": tenant,
        "token": token,
    })
    return (
        f"{websocket_base}/api/v2/tools/streams/{quote(interaction_id, safe='')}"
        f"?{query}"
    )


def _config() -> str:
    return json.dumps({
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
            "audioFormat": "audio/pcm; rate=16000; channels=1; bits=16",
        },
    })


async def _accepted_session(uri: str):
    socket = await websockets.connect(uri, proxy=None, open_timeout=10)
    await socket.send(_config())
    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
    if message.get("type") != "CONFIG_ACCEPTED":
        await socket.close()
        raise RuntimeError("Streams configuration was not accepted")
    return socket, str(message.get("sessionId") or "")


async def run(args: argparse.Namespace) -> dict[str, object]:
    primary_uri = _uri(args.primary, args.interaction_id, args.tenant, args.token)
    secondary_uri = _uri(args.secondary, args.interaction_id, args.tenant, args.token)
    primary_socket, first_session = await _accepted_session(primary_uri)

    checkpoint_audio = b"\x00\x00" * 320
    await primary_socket.send(checkpoint_audio)
    await primary_socket.send(json.dumps({"type": "flush"}))
    flush_events: list[str] = []
    while True:
        message = json.loads(await asyncio.wait_for(primary_socket.recv(), timeout=10))
        flush_events.append(str(message.get("type") or ""))
        if message.get("type") == "delta_usage":
            break
    if flush_events[-2:] != ["flushed", "delta_usage"]:
        raise RuntimeError("Primary worker did not durably flush checkpointed audio")

    conflict_rejected = False
    conflict_socket = None
    try:
        conflict_socket = await websockets.connect(
            secondary_uri,
            proxy=None,
            open_timeout=10,
        )
        await conflict_socket.send(_config())
        message = json.loads(await asyncio.wait_for(conflict_socket.recv(), timeout=5))
        if message.get("type") == "CONFIG_ACCEPTED":
            raise RuntimeError("Secondary worker accepted a concurrent duplicate stream")
    except RuntimeError:
        raise
    except Exception:
        conflict_rejected = True
    finally:
        if conflict_socket is not None:
            await conflict_socket.close()

    args.ready.write_text("ready\n", encoding="utf-8")
    deadline = asyncio.get_running_loop().time() + 30
    while not args.resume.exists():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Crash recovery continuation was not signaled")
        await asyncio.sleep(0.1)

    try:
        await primary_socket.close()
    except Exception:
        pass

    recovered_socket, recovered_session = await _accepted_session(secondary_uri)
    try:
        await recovered_socket.send(json.dumps({"type": "end"}))
        event_types: list[str] = []
        while True:
            message = json.loads(await asyncio.wait_for(recovered_socket.recv(), timeout=10))
            event_types.append(str(message.get("type") or ""))
            if message.get("type") == "ENDED":
                break
    finally:
        await recovered_socket.close()

    if event_types[-2:] != ["usage", "ENDED"]:
        raise RuntimeError("Recovered session did not complete in current usage/end order")
    return {
        "status": "passed",
        "conflict_rejected": conflict_rejected,
        "crash_recovered": True,
        "session_fence_rotated": bool(
            first_session and recovered_session and first_session != recovered_session
        ),
        "checkpointed_audio_bytes": len(checkpoint_audio),
        "checkpoint_flush_event_types": flush_events,
        "recovered_event_types": event_types,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", required=True)
    parser.add_argument("--secondary", required=True)
    parser.add_argument("--interaction-id", required=True)
    parser.add_argument("--ready", required=True, type=Path)
    parser.add_argument("--resume", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.tenant = os.environ.get("ICODER_E2E_STREAMS_TENANT", "")
    args.token = os.environ.get("ICODER_E2E_STREAMS_TOKEN", "")
    if not args.tenant or not args.token:
        raise RuntimeError("missing isolated Streams lease E2E credentials")
    result = asyncio.run(run(args))
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
