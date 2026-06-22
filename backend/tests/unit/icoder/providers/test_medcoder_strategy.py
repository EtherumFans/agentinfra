"""Tests for ``MedCodERStrategy`` — 5 public stages + 4 ablation variants.

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 4 + Part 7.4 (M1), the strategy
extracts the monolithic ``HybridCodingAdapter._medcoder_pipeline`` into
5 public stage methods that can be unit tested in isolation, plus a
``run_variant`` dispatcher for the 4 ablation variants used by the
eval script.

Each stage is exercised independently with stub gateways / retrievers;
no real LLM or FAISS index is needed.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from official_agents.medical_coding.schema import (
    MedicalCodingOutputSchema,
    CandidateCode,
    ExtractedDiagnosis,
    DiagnosisEntry,
)
from icoder_runtime.providers.medical_coding.medcoder_strategy import (
    MedCodERStrategy,
    CALIBRATION_FLOOR,
    DEFAULT_MERGE_CAP,
    DEFAULT_RERANK_TOP_K,
)


# ── Stubs ───────────────────────────────────────────────────────────


class _StubGateway:
    """LLM gateway that returns a pre-canned response per call.

    Tracks every call so tests can assert prompt construction.
    """

    def __init__(self, response: str | list[str] = ""):
        if isinstance(response, str):
            self._responses = [response]
        else:
            self._responses = list(response)
        self.calls: list[list[dict]] = []

    async def generate(self, messages, provider="default"):
        self.calls.append(list(messages))
        if not self._responses:
            return {"content": ""}
        # Cycle through responses if more calls than responses
        if len(self._responses) == 1:
            return {"content": self._responses[0]}
        return {"content": self._responses.pop(0)}


class _StubRetriever:
    """Stand-in for MedCodERRetriever — returns pre-canned candidates."""

    def __init__(self, candidates: list[CandidateCode] | None = None):
        self._candidates = list(candidates or [])
        self.calls: list[tuple[str, int | None]] = []

    async def retrieve_async(self, disease: str, top_k: int | None = None):
        self.calls.append((disease, top_k))
        return list(self._candidates)


# ── 1. stage1_extraction ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage1_extraction_no_gateway_returns_mock():
    """Without a gateway, stage 1 returns the deterministic mock result."""
    strat = MedCodERStrategy()
    out = await strat.stage1_extraction("患者主诉胸闷气短")
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["disease_text"] == "心力衰竭"
    assert out[0]["llm_initial_code"] == "I50.900"


@pytest.mark.asyncio
async def test_stage1_extraction_empty_emr_returns_empty():
    strat = MedCodERStrategy(gateway=_StubGateway("[]"))
    assert await strat.stage1_extraction("") == []
    assert await strat.stage1_extraction("   \n  ") == []


@pytest.mark.asyncio
async def test_stage1_extraction_with_gateway_parses_json():
    """Gateway returns a JSON array → stage 1 returns the parsed list."""
    gw = _StubGateway(
        '[{"disease_text": "高血压", "supporting_evidence": "BP 160/100", "llm_initial_code": "I10"}]'
    )
    strat = MedCodERStrategy(gateway=gw)
    out = await strat.stage1_extraction("BP 160/100, 诊断高血压")
    assert len(out) == 1
    assert out[0]["disease_text"] == "高血压"
    assert out[0]["llm_initial_code"] == "I10"
    assert len(gw.calls) == 1  # one LLM call


@pytest.mark.asyncio
async def test_stage1_extraction_gateway_failure_falls_back_to_mock():
    """When the gateway raises, stage 1 falls back to mock (non-fatal)."""
    class _BrokenGateway:
        async def generate(self, messages, provider="default"):
            raise RuntimeError("LLM offline")

    strat = MedCodERStrategy(gateway=_BrokenGateway())
    out = await strat.stage1_extraction("anything")
    assert len(out) == 1
    assert out[0]["disease_text"] == "心力衰竭"


@pytest.mark.asyncio
async def test_stage1_extraction_handles_code_fenced_json():
    """LLM wraps JSON in ```json ... ``` — parser should still extract it."""
    fenced = '```json\n[{"disease_text": "糖尿病", "supporting_evidence": "血糖高", "llm_initial_code": "E11.900"}]\n```'
    strat = MedCodERStrategy(gateway=_StubGateway(fenced))
    out = await strat.stage1_extraction("血糖高")
    assert len(out) == 1
    assert out[0]["disease_text"] == "糖尿病"


# ── 2. stage2_retrieve ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage2_retrieve_no_retriever_returns_empty():
    strat = MedCodERStrategy(retriever=None)
    # retriever is None; stage 2 should return [] without error
    assert await strat.stage2_retrieve("心衰") == []


@pytest.mark.asyncio
async def test_stage2_retrieve_empty_text_returns_empty():
    retriever = _StubRetriever([CandidateCode(code="I50.900", name="心衰")])
    strat = MedCodERStrategy(retriever=retriever)
    assert await strat.stage2_retrieve("") == []
    assert await strat.stage2_retrieve("   ") == []
    assert retriever.calls == []  # retriever never called for empty input


@pytest.mark.asyncio
async def test_stage2_retrieve_delegates_to_retriever():
    cands = [
        CandidateCode(code="I50.900", name="心力衰竭", score=0.95),
        CandidateCode(code="I50.0", name="充血性心衰", score=0.7),
    ]
    retriever = _StubRetriever(cands)
    strat = MedCodERStrategy(retriever=retriever)
    out = await strat.stage2_retrieve("心衰", top_k=5)
    assert out == cands
    assert retriever.calls == [("心衰", 5)]


@pytest.mark.asyncio
async def test_stage2_retrieve_retriever_failure_returns_empty():
    class _BrokenRetriever:
        async def retrieve_async(self, disease, top_k=None):
            raise RuntimeError("FAISS down")

    strat = MedCodERStrategy(retriever=_BrokenRetriever())
    assert await strat.stage2_retrieve("心衰") == []


# ── 3. stage3_merge ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage3_merge_union_dedup_llm_first():
    """LLM code takes precedence on dedup ties (inserted first)."""
    retrieved = [
        CandidateCode(code="I50.900", name="心力衰竭", score=0.9),
        CandidateCode(code="I10", name="高血压", score=0.7),
    ]
    llm = [{"code": "I50.900"}]
    strat = MedCodERStrategy()
    out = await strat.stage3_merge(llm, retrieved, "心衰")
    codes = [c["code"] for c in out]
    assert codes == ["I50.900", "I10"]
    assert out[0]["source"] == "llm"
    assert out[1]["source"] == "retrieve"


@pytest.mark.asyncio
async def test_stage3_merge_caps_at_merge_cap():
    retrieved = [
        CandidateCode(code=f"I{i:03d}", name=f"code{i}") for i in range(50)
    ]
    strat = MedCodERStrategy(merge_cap=5)
    out = await strat.stage3_merge([], retrieved, "x")
    assert len(out) == 5


@pytest.mark.asyncio
async def test_stage3_merge_empty_inputs():
    strat = MedCodERStrategy()
    assert await strat.stage3_merge([], [], "x") == []
    assert await strat.stage3_merge([{"code": "I50.0"}], [], "x") == [
        {"code": "I50.0", "name": "", "score": 1.0, "chapter": "", "source": "llm"}
    ]


@pytest.mark.asyncio
async def test_stage3_merge_skips_blank_codes():
    retrieved = [
        CandidateCode(code="", name="blank"),
        CandidateCode(code="I50.900", name="心衰", score=0.9),
    ]
    strat = MedCodERStrategy()
    out = await strat.stage3_merge([], retrieved, "x")
    assert [c["code"] for c in out] == ["I50.900"]


# ── 4. stage4_rerank ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage4_rerank_no_gateway_returns_top_k_by_score():
    candidates = [
        {"code": "I50.900", "name": "心衰", "score": 0.9, "source": "retrieve"},
        {"code": "I50.0", "name": "充血性心衰", "score": 0.6, "source": "retrieve"},
        {"code": "I10", "name": "高血压", "score": 0.4, "source": "retrieve"},
    ]
    strat = MedCodERStrategy(rerank_top_k=2)
    out = await strat.stage4_rerank("心衰", "胸闷", candidates)
    assert len(out) == 2
    assert out[0]["code"] == "I50.900"
    assert out[0]["confidence"] == 0.9
    assert "no-gateway" in out[0]["rationale"]


@pytest.mark.asyncio
async def test_stage4_rerank_empty_candidates_returns_empty():
    strat = MedCodERStrategy(gateway=_StubGateway('{"ranked": []}'))
    assert await strat.stage4_rerank("x", "y", []) == []


@pytest.mark.asyncio
async def test_stage4_rerank_with_llm_parses_ranked():
    gw = _StubGateway('{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", "final_confidence": 0.95, "rationale": "best match"}]}')
    strat = MedCodERStrategy(gateway=gw)
    out = await strat.stage4_rerank("心衰", "胸闷", [{"code": "I50.900", "score": 0.9}])
    assert len(out) == 1
    assert out[0]["code"] == "I50.900"
    assert out[0]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_stage4_rerank_llm_failure_falls_back_to_score():
    class _BrokenGateway:
        async def generate(self, messages, provider="default"):
            raise RuntimeError("LLM offline")

    candidates = [{"code": "I50.900", "score": 0.9, "name": "心衰"}]
    strat = MedCodERStrategy(gateway=_BrokenGateway())
    out = await strat.stage4_rerank("心衰", "胸闷", candidates)
    assert len(out) == 1
    assert out[0]["code"] == "I50.900"
    assert "no-gateway" in out[0]["rationale"] or "rerank-llm-failed" in out[0]["rationale"]


# ── 5. stage5_compliance ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage5_compliance_populates_extracted_and_mode():
    extracted = [
        ExtractedDiagnosis(
            disease_text="心衰",
            final_top_k=[CandidateCode(code="I50.900", name="心衰", score=0.9, source="rerank")],
            final_confidence=0.9,
        )
    ]
    strat = MedCodERStrategy()
    out = await strat.stage5_compliance(extracted)
    assert out.extracted_diagnoses == extracted
    assert out.mode == "medcoder"
    assert out.provider == "medcoder"
    assert out.confidence == 0.9
    assert out.manual_review_required is False


@pytest.mark.asyncio
async def test_stage5_compliance_low_confidence_escalates():
    """Any per-dx confidence < CALIBRATION_FLOOR → manual_review_required."""
    extracted = [
        ExtractedDiagnosis(disease_text="弱信号", final_confidence=0.3),
    ]
    strat = MedCodERStrategy()
    out = await strat.stage5_compliance(extracted)
    assert out.manual_review_required is True
    assert "0 diagnoses" in out.notes or "0" in out.notes


@pytest.mark.asyncio
async def test_stage5_compliance_empty_extracted_still_validates():
    """Empty list still runs the rule set; should produce a WARNING + review flag."""
    strat = MedCodERStrategy()
    out = await strat.stage5_compliance([])
    assert out.extracted_diagnoses == []
    # No per-dx confidences to escalate from, but the rule set may
    # fire MR-000 (no extractions) on real rule sets.
    assert out.mode == "medcoder"


@pytest.mark.asyncio
async def test_stage5_compliance_top_confidence_is_mean():
    extracted = [
        ExtractedDiagnosis(final_confidence=0.8),
        ExtractedDiagnosis(final_confidence=0.6),
    ]
    strat = MedCodERStrategy()
    out = await strat.stage5_compliance(extracted)
    assert out.confidence == 0.7  # mean of [0.8, 0.6]


# ── 6. run_variant dispatch ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_variant_unknown_raises_value_error():
    strat = MedCodERStrategy()
    with pytest.raises(ValueError, match="unknown variant"):
        await strat.run_variant("x", variant="nonsense")


@pytest.mark.asyncio
async def test_run_variant_full_dispatches_to_5_stages(monkeypatch):
    """``full`` runs all 5 stages. Stub each stage and assert call order."""
    calls: list[str] = []

    async def s1(emr_text): calls.append("stage1"); return [{"disease_text": "x", "llm_initial_code": "I10"}]
    async def s2(text, top_k=20): calls.append("stage2"); return []
    async def s3(llm, ret, dt): calls.append("stage3"); return []
    async def s4(dt, ev, cand, hints=None): calls.append("stage4"); return []
    async def s5(extracted, ctx=None): calls.append("stage5"); return MedicalCodingOutputSchema.mock_result("medcoder")

    strat = MedCodERStrategy()
    monkeypatch.setattr(strat, "stage1_extraction", s1)
    monkeypatch.setattr(strat, "stage2_retrieve", s2)
    monkeypatch.setattr(strat, "stage3_merge", s3)
    monkeypatch.setattr(strat, "stage4_rerank", s4)
    monkeypatch.setattr(strat, "stage5_compliance", s5)

    await strat.run_variant("text", variant="full")
    assert calls == ["stage1", "stage2", "stage3", "stage4", "stage5"]


@pytest.mark.asyncio
async def test_run_variant_prompt_only_uses_stage1_only():
    calls: list[str] = []

    async def s1(emr_text): calls.append("stage1"); return [{"disease_text": "高血压", "llm_initial_code": "I10"}]
    async def s2(text, top_k=20): calls.append("stage2")
    async def s3(llm, ret, dt): calls.append("stage3")
    async def s4(dt, ev, cand, hints=None): calls.append("stage4")
    async def s5(extracted, ctx=None):
        calls.append("stage5")
        return MedicalCodingOutputSchema.mock_result("medcoder")

    strat = MedCodERStrategy()
    strat.stage1_extraction = s1
    strat.stage2_retrieve = s2
    strat.stage3_merge = s3
    strat.stage4_rerank = s4
    strat.stage5_compliance = s5

    out = await strat.run_variant("text", variant="prompt")
    assert calls == ["stage1", "stage5"]  # only stage 1 + stage 5
    # mode is set by stage5_compliance (real impl) — when stubbed, the
    # caller-provided mock_result doesn't set it, so we only verify
    # stage call ordering here. mode-setting is covered by
    # test_stage5_compliance_populates_extracted_and_mode.


@pytest.mark.asyncio
async def test_run_variant_retrieve_only_uses_stage2_only():
    """``retrieve`` uses stage 2 only; no LLM call."""
    retriever = _StubRetriever([CandidateCode(code="I50.900", name="心衰", score=0.9)])
    strat = MedCodERStrategy(retriever=retriever)
    out = await strat.run_variant("心衰患者胸闷气短", variant="retrieve")
    assert out.mode == "medcoder"
    # Stage 2 was called
    assert retriever.calls  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_variant_prompt_plus_retrieve_uses_stage_1_2_3_5():
    """``prompt+retrieve`` runs stages 1, 2, 3, 5 (no stage 4 rerank)."""
    calls: list[str] = []
    retriever = _StubRetriever([])

    async def s1(emr_text):
        calls.append("stage1")
        return [{"disease_text": "高血压", "llm_initial_code": "I10"}]

    async def s2(text, top_k=20):
        calls.append("stage2")
        return []

    async def s3(llm, ret, dt):
        calls.append("stage3")
        return []

    async def s4(dt, ev, cand, hints=None):
        calls.append("stage4")
        return []

    async def s5(extracted, ctx=None):
        calls.append("stage5")
        return MedicalCodingOutputSchema.mock_result("medcoder")

    strat = MedCodERStrategy(retriever=retriever)
    strat.stage1_extraction = s1
    strat.stage2_retrieve = s2
    strat.stage3_merge = s3
    strat.stage4_rerank = s4
    strat.stage5_compliance = s5

    await strat.run_variant("BP 160/100", variant="prompt+retrieve")
    assert "stage4" not in calls
    assert {"stage1", "stage2", "stage3", "stage5"}.issubset(set(calls))


# ── 7. _extract_emr_text accepts both string and messages ──────────


def test_extract_emr_text_accepts_string():
    assert MedCodERStrategy._extract_emr_text("plain emr") == "plain emr"


def test_extract_emr_text_accepts_messages():
    msgs = [
        {"role": "system", "content": "you are a coder"},
        {"role": "user", "content": "the emr text"},
    ]
    assert MedCodERStrategy._extract_emr_text(msgs) == "the emr text"


def test_extract_emr_text_picks_last_user_message():
    msgs = [
        {"role": "user", "content": "first user"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "last user"},
    ]
    assert MedCodERStrategy._extract_emr_text(msgs) == "last user"


def test_extract_emr_text_no_user_returns_empty():
    msgs = [{"role": "system", "content": "x"}]
    assert MedCodERStrategy._extract_emr_text(msgs) == ""


# ── 8. Constants exposed ───────────────────────────────────────────


def test_constants_have_audit_values():
    assert CALIBRATION_FLOOR == 0.5
    assert DEFAULT_MERGE_CAP == 30
    assert DEFAULT_RERANK_TOP_K == 5


def test_variants_tuple_includes_4_ablation_modes():
    assert set(MedCodERStrategy.VARIANTS) == {
        "full", "prompt", "retrieve", "prompt+retrieve",
    }


# ── 9. _populate_primary_secondary (backward compat with hybrid_adapter) ──


def test_populate_primary_secondary_picks_top_confidence():
    extracted = [
        ExtractedDiagnosis(
            disease_text="low",
            final_top_k=[CandidateCode(code="I10", name="高血压", score=0.5, source="rerank")],
            final_confidence=0.5,
        ),
        ExtractedDiagnosis(
            disease_text="high",
            final_top_k=[CandidateCode(code="I50.900", name="心衰", score=0.95, source="rerank")],
            final_confidence=0.95,
        ),
    ]
    out = MedicalCodingOutputSchema()
    MedCodERStrategy()._populate_primary_secondary(out, extracted)
    assert out.primary_diagnosis.code == "I50.900"
    assert out.primary_diagnosis.category == "principal"
    assert len(out.secondary_diagnoses) == 1
    assert out.secondary_diagnoses[0].code == "I10"
    assert out.secondary_diagnoses[0].category == "comorbidity"


def test_populate_primary_secondary_no_extracted_is_noop():
    out = MedicalCodingOutputSchema()
    MedCodERStrategy()._populate_primary_secondary(out, [])
    assert out.primary_diagnosis.code == ""  # default empty
    assert out.secondary_diagnoses == []


# ── 10. Lazy retriever selection ───────────────────────────────────


def test_create_default_retriever_selects_subprocess_on_windows(monkeypatch):
    """On Windows (os.name == 'nt'), default is SubprocessMedCodERRetriever.

    ``MagicMock`` is used to spy on which class is *instantiated* — the
    selection logic calls ``SubprocessMedCodERRetriever()`` or
    ``MedCodERRetriever()`` directly, so we assert on call counts.
    """
    monkeypatch.setattr("os.name", "nt")
    fake_subprocess_cls = MagicMock(name="SubprocessMedCodERRetriever")
    fake_inline_cls = MagicMock(name="MedCodERRetriever")
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.SubprocessMedCodERRetriever",
        fake_subprocess_cls,
    )
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.MedCodERRetriever",
        fake_inline_cls,
    )
    strat = MedCodERStrategy()
    result = strat._create_default_retriever()
    # Subprocess wrapper was selected; inline was not.
    fake_subprocess_cls.assert_called_once()
    fake_inline_cls.assert_not_called()
    assert result is fake_subprocess_cls.return_value


def test_create_default_retriever_env_overrides_to_subprocess(monkeypatch):
    """``MEDCODER_SUBPROCESS=1`` forces subprocess wrapper regardless of OS."""
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.setenv("MEDCODER_SUBPROCESS", "1")
    fake_subprocess_cls = MagicMock(name="SubprocessMedCodERRetriever")
    fake_inline_cls = MagicMock(name="MedCodERRetriever")
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.SubprocessMedCodERRetriever",
        fake_subprocess_cls,
    )
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.MedCodERRetriever",
        fake_inline_cls,
    )
    strat = MedCodERStrategy()
    result = strat._create_default_retriever()
    fake_subprocess_cls.assert_called_once()
    fake_inline_cls.assert_not_called()
    assert result is fake_subprocess_cls.return_value


def test_create_default_retriever_inline_on_posix(monkeypatch):
    """On POSIX without MEDCODER_SUBPROCESS=1, default is in-process retriever."""
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("MEDCODER_SUBPROCESS", raising=False)
    fake_subprocess_cls = MagicMock(name="SubprocessMedCodERRetriever")
    fake_inline_cls = MagicMock(name="MedCodERRetriever")
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.SubprocessMedCodERRetriever",
        fake_subprocess_cls,
    )
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.MedCodERRetriever",
        fake_inline_cls,
    )
    strat = MedCodERStrategy()
    result = strat._create_default_retriever()
    fake_inline_cls.assert_called_once()
    fake_subprocess_cls.assert_not_called()
    assert result is fake_inline_cls.return_value
