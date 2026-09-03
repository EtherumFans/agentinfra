"""Unit tests for real Ambient processing adapters."""

from __future__ import annotations

import pytest
import wave

from app.services.ambient_processing import (
    extract_stream_facts,
    parse_stream_facts,
    transcribe_stream_audio,
)


def test_parse_stream_facts_accepts_fenced_object_and_deduplicates():
    facts = parse_stream_facts(
        """```json
        {"facts": [
          {"group": "chief-complaint", "text": "胸痛三天"},
          {"group": "chief-complaint", "text": "胸痛三天"},
          {"group": "medications-prior-to-visit", "value": "阿司匹林"},
          {"group": "empty", "text": ""}
        ]}
        ```"""
    )
    assert [(fact.group, fact.text) for fact in facts] == [
        ("chief-complaint", "胸痛三天"),
        ("medications-prior-to-visit", "阿司匹林"),
    ]


@pytest.mark.asyncio
async def test_transcribe_stream_audio_rejects_unverified_language_without_calling_asr(
    monkeypatch,
):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("ASR must not run for an unsupported language")

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", should_not_run)
    assert await transcribe_stream_audio(
        b"audio", media_type="audio/webm", primary_language="en-US"
    ) == ("", "unsupported_language")


@pytest.mark.asyncio
async def test_recommended_pcm_is_wrapped_as_wave_before_local_asr(monkeypatch):
    observed = {}

    async def inspect_wave(path):
        with wave.open(path, "rb") as reader:
            observed.update({
                "channels": reader.getnchannels(),
                "sample_width": reader.getsampwidth(),
                "rate": reader.getframerate(),
                "frames": reader.readframes(reader.getnframes()),
            })
        return "患者胸痛。", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_audio", inspect_wave)
    pcm = b"\x00\x00\x01\x00"
    result = await transcribe_stream_audio(
        pcm,
        media_type=(
            "audio/pcm; rate=16000; channels=1; bits=16; "
            "endian=little; encoding=sint"
        ),
        primary_language="zh-CN",
    )

    assert result == ("患者胸痛。", "")
    assert observed == {
        "channels": 1,
        "sample_width": 2,
        "rate": 16000,
        "frames": pcm,
    }


@pytest.mark.asyncio
async def test_stream_keyterms_are_forwarded_without_logging_or_rewriting(monkeypatch):
    observed = {}

    async def capture(_audio, _media_type, *, keyterms):
        observed["keyterms"] = keyterms
        return "房颤复诊。", ""

    monkeypatch.setattr("app.services.stt_service.transcribe_bytes", capture)
    result = await transcribe_stream_audio(
        b"audio",
        media_type="audio/ogg",
        primary_language="zh-CN",
        keyterms=("房颤", "Corti Health"),
    )

    assert result == ("房颤复诊。", "")
    assert observed["keyterms"] == ("房颤", "Corti Health")


@pytest.mark.asyncio
async def test_extract_stream_facts_uses_real_llm_result(monkeypatch):
    observed = {}

    class FakeGateway:
        async def generate(self, messages, **kwargs):
            observed["messages"] = messages
            observed.update(kwargs)
            return {
                "content": '[{"group":"assessment","text":"考虑冠心病"}]',
                "usage": {"total_tokens": 20},
            }

    from app.main import app

    monkeypatch.setattr(app.state, "platform_gateway", FakeGateway(), raising=False)
    facts = await extract_stream_facts("患者胸痛三天", output_language="zh-CN")
    assert [(fact.group, fact.text) for fact in facts] == [
        ("assessment", "考虑冠心病")
    ]
    assert observed["messages"][-1]["content"] == "患者胸痛三天"
    assert observed["context"] == {
        "operation": "corti_stream_facts",
        "clinical": True,
    }


@pytest.mark.asyncio
async def test_extract_stream_facts_rejects_degraded_provider(monkeypatch):
    class DegradedGateway:
        async def generate(self, *_args, **_kwargs):
            return {
                "content": '[{"group":"assessment","text":"不应返回"}]',
                "is_mock": True,
            }

    from app.main import app

    monkeypatch.setattr(app.state, "platform_gateway", DegradedGateway(), raising=False)
    with pytest.raises(RuntimeError, match="facts_provider_degraded"):
        await extract_stream_facts("患者胸痛三天", output_language="zh-CN")
