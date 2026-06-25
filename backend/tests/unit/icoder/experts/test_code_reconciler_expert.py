"""CodeReconcilerExpert tests (~10 cases).

Covers:
  - Metadata (EXPERT_ID / EXPERT_NAME)
  - Shape: primary + secondary + procedures + issues + manual_review + conclusion
  - Empty input → no primary → conclusion=FAIL, manual_review_required=True
  - Single disease fact with candidates → primary chosen from top-1
  - Multiple facts → first fact's top-1 = primary, rest = secondary
  - Low confidence triggers manual_review_required=True
  - Procedures flow into procedures[] not secondary
  - top_k override from context
  - __call__ alias matches invoke_sync
  - LLM gateway path (mocked) returns parsed content
  - LLM gateway error falls back to offline
  - offline_only ctx flag bypasses gateway
  - Error translation on hard failure
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.icoder.agent_runtime.experts.code_reconciler_expert import (
    CodeReconcilerExpert,
)
from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)


# ── Metadata ──


class TestMetadata:
    def test_expert_id(self):
        assert CodeReconcilerExpert.EXPERT_ID == "code-reconciler"

    def test_expert_name(self):
        assert "Stage 4" in CodeReconcilerExpert.EXPERT_NAME


# ── Helpers ──


def _cand(code: str, name: str, score: float):
    return {"code": code, "name": name, "score": score, "chapter": "X"}


def _empty_invocation(payload: dict | None = None) -> ExpertInvocation:
    return ExpertInvocation(
        expert_id="code-reconciler",
        subtask_input=json.dumps(payload) if payload is not None else "",
        context={},
        attempt=1,
    )


# ── Shape ──


class TestShape:
    def test_invoke_sync_returns_required_fields(self):
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation({}))
        assert "primary_diagnosis" in result
        assert "secondary_diagnoses" in result
        assert "procedures" in result
        assert "issues_found" in result
        assert "manual_review_required" in result
        assert "review_conclusion" in result
        assert result["expert_id"] == "code-reconciler"
        # Offline is the default when no gateway is supplied
        assert result["is_mock"] is True

    @pytest.mark.asyncio
    async def test_invoke_async_returns_required_fields(self):
        exp = CodeReconcilerExpert()
        result = await exp.invoke_async({})
        assert "primary_diagnosis" in result
        assert "review_conclusion" in result

    def test_callable_equals_invoke_sync(self):
        exp = CodeReconcilerExpert()
        inv = _empty_invocation({})
        assert exp(inv) == exp.invoke_sync(inv)


# ── Offline re-rank logic ──


class TestOfflineRerank:
    def test_empty_input_no_primary_fail(self):
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation({}))
        assert result["primary_diagnosis"] == {}
        assert result["review_conclusion"] == "FAIL"
        assert result["manual_review_required"] is True
        # No primary issue raised
        issue_codes = {i["code"] for i in result["issues_found"]}
        assert "MC-R-NO-PRIMARY" in issue_codes

    def test_single_fact_top1_becomes_primary(self):
        payload = {
            "diagnosis_candidates": [
                {
                    "fact": "心衰",
                    "candidates": [
                        _cand("I50.900", "心力衰竭", 0.95),
                        _cand("I50.100", "左心衰竭", 0.80),
                    ],
                }
            ],
            "procedure_candidates": [],
        }
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation(payload))
        assert result["primary_diagnosis"]["code"] == "I50.900"
        assert result["primary_diagnosis"]["confidence"] == 0.95
        assert result["primary_diagnosis"]["fact"] == "心衰"
        assert result["review_conclusion"] == "PASS"
        assert result["manual_review_required"] is False
        # The 0.80 candidate becomes secondary
        assert len(result["secondary_diagnoses"]) == 1
        assert result["secondary_diagnoses"][0]["code"] == "I50.100"

    def test_multiple_facts_first_top1_is_primary(self):
        payload = {
            "diagnosis_candidates": [
                {
                    "fact": "心衰",
                    "candidates": [_cand("I50.900", "心力衰竭", 0.95)],
                },
                {
                    "fact": "高血压",
                    "candidates": [_cand("I10.x00", "原发性高血压", 0.85)],
                },
            ],
            "procedure_candidates": [],
        }
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation(payload))
        assert result["primary_diagnosis"]["code"] == "I50.900"
        # Second fact's top-1 → secondary
        assert len(result["secondary_diagnoses"]) == 1
        assert result["secondary_diagnoses"][0]["code"] == "I10.x00"
        assert result["secondary_diagnoses"][0]["fact"] == "高血压"

    def test_low_confidence_triggers_manual_review(self):
        payload = {
            "diagnosis_candidates": [
                {
                    "fact": "心衰",
                    "candidates": [_cand("I50.900", "心力衰竭", 0.30)],
                }
            ],
        }
        exp = CodeReconcilerExpert(confidence_floor=0.5)
        result = exp.invoke_sync(_empty_invocation(payload))
        assert result["primary_diagnosis"]["code"] == "I50.900"
        assert result["manual_review_required"] is True
        assert result["review_conclusion"] == "WARNING"
        issue_codes = {i["code"] for i in result["issues_found"]}
        assert "MC-R-LOW-CONFIDENCE" in issue_codes

    def test_procedures_separated_from_diagnoses(self):
        payload = {
            "diagnosis_candidates": [
                {
                    "fact": "心衰",
                    "candidates": [_cand("I50.900", "心力衰竭", 0.95)],
                }
            ],
            "procedure_candidates": [
                {
                    "fact": "PCI 支架置入术",
                    "candidates": [_cand("00.66", "经皮冠状动脉支架置入术", 0.92)],
                }
            ],
        }
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation(payload))
        assert len(result["procedures"]) == 1
        assert result["procedures"][0]["code"] == "00.66"
        # Procedure is NOT in secondary
        assert all(d.get("code") != "00.66" for d in result["secondary_diagnoses"])

    def test_top_k_override(self):
        payload = {
            "diagnosis_candidates": [
                {
                    "fact": "心衰",
                    "candidates": [
                        _cand("I50.900", "心力衰竭", 0.95),
                        _cand("I50.100", "左心衰竭", 0.80),
                        _cand("I50.000", "右心衰竭", 0.70),
                    ],
                }
            ],
        }
        exp = CodeReconcilerExpert(top_k=1)
        result = exp.invoke_sync(_empty_invocation(payload))
        # top_k=1 → only top-1 is primary, no secondary
        assert result["primary_diagnosis"]["code"] == "I50.900"
        assert result["secondary_diagnoses"] == []

    def test_no_candidates_emits_issue(self):
        payload = {
            "diagnosis_candidates": [
                {"fact": "罕见病", "candidates": []},
            ],
        }
        exp = CodeReconcilerExpert()
        result = exp.invoke_sync(_empty_invocation(payload))
        # No primary, manual review triggered
        assert result["primary_diagnosis"] == {}
        assert result["manual_review_required"] is True
        issue_codes = {i["code"] for i in result["issues_found"]}
        assert "MC-R-NO-CANDIDATES" in issue_codes


# ── LLM gateway path (mocked) ──


class TestLLMGatewayPath:
    @pytest.mark.asyncio
    async def test_gateway_returns_parsed_json(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={
            "content": json.dumps({
                "primary_diagnosis": {"code": "I50.900", "name": "心力衰竭",
                                      "confidence": 0.95, "evidence": ["心衰"],
                                      "justification": "best match"},
                "secondary_diagnoses": [],
                "procedures": [],
                "issues_found": [],
            })
        })
        exp = CodeReconcilerExpert(llm_gateway=gateway)
        result = await exp.invoke_async({
            "diagnosis_candidates": [
                {"fact": "心衰", "candidates": [_cand("I50.900", "心力衰竭", 0.95)]}
            ],
        })
        # LLM path → is_mock=False
        assert result["is_mock"] is False
        assert result["primary_diagnosis"]["code"] == "I50.900"
        assert result["primary_diagnosis"]["justification"] == "best match"

    @pytest.mark.asyncio
    async def test_gateway_error_falls_back_to_offline(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(side_effect=RuntimeError("network down"))
        exp = CodeReconcilerExpert(llm_gateway=gateway)
        result = await exp.invoke_async({
            "diagnosis_candidates": [
                {"fact": "心衰", "candidates": [_cand("I50.900", "心力衰竭", 0.95)]}
            ],
        })
        assert result["is_mock"] is True
        assert result["primary_diagnosis"]["code"] == "I50.900"

    @pytest.mark.asyncio
    async def test_gateway_invalid_json_falls_back_to_offline(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={"content": "not valid json {"})
        exp = CodeReconcilerExpert(llm_gateway=gateway)
        result = await exp.invoke_async({
            "diagnosis_candidates": [
                {"fact": "心衰", "candidates": [_cand("I50.900", "心力衰竭", 0.95)]}
            ],
        })
        assert result["is_mock"] is True

    @pytest.mark.asyncio
    async def test_offline_only_ctx_flag(self):
        gateway = MagicMock()
        gateway.generate = AsyncMock(return_value={"content": "{}"})
        exp = CodeReconcilerExpert(llm_gateway=gateway)
        result = await exp.invoke_async({}, ctx={"offline_only": True})
        assert result["is_mock"] is True
        gateway.generate.assert_not_called()


# ── Error handling ──


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unexpected_error_translated(self):
        exp = CodeReconcilerExpert()

        # Patch offline to raise unexpected
        def _bad(_p, _c):
            raise RuntimeError("intentional crash")
        exp._rerank_offline = _bad
        with pytest.raises(ExpertInvocationError) as exc_info:
            await exp.invoke_async({})
        assert "re-ranking failed" in str(exc_info.value)
        assert exc_info.value.stage == "reconciling"