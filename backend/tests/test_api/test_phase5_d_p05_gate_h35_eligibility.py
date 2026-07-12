"""Phase 5 Track H3.5 — Query Eligibility Gate unit tests.

Verifies:
- Chart completeness detection across 8 dimensions (type/site/severity/
  etiology/procedure/pathology/complications/course)
- Ambiguity markers (可疑/疑似/可能) suppress chart_complete
- QE-001 drops all queries on complete charts (fixes complete_chart over-query)
- QE-002 drops queries with no matching gap
- apply_eligibility_to_case mutates case.proposed_provider_queries correctly
"""

from __future__ import annotations

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.icoder.agent_runtime.cdi.query_eligibility_gate import (
    apply_eligibility_to_case,
    detect_chart_completeness,
    evaluate_case_eligibility,
    evaluate_query_eligibility,
)


def _mk_query(qid: str, topic: str, query_text: str = "", gap_id: str = "GAP-1") -> ProviderQuery:
    return ProviderQuery(
        query_id=qid,
        gap_id=gap_id,
        topic=topic,
        reason="r",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
        query_text=query_text or f"请明确{topic}",
        response_options=["A", "B", "无法确定"],
    )


def _mk_case(
    queries: list[ProviderQuery],
    chart: str,
    gaps: list[DocumentationGap] | None = None,
) -> CDICase:
    if gaps is None:
        gaps = [
            DocumentationGap(
                gap_id=q.gap_id,
                description=f"gap about {q.topic}",
                why_it_matters="w",
                evidence_span=EvidenceSpan(document_id="D", quote="x"),
            )
            for q in queries
        ]
    return CDICase(
        case_id="CASE-test",
        chart_excerpt=chart,
        documentation_gaps=gaps,
        proposed_provider_queries=queries,
    )


# ---------------------------------------------------------------------------
# Chart completeness detection
# ---------------------------------------------------------------------------


def test_complete_chart_appendicitis_detected():
    """The canonical COMPLETE-011 chart triggers chart_complete=True."""
    chart = (
        "中年男性,45岁,转移性右下腹痛1天,McBurney点压痛、反跳痛阳性。"
        "WBC 13.2,中性85%。CT:阑尾肿胀,周围少量渗出。"
        "术前诊断:急性化脓性阑尾炎(局限性,无穿孔)。"
        "腹腔镜阑尾切除术。术后病理:急性化脓性阑尾炎。"
        "无并发症。恢复顺利,术后3天出院。"
    )
    score, dims, complete = detect_chart_completeness(chart)
    assert complete is True, f"expected complete, got score={score} dims={dims}"
    assert score >= 0.75  # ≥6/8 dimensions


def test_ambiguity_marker_suppresses_complete():
    """可疑/疑似 marker keeps the chart non-complete even with all dimensions."""
    chart = (
        "中年男性,45岁,转移性右下腹痛1天。WBC 13.2,中性85%。"
        "CT:阑尾肿胀,可疑周围渗出。术前诊断:急性化脓性阑尾炎。"
        "腹腔镜阑尾切除术。术后病理:急性化脓性阑尾炎。无并发症。3天出院。"
    )
    score, dims, complete = detect_chart_completeness(chart)
    assert complete is False, "ambiguity marker 可疑 must suppress chart_complete"


def test_sparse_chart_not_complete():
    """A short chart without procedures/pathology is not complete."""
    chart = "患者咳嗽发热3天。胸片:肺炎。"
    score, dims, complete = detect_chart_completeness(chart)
    assert complete is False
    assert score < 0.5


# ---------------------------------------------------------------------------
# QE-001 chart-completeness drop
# ---------------------------------------------------------------------------


def test_qe001_complete_chart_drops_all_queries():
    """On a complete chart, all queries are INELIGIBLE (QE-001 hard-fails)."""
    chart = (
        "中年男性,45岁,转移性右下腹痛1天,McBurney点压痛。WBC 13.2,中性85%。"
        "CT:阑尾肿胀。术前诊断:急性化脓性阑尾炎(局限性)。"
        "腹腔镜阑尾切除术。术后病理:急性化脓性阑尾炎。无并发症。3天出院。"
    )
    q1 = _mk_query("Q-1", "类型")
    q2 = _mk_query("Q-2", "严重程度")
    case = _mk_case([q1, q2], chart=chart)

    result = apply_eligibility_to_case(case)
    assert result.chart_complete is True
    assert result.dropped_count == 2
    assert len(case.proposed_provider_queries) == 0


def test_qe001_non_complete_chart_keeps_queries():
    """On a sparse chart with gaps, queries are ELIGIBLE."""
    chart = "患者咳嗽发热3天。胸片:肺炎。"
    q1 = _mk_query("Q-1", "病原体")
    case = _mk_case([q1], chart=chart)

    result = apply_eligibility_to_case(case)
    assert result.chart_complete is False
    assert len(case.proposed_provider_queries) == 1


# ---------------------------------------------------------------------------
# QE-002 topic-gap relevance
# ---------------------------------------------------------------------------


def test_qe002_query_topic_matches_gap_via_gap_id():
    """Direct gap_id linkage = eligible."""
    chart = "患者咳嗽发热3天。胸片:肺炎。"
    q = _mk_query("Q-1", "病原体", gap_id="GAP-X")
    gap = DocumentationGap(
        gap_id="GAP-X",
        description="病原体未明确",
        why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q], chart=chart, gaps=[gap])
    result = evaluate_query_eligibility(
        q, chart=chart, case=case, chart_complete=False
    )
    assert result.verdict == "ELIGIBLE"


def test_qe002_query_topic_no_match_dropped():
    """Query with topic unrelated to any gap is INELIGIBLE."""
    chart = "患者咳嗽发热3天。胸片:肺炎。"
    q = _mk_query("Q-1", "家族肿瘤史", gap_id="GAP-UNRELATED")
    unrelated_gap = DocumentationGap(
        gap_id="GAP-OTHER",
        description="病原体未明确",
        why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q], chart=chart, gaps=[unrelated_gap])
    result = evaluate_query_eligibility(
        q, chart=chart, case=case, chart_complete=False
    )
    assert result.verdict == "INELIGIBLE"
    assert any("QE-002" in r for r in result.drop_reasons)


def test_qe002_topic_overlap_via_substring():
    """Query topic that is a substring of a gap description = eligible."""
    chart = "患者腹痛。"
    q = _mk_query("Q-1", "严重程度", gap_id="GAP-1")
    gap = DocumentationGap(
        gap_id="GAP-1",
        description="严重程度未分级",
        why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q], chart=chart, gaps=[gap])
    result = evaluate_query_eligibility(
        q, chart=chart, case=case, chart_complete=False
    )
    assert result.verdict == "ELIGIBLE"


# ---------------------------------------------------------------------------
# apply_eligibility_to_case
# ---------------------------------------------------------------------------


def test_apply_eligibility_drops_mixed_case():
    """Mixed case: 1 eligible + 1 ineligible query → only eligible survives."""
    chart = "患者咳嗽发热3天。胸片:肺炎。"
    q_eligible = _mk_query("Q-1", "病原体", gap_id="GAP-1")
    q_off_topic = _mk_query("Q-2", "家族肿瘤史", gap_id="GAP-2")
    gap1 = DocumentationGap(
        gap_id="GAP-1",
        description="病原体未明确",
        why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q_eligible, q_off_topic], chart=chart, gaps=[gap1])
    result = apply_eligibility_to_case(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].query_id == "Q-1"
    assert result.dropped_count == 1


def test_apply_eligibility_preserves_all_when_all_eligible():
    """All eligible queries survive; dropped_count = 0."""
    chart = "患者腹痛。"
    q1 = _mk_query("Q-1", "部位", gap_id="GAP-1")
    q2 = _mk_query("Q-2", "严重程度", gap_id="GAP-2")
    g1 = DocumentationGap(
        gap_id="GAP-1", description="部位不明确", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    g2 = DocumentationGap(
        gap_id="GAP-2", description="严重程度未分级", why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q1, q2], chart=chart, gaps=[g1, g2])
    result = apply_eligibility_to_case(case)
    assert len(case.proposed_provider_queries) == 2
    assert result.dropped_count == 0


# ---------------------------------------------------------------------------
# evaluate_case_eligibility (side-effect-free)
# ---------------------------------------------------------------------------


def test_evaluate_case_eligibility_does_not_mutate():
    """The evaluate_* function must NOT mutate case.proposed_provider_queries."""
    chart = "患者咳嗽。"
    q = _mk_query("Q-1", "家族史", gap_id="GAP-X")
    case = _mk_case([q], chart=chart)
    original_count = len(case.proposed_provider_queries)
    _ = evaluate_case_eligibility(case)
    assert len(case.proposed_provider_queries) == original_count


# ---------------------------------------------------------------------------
# Track H3.10 — contradiction override
# ---------------------------------------------------------------------------


def test_h310_contradiction_risk_flag_overrides_chart_complete():
    """A complete chart with a contradiction risk_flag is NOT marked complete.

    The document_conflict fixture category has charts that often have
    ≥6 dimensions explicit PLUS an internal contradiction. Pre-H3.10
    the eligibility gate dropped all queries; post-H3.10 the contradiction
    override keeps them alive for downstream gates.
    """
    from app.icoder.agent_runtime.cdi.domain import RiskFlag

    chart = (
        "中年男性,45岁,转移性右下腹痛1天,McBurney点压痛。WBC 13.2,中性85%。"
        "CT:阑尾肿胀。术前诊断:急性化脓性阑尾炎(局限性)。"
        "腹腔镜阑尾切除术。术后病理:急性化脓性阑尾炎。无并发症。3天出院。"
        "术后第2天体温38.5°C,但白细胞降至6.5(矛盾:症状与检验不一致)。"
    )
    q = _mk_query("Q-1", "症状与检验矛盾", gap_id="GAP-1")
    gap = DocumentationGap(
        gap_id="GAP-1",
        description="症状与检验矛盾未澄清",
        why_it_matters="w",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
    )
    case = _mk_case([q], chart=chart, gaps=[gap])
    case.risk_flags = [
        RiskFlag(
            category="contradiction",
            description="WBC下降但体温上升,症状与检验不一致",
        )
    ]

    result = apply_eligibility_to_case(case)
    assert result.chart_complete is False, "contradiction must override completeness"
    assert len(case.proposed_provider_queries) == 1, "query must survive"


def test_h310_no_contradiction_keeps_complete_behavior():
    """Sanity: a complete chart with NO contradiction still drops queries."""
    chart = (
        "中年男性,45岁,转移性右下腹痛1天,McBurney点压痛。WBC 13.2,中性85%。"
        "CT:阑尾肿胀。术前诊断:急性化脓性阑尾炎(局限性)。"
        "腹腔镜阑尾切除术。术后病理:急性化脓性阑尾炎。无并发症。3天出院。"
    )
    q1 = _mk_query("Q-1", "类型")
    q2 = _mk_query("Q-2", "严重程度")
    case = _mk_case([q1, q2], chart=chart)
    # No risk_flags → no contradiction override

    result = apply_eligibility_to_case(case)
    assert result.chart_complete is True
    assert len(case.proposed_provider_queries) == 0
