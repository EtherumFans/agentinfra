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


def test_system_prompt_forbids_unsupported_pathological_fracture_inference():
    from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
        CODING_SYSTEM_PROMPT,
    )

    assert "骨质疏松与骨折并存不得自动推断因果" in CODING_SYSTEM_PROMPT
    assert "骨质疏松症 + 椎体压缩骨折 + 高龄 → M80.0" not in CODING_SYSTEM_PROMPT


def test_catalog_boundary_withholds_ghost_codes_and_canonicalizes_case():
    from official_agents.medical_coding.schema import (
        DiagnosisEntry,
        MedicalCodingOutputSchema,
        ProcedureEntry,
    )

    schema = MedicalCodingOutputSchema(
        review_conclusion="PASS",
        primary_diagnosis=DiagnosisEntry(code="I10.X09", category="principal"),
        secondary_diagnoses=[DiagnosisEntry(code="M80.08")],
        procedures=[
            ProcedureEntry(code="36.0601"),
            ProcedureEntry(code="81.05"),
        ],
    )

    result = DeepSeekCodingAdapter._enforce_governed_catalog(schema)

    assert result.primary_diagnosis.code == "I10.x09"
    assert result.secondary_diagnoses == []
    assert [item.code for item in result.procedures] == ["36.0601"]
    assert result.review_conclusion == "WARNING"
    assert result.manual_review_required is True
    assert [issue.code for issue in result.issues_found] == [
        "CATALOG_CODE_WITHHELD",
        "CATALOG_CODE_WITHHELD",
    ]


@pytest.mark.asyncio
async def test_rag_block_appears_in_system_prompt():
    """Documented osteoporosis reaches the governed catalog without
    inferring a pathological-fracture relationship."""
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
    assert "M81.900" in sys_msg


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


@pytest.mark.asyncio
async def test_combined_coding_request_injects_icd9cm3_procedure_candidate():
    gw = _FakeGateway(_make_response())
    adapter = DeepSeekCodingAdapter(gateway=gw, max_retries=0, timeout=30)

    await adapter.infer_async(
        [{
            "role": "user",
            "content": "Acute appendicitis. Underwent laparoscopic appendectomy.",
        }],
        context={"coding_systems": ["icd10cn", "icd9cm3"]},
    )

    sys_msg = gw.captured_messages[0]["content"]
    assert "[icd9cm3]" in sys_msg
    assert "47.0100" in sys_msg


@pytest.mark.asyncio
async def test_project_policy_is_applied_additively_without_result_leakage():
    sentinel = "MEDICAL_PROJECT_POLICY_SECRET_SENTINEL"
    gw = _FakeGateway(_make_response())
    adapter = DeepSeekCodingAdapter(gateway=gw, max_retries=0, timeout=30)

    result = await adapter.infer_async(
        [{"role": "user", "content": "高血压，血压 160/100 mmHg"}],
        context={"project_policy": sentinel, "coding_systems": ["icd10cn"]},
    )

    sys_msg = gw.captured_messages[0]["content"]
    assert sentinel in sys_msg
    assert "IMMUTABLE_MEDICAL_CODING_BOUNDARY" in sys_msg
    assert "不得返回 ICD-9-CM-3" in sys_msg
    assert sentinel not in repr(result)


@pytest.mark.asyncio
async def test_invalid_structured_response_gets_one_bounded_repair_retry(caplog):
    sentinel = "PRIVATE_INVALID_PROVIDER_OUTPUT_SENTINEL"

    class SequentialGateway(_FakeGateway):
        def __init__(self):
            super().__init__(_make_response())
            self.calls = 0
            self.all_messages = []

        async def generate(self, messages, provider=None):
            self.calls += 1
            self.all_messages.append(list(messages))
            if self.calls == 1:
                return {"content": sentinel}
            return self.response

    gateway = SequentialGateway()
    adapter = DeepSeekCodingAdapter(gateway=gateway, max_retries=0)

    result = await adapter.infer_async([{"role": "user", "content": "高血压"}])

    assert result.review_conclusion == "PASS"
    assert gateway.calls == 2
    assert "prior response did not satisfy the JSON contract" in (
        gateway.all_messages[1][0]["content"]
    )
    assert sentinel not in caplog.text


@pytest.mark.asyncio
async def test_invalid_structured_response_fails_closed_after_one_retry():
    class AlwaysInvalidGateway(_FakeGateway):
        def __init__(self):
            super().__init__(_make_response())
            self.calls = 0

        async def generate(self, messages, provider=None):
            self.calls += 1
            return {"content": "not-json"}

    gateway = AlwaysInvalidGateway()
    adapter = DeepSeekCodingAdapter(gateway=gateway, max_retries=0)

    result = await adapter.infer_async([{"role": "user", "content": "高血压"}])

    assert result.review_conclusion == "FAIL"
    assert result.degraded_reason == "invalid_response"
    assert gateway.calls == 2
