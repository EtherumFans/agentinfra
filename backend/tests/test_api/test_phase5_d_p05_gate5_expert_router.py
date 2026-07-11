"""Phase 5 Track D P0.5 Gate 5 — Conditional Expert Routing tests.

Tests the pure-logic ``route_experts`` per Master Task §6.1-§6.5:

  - 6 execution modes (REAL_TOOL / LLM_KNOWLEDGE_ONLY /
    SKIPPED_NOT_NEEDED / SKIPPED_MISSING_INPUTS / TOOL_UNAVAILABLE /
    DEGRADED)
  - Empty-chart C09 rule: all 4 Experts SKIPPED_NOT_NEEDED
  - Per-Expert routing: coding-relevance, criteria markers, guideline
    markers, score markers, parameter presence
  - ``available_tools`` upgrade from LLM_KNOWLEDGE_ONLY to REAL_TOOL
  - Real runner integration: route decisions propagate to
    case.specialist_trace
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import (
    CDICase,
    CDIOrchestrator,
    DocumentationGap,
    EvidenceSpan,
    ExpertRouteDecision,
    ProviderQuery,
    RealCDIRunner,
    route_experts,
    should_invoke,
)


# ---------------------------------------------------------------------------
# Substrate detector — empty-chart C09 rule (§6.3)
# ---------------------------------------------------------------------------


def test_c09_empty_chart_all_four_experts_skipped_not_needed() -> None:
    """Master Task §6.3: 无诊断/无检验/无影像/无临床指标 → all SKIPPED_NOT_NEEDED."""
    case = CDICase(
        case_id="c09",
        chart_excerpt="患者主诉腹痛. 建议进一步检查.",
    )
    result = route_experts(case)
    assert len(result.decisions) == 4
    for d in result.decisions:
        assert d.execution_mode == "SKIPPED_NOT_NEEDED"
        assert d.reason == "empty_chart"
        assert d.needed is False
    assert result.invoked_expert_ids == []
    assert result.skipped_expert_ids == [
        "coding-expert", "pubmed-expert", "web-search-expert", "medical-calculator-expert",
    ]


def test_blank_chart_treated_as_empty() -> None:
    case = CDICase(case_id="c", chart_excerpt="   ")
    result = route_experts(case)
    for d in result.decisions:
        assert d.execution_mode == "SKIPPED_NOT_NEEDED"


def test_empty_chart_with_no_gaps_skips_all() -> None:
    """Chart with substrate but zero gaps → all Experts SKIPPED_NOT_NEEDED."""
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,55岁,急性前壁ST段抬高型心肌梗死,行PCI植入支架1枚。",
    )
    # documentation_gaps defaults to [] — nothing for any Expert to do
    result = route_experts(case)
    assert result.invoked_expert_ids == []


# ---------------------------------------------------------------------------
# Coding-expert routing
# ---------------------------------------------------------------------------


def _make_gap(*, gap_type: str, description: str = "肺炎病原体未明确") -> DocumentationGap:
    return DocumentationGap(
        gap_id="g1",
        description=description,
        why_it_matters="影响编码特异性",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
        gap_type=gap_type,  # type: ignore[arg-type]
    )


def test_coding_expert_needed_when_diagnostic_specificity_gap() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,58岁,诊断肺炎。痰培养阳性。",
        documentation_gaps=[_make_gap(gap_type="diagnostic_specificity")],
    )
    d = route_experts(case).for_expert("coding-expert")
    assert d is not None
    assert d.needed is True
    assert d.execution_mode == "LLM_KNOWLEDGE_ONLY"
    assert d.reason == "coding_relevant_gap"
    assert d.priority == "high"


def test_coding_expert_skipped_when_no_relevant_gap_types() -> None:
    """clinical_correlation + temporal are NOT coding-relevant."""
    case = CDICase(
        case_id="c",
        chart_excerpt="患者诊断肺炎。临床表现与培养结果未关联。术后发热时间不明。",
        documentation_gaps=[
            _make_gap(gap_type="clinical_correlation_unestablished"),
            _make_gap(gap_type="temporal_unspecified"),
        ],
    )
    d = route_experts(case).for_expert("coding-expert")
    assert d is not None
    assert d.needed is False
    assert d.execution_mode == "SKIPPED_NOT_NEEDED"
    assert d.reason == "no_relevant_gap"


def test_coding_expert_upgrades_to_real_tool_when_wired() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,58岁,诊断肺炎。",
        documentation_gaps=[_make_gap(gap_type="diagnostic_specificity")],
    )
    result = route_experts(case, available_tools={"coding-expert": True})
    d = result.for_expert("coding-expert")
    assert d is not None
    assert d.execution_mode == "REAL_TOOL"
    assert d.reason == "real_tool_wired"


# ---------------------------------------------------------------------------
# PubMed-expert routing
# ---------------------------------------------------------------------------


def test_pubmed_expert_needed_when_criteria_marker_present() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者头晕乏力1月。需要明确诊断标准。",
    )
    d = route_experts(case).for_expert("pubmed-expert")
    assert d is not None
    assert d.needed is True
    assert d.execution_mode == "LLM_KNOWLEDGE_ONLY"
    assert d.reason == "criteria_marker_present"
    # Must disclose missing real-PubMed tool
    assert "real_pubmed_search" in d.missing_inputs


def test_pubmed_expert_upgrades_to_real_tool() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者头晕乏力。需要明确诊断标准。",
    )
    result = route_experts(case, available_tools={"pubmed-expert": True})
    d = result.for_expert("pubmed-expert")
    assert d is not None
    assert d.execution_mode == "REAL_TOOL"


def test_pubmed_expert_skipped_when_no_markers() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,58岁,诊断肺炎。痰培养阳性。",
        documentation_gaps=[_make_gap(gap_type="diagnostic_specificity")],
    )
    d = route_experts(case).for_expert("pubmed-expert")
    assert d is not None
    assert d.execution_mode == "SKIPPED_NOT_NEEDED"
    assert d.reason == "no_relevant_gap"


# ---------------------------------------------------------------------------
# Web-search-expert routing — TOOL_UNAVAILABLE by default
# ---------------------------------------------------------------------------


def test_web_search_returns_tool_unavailable_without_real_tool() -> None:
    """§6.2: 没有真实 Web 工具时, 必须跳过或标记 TOOL_UNAVAILABLE.

    LLM_KNOWLEDGE_ONLY is forbidden for time-sensitive guidelines.
    """
    case = CDICase(
        case_id="c",
        chart_excerpt="患者诊断2型糖尿病。请参照2025年最新指南。",
    )
    d = route_experts(case).for_expert("web-search-expert")
    assert d is not None
    assert d.needed is True
    assert d.execution_mode == "TOOL_UNAVAILABLE"
    assert d.reason == "no_real_tool_wired"
    assert "real_web_search" in d.missing_inputs


def test_web_search_upgrades_to_real_tool_when_wired() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者诊断2型糖尿病。请参照2025年最新指南。",
    )
    result = route_experts(case, available_tools={"web-search-expert": True})
    d = result.for_expert("web-search-expert")
    assert d is not None
    assert d.execution_mode == "REAL_TOOL"


def test_web_search_skipped_when_no_guideline_markers() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,58岁,诊断肺炎。",
        documentation_gaps=[_make_gap(gap_type="diagnostic_specificity")],
    )
    d = route_experts(case).for_expert("web-search-expert")
    assert d is not None
    assert d.execution_mode == "SKIPPED_NOT_NEEDED"


# ---------------------------------------------------------------------------
# Medical-calculator-expert routing
# ---------------------------------------------------------------------------


def test_calculator_returns_skipped_missing_inputs_when_no_params() -> None:
    """§6.2: 参数不足 → SKIPPED_MISSING_INPUTS."""
    case = CDICase(
        case_id="c",
        chart_excerpt="患者心力衰竭。需要评估NYHA分级。",
        # No vitals / labs / numeric markers in chart
    )
    d = route_experts(case).for_expert("medical-calculator-expert")
    assert d is not None
    assert d.needed is True
    assert d.execution_mode == "SKIPPED_MISSING_INPUTS"
    assert d.reason == "calculator_params_missing"
    assert "clinical_parameters" in d.missing_inputs


def test_calculator_returns_tool_unavailable_when_params_present_no_tool() -> None:
    """§6.2: 不得用普通 LLM 猜测评分 → TOOL_UNAVAILABLE when params present but no tool."""
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,70岁,血压160/95 mmHg,心率80次/分。CHA2DS2-VASc评分待评估。",
    )
    d = route_experts(case).for_expert("medical-calculator-expert")
    assert d is not None
    assert d.needed is True
    assert d.execution_mode == "TOOL_UNAVAILABLE"
    assert d.reason == "no_real_tool_wired"


def test_calculator_upgrades_to_real_tool_when_wired() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,70岁,血压160/95 mmHg。CHA2DS2-VASc评分。",
    )
    result = route_experts(case, available_tools={"medical-calculator-expert": True})
    d = result.for_expert("medical-calculator-expert")
    assert d is not None
    assert d.execution_mode == "REAL_TOOL"


# ---------------------------------------------------------------------------
# Aggregate behaviors
# ---------------------------------------------------------------------------


def test_should_invoke_predicate() -> None:
    d_real = ExpertRouteDecision(
        expert_id="coding-expert", needed=True, reason="real_tool_wired",
        execution_mode="REAL_TOOL",
    )
    d_llm = ExpertRouteDecision(
        expert_id="coding-expert", needed=True, reason="coding_relevant_gap",
        execution_mode="LLM_KNOWLEDGE_ONLY",
    )
    d_skip = ExpertRouteDecision(
        expert_id="coding-expert", needed=False, reason="no_relevant_gap",
        execution_mode="SKIPPED_NOT_NEEDED",
    )
    d_unavail = ExpertRouteDecision(
        expert_id="web-search-expert", needed=True, reason="no_real_tool_wired",
        execution_mode="TOOL_UNAVAILABLE",
    )
    d_missing = ExpertRouteDecision(
        expert_id="medical-calculator-expert", needed=True, reason="calculator_params_missing",
        execution_mode="SKIPPED_MISSING_INPUTS",
    )
    assert should_invoke(d_real) is True
    assert should_invoke(d_llm) is True
    assert should_invoke(d_skip) is False
    assert should_invoke(d_unavail) is False
    assert should_invoke(d_missing) is False


def test_invoked_and_skipped_partitions_match() -> None:
    case = CDICase(
        case_id="c",
        chart_excerpt="患者诊断肺炎。需要明确诊断标准。请参照2025年最新指南。",
        documentation_gaps=[_make_gap(gap_type="diagnostic_specificity")],
    )
    result = route_experts(case)
    # coding (LLM) + pubmed (LLM) → invoked
    # web (TOOL_UNAVAILABLE) + calculator (no marker) → skipped
    assert set(result.invoked_expert_ids) == {"coding-expert", "pubmed-expert"}
    assert set(result.skipped_expert_ids) == {"web-search-expert", "medical-calculator-expert"}


# ---------------------------------------------------------------------------
# Integration: real runner populates case.specialist_trace
# ---------------------------------------------------------------------------


class _MockLLM:
    """Returns minimal canned JSON for non-Expert stages + content for Expert calls."""

    def __init__(self) -> None:
        self.expert_calls: list[str] = []

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> dict:
        sys_text = system_prompt or ""
        for marker, eid in (
            ("coding-specialist Expert", "coding-expert"),
            ("PubMed literature Expert", "pubmed-expert"),
            ("clinical web-search Expert", "web-search-expert"),
            ("medical-calculator Expert", "medical-calculator-expert"),
        ):
            if marker in sys_text:
                self.expert_calls.append(eid)
                return {
                    "content": f"Advice from {eid}.",
                    "usage": {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
                }

        # Non-Expert stages: return minimal valid JSON
        user_text = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        if "Extract the key clinical points" in user_text:
            content = json.dumps({"key_points": ["肺炎"], "encounter_metadata": {}})
        elif "Identify documentation gaps" in user_text:
            # Produce one coding-relevant gap so coding-expert routes to LLM.
            content = json.dumps({
                "gaps": [
                    {
                        "gap_id": "g1",
                        "description": "肺炎病原体未明确",
                        "why_it_matters": "影响编码特异性",
                        "evidence_span": {"document_id": "入院记录", "quote": "诊断: 肺炎"},
                        "priority": "routine",
                    }
                ]
            })
        elif "draft a NON-LEADING provider query" in user_text:
            content = json.dumps({"queries": []})
        else:
            content = "{}"
        return {"content": content, "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}}


def test_real_runner_only_invokes_routed_experts() -> None:
    """Real runner honors router: only needed Experts consume tokens."""
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(
        case_id="c",
        chart_excerpt="患者男性,58岁,诊断肺炎。需要明确诊断标准。",
    )
    CDIOrchestrator(runner=runner).run(case)

    # coding + pubmed both invoked; web + calculator skipped
    assert set(mock.expert_calls) == {"coding-expert", "pubmed-expert"}

    # All 4 Specialists appear in case.specialist_trace (audit complete)
    assert len(case.specialist_trace) == 4
    consulted = {e.expert_id for e in case.specialist_trace if e.consulted}
    skipped = {e.expert_id for e in case.specialist_trace if not e.consulted}
    assert consulted == {"coding-expert", "pubmed-expert"}
    assert skipped == {"web-search-expert", "medical-calculator-expert"}


def test_real_runner_empty_chart_skips_all_experts() -> None:
    """Master Task §6.3: C09 → 0 LLM Expert calls."""
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c09", chart_excerpt="患者主诉腹痛. 建议进一步检查.")
    CDIOrchestrator(runner=runner).run(case)

    assert mock.expert_calls == []  # no Expert LLM calls
    for entry in case.specialist_trace:
        assert entry.consulted is False
        assert entry.execution_mode == "SKIPPED_NOT_NEEDED"
