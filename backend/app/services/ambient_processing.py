"""Real processing primitives for the Corti-compatible Ambient stream."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.schemas.v2_tools_facts import FACTSR_SYSTEM_PROMPT_EN


@dataclass(frozen=True)
class ExtractedStreamFact:
    group: str
    text: str


@dataclass(frozen=True)
class StreamFactExtraction:
    facts: tuple[ExtractedStreamFact, ...]
    usage: dict[str, int | float | str]


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines.pop()
    return "\n".join(lines).strip()


def parse_stream_facts(raw: str) -> list[ExtractedStreamFact]:
    """Parse model JSON without inventing or repairing clinical facts."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(_strip_code_fence(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("facts", [])
    if not isinstance(payload, list):
        return []

    facts: list[ExtractedStreamFact] = []
    seen: set[tuple[str, str]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        group = str(item.get("group", "") or "").strip() or "other"
        text = str(item.get("text", "") or item.get("value", "") or "").strip()
        identity = (group, text)
        if not text or identity in seen:
            continue
        seen.add(identity)
        facts.append(ExtractedStreamFact(group=group, text=text))
    return facts


async def transcribe_stream_audio(
    audio: bytes,
    *,
    media_type: str,
    primary_language: str,
    keyterms: tuple[str, ...] = (),
) -> tuple[str, str]:
    """Run the configured ASR engine for the accumulated stream buffer."""
    if not primary_language.lower().startswith("zh"):
        return "", "unsupported_language"
    # Resolve dynamically so test and deployment adapters can replace the
    # engine without a stale function alias in this long-lived module.
    from app.services import stt_service

    if keyterms:
        return await stt_service.transcribe_bytes(
            audio,
            media_type,
            keyterms=keyterms,
        )
    return await stt_service.transcribe_bytes(audio, media_type)


def deinterleave_pcm_s16le(audio: bytes, *, channels: int) -> tuple[bytes, ...]:
    """Split aligned interleaved signed 16-bit little-endian PCM by channel.

    The operation is deliberately implemented without native audio libraries so
    the Streams boundary remains deterministic and safe on Windows.  It does
    not resample or infer speakers: one declared input channel maps to one
    output channel exactly.
    """
    if channels < 2 or channels > 8:
        raise ValueError("pcm_multichannel_count_not_supported")
    frame_bytes = channels * 2
    if not audio or len(audio) % frame_bytes:
        raise ValueError("pcm_multichannel_frame_alignment_invalid")
    outputs = [bytearray() for _ in range(channels)]
    view = memoryview(audio)
    for frame_start in range(0, len(audio), frame_bytes):
        for channel in range(channels):
            sample_start = frame_start + channel * 2
            outputs[channel].extend(view[sample_start:sample_start + 2])
    return tuple(bytes(output) for output in outputs)


async def extract_stream_facts(
    transcript: str,
    *,
    output_language: str,
) -> list[ExtractedStreamFact]:
    """Compatibility wrapper returning only verified Provider-derived facts."""
    extraction = await extract_stream_facts_with_usage(
        transcript,
        output_language=output_language,
    )
    return list(extraction.facts)


def _safe_usage(value: Any) -> dict[str, int | float | str]:
    """Keep only bounded, content-free Provider accounting fields."""
    if not isinstance(value, dict):
        return {}
    safe: dict[str, int | float | str] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 10_000_000:
            safe[key] = item
    for key in ("cost_usd",):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool) and 0 <= float(item) <= 1_000_000:
            safe[key] = round(float(item), 8)
    for key in ("provider", "model"):
        item = value.get(key)
        if isinstance(item, str) and 0 < len(item) <= 128 and all(
            char.isascii() and (char.isalnum() or char in "._:/@+-")
            for char in item
        ):
            safe[key] = item
    return safe


async def extract_stream_facts_with_usage(
    transcript: str,
    *,
    output_language: str,
) -> StreamFactExtraction:
    """Extract facts through the governed gateway and reject degraded output."""
    if not transcript.strip():
        return StreamFactExtraction(facts=(), usage={})
    from app.main import app as application

    gateway = getattr(application.state, "platform_gateway", None)
    if gateway is None:
        raise RuntimeError("platform_gateway_unavailable")
    result = await gateway.generate(
        [
            {
                "role": "system",
                "content": f"{FACTSR_SYSTEM_PROMPT_EN}\n\noutputLanguage={output_language}.",
            },
            {"role": "user", "content": transcript},
        ],
        response_schema={
            "type": "object",
            "required": ["facts"],
            "properties": {"facts": {"type": "array"}},
        },
        context={"operation": "corti_stream_facts", "clinical": True},
    )
    if not isinstance(result, dict):
        raise RuntimeError("facts_provider_response_invalid")
    if result.get("degraded") is True or result.get("is_mock") is True:
        raise RuntimeError("facts_provider_degraded")
    content = result.get("content", "") if isinstance(result, dict) else ""
    facts = tuple(parse_stream_facts(content))
    return StreamFactExtraction(
        facts=facts,
        usage=_safe_usage(result.get("usage")),
    )


__all__ = [
    "ExtractedStreamFact",
    "StreamFactExtraction",
    "extract_stream_facts",
    "extract_stream_facts_with_usage",
    "parse_stream_facts",
    "deinterleave_pcm_s16le",
    "transcribe_stream_audio",
]
