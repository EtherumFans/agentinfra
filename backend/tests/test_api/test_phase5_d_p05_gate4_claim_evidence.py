"""Phase 5 Track D P0.5 Gate 4 — Claim-Evidence Alignment tests.

Tests the 9 deterministic CEA-XXX rules (Master Task §5.4) + LLM-backed
``extract_claims`` + the orchestrator-friendly ``apply_claim_evidence_to_case``.

Each rule has at least one PASS + one BLOCK fixture. Aggregation tests
verify critical-claim logic (CEA-008 hard / CEA-009 soft).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import (
    CDICase,
    Claim,
    ClaimEvidenceAlignment,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
    apply_claim_evidence_to_case,
    evaluate_claim_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query(
    *,
    query_id: str = "q1",
    topic: str = "病原体",
    query_text: str = "患者诊断为肺炎, 痰培养为肺炎链球菌. 请明确病原体.",
    quote: str = "诊断: 肺炎",
    chart: str = "患者男. 诊断: 肺炎. 痰培养: 肺炎链球菌.",
) -> tuple[ProviderQuery, str]:
    q = ProviderQuery(
        query_id=query_id,
        gap_id="g1",
        topic=topic,
        reason="test",
        evidence_span=EvidenceSpan(document_id="入院记录", quote=quote),
        query_text=query_text,
    )
    return q, chart


def _alignment(
    claim_id: str,
    *,
    quote: str,
    document_id: str = "入院记录",
    support_type: str = "direct",
    char_start: int = -1,
    char_end: int = -1,
) -> ClaimEvidenceAlignment:
    return ClaimEvidenceAlignment(
        claim_id=claim_id,
        evidence_span_id=f"es_{claim_id}",
        document_id=document_id,
        quote=quote,
        char_start=char_start,
        char_end=char_end,
        support_type=supply_type(support_type),  # type: ignore[arg-type]
    )


def supply_type(s: str) -> str:
    # coerce to SupportType Literal accepted values
    if s not in ("direct", "contextual", "inferred", "unsupported"):
        return "unsupported"
    return s


# ---------------------------------------------------------------------------
# CEA-001 quote_exists_in_chart
# ---------------------------------------------------------------------------


def test_cea_001_pass_when_quote_verbatim_in_chart() -> None:
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="痰培养为肺炎链球菌", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="痰培养: 肺炎链球菌", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"
    cea_001 = next(
        r for c in result.claims for r in c.rule_results if r.rule_id == "CEA-001"
    )
    assert cea_001.passed is True


def test_cea_001_block_when_quote_not_in_chart() -> None:
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="左肺肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="左肺肺炎", support_type="direct")  # not in chart
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "BLOCK"
    assert any("CEA-008" in r for r in result.block_reasons)


# ---------------------------------------------------------------------------
# CEA-002 char_span_accurate
# ---------------------------------------------------------------------------


def test_cea_002_skips_when_no_span_provided() -> None:
    """LLM doesn't reliably emit char offsets — we defer to CEA-001."""
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="肺炎链球菌", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="肺炎链球菌", support_type="direct", char_start=-1, char_end=-1)
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"
    cea_002 = next(
        r for c in result.claims for r in c.rule_results if r.rule_id == "CEA-002"
    )
    assert cea_002.passed is True


def test_cea_002_passes_when_span_matches() -> None:
    chart = "诊断: 肺炎. 痰培养: 肺炎链球菌."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="肺炎链球菌", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment(
            "c1",
            quote="肺炎链球菌",
            support_type="direct",
            char_start=chart.find("肺炎链球菌"),
            char_end=chart.find("肺炎链球菌") + len("肺炎链球菌"),
        )
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# CEA-003 document_id_valid
# ---------------------------------------------------------------------------


def test_cea_003_blocks_empty_document_id() -> None:
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        ClaimEvidenceAlignment(
            claim_id="c1",
            evidence_span_id="es1",
            document_id="",  # invalid
            quote="肺炎",
            support_type="direct",
        )
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert any(r.rule_id == "CEA-003" and not r.passed for c in result.claims for r in c.rule_results)


# ---------------------------------------------------------------------------
# CEA-004 no_cross_case_evidence
# ---------------------------------------------------------------------------


def test_cea_004_passes_when_document_id_in_case_documents() -> None:
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="诊断: 肺炎", document_id="入院记录", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart, case_documents=["入院记录", "出院记录"])
    assert result.verdict == "PASS"


def test_cea_004_blocks_when_document_id_not_in_case() -> None:
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="诊断: 肺炎", document_id="其他病例记录", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart, case_documents=["入院记录"])
    assert any(
        r.rule_id == "CEA-004" and not r.passed
        for c in result.claims for r in c.rule_results
    )


def test_cea_004_accepts_generic_chart_document_id() -> None:
    """Track H3.16 — extract_claims emits document_id='chart' by default.

    Without this fix, every LLM-extracted alignment would fail CEA-004
    because 'chart' ∉ case_documents, cascading to CEA-008 BLOCK.
    """
    q, chart = _make_query()
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="诊断: 肺炎", document_id="chart", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart, case_documents=["DOC-001"])
    assert result.verdict == "PASS"
    assert all(
        r.passed for c in result.claims for r in c.rule_results if r.rule_id == "CEA-004"
    )


# ---------------------------------------------------------------------------
# CEA-005 no_negation_as_support
# ---------------------------------------------------------------------------


def test_cea_005_blocks_negated_facts() -> None:
    chart = "否认发热. 否认高血压. 诊断: 肺炎."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者有发热", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="发热", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert any(
        r.rule_id == "CEA-005" and not r.passed
        for c in result.claims for r in c.rule_results
    )


def test_cea_005_passes_positive_assertion() -> None:
    chart = "患者发热3天. 体温38.5°C. 诊断: 肺炎."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者发热", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="患者发热3天", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# CEA-006 no_pmh_as_current
# ---------------------------------------------------------------------------


def test_cea_006_blocks_pmh_as_current() -> None:
    chart = "既往史: 高血压10年. 现病史: 头痛3天. 体温37.0°C."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者高血压未控制", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="高血压10年", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert any(
        r.rule_id == "CEA-006" and not r.passed
        for c in result.claims for r in c.rule_results
    )


def test_cea_006_passes_current_active_section() -> None:
    chart = "现病史: 患者高血压10年, 控制不佳. 主诉头痛."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="高血压控制不佳", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="高血压10年", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    # Quote appears in 现病史 (current), not 既往史 → CEA-006 should pass
    assert all(
        r.passed for c in result.claims for r in c.rule_results if r.rule_id == "CEA-006"
    )


# ---------------------------------------------------------------------------
# CEA-007 no_inferred_as_direct
# ---------------------------------------------------------------------------


def test_cea_007_blocks_inferred_mislabelled_as_direct() -> None:
    chart = "考虑肺炎可能. 建议痰培养."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="考虑肺炎可能", support_type="direct")  # WRONG label
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert any(
        r.rule_id == "CEA-007" and not r.passed
        for c in result.claims for r in c.rule_results
    )


def test_cea_007_passes_when_inferred_correctly_labelled() -> None:
    chart = "考虑肺炎可能. 建议痰培养."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="考虑肺炎可能", support_type="inferred")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    # Claim is critical and only inferred → REVIEW_REQUIRED
    assert result.verdict == "REVIEW_REQUIRED"


# ---------------------------------------------------------------------------
# CEA-008 critical_claim_must_have_evidence (HARD)
# ---------------------------------------------------------------------------


def test_cea_008_blocks_critical_claim_with_no_evidence() -> None:
    q, chart = _make_query()
    q.claims = [
        Claim(claim_id="c1", text="左肺肺炎", criticality="critical"),
        Claim(claim_id="c2", text="诊断肺炎", criticality="supporting"),
    ]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="", support_type="unsupported"),  # critical, no evidence
        _alignment("c2", quote="诊断: 肺炎", support_type="direct"),
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "BLOCK"
    assert any("CEA-008" in r for r in result.block_reasons)


def test_cea_008_passes_when_critical_claim_rescued_by_direct_evidence() -> None:
    chart = "诊断: 肺炎. 痰培养: 肺炎链球菌."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="痰培养肺炎链球菌", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="痰培养: 肺炎链球菌", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# CEA-009 inferred_critical_demotes_to_review (SOFT)
# ---------------------------------------------------------------------------


def test_cea_009_review_required_when_critical_only_inferred() -> None:
    chart = "考虑肺炎可能. 建议痰培养."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="考虑肺炎可能", support_type="inferred")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("CEA-009" in r for r in result.flag_reasons)


# ---------------------------------------------------------------------------
# DEGRADED when no claims extracted
# ---------------------------------------------------------------------------


def test_returns_degraded_when_no_claims() -> None:
    q, chart = _make_query()
    q.claims = []  # LLM extraction failed
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "DEGRADED"
    assert result.degraded is True


# ---------------------------------------------------------------------------
# apply_claim_evidence_to_case — end-to-end
# ---------------------------------------------------------------------------


def test_apply_drops_blocked_queries_keeps_passing() -> None:
    chart = "诊断: 肺炎. 痰培养: 肺炎链球菌."
    q_pass = ProviderQuery(
        query_id="q_pass",
        gap_id="g",
        topic="病原体",
        reason="",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
        query_text="请明确病原体:",
    )
    q_pass.claims = [Claim(claim_id="c1", text="肺炎链球菌", criticality="critical")]
    q_pass.claim_evidence_alignments = [
        _alignment("c1", quote="痰培养: 肺炎链球菌", support_type="direct")
    ]
    q_block = ProviderQuery(
        query_id="q_block",
        gap_id="g",
        topic="部位",
        reason="",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
        query_text="请明确左肺/右肺:",
    )
    q_block.claims = [Claim(claim_id="c1", text="左肺肺炎", criticality="critical")]
    q_block.claim_evidence_alignments = [
        _alignment("c1", quote="左肺肺炎", support_type="unsupported")  # not in chart
    ]
    case = CDICase(case_id="c", chart_excerpt=chart, proposed_provider_queries=[q_pass, q_block])
    result = apply_claim_evidence_to_case(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].query_id == "q_pass"
    assert result.blocked_query_ids == ["q_block"]
    assert len(case.query_rewrite_queue) == 1
    rejected = case.query_rewrite_queue[0]
    assert rejected["query_id"] == "q_block"
    assert rejected["status"] == "REJECTED_BY_CLAIM_EVIDENCE"
    assert rejected["gate_reasons"]


def test_apply_keeps_review_required_queries_flagged() -> None:
    chart = "考虑肺炎可能."
    q = ProviderQuery(
        query_id="q_review",
        gap_id="g",
        topic="病原体",
        reason="",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="考虑肺炎可能"),
        query_text="请明确病原体:",
    )
    q.claims = [Claim(claim_id="c1", text="肺炎", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="考虑肺炎可能", support_type="inferred")
    ]
    case = CDICase(case_id="c", chart_excerpt=chart, proposed_provider_queries=[q])
    result = apply_claim_evidence_to_case(case)
    assert len(case.proposed_provider_queries) == 1  # NOT dropped
    assert q.query_id in result.flagged_query_ids
    # Query is flagged for review
    assert any("CEA-009" in r for r in q.nlq_gate_block_reasons)


def test_apply_handles_empty_case_gracefully() -> None:
    case = CDICase(case_id="c", chart_excerpt="任何")
    result = apply_claim_evidence_to_case(case)
    assert case.proposed_provider_queries == []
    assert result.blocked_query_ids == []


# ---------------------------------------------------------------------------
# LLM extract_claims — DEGRADED path
# ---------------------------------------------------------------------------


class _FailLLM:
    async def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated LLM outage")


async def _async_call() -> tuple[list[Claim], list[ClaimEvidenceAlignment]]:
    from app.icoder.agent_runtime.cdi.claim_evidence_gate import extract_claims
    q, chart = _make_query()
    return await extract_claims(q, chart=chart, llm=_FailLLM())


def test_extract_claims_degraded_on_llm_failure() -> None:
    import asyncio
    claims, aligns = asyncio.run(_async_call())
    assert claims == []
    assert aligns == []


# ---------------------------------------------------------------------------
# Phase 5 Track H3.6 — CEA-001 fuzzy relaxation
# ---------------------------------------------------------------------------


def test_h36_cea_001_fuzzy_match_minor_punctuation_difference() -> None:
    """Quote with minor punctuation difference passes via fuzzy ≥0.90.

    Scenario: chart says "痰培养:肺炎链球菌" but the LLM emitted quote
    "痰培养：肺炎链球菌" (full-width colon). Verbatim fails; fuzzy passes.
    Pre-H3.6 this would BLOCK; post-H3.6 it PASSES.
    """
    chart = "患者男. 诊断: 肺炎. 痰培养:肺炎链球菌."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="痰培养示肺炎链球菌", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="痰培养：肺炎链球菌", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"
    cea_001 = next(
        r for c in result.claims for r in c.rule_results if r.rule_id == "CEA-001"
    )
    assert cea_001.passed is True
    assert "fuzzy" in cea_001.evidence.lower()


def test_h36_cea_001_fuzzy_match_partial_word() -> None:
    """Quote with a missing space/particle still passes via fuzzy.

    Chart: "患者的体温 38.5度" Quote: "患者的体温38.5度" — 1 character
    (space) difference; fuzzy should pass.
    """
    chart = "患者的体温 38.5度, 血压120/80mmHg."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="患者的体温38.5度", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="患者的体温38.5度", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "PASS"


def test_h36_cea_001_still_blocks_unrelated_quote() -> None:
    """Sanity: a quote that has NO relation to the chart still BLOCKs.

    Fuzzy threshold 0.90 means random text won't pass. Verify the gate
    is not permissive beyond design.
    """
    chart = "患者男. 诊断: 肺炎."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="急性心肌梗死", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="急性ST段抬高型心肌梗死", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    assert result.verdict == "BLOCK"


def test_h36_cea_005_negation_still_blocks_with_fuzzy_location() -> None:
    """Negation check runs on fuzzy-located window too.

    Chart: "无痰培养阳性结果. 诊断: 肺炎."
    Quote: "痰培养阳性" — verbatim not found, but fuzzy locates "痰培养阳性"
    within "无痰培养阳性结果". The preceding "无" must trigger CEA-005.
    """
    chart = "患者无痰培养阳性结果. 诊断: 肺炎."
    q, _ = _make_query(chart=chart)
    q.claims = [Claim(claim_id="c1", text="痰培养阳性", criticality="critical")]
    q.claim_evidence_alignments = [
        _alignment("c1", quote="痰培养阳性", support_type="direct")
    ]
    result = evaluate_claim_evidence(q, chart=chart)
    # Either BLOCK (CEA-005 hard-fails) or REVIEW_REQUIRED (depending on
    # aggregation) — but the negation must be detected somewhere.
    all_rule_evidences = [
        r.evidence for c in result.claims for r in c.rule_results
    ]
    assert any("无" in e or "negation" in e.lower() for e in all_rule_evidences), (
        f"CEA-005 should detect 无 negation; evidences: {all_rule_evidences}"
    )
