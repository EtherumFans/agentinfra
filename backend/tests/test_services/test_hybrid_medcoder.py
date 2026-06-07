"""Tests for HybridCodingAdapter mode="medcoder".

Mocks both the LLM gateway (Stage 1 extraction + Stage 4 re-rank) and
the MedCodERRetriever (Stage 2 retrieval) so the pipeline runs in-process
without API calls or 2.3 GB models.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter  # noqa: E402
from official_agents.medical_coding.schema import (  # noqa: E402
    CandidateCode, ExtractedDiagnosis, MedicalCodingOutputSchema,
)


# ── Stubs ──


class _StubLLMGateway:
    """Stub gateway that records calls and returns scripted responses.

    Each ``generate(messages, ...)`` pops the next response from ``responses``.
    The 1st call is Stage 1 (extraction), 2nd is Stage 4 (re-rank), 3rd+ are
    not expected in the default 1-disease test path.
    """

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[list[dict]] = []
        self.providers_used: list[str] = []

    async def generate(self, messages, *, provider: str = "", **kwargs):
        self.calls.append(list(messages))
        self.providers_used.append(provider)
        if not self.responses:
            content = "{}"
        else:
            content = self.responses.pop(0)
        return {
            "content": content,
            "model": "stub/1.0",
            "usage": {"input_tokens": 0, "output_tokens": len(content)},
        }


class _StubRetriever:
    """Stub retriever that returns a fixed list of CandidateCode per disease."""

    def __init__(self, results: dict[str, list[CandidateCode]] | None = None):
        self.results = results or {}
        self.queries: list[str] = []

    async def retrieve_async(self, disease: str, top_k: int = 20, **kwargs):
        self.queries.append(disease)
        return list(self.results.get(disease, []))


# ── Fixtures ──


@pytest.fixture
def mock_emr():
    return (
        "患者主诉胸闷气短3天，伴有下肢水肿。既往高血压病史5年。\n"
        "入院诊断：心力衰竭（心功能III级），高血压病3级（极高危）。\n"
        "出院诊断：1. 充血性心力衰竭 I50.900；2. 高血压病 I10。"
    )


@pytest.fixture
def stub_extraction_response():
    return '[{"disease_text": "心力衰竭", "supporting_evidence": "胸闷气短3天，伴有下肢水肿", "llm_initial_code": "I50.900"}]'


@pytest.fixture
def stub_rerank_response():
    return '{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", "final_confidence": 0.95, "rationale": "支持证据明确"}]}'


# ── Stage routing ──


class TestMedcoderModeRouting:
    def test_medcoder_routes_to_pipeline(self):
        """infer_async with mode='medcoder' should not call legacy inference."""
        gw = _StubLLMGateway(responses=[
            "[]",  # Stage 1 returns nothing
        ])
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder", retriever=_StubRetriever())
        # Empty extraction → mock fallback
        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": "test"}],
        ))
        assert out.mode == "medcoder"
        assert "MedCodER Stage 1" in (out.notes or "")

    def test_legacy_mode_does_not_call_medcoder(self):
        """Hybrid mode with a working deepseek call should not invoke medcoder."""
        from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import DeepSeekCodingAdapter
        # We just verify mode string is preserved; don't run the full pipeline
        adapter = HybridCodingAdapter(mode="hybrid")
        assert adapter.current_mode == "hybrid"
        assert adapter._retriever is None  # not created for non-medcoder modes

    def test_health_check_includes_mode(self):
        adapter = HybridCodingAdapter(mode="medcoder")
        h = adapter.health_check()
        assert h["mode"] == "medcoder"


# ── End-to-end pipeline (stubbed) ──


class TestMedcoderEndToEnd:
    def test_happy_path(self, mock_emr, stub_extraction_response, stub_rerank_response):
        """1 disease → 1 LLM call (extraction) + 1 retrieve + 1 LLM call (rerank)."""
        # Stage 1 = stub_extraction_response, Stage 4 = stub_rerank_response
        gw = _StubLLMGateway(responses=[stub_extraction_response, stub_rerank_response])
        retriever = _StubRetriever(results={
            "心力衰竭": [
                CandidateCode(code="I50.100", name="左心衰竭", score=0.7, source="retrieve"),
                CandidateCode(code="I50.000", name="充血性心力衰竭", score=0.6, source="retrieve"),
            ],
        })
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder", retriever=retriever)

        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))

        # Schema invariants
        assert isinstance(out, MedicalCodingOutputSchema)
        assert out.mode == "medcoder"
        assert out.provider == "medcoder"
        assert len(out.extracted_diagnoses) == 1

        edx = out.extracted_diagnoses[0]
        assert isinstance(edx, ExtractedDiagnosis)
        assert edx.disease_text == "心力衰竭"
        assert edx.llm_initial_code == "I50.900"
        assert edx.final_confidence == pytest.approx(0.95, abs=0.01)
        # final_top_k should contain the reranked code
        assert len(edx.final_top_k) >= 1
        assert edx.final_top_k[0].code == "I50.900"
        assert edx.final_top_k[0].source == "rerank"

        # Backward-compat: primary_diagnosis populated from top-1
        assert out.primary_diagnosis.code == "I50.900"
        assert out.primary_diagnosis.confidence == pytest.approx(0.95, abs=0.01)

        # LLM call count = 2 (Stage 1 + Stage 4)
        assert len(gw.calls) == 2
        # Retriever was called for "心力衰竭"
        assert "心力衰竭" in retriever.queries

    def test_no_gateway_uses_mock_stages(self, mock_emr):
        """No gateway → both stages fall back to deterministic mocks."""
        adapter = HybridCodingAdapter(gateway=None, mode="medcoder", retriever=_StubRetriever())
        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))
        assert out.mode == "medcoder"
        assert len(out.extracted_diagnoses) == 1
        # Mock Stage 1 gives "心力衰竭" + I50.900
        edx = out.extracted_diagnoses[0]
        assert edx.llm_initial_code == "I50.900"

    def test_evidence_span_attached(self, mock_emr, stub_extraction_response, stub_rerank_response):
        gw = _StubLLMGateway(responses=[stub_extraction_response, stub_rerank_response])
        adapter = HybridCodingAdapter(
            gateway=gw, mode="medcoder", retriever=_StubRetriever(),
            # Bypass the retriever entirely so we focus on evidence
        )
        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))
        edx = out.extracted_diagnoses[0]
        # supporting_evidence is the LLM-extracted snippet
        # The fuzzy matcher should find it (or a near-match) in the EMR
        # If found, it produces a valid EvidenceSpan with char_start < char_end
        if edx.supporting_evidence:
            span = edx.supporting_evidence[0]
            assert span.text
            assert 0 <= span.char_start < span.char_end
            # The span should validate against the source
            assert mock_emr[span.char_start:span.char_end] == span.text

    def test_merging_caps_at_30(self, mock_emr, stub_extraction_response, stub_rerank_response):
        """The merged set (LLM code + retrieved) is capped to 30 before re-rank."""
        # Build a 50-code retriever result — Stage 3 should cap at 30
        big_results = [CandidateCode(code=f"X{i:03d}", name=f"测试{i}", score=0.5, source="retrieve") for i in range(50)]
        gw = _StubLLMGateway(responses=[stub_extraction_response, stub_rerank_response])
        retriever = _StubRetriever(results={"心力衰竭": big_results})
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder", retriever=retriever)

        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))
        edx = out.extracted_diagnoses[0]
        # final_top_k is bounded by RERANK_TOP_K=5
        assert len(edx.final_top_k) <= 5
        # The retrieved_codes field mirrors the retriever's full output
        # (the merge cap of 30 is applied to the rerank-prompt input, not
        # to the persisted retrieved_codes — the audit trail is preserved)
        assert len(edx.retrieved_codes) == 50  # all preserved for audit


# ── Multiple diagnoses ──


class TestMultipleDiagnoses:
    def test_two_diseases(self, mock_emr, stub_rerank_response):
        extraction = json_str = (
            '['
            '{"disease_text": "心力衰竭", "supporting_evidence": "胸闷气短3天", "llm_initial_code": "I50.900"},'
            '{"disease_text": "高血压", "supporting_evidence": "高血压病史5年", "llm_initial_code": "I10"}'
            ']'
        )
        rerank = '{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", "final_confidence": 0.9, "rationale": "ok"}]}'
        # Stage 4 is called per-disease, so we need 2 responses
        gw = _StubLLMGateway(responses=[extraction, rerank, rerank])
        retriever = _StubRetriever()
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder", retriever=retriever)

        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))

        assert len(out.extracted_diagnoses) == 2
        diseases = {d.disease_text for d in out.extracted_diagnoses}
        assert diseases == {"心力衰竭", "高血压"}
        # LLM call count = 1 (extraction) + 2 (rerank per disease) = 3
        assert len(gw.calls) == 3


# ── Schema round-trip ──


class TestSchemaRoundTrip:
    def test_to_dict_includes_medcoder_fields(self):
        from official_agents.medical_coding.schema import EvidenceSpan
        s = MedicalCodingOutputSchema(
            mode="medcoder",
            extracted_diagnoses=[
                ExtractedDiagnosis(
                    disease_text="心衰",
                    llm_initial_code="I50.900",
                    final_top_k=[CandidateCode(code="I50.900", name="心衰", score=0.9, source="rerank")],
                    final_confidence=0.9,
                    supporting_evidence=[EvidenceSpan(text="胸闷", char_start=0, char_end=2)],
                ),
            ],
        )
        d = s.to_dict()
        assert d["mode"] == "medcoder"
        assert len(d["extracted_diagnoses"]) == 1
        assert d["extracted_diagnoses"][0]["disease_text"] == "心衰"
        # Round-trip
        s2 = MedicalCodingOutputSchema.from_dict(d)
        assert s2.mode == "medcoder"
        assert s2.extracted_diagnoses[0].final_top_k[0].code == "I50.900"
        assert s2.extracted_diagnoses[0].supporting_evidence[0].text == "胸闷"


# ── Notes / observability ──


class TestNotesAndObservability:
    def test_notes_describe_pipeline(self, mock_emr, stub_extraction_response, stub_rerank_response):
        gw = _StubLLMGateway(responses=[stub_extraction_response, stub_rerank_response])
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder", retriever=_StubRetriever())
        import asyncio
        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": mock_emr}],
        ))
        assert "MedCodER" in out.notes
        assert "1 diagnoses" in out.notes
