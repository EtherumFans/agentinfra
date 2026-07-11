"""Phase 5 Track D P0.5 Gate 2 — Query Necessity Gate unit tests."""

from __future__ import annotations

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.icoder.agent_runtime.cdi.necessity_gate import (
    apply_necessity_to_case,
    evaluate_case_necessity,
    evaluate_necessity,
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


def _mk_case(queries: list[ProviderQuery], chart: str = "患者咳嗽。") -> CDICase:
    return CDICase(
        case_id="CASE-test",
        chart_excerpt=chart,
        documentation_gaps=[
            DocumentationGap(
                gap_id=q.gap_id,
                description="d",
                why_it_matters="w",
                evidence_span=EvidenceSpan(document_id="D", quote="x"),
            )
            for q in queries
        ],
        proposed_provider_queries=queries,
    )


def test_nq001_chart_already_has_diagnosis_type():
    """Chart says '急性阑尾炎' → query asking for 类型 is unnecessary."""
    q = _mk_query("Q-1", "类型")
    case = _mk_case([q], chart="患者转移性右下腹痛,诊断为急性阑尾炎,手术:腹腔镜阑尾切除术。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "UNNECESSARY"
    assert any("NQ-001" in r for r in result.drop_reasons)


def test_nq001_chart_does_not_answer():
    """Chart says '肺炎' without type → query for 类型 is necessary."""
    q = _mk_query("Q-1", "类型")
    case = _mk_case([q], chart="患者咳嗽发热。胸片:肺炎。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq002_family_history_only_soft_flag():
    """Family-history-only detail soft-fails but does not drop."""
    q = _mk_query("Q-1", "家族史",
                  query_text="患者父亲有糖尿病史,请明确其父亲所患糖尿病的具体类型")
    case = _mk_case([q], chart="父亲糖尿病。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    # Family-history soft-fails, but no hard fail → still NECESSARY
    assert result.verdict == "NECESSARY"
    assert any("NQ-002" in r for r in result.flag_reasons)


def test_nq004_pathogen_already_cultured():
    """Chart has 痰培养:肺炎链球菌 → query for 病原体 is unnecessary."""
    q = _mk_query("Q-1", "病原体")
    case = _mk_case([q], chart="患者咳嗽。痰培养:肺炎链球菌。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "UNNECESSARY"
    assert any("NQ-004" in r for r in result.drop_reasons)


def test_nq005_redundant_topic_dropped():
    """Two queries with same topic — second one is redundant."""
    q1 = _mk_query("Q-1", "部位")
    q2 = _mk_query("Q-2", "部位")
    case = _mk_case([q1, q2], chart="x")
    r1 = evaluate_necessity(q1, chart=case.chart_excerpt, all_queries=[q1, q2])
    r2 = evaluate_necessity(q2, chart=case.chart_excerpt, all_queries=[q1, q2])
    # Exactly one should hard-fail NQ-005
    assert (r1.verdict == "UNNECESSARY") != (r2.verdict == "UNNECESSARY")


def test_overquery_guard_triggers_at_5_queries():
    """Case with ≥5 queries triggers NQ-006."""
    queries = [_mk_query(f"Q-{i}", f"topic-{i}") for i in range(1, 6)]
    case = _mk_case(queries, chart="x")
    result = evaluate_case_necessity(case)
    assert result.overquery_triggered is True
    assert result.overquery_count == 5


def test_overquery_guard_does_not_trigger_at_4():
    """Case with exactly 4 queries does NOT trigger NQ-006 (threshold = >4)."""
    queries = [_mk_query(f"Q-{i}", f"topic-{i}") for i in range(1, 5)]
    case = _mk_case(queries, chart="x")
    result = evaluate_case_necessity(case)
    assert result.overquery_triggered is False


def test_apply_necessity_drops_unnecessary():
    """apply_necessity_to_case mutates the case — drops UNNECESSARY queries."""
    q1 = _mk_query("Q-1", "类型")  # unnecessary (chart has 急性阑尾炎)
    q2 = _mk_query("Q-2", "部位")  # necessary (chart doesn't specify)
    case = _mk_case([q1, q2], chart="患者诊断为急性阑尾炎。")
    result = apply_necessity_to_case(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].query_id == "Q-2"
    assert "Q-1" in result.per_query
    assert result.per_query["Q-1"].verdict == "UNNECESSARY"


def test_apply_necessity_preserves_all_when_necessary():
    """All queries necessary → none dropped."""
    queries = [
        _mk_query("Q-1", "类型"),
        _mk_query("Q-2", "部位"),
    ]
    case = _mk_case(queries, chart="患者咳嗽。诊断肺炎。")
    apply_necessity_to_case(case)
    assert len(case.proposed_provider_queries) == 2
