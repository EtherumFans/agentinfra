"""Track H3.19 — sentence-bounded CEA-005 / CEA-006 window.

Closes negation_history agreement regression 0.80 → 0.60 (iter 4 → iter 6).

Root cause: CEA-005 negation look-back window (25 chars) and CEA-006 PMH
walk-back both crossed sentence boundaries. Charts like NEG-026
("否认糖尿病。家族史:父亲糖尿病。入院诊断:2型糖尿病?") had 否认 + 家族史
in prior sentences trigger false-positive negation_as_support / PMH context
→ cascade to CEA-008 BLOCK → query dropped → agreement dropped.

Fix: bound both look-backs to the same sentence as the quote (delimited by
。！？；;). The sentence boundary established by 。 closes the prior
section/negation context, just like a section_end_marker.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make backend.app.* importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.icoder.agent_runtime.cdi.claim_evidence_gate import (  # noqa: E402
    _rule_cea_005, _rule_cea_006, _sentence_start_before, evaluate_claim_evidence,
)
from app.icoder.agent_runtime.cdi.domain import (  # noqa: E402
    Claim, ClaimEvidenceAlignment, EvidenceSpan, ProviderQuery,
)


# NEG-026 chart — the canonical "diagnosis marked uncertain" case.
NEG026_CHART = (
    "患者男性, 55岁, 多饮多尿1周。既往:高血压5年。否认糖尿病、冠心病、慢性肾病。"
    "家族史:父亲糖尿病。入院诊断:2型糖尿病?"
)


def _alignment(quote: str, document_id: str = "chart") -> ClaimEvidenceAlignment:
    return ClaimEvidenceAlignment(
        claim_id="c1",
        evidence_span_id="es1",
        document_id=document_id,
        quote=quote,
        char_start=-1,
        char_end=-1,
        support_type="direct",
        confidence=0.9,
        validation_status="unchecked",
    )


def test_sentence_start_helper_finds_period_boundary():
    """_sentence_start_before returns char after the most recent 。！？；."""
    chart = "第一句。第二句。第三句包含引文"
    pos = chart.find("第三句")
    assert _sentence_start_before(chart, pos) == chart.find("第三句")


def test_sentence_start_helper_returns_zero_when_no_delimiter():
    chart = "no sentence delimiter here"
    assert _sentence_start_before(chart, 5) == 0


def test_sentence_start_helper_handles_question_mark():
    chart = "诊断:2型糖尿病?后续内容"
    pos = chart.find("后续")
    # The "?" half-width ends the first sentence → "后续" starts a new sentence
    # at the char right after "?".
    expected = chart.find("?") + 1
    assert _sentence_start_before(chart, pos) == expected


def test_cea_005_passes_when_negation_in_prior_sentence():
    """H3.19 fix: 否认 in a prior sentence must NOT trip CEA-005."""
    quote = "入院诊断:2型糖尿病?"
    result = _rule_cea_005(_alignment(quote), NEG026_CHART)
    assert result.passed, f"expected PASS, got FAIL: {result.evidence}"


def test_cea_005_fails_when_negation_in_same_sentence():
    """Sanity: 否认 immediately before the quote in the SAME sentence still FAILs."""
    chart = "否认糖尿病,入院诊断:糖尿病"
    quote = "入院诊断:糖尿病"
    result = _rule_cea_005(_alignment(quote), chart)
    assert not result.passed


def test_cea_006_passes_when_pmh_in_prior_sentence():
    """H3.19 fix: 家族史 in a prior sentence must NOT trip CEA-006."""
    quote = "入院诊断:2型糖尿病?"
    result = _rule_cea_006(_alignment(quote), NEG026_CHART)
    assert result.passed, f"expected PASS, got FAIL: {result.evidence}"


def test_cea_006_fails_when_pmh_in_same_sentence():
    """Sanity: 家族史：... in same sentence as quote still FAILs."""
    chart = "家族史:父亲糖尿病,当前症状"
    quote = "当前症状"
    result = _rule_cea_006(_alignment(quote), chart)
    assert not result.passed


def test_neg026_full_cea_passes_with_h319_fix():
    """End-to-end: NEG-026 query with critical claim + 入院诊断 quote → PASS.

    Before H3.19: CEA-008 BLOCK (negation_as_support).
    After H3.19: PASS (negation in prior sentence, current sentence is 入院诊断).
    """
    q = ProviderQuery(
        query_id="q1",
        gap_id="g1",
        topic="diabetes_type_confirmation",
        reason="diagnostic specificity gap",
        evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:2型糖尿病?"),
        query_text="请明确该患者糖尿病的诊断分型(T1DM/T2DM/其他)",
        response_options=["A. 是", "B. 否", "C. 不确定"],
        claims=[Claim(claim_id="c1", text="患者2型糖尿病诊断未确诊", criticality="critical")],
        claim_evidence_alignments=[_alignment("入院诊断:2型糖尿病?")],
    )
    result = evaluate_claim_evidence(q, chart=NEG026_CHART, case_documents=["DOC-001"])
    assert result.verdict == "PASS", (
        f"expected PASS, got {result.verdict}; block={result.block_reasons}; "
        f"flag={result.flag_reasons}"
    )


def test_neg028_pmh_in_same_sentence_still_blocks():
    """NEG-028-style: quote inside an explicit 既往史 section still FAILs.

    H3.19 fix preserves the original CEA-006 contract: when the quote
    appears INSIDE a 既往史 section in the SAME sentence, CEA-006 still
    trips. The fix only bounds the look-back across sentence boundaries.
    """
    chart = "既往史:10年前因急性阑尾炎行阑尾切除术,目前无症状。"
    quote = "10年前因急性阑尾炎行阑尾切除术"
    result = _rule_cea_006(_alignment(quote), chart)
    assert not result.passed, f"expected FAIL for quote inside 既往史 section, got PASS"


def test_lab_positive_uncertain_chart_still_works():
    """H3.16 fix must not regress with H3.19 fix co-applied."""
    chart = "患者女性, 60岁, 腹胀2月。CA-125 65 U/mL (正常 <35)。否认卵巢癌家族史。"
    # Critical claim anchored on the lab value quote:
    q = ProviderQuery(
        query_id="q1",
        gap_id="g1",
        topic="clinical_correlation_lab",
        reason="lab-positive uncertain",
        evidence_span=EvidenceSpan(document_id="chart", quote="CA-125 65 U/mL"),
        query_text="请明确 CA-125 升高的临床意义",
        response_options=["A", "B", "C"],
        claims=[Claim(claim_id="c1", text="CA-125 升高", criticality="critical")],
        claim_evidence_alignments=[_alignment("CA-125 65 U/mL")],
    )
    result = evaluate_claim_evidence(q, chart=chart, case_documents=["DOC-001"])
    assert result.verdict == "PASS", (
        f"expected PASS, got {result.verdict}; block={result.block_reasons}"
    )
