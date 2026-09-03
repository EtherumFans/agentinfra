"""Phase 5 Track D P0.5 Gate 3 — single-dimension gate + NLQ-011 tests.

Seeded from the actual Gate 2 after-baseline truth table:

  C05 Q2 topic "左侧肋骨骨折具体部位及数量"               → DROP (site + count)
  C05 Q3 query_text "...及其与右侧骨折的关系"             → DROP (type + correlation)
  C03 Q1 topic "高血压病分级或分期"                       → PASS (single axis severity)
  C03 Q2 query_text "头晕乏力症状与血压...的关系"         → PASS (single axis correlation)
  C10 Q2 topic "咳嗽和发热的持续时间"                     → PASS (single axis course)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.icoder.agent_runtime.cdi.domain import CDICase, EvidenceSpan, ProviderQuery
from app.icoder.agent_runtime.cdi.necessity_gate import (
    NecessityGateResult,
    NecessityRuleResult,
)
from app.icoder.agent_runtime.cdi.nlq_gate import (
    ProviderQueryForGate,
    evaluate as evaluate_nlq,
)
from app.icoder.agent_runtime.cdi.single_dimension_gate import (
    AXIS_KEYWORDS,
    apply_single_dimension_to_case,
    detect_axes,
    evaluate_case_single_dimension,
    evaluate_single_dimension,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _q(query_id: str, topic: str, query_text: str = "") -> ProviderQuery:
    return ProviderQuery(
        query_id=query_id,
        gap_id=f"g-{query_id}",
        topic=topic,
        reason="test",
        evidence_span=EvidenceSpan(document_id="d1", quote=""),
        query_text=query_text or topic,
        response_options=[],
    )


# ---------------------------------------------------------------------------
# detect_axes — taxonomy primitive
# ---------------------------------------------------------------------------


def test_detect_axes_empty_returns_empty_set() -> None:
    assert detect_axes("") == set()


def test_detect_axes_single_keyword() -> None:
    assert detect_axes("肺炎的部位未明确") == {"site"}


def test_detect_axes_multi_axis() -> None:
    # Both "部位" (site) and "严重程度" (severity) present
    assert detect_axes("请明确部位和严重程度") == {"site", "severity"}


def test_detect_axes_grading_and_staging_unify_to_severity() -> None:
    # 分级 + 分期 both map to severity → single axis
    assert detect_axes("高血压病分级或分期") == {"severity"}


def test_detect_axes_correlation_is_single_axis() -> None:
    # 关联 / 关系 are the correlation axis — single axis by itself
    assert detect_axes("头晕与高血压的关联") == {"correlation"}
    assert detect_axes("症状与血压的关系") == {"correlation"}


def test_document_section_label_does_not_add_course_axis() -> None:
    assert detect_axes("病程记录中的严重程度不一致") == {"severity"}


def test_true_clinical_course_still_detected() -> None:
    assert detect_axes("请明确头痛的病程和持续时间") == {"course"}


def test_evidence_preamble_does_not_make_severity_request_compound() -> None:
    q = _q(
        "q-evidence-preamble",
        topic="COPD急性加重严重程度",
        query_text="根据血气分析及临床病程，本次COPD急性加重的严重程度应如何界定？",
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "SINGLE_DIM"
    assert result.axes_detected == ["severity"]


def test_course_in_actual_request_clause_still_makes_query_compound() -> None:
    q = _q(
        "q-compound",
        topic="COPD急性加重严重程度和病程",
        query_text="根据血气分析，请明确严重程度和病程。",
    )
    assert evaluate_single_dimension(q).verdict == "MULTI_DIM"


# ---------------------------------------------------------------------------
# SD-001 — topic multi-axis
# ---------------------------------------------------------------------------


def test_sd001_topic_two_axes_drops() -> None:
    """Synthetic positive: topic spans type + site → MULTI_DIM."""
    q = _q("q1", topic="肺炎的类型和部位")
    result = evaluate_single_dimension(q)
    assert result.verdict == "MULTI_DIM"
    sd001 = next(r for r in result.rules_failed if r.rule_id == "SD-001")
    assert sd001.passed is False
    assert "type" in sd001.evidence and "site" in sd001.evidence


def test_sd001_topic_single_axis_passes() -> None:
    """Synthetic negative: topic has only one axis."""
    q = _q("q1", topic="肺炎的病原体")
    result = evaluate_single_dimension(q)
    assert result.verdict == "SINGLE_DIM"


def test_sd001_baseline_c05_q2_drops() -> None:
    """Regression: C05 Q2 from after-baseline must DROP.

    topic = "左侧肋骨骨折具体部位及数量" → site + count axes.
    """
    q = _q(
        "c05_q2",
        topic="左侧肋骨骨折具体部位及数量",
        query_text=(
            "影像学检查提示左侧肋骨骨折，但未明确具体肋骨编号及数量。"
            "请补充左侧骨折的具体部位和数量，以及右侧是否有多发骨折。"
        ),
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "MULTI_DIM", f"expected drop, got axes={result.axes_detected}"


def test_sd001_baseline_c03_q1_passes() -> None:
    """Regression: C03 Q1 from after-baseline must PASS.

    topic = "高血压病分级或分期" — both 分级/分期 are severity axis (single).
    """
    q = _q(
        "c03_q1",
        topic="高血压病分级或分期",
        query_text="根据患者血压160/95mmHg，请明确高血压病的分级或分期：",
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "SINGLE_DIM", f"expected pass, got axes={result.axes_detected}"


def test_sd001_baseline_c10_q2_passes() -> None:
    """Regression: C10 Q2 from after-baseline must PASS.

    topic = "咳嗽和发热的持续时间" — only course axis (single).
    The 和 joins clinical entities (咳嗽, 发热), not axis keywords.
    """
    q = _q(
        "c10_q2",
        topic="咳嗽和发热的持续时间",
        query_text="请明确患儿咳嗽和发热的具体持续时间（例如：咳嗽几天，发热几天，最高体温多少）？",
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "SINGLE_DIM", f"expected pass, got axes={result.axes_detected}"


# ---------------------------------------------------------------------------
# SD-002 — query_text multi-axis within 40-char window
# ---------------------------------------------------------------------------


def test_sd002_text_two_axes_in_same_clause_drops() -> None:
    """C05 Q3 regression: query_text mixes 性质 (type) + 关系 (correlation)."""
    q = _q(
        "c05_q3",
        topic="左胸外伤的具体性质",
        query_text=(
            "患者初步诊断为左胸外伤，但最终诊断为右侧肋骨骨折。"
            "请明确左胸外伤的具体性质（如软组织挫伤、血肿等）及其与右侧骨折的关系。"
        ),
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "MULTI_DIM", f"expected drop, got axes={result.axes_detected}"
    sd002 = next(r for r in result.rules_failed if r.rule_id == "SD-002")
    assert sd002.passed is False


def test_sd002_text_two_axes_far_apart_passes() -> None:
    """When 2 axis keywords appear but >40 chars apart, treat as single-axis.

    This protects against false positives on long queries that legitimately
    mention one axis in the question and another in a side note.
    """
    long_text = (
        "请明确肺炎的病原体。"
        + "题目背景描述" * 10  # ~60 chars of filler
        + "另外可以讨论严重程度。"
    )
    q = _q("q1", topic="肺炎病原体", query_text=long_text)
    result = evaluate_single_dimension(q)
    # Topic alone is single-axis (etiology only); the 40-char window
    # in SD-002 should not span 病原体 + 严重程度.
    assert result.verdict == "SINGLE_DIM", f"expected pass, got axes={result.axes_detected}"


def test_sd002_baseline_c03_q2_passes() -> None:
    """Regression: C03 Q2 from after-baseline must PASS.

    query_text contains "头晕乏力症状与血压160/95mmHg的关系" — the 与 joins
    clinical entities (头晕/血压), not axis keywords. Single axis = correlation.
    """
    q = _q(
        "c03_q2",
        topic="头晕乏力与高血压的关联",
        query_text="患者头晕乏力症状与血压160/95mmHg的关系：",
    )
    result = evaluate_single_dimension(q)
    assert result.verdict == "SINGLE_DIM", f"expected pass, got axes={result.axes_detected}"


# ---------------------------------------------------------------------------
# SD-003 — case-level cluster tag
# ---------------------------------------------------------------------------


def test_sd003_cluster_triggers_at_3_queries_same_axis() -> None:
    """3 queries touching 'severity' axis → tag triggered, no drops."""
    qs = [
        _q("q1", topic="严重程度分级"),
        _q("q2", topic="心力衰竭严重程度"),
        _q("q3", topic="慢性肾病严重程度"),
    ]
    case = CDICase(case_id="c1", chart_excerpt="any", proposed_provider_queries=qs)
    result = evaluate_case_single_dimension(case)
    assert result.axis_cluster_triggered is True
    assert result.axis_cluster_axis == "severity"
    assert result.axis_cluster_count == 3
    # All queries survive (cluster is tag-only, not block)
    assert len(case.proposed_provider_queries) == 3


def test_sd003_cluster_does_not_trigger_at_2() -> None:
    qs = [
        _q("q1", topic="严重程度分级"),
        _q("q2", topic="心力衰竭严重程度"),
    ]
    case = CDICase(case_id="c1", chart_excerpt="any", proposed_provider_queries=qs)
    result = evaluate_case_single_dimension(case)
    assert result.axis_cluster_triggered is False


# ---------------------------------------------------------------------------
# apply_single_dimension_to_case — end-to-end mutation
# ---------------------------------------------------------------------------


def test_apply_single_dimension_drops_multi_dim_preserves_single() -> None:
    """3 queries: 1 multi-dim, 2 single-dim → 2 survive."""
    qs = [
        _q("q_multi", topic="类型和部位", query_text="请明确肺炎的类型和部位"),
        _q("q_single1", topic="肺炎病原体", query_text="请明确肺炎的病原体"),
        _q("q_single2", topic="骨折部位", query_text="请明确骨折的具体部位"),
    ]
    case = CDICase(case_id="c1", chart_excerpt="any", proposed_provider_queries=qs)
    result = apply_single_dimension_to_case(case)
    assert len(case.proposed_provider_queries) == 2
    surviving_ids = {q.query_id for q in case.proposed_provider_queries}
    assert surviving_ids == {"q_single1", "q_single2"}
    # The dropped query is still in the result for traceability
    assert "q_multi" in result.per_query
    assert result.per_query["q_multi"].verdict == "MULTI_DIM"
    assert len(case.query_rewrite_queue) == 1
    rewrite = case.query_rewrite_queue[0]
    assert rewrite["query_id"] == "q_multi"
    assert rewrite["status"] == "NEEDS_CDI_REWRITE"
    assert len(rewrite["detected_axes"]) >= 2
    assert rewrite["gate_reasons"]


def test_apply_single_dimension_never_sends_only_multi_dim_draft_but_preserves_it() -> None:
    case = CDICase(
        case_id="c1",
        chart_excerpt="any",
        proposed_provider_queries=[
            _q(
                "q_multi",
                topic="\u7c7b\u578b\u548c\u90e8\u4f4d",
                query_text="\u8bf7\u660e\u786e\u80ba\u708e\u7684\u7c7b\u578b\u548c\u90e8\u4f4d",
            )
        ],
    )

    apply_single_dimension_to_case(case)

    assert case.proposed_provider_queries == []
    assert [item["query_id"] for item in case.query_rewrite_queue] == ["q_multi"]


def test_apply_single_dimension_preserves_all_when_single_dim() -> None:
    qs = [
        _q("q1", topic="肺炎病原体"),
        _q("q2", topic="骨折部位"),
    ]
    case = CDICase(case_id="c1", chart_excerpt="any", proposed_provider_queries=qs)
    apply_single_dimension_to_case(case)
    assert len(case.proposed_provider_queries) == 2


# ---------------------------------------------------------------------------
# NLQ-011 — max 5 response options
# ---------------------------------------------------------------------------


def test_nlq011_six_options_blocks() -> None:
    query = ProviderQueryForGate(
        query_text="请问A还是B？",
        response_options=["A. 选项一", "B. 选项二", "C. 选项三", "D. 选项四", "E. 选项五", "F. 选项六"],
    )
    result = evaluate_nlq(query)
    assert result.verdict == "BLOCK"
    nlq011 = next(r for r in result.rules_failed if r.rule_id == "NLQ-011")
    assert "count=6" in nlq011.evidence


def test_nlq011_five_options_passes() -> None:
    query = ProviderQueryForGate(
        query_text="请问A还是B？",
        response_options=["A. 一", "B. 二", "C. 三", "D. 四", "E. 无法确定"],
    )
    result = evaluate_nlq(query)
    # NLQ-011 passes; verdict may still be BLOCK from other rules but not from 011
    nlq011 = next(r for r in (result.rules_failed + result.rules_passed_detail) if r.rule_id == "NLQ-011")
    assert nlq011.action == "PASS"


def test_nlq011_three_options_passes() -> None:
    """NLQ-004 floor (≥3) and NLQ-011 ceiling (≤5) both satisfied at 3."""
    query = ProviderQueryForGate(
        query_text="请问A？",
        response_options=["A. 一", "B. 二", "C. 无法确定"],
    )
    result = evaluate_nlq(query)
    nlq011 = next(r for r in (result.rules_failed + result.rules_passed_detail) if r.rule_id == "NLQ-011")
    assert nlq011.action == "PASS"
    nlq004 = next(r for r in (result.rules_failed + result.rules_passed_detail) if r.rule_id == "NLQ-004")
    assert nlq004.action == "PASS"


# ---------------------------------------------------------------------------
# Sanity — AXIS_KEYWORDS coverage
# ---------------------------------------------------------------------------


def test_axis_keywords_covers_all_9_axes() -> None:
    """If this fails, the taxonomy was edited — update tests accordingly."""
    expected_axes = {
        "type", "etiology", "severity", "acuity", "site",
        "course", "complication", "count", "correlation",
    }
    assert set(AXIS_KEYWORDS.keys()) == expected_axes
