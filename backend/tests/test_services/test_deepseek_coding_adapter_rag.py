"""Test that DeepSeekCodingAdapter injects the RAG candidate block into the
system prompt sent to the LLM gateway. Uses a fake gateway that captures
the messages instead of calling DeepSeek.
"""
import json
import pytest

from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
    DeepSeekCodingAdapter,
)


class _FakeProvider:
    """Mimics a LLMGateway provider with health_check returning configured."""
    def health_check(self):
        return {"status": "configured", "model": "deepseek-v4"}


class _FakeGateway:
    is_configured = True

    def __init__(self, response_data: dict):
        self.captured_messages = None
        self.response = {"content": json.dumps(response_data, ensure_ascii=False)}

    def get(self, name):
        return _FakeProvider()

    async def generate(self, messages, provider=None):
        self.captured_messages = list(messages)
        return self.response


def _make_response():
    """Minimal valid MedicalCodingOutputSchema JSON."""
    return {
        "review_conclusion": "PASS",
        "primary_diagnosis": {
            "code": "M80.900",
            "description": "老年性骨质疏松",
            "confidence": 0.9,
            "category": "principal",
            "evidence": ["重度骨质疏松伴椎体压缩骨折"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [],
        "manual_review_required": False,
        "confidence": 0.9,
        "notes": "",
    }


@pytest.mark.asyncio
async def test_rag_block_appears_in_system_prompt():
    """When given a 骨质疏松 encounter, the system prompt must contain
    '候选编码参考' and an M80.x candidate code."""
    gw = _FakeGateway(_make_response())
    adapter = DeepSeekCodingAdapter(gateway=gw, max_retries=0, timeout=30)

    await adapter.infer_async([{
        "role": "user",
        "content": "重度骨质疏松伴椎体压缩骨折，高龄女性，予降钙素治疗",
    }])

    # The first message is the system prompt
    assert gw.captured_messages is not None
    sys_msg = gw.captured_messages[0]["content"]
    assert "候选编码参考" in sys_msg, f"system prompt missing RAG block: {sys_msg[:500]}"
    assert any(c in sys_msg for c in ("M80", "M80.0", "M80.900", "M80.9"))


@pytest.mark.asyncio
async def test_rag_block_omitted_for_empty_user_text():
    """If there's no user text, the system prompt is just CODING_SYSTEM_PROMPT
    (no RAG block, no crash)."""
    gw = _FakeGateway(_make_response())
    adapter = DeepSeekCodingAdapter(gateway=gw, max_retries=0, timeout=30)

    await adapter.infer_async([{"role": "user", "content": ""}])

    sys_msg = gw.captured_messages[0]["content"]
    # No RAG block injected for empty input
    assert "候选编码参考" not in sys_msg


@pytest.mark.asyncio
async def test_rag_block_present_for_heart_failure():
    """I50 heart failure encounter → RAG block should include I50.x."""
    gw = _FakeGateway(_make_response())
    adapter = DeepSeekCodingAdapter(gateway=gw, max_retries=0, timeout=30)

    await adapter.infer_async([{
        "role": "user",
        "content": "充血性心力衰竭 NYHA III级，高血压 3 级",
    }])

    sys_msg = gw.captured_messages[0]["content"]
    assert "候选编码参考" in sys_msg
    assert "I50" in sys_msg
