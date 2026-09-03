"""Real loopback WebSocket recovery smoke with synthetic non-audio bytes."""

from __future__ import annotations

import asyncio
import json
import os

from icoder_sdk import iCoDerClient, iCoDerConfig


async def main() -> None:
    base_url = os.environ.get("ICODER_E2E_STT_BASE_URL", "")
    access_token = os.environ.get("ICODER_E2E_ACCESS_TOKEN", "")
    if not base_url or not access_token:
        raise RuntimeError("missing local STT E2E environment")
    client = iCoDerClient(iCoDerConfig(base_url=base_url, access_token=access_token))
    reconnecting: list[dict] = []
    acknowledgements: list[dict] = []
    terminal = asyncio.get_running_loop().create_future()
    try:
        session = await client.speech_to_text.connect_managed_session_async(
            reconnect_attempts=2,
            reconnect_initial_delay=0,
            reconnect_max_delay=0,
            setup_timeout=5,
        )
        session.on("reconnecting", reconnecting.append)
        session.on(
            "message",
            lambda message: acknowledgements.append(message)
            if message.get("type") == "audio_ack"
            else None,
        )
        session.on(
            "error",
            lambda error: terminal.set_result(error)
            if error.code == "transcription_failed" and not terminal.done()
            else None,
        )
        await session.send_audio(b"ICODER")
        await session.send_end()
        await asyncio.wait_for(terminal, timeout=15)
        if len(reconnecting) != 1 or len(acknowledgements) < 2:
            raise RuntimeError("managed STT did not prove one disconnect and replay")
        await session.close()
        print(json.dumps({
            "sdk": "python",
            "status": "passed",
            "reconnects": len(reconnecting),
            "acknowledgements": len(acknowledgements),
            "synthetic_audio_bytes": 6,
            "real_stt_engine_used": False,
        }, sort_keys=True))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
