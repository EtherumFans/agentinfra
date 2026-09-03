"""Real loopback Streams smoke using generated silent Ogg/Opus audio."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from icoder_sdk import iCoDerClient, iCoDerConfig


async def main() -> None:
    base_url = os.environ.get("ICODER_E2E_STREAMS_BASE_URL", "")
    access_token = os.environ.get("ICODER_E2E_ACCESS_TOKEN", "")
    tenant_name = os.environ.get("ICODER_E2E_TENANT_NAME", "")
    audio_path = os.environ.get("ICODER_E2E_STREAMS_AUDIO_PATH", "")
    if not base_url or not access_token or not tenant_name or not audio_path:
        raise RuntimeError("missing local Streams E2E environment")
    audio = Path(audio_path).read_bytes()
    interaction_id = str(uuid.uuid4())
    client = iCoDerClient(iCoDerConfig(base_url=base_url, access_token=access_token))
    messages: list[dict] = []
    try:
        session = await client.streams.connect_async(
            interaction_id=interaction_id,
            tenant_name=tenant_name,
            environment="cn",
            configuration={
                "transcription": {
                    "primaryLanguage": "zh-CN",
                    "diarize": False,
                    "isMultichannel": False,
                    "participants": [{"channel": 0, "role": "multiple"}],
                },
                "mode": {"type": "transcription"},
                "retentionPolicy": "none",
                "audioFormat": "audio/ogg; codecs=opus",
            },
        )
        session.on("message", messages.append)
        await session.send_audio(audio)
        await session.flush()
        await session.end()
        await asyncio.wait_for(session.wait_ended(), timeout=15)
        types = [message.get("type") for message in messages]
        for required in ("flushed", "delta_usage", "usage", "ENDED"):
            if required not in types:
                raise RuntimeError(f"missing Streams event: {required}")
        error_codes = sorted(
            message.get("code")
            for message in messages
            if message.get("type") == "error"
        )
        if error_codes != ["STT_UNAVAILABLE"]:
            raise RuntimeError("local disabled-provider errors were not explicit and bounded")
        usage = next(message for message in messages if message.get("type") == "usage")
        if usage.get("credits") != 0.0:
            raise RuntimeError("local Streams usage must not invent credits")
        await session.close()
        print(json.dumps({
            "sdk": "python",
            "status": "passed",
            "interaction_id": interaction_id,
            "retention_policy": "none",
            "event_types": types,
            "expected_error_codes": error_codes,
            "synthetic_audio_bytes": len(audio),
            "synthetic_silence_ogg_opus": True,
            "real_stt_engine_used": False,
            "real_llm_used": False,
        }, sort_keys=True))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
