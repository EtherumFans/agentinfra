"""Phase 5 Track D P0 Gate 4 — Semantic Reviewer + Clinician View tests.

Covers the three new Gate 4 surfaces:

1. ``nlq_semantic.review_query`` — LLM-backed semantic reviewer for
   NLQ-002/007/008 with DEGRADED fallback on provider failure.
2. ``clinician_view.to_clinician_view`` — strips ICD/DRG/CMI codes from
   response_options so clinicians never see coding info (PDF §A6).
3. ``claim_evidence_alignment_score`` — multi-evidence alignment helper.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import (
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
    SemanticReviewResult,
    claim_evidence_alignment_score,
    is_safe_for_clinician,
    review_query_semantic,
    strip_codes_from_text,
    to_clinician_view,
)


# ---------------------------------------------------------------------------
# Mock LLM for semantic reviewer
# ---------------------------------------------------------------------------


class _MockLLM:
    """Records calls + returns canned JSON for the semantic reviewer."""

    def __init__(self, *, response: dict | None = None, fail: bool = False):
        self.response = response or {
            "nlq_002_pass": True,
            "nlq_002_reason": "",
            "nlq_007_pass": True,
            "nlq_007_reason": "",
            "nlq_008_pass": True,
            "nlq_008_reason": "",
            "overall_verdict": "PASS",
            "block_reasons": [],
        }
        self.fail = fail
        self.calls: list[dict] = []
        self.provider = "deepseek"
        self.model = "deepseek-v4-flash"

    async def chat(self, messages, system_prompt=None, **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        if self.fail:
            raise RuntimeError("mock LLM failure")
        return {
            "content": json.dumps(self.response),
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }


# ---------------------------------------------------------------------------
# Semantic reviewer — happy path
# ---------------------------------------------------------------------------


def test_semantic_review_passes_compliant_query() -> None:
    mock = _MockLLM()
    q = ProviderQuery(
        query_id="q1",
        gap_id="g1",
        topic="肺炎病原体",
        reason="特异性不足",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
        query_text="请根据痰培养结果回答病原体",
        response_options=["A. 肺炎链球菌", "B. 其他", "C. 无法确定"],
    )
    result = asyncio.run(review_query_semantic(q, llm=mock))
    assert isinstance(result, SemanticReviewResult)
    assert result.verdict == "PASS"
    assert result.nlq_002_pass is True
    assert result.nlq_007_pass is True
    assert result.nlq_008_pass is True
    assert result.degraded is False
    assert result.total_tokens == 150
    assert result.latency_ms >= 0
    assert len(mock.calls) == 1


def test_semantic_review_blocks_on_nlq_002_violation() -> None:
    mock = _MockLLM(response={
        "nlq_002_pass": False,
        "nlq_002_reason": "query body asserts pneumococcal diagnosis",
        "nlq_007_pass": True,
        "nlq_007_reason": "",
        "nlq_008_pass": True,
        "nlq_008_reason": "",
        "overall_verdict": "BLOCK",
        "block_reasons": ["NLQ-002 presumption"],
    })
    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="t", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="鉴于已明确为肺炎链球菌, 请确认", response_options=["A", "B", "C"],
    )
    result = asyncio.run(review_query_semantic(q, llm=mock))
    assert result.verdict == "BLOCK"
    assert any("NLQ-002" in r for r in result.block_reasons)


def test_semantic_review_blocks_on_multiple_violations() -> None:
    mock = _MockLLM(response={
        "nlq_002_pass": False,
        "nlq_002_reason": "presumption",
        "nlq_007_pass": False,
        "nlq_007_reason": "AKI not in chart",
        "nlq_008_pass": False,
        "nlq_008_reason": "option A says '最可能'",
        "overall_verdict": "BLOCK",
        "block_reasons": ["NLQ-002", "NLQ-007", "NLQ-008"],
    })
    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="t", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="...", response_options=["A", "B", "C"],
    )
    result = asyncio.run(review_query_semantic(q, llm=mock))
    assert result.verdict == "BLOCK"
    assert len(result.block_reasons) == 3


# ---------------------------------------------------------------------------
# DEGRADED fallback
# ---------------------------------------------------------------------------


def test_semantic_review_degrades_on_llm_failure() -> None:
    """When LLM raises, semantic review must NOT raise — returns PASS + degraded."""
    mock = _MockLLM(fail=True)
    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="t", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="...", response_options=["A", "B", "C"],
    )
    result = asyncio.run(review_query_semantic(q, llm=mock))
    assert result.degraded is True
    assert result.verdict == "PASS"  # never block on LLM outage
    assert result.error_reason  # populated
    assert all([result.nlq_002_pass, result.nlq_007_pass, result.nlq_008_pass])


def test_semantic_review_degrades_on_non_json_response() -> None:
    """Malformed JSON content → degrade to PASS, set error_reason."""
    mock = _MockLLM()
    mock.response = "not a json string"  # type: ignore  # will be json.dumps'd

    # Actually we need to override chat to return raw non-JSON
    async def _bad_chat(messages, system_prompt=None, **kwargs):
        return {
            "content": "this is not json",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    mock.chat = _bad_chat  # type: ignore

    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="t", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="...", response_options=["A", "B", "C"],
    )
    result = asyncio.run(review_query_semantic(q, llm=mock))
    assert result.degraded is True
    assert result.verdict == "PASS"
    assert "non-json" in result.error_reason or "json" in result.error_reason


# ---------------------------------------------------------------------------
# Clinician view de-coding (PDF §A6)
# ---------------------------------------------------------------------------


def test_strip_codes_from_text_removes_icd10() -> None:
    assert strip_codes_from_text("A. 肺炎链球菌 (J13)") == "A. 肺炎链球菌"
    assert strip_codes_from_text("A. 流感 (J10.1)") == "A. 流感"
    assert strip_codes_from_text("A. 病因 (J10.1A)") == "A. 病因"


def test_strip_codes_from_text_removes_icd9() -> None:
    assert strip_codes_from_text("A. 腹腔镜胆囊切除术 (51.23)") == "A. 腹腔镜胆囊切除术"


def test_strip_codes_from_text_removes_drg_and_payment_terms() -> None:
    out = strip_codes_from_text("对应 AH1 分组, 进入 DRG 一组, 权重 1.2")
    assert "AH1" not in out
    assert "DRG" not in out
    assert "权重" not in out


def test_strip_codes_from_text_removes_explicit_code_system_refs() -> None:
    out = strip_codes_from_text("编码为 ICD-10 J13")
    assert "ICD-10" not in out
    assert "J13" not in out


def test_to_clinician_view_strips_codes_from_options_and_body() -> None:
    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="肺炎病原体", reason="特异性",
        evidence_span=EvidenceSpan(document_id="d", quote="诊断: 肺炎"),
        query_text="请回答病原体 (编码到 ICD-10)",
        response_options=[
            "A. 肺炎链球菌 (J13)",
            "B. 其他已知病原体",
            "C. 无法确定",
        ],
    )
    cv = to_clinician_view(q)
    assert cv is not None
    # ICD codes gone from options
    assert all("J13" not in opt for opt in cv.response_options)
    assert all("ICD-10" not in opt for opt in cv.response_options)
    # Query body also cleaned
    assert "ICD-10" not in cv.query_text
    # Original NOT mutated — audit trail intact
    assert "J13" in q.response_options[0]
    assert "ICD-10" in q.query_text


def test_to_clinician_view_returns_none_when_topic_is_code() -> None:
    """If topic is itself a bare code, the query is fundamentally unsafe — drop."""
    q = ProviderQuery(
        query_id="q1", gap_id="g1", topic="J18.9", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="请确认编码", response_options=["A", "B", "C"],
    )
    assert to_clinician_view(q) is None


def test_is_safe_for_clinician_rejects_bare_codes() -> None:
    q_bad = ProviderQuery(
        query_id="q1", gap_id="g1", topic="A00", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="x", response_options=["A"],
    )
    q_ok = ProviderQuery(
        query_id="q1", gap_id="g1", topic="肺炎病原体", reason="r",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        query_text="x", response_options=["A"],
    )
    assert is_safe_for_clinician(q_bad) is False
    assert is_safe_for_clinician(q_ok) is True


# ---------------------------------------------------------------------------
# Claim-Evidence alignment
# ---------------------------------------------------------------------------


def test_alignment_score_all_aligned() -> None:
    g = DocumentationGap(
        gap_id="g1", description="d", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        evidence_spans=[
            EvidenceSpan(document_id="d1", quote="q1", supports_claim=True),
            EvidenceSpan(document_id="d2", quote="q2", supports_claim=True),
        ],
    )
    assert claim_evidence_alignment_score(g) == 1.0


def test_alignment_score_partial() -> None:
    g = DocumentationGap(
        gap_id="g1", description="d", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        evidence_spans=[
            EvidenceSpan(document_id="d1", quote="q1", supports_claim=True),
            EvidenceSpan(document_id="d2", quote="q2", supports_claim=False),
        ],
    )
    assert claim_evidence_alignment_score(g) == 0.5


def test_alignment_score_none_checked_defers_to_1() -> None:
    """Spans with supports_claim=None are excluded from denominator.
    If NO span has been checked, score defaults to 1.0 (deferred).
    """
    g = DocumentationGap(
        gap_id="g1", description="d", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="d", quote="q"),
        evidence_spans=[
            EvidenceSpan(document_id="d1", quote="q1"),  # None
            EvidenceSpan(document_id="d2", quote="q2"),  # None
        ],
    )
    assert claim_evidence_alignment_score(g) == 1.0


def test_alignment_score_zero_when_no_evidence() -> None:
    g = DocumentationGap(
        gap_id="g1", description="d", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="", quote=""),
    )
    assert claim_evidence_alignment_score(g) == 0.0
