"""EvidenceExtractorExpert tests (~10 cases).

Covers:
  - Metadata (EXPERT_ID / EXPERT_NAME)
  - invoke_sync returns dict shape with required fields
  - invoke_async returns dict shape with required fields
  - Empty input short-circuits to is_mock=True with empty lists
  - Offline path extracts disease + procedure + negated + historical facts
  - LLM gateway stub path (mocked) returns parsed content
  - LLM gateway error falls back to offline
  - __call__ alias matches invoke_sync
  - Stage error label on hard failure
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.icoder.agent_runtime.experts.evidence_extractor_expert import (
    EvidenceExtractorExpert,
)
from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)


# ── Metadata ──


class TestMetadata:
    def test_expert_id(self):
        assert EvidenceExtractorExpert.EXPERT_ID == "evidence-extractor"

    def test_expert_name(self):
        assert "Stage 1" in EvidenceExtractorExpert.EXPERT_NAME
        assert "MedCodER" in EvidenceExtractorExpert.EXPERT_NAME


# ── Shape ──


def _empty_invocation(text: str = "") -> ExpertInvocation:
    return ExpertInvocation(
        expert_id="evidence-extractor",
        subtask_input=text,
        context={},
        attempt=1,
    )


class TestShape:
    def test_invoke_sync_returns_required_fields(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("冠心病合并高血压"))
        assert isinstance(result, dict)
        assert "diagnosis_facts" in result
        assert "procedure_facts" in result
        assert "negated_findings" in result
        assert "historical_conditions" in result
        assert result["expert_id"] == "evidence-extractor"
        # Offline path is the default when no gateway is supplied.
        assert result["is_mock"] is True

    @pytest.mark.asyncio
    async def test_invoke_async_returns_required_fields(self):
        exp = EvidenceExtractorExpert()
        result = await exp.invoke_async("冠心病合并高血压")
        assert isinstance(result, dict)
        assert "diagnosis_facts" in result
        assert result["expert_id"] == "evidence-extractor"

    def test_callable_equals_invoke_sync(self):
        exp = EvidenceExtractorExpert()
        inv = _empty_invocation("高血压病史10年")
        via_call = exp(inv)
        via_invoke = exp.invoke_sync(inv)
        assert via_call == via_invoke


# ── Edge cases ──


class TestEdgeCases:
    def test_empty_emr_returns_empty_lists(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation(""))
        assert result["diagnosis_facts"] == []
        assert result["procedure_facts"] == []
        assert result["negated_findings"] == []
        assert result["historical_conditions"] == []
        assert result["is_mock"] is True

    def test_whitespace_emr_returns_empty_lists(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("   \n  "))
        assert result["diagnosis_facts"] == []

    @pytest.mark.asyncio
    async def test_invoke_async_empty_input(self):
        exp = EvidenceExtractorExpert()
        result = await exp.invoke_async("")
        assert result["diagnosis_facts"] == []
        assert result["is_mock"] is True


# ── Offline extraction logic ──


class TestOfflineExtraction:
    def test_disease_keyword_captured(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("患者诊断为冠心病"))
        assert len(result["diagnosis_facts"]) >= 1
        dx = result["diagnosis_facts"][0]
        assert "冠心病" in dx["fact"]
        assert "evidence_text" in dx
        assert isinstance(dx["char_start"], int)
        assert isinstance(dx["char_end"], int)
        assert dx["char_start"] < dx["char_end"]

    def test_procedure_keyword_captured(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("行冠状动脉造影术"))
        # "术" is the keyword
        procs = result["procedure_facts"]
        assert len(procs) >= 1
        assert "造影" in procs[0]["fact"]

    def test_negation_captured(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("否认肝炎、结核等传染病史"))
        negs = result["negated_findings"]
        assert len(negs) >= 1
        reasons = {n["reason"] for n in negs}
        assert "否认" in reasons

    def test_historical_condition_captured(self):
        exp = EvidenceExtractorExpert()
        result = exp.invoke_sync(_empty_invocation("高血压病史10年"))
        hist = result["historical_conditions"]
        assert len(hist) >= 1
        assert any(h.get("years_ago") == 10 for h in hist)


# ── LLM gateway path (mocked) ──


class TestLLMGatewayPath:
    @pytest.mark.asyncio
    async def test_gateway_returns_parsed_json(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={
            "content": json.dumps({
                "diagnosis_facts": [
                    {"fact": "糖尿病", "evidence_text": "糖尿病史5年",
                     "char_start": 0, "char_end": 5, "doc_type": "present_illness"},
                ],
                "procedure_facts": [],
                "negated_findings": [],
                "historical_conditions": [],
            })
        })
        exp = EvidenceExtractorExpert(llm_gateway=gateway)
        result = await exp.invoke_async("糖尿病史5年")
        # LLM path → is_mock should NOT be set
        assert "is_mock" not in result or result.get("is_mock") is False
        assert len(result["diagnosis_facts"]) == 1
        assert result["diagnosis_facts"][0]["fact"] == "糖尿病"

    @pytest.mark.asyncio
    async def test_gateway_error_falls_back_to_offline(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(side_effect=RuntimeError("network down"))
        exp = EvidenceExtractorExpert(llm_gateway=gateway)
        result = await exp.invoke_async("患者诊断为冠心病")
        # Offline path → is_mock=True
        assert result.get("is_mock") is True
        assert len(result["diagnosis_facts"]) >= 1

    @pytest.mark.asyncio
    async def test_gateway_invalid_json_falls_back_to_offline(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={"content": "not valid JSON {"})
        exp = EvidenceExtractorExpert(llm_gateway=gateway)
        result = await exp.invoke_async("冠心病")
        assert result.get("is_mock") is True
        assert isinstance(result["diagnosis_facts"], list)

    @pytest.mark.asyncio
    async def test_offline_only_ctx_flag(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={"content": "{}"})
        exp = EvidenceExtractorExpert(llm_gateway=gateway)
        result = await exp.invoke_async("冠心病", ctx={"offline_only": True})
        # ctx flag bypasses gateway even when configured
        assert result.get("is_mock") is True
        gateway.generate.assert_not_called()


# ── Error handling ──


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_invoke_async_wraps_unexpected_error(self):
        # Force an unexpected exception inside the offline path by
        # passing a non-string input. The expert should translate
        # to ExpertInvocationError.
        exp = EvidenceExtractorExpert()

        # Patch the offline extractor to raise something unexpected.
        def _bad(_):
            raise RuntimeError("intentional crash")
        exp._extract_offline = _bad
        with pytest.raises(ExpertInvocationError) as exc_info:
            await exp.invoke_async("emr text")
        assert "extraction failed" in str(exc_info.value)
        assert exc_info.value.stage == "extracting"