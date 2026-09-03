"""Phase 5 Track D P0.5 Gate 5 — Conditional Expert Routing.

Per Master Task §6.1-§6.5. Each Expert's invocation is gated by a
pure-logic routing decision: needed? required_inputs present? real
tool wired? The decision is one of 6 ``ExpertExecutionMode`` values.

Why this gate exists
====================

Pre-Gate-5 ``_stage_expert_consultation`` invoked all 4 Experts
unconditionally per case (40 calls / 10 cases). That:
  - Burns tokens on cases where the Expert has nothing to add (C09).
  - Conflates ``LLM_KNOWLEDGE_ONLY`` (no real PubMed/web/calculator
    tool wired; LLM is recalling from training data) with ``REAL_TOOL``
    (actual MCP tool call). PDF §A2 forbids the conflation.
  - Leaves the audit trail blind to *why* an Expert was/wasn't called.

The router is a deterministic pre-stage: it does NOT call any LLM. It
reads ``case.chart_excerpt`` + ``case.documentation_gaps`` and emits a
per-Expert decision. ``RealCDIRunner._stage_expert_consultation`` then
honors the decision: invoke only when execution_mode ∈ {REAL_TOOL,
LLM_KNOWLEDGE_ONLY}; skip otherwise.

The 6 modes
===========

    REAL_TOOL                  — real MCP/tool call will be made
    LLM_KNOWLEDGE_ONLY         — no real tool; LLM recalls training data
                                 (disclosed in Specialist Trace)
    SKIPPED_NOT_NEEDED         — case has no relevant gap for this Expert
    SKIPPED_MISSING_INPUTS     — gap exists but required inputs absent
    TOOL_UNAVAILABLE           — gap exists, inputs present, no tool wired
    DEGRADED                   — needed but LLM/tool failed earlier

Empty-chart C09 rule (§6.3)
===========================

When ``case.chart_excerpt`` is empty/whitespace OR no gaps survive the
prior gates, all 4 Experts → ``SKIPPED_NOT_NEEDED``. No LLM calls.

Tool availability
=================

``available_tools`` parameter lets the runtime advertise which Experts
have real MCP tools wired. In Phase 5 Track D P0.5 nothing does, so the
defaults are all False — meaning the router never emits ``REAL_TOOL``.
When a future phase wires PubMed search, set
``available_tools={"pubmed-expert": True}`` and that Expert upgrades
from ``LLM_KNOWLEDGE_ONLY`` to ``REAL_TOOL``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .domain import CDICase, DocumentationGap, GapType


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


ExpertExecutionMode = Literal[
    "REAL_TOOL",
    "LLM_KNOWLEDGE_ONLY",
    "SKIPPED_NOT_NEEDED",
    "SKIPPED_MISSING_INPUTS",
    "TOOL_UNAVAILABLE",
    "DEGRADED",
]
"""Per Master Task §6.1 — the only allowed execution_mode values."""


ExpertId = Literal[
    "coding-expert",
    "pubmed-expert",
    "web-search-expert",
    "medical-calculator-expert",
]
"""The 4 CDI Experts declared in ``real_runner._stage_expert_consultation``."""


RouteReason = Literal[
    "empty_chart",
    "no_relevant_gap",
    "coding_relevant_gap",
    "criteria_marker_present",
    "guideline_marker_present",
    "score_marker_present",
    "calculator_params_missing",
    "no_real_tool_wired",
    "real_tool_wired",
]


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------


@dataclass
class ExpertRouteDecision:
    """One Expert's routing outcome for one CDI case.

    Per Master Task §6.1 YAML schema.
    """

    expert_id: ExpertId
    needed: bool
    reason: RouteReason
    required_inputs: list[str] = field(default_factory=list)
    available_inputs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    execution_mode: ExpertExecutionMode = "SKIPPED_NOT_NEEDED"
    priority: Literal["high", "medium", "low"] = "medium"
    expected_value: str = ""


@dataclass
class ExpertRouteResult:
    """Aggregate routing outcome for a case."""

    decisions: list[ExpertRouteDecision] = field(default_factory=list)

    @property
    def invoked_expert_ids(self) -> list[str]:
        """Experts that the runner should actually call (LLM or tool)."""
        return [
            d.expert_id for d in self.decisions
            if d.execution_mode in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY")
        ]

    @property
    def skipped_expert_ids(self) -> list[str]:
        """Experts recorded but not invoked."""
        return [
            d.expert_id for d in self.decisions
            if d.execution_mode not in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY")
        ]

    def for_expert(self, expert_id: str) -> ExpertRouteDecision | None:
        return next((d for d in self.decisions if d.expert_id == expert_id), None)


# ---------------------------------------------------------------------------
# Default tool availability — Phase 5 Track D P0.5 has no real MCP tools
# ---------------------------------------------------------------------------


_DEFAULT_AVAILABLE_TOOLS: dict[str, bool] = {
    "coding-expert": False,
    "pubmed-expert": False,
    "web-search-expert": False,
    "medical-calculator-expert": False,
}


# ---------------------------------------------------------------------------
# Coding-relevance — which gap_types trigger the coding Expert
# ---------------------------------------------------------------------------


_CODING_RELEVANT_GAP_TYPES: frozenset[GapType] = frozenset({
    "unknown",
    "diagnostic_specificity",
    "etiology_unspecified",
    "severity_unspecified",
    "acuity_unspecified",
    "anatomical_site_unspecified",
    "conflicting_documentation",
})
"""Gap types whose clarification affects downstream ICD code selection.

Per §6.2 Coding Expert rule: "Gap 涉及编码特异性" / "需要内部编码影响分析".
The two non-coding gap types are ``clinical_correlation_unestablished``
(PubMed territory) and ``temporal_unspecified`` (documentation-only).
``unknown`` (Gate 4 fallback bucket) is treated as coding-relevant by
default — better to over-consult than miss coding impact.
"""


# ---------------------------------------------------------------------------
# Substrate detector — the C09 empty-chart rule (§6.3)
# ---------------------------------------------------------------------------


def _chart_has_substrate(chart: str) -> bool:
    """Per §6.3: empty-chart pathology = 无诊断/无检验/无影像/无临床指标.

    The C09 fixture ("患者主诉腹痛. 建议进一步检查.") lacks all four
    categories — just a chief complaint + referral suggestion. We detect
    "has substrate" by scanning for clinical fact markers in 4 buckets:

        - diagnosis statements (诊断 / 入院诊断 / 出院诊断)
        - lab/imaging (痰培养 / CT / MRI / 心电图 / mmol / mg / g/L ...)
        - clinical indicator units (mmHg / 次分 / ℃ ...)
        - common disease names (肺炎 / 骨折 / 梗死 / 高血压 / 糖尿病 ...)

    A chart with only administrative text (主诉 / 建议 / 进一步检查)
    fails all 4 buckets → False → all Experts SKIPPED_NOT_NEEDED.
    """
    if not chart or not chart.strip():
        return False
    return any(m in chart for m in _SUBSTRATE_MARKERS)


_SUBSTRATE_MARKERS: tuple[str, ...] = (
    # Diagnosis statements
    "诊断", "入院诊断", "出院诊断", "初步诊断",
    # Lab / imaging / procedures
    "痰培养", "血培养", "尿培养", "培养",
    "心电图", "CT", "MRI", "B超", "X光", "X射线", "造影",
    "手术记录", "术后", "PCI", "支架",
    "病理", "活检",
    # Clinical indicator units (vitals + labs)
    "mmHg", "kpa", "mg/dL", "mg/", "g/L", "mmol", "次/分", "bpm",
    "℃", "°C", "kg", "cm",
    # Common disease names
    "肺炎", "骨折", "梗死", "梗塞", "出血",
    "高血压", "糖尿病", "冠心病", "脑梗", "脑出血",
    "心力衰竭", "心衰", "肾功能", "肝功能", "脑卒中",
    "感染", "炎症", "肿瘤", "癌",
    # Clinical history sections that imply content beyond a chief complaint
    "现病史", "既往史", "查体", "专科查体",
)


# ---------------------------------------------------------------------------
# Per-Expert markers (heuristic text matching)
# ---------------------------------------------------------------------------


_PUBMED_MARKERS: tuple[str, ...] = (
    "诊断标准", "临床定义", "标准", "定义", "criteria", "definition",
    "分类", "classification", "亚型", "subtype",
)
"""Per §6.2 PubMed: needed when diagnostic criteria / clinical definitions / ambiguous terms."""


_WEB_MARKERS: tuple[str, ...] = (
    "最新指南", "当前指南", "指南", "2024", "2025", "2026",
    "guideline", "policy", "共识", "recommendation",
)
"""Per §6.2 Web Search: needed when current official guidance / policy."""


_CALCULATOR_MARKERS: tuple[str, ...] = (
    "评分", "分级", "评分系统", "score", "grading", "grade",
    "CHA2DS2", "CHA₂DS₂", "MELD", "APACHE", "GCS", "NIHSS",
    "CURB-65", "PSI", "Wells", "BMI", "肌酐清除率", "Ccr",
)
"""Per §6.2 Medical Calculator: needed when a deterministic clinical score is required."""


_CALCULATOR_PARAM_HINTS: tuple[str, ...] = (
    "mmHg", "kpa", "mg/dL", "g/L", "mmol", "mg/", "次/分", "bpm",
    "℃", "°C", "kg", "cm", "身高", "体重", "血压", "脉搏", "呼吸",
    "肌酐", "钠", "钾", "钙", "血红蛋白", "白蛋白", "胆红素",
)
"""Concrete numeric/vital-sign tokens that indicate calculator parameters exist in the chart."""


# ---------------------------------------------------------------------------
# Per-Expert routing
# ---------------------------------------------------------------------------


def _has_any_marker(text: str, markers: tuple[str, ...]) -> tuple[bool, str]:
    """Return ``(found, matched_marker)`` — case-insensitive substring scan."""
    low = text.lower()
    for m in markers:
        if m.lower() in low:
            return True, m
    return False, ""


def _case_text(case: CDICase) -> str:
    """Concatenate chart + gap descriptions into a single scan string."""
    parts: list[str] = [case.chart_excerpt or ""]
    for g in case.documentation_gaps:
        parts.append(g.description or "")
        parts.append(g.why_it_matters or "")
    return " ".join(parts)


def _route_coding_expert(
    case: CDICase, *, available_tools: dict[str, bool]
) -> ExpertRouteDecision:
    if not _chart_has_substrate(case.chart_excerpt):
        return ExpertRouteDecision(
            expert_id="coding-expert",
            needed=False,
            reason="empty_chart",
            execution_mode="SKIPPED_NOT_NEEDED",
            expected_value="empty chart — no coding substrate",
        )
    relevant_gaps = [
        g for g in case.documentation_gaps
        if g.gap_type in _CODING_RELEVANT_GAP_TYPES
    ]
    if not relevant_gaps:
        return ExpertRouteDecision(
            expert_id="coding-expert",
            needed=False,
            reason="no_relevant_gap",
            execution_mode="SKIPPED_NOT_NEEDED",
            expected_value="no coding-relevant gaps survived earlier gates",
        )
    if available_tools.get("coding-expert", False):
        return ExpertRouteDecision(
            expert_id="coding-expert",
            needed=True,
            reason="real_tool_wired",
            required_inputs=["documentation_gaps", "chart_excerpt"],
            available_inputs=["documentation_gaps", "chart_excerpt"],
            execution_mode="REAL_TOOL",
            priority="high",
            expected_value="specificity required for accurate coding",
        )
    return ExpertRouteDecision(
        expert_id="coding-expert",
        needed=True,
        reason="coding_relevant_gap",
        required_inputs=["documentation_gaps", "chart_excerpt"],
        available_inputs=["documentation_gaps", "chart_excerpt"],
        execution_mode="LLM_KNOWLEDGE_ONLY",
        priority="high",
        expected_value="specificity required for accurate coding (LLM knowledge; not a code lookup)",
    )


def _route_pubmed_expert(
    case: CDICase, *, available_tools: dict[str, bool]
) -> ExpertRouteDecision:
    if not _chart_has_substrate(case.chart_excerpt):
        return ExpertRouteDecision(
            expert_id="pubmed-expert",
            needed=False,
            reason="empty_chart",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    text = _case_text(case)
    found, marker = _has_any_marker(text, _PUBMED_MARKERS)
    if not found:
        return ExpertRouteDecision(
            expert_id="pubmed-expert",
            needed=False,
            reason="no_relevant_gap",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    if available_tools.get("pubmed-expert", False):
        return ExpertRouteDecision(
            expert_id="pubmed-expert",
            needed=True,
            reason="real_tool_wired",
            required_inputs=["clinical_question", "chart_excerpt"],
            available_inputs=["chart_excerpt"],
            execution_mode="REAL_TOOL",
            priority="medium",
            expected_value=f"literature support for '{marker}'",
        )
    return ExpertRouteDecision(
        expert_id="pubmed-expert",
        needed=True,
        reason="criteria_marker_present",
        required_inputs=["clinical_question"],
        available_inputs=["chart_excerpt"],
        missing_inputs=["real_pubmed_search"],
        execution_mode="LLM_KNOWLEDGE_ONLY",
        priority="medium",
        expected_value=f"criteria/definition recall for '{marker}' (no real PubMed search wired)",
    )


def _route_web_search_expert(
    case: CDICase, *, available_tools: dict[str, bool]
) -> ExpertRouteDecision:
    if not _chart_has_substrate(case.chart_excerpt):
        return ExpertRouteDecision(
            expert_id="web-search-expert",
            needed=False,
            reason="empty_chart",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    text = _case_text(case)
    found, marker = _has_any_marker(text, _WEB_MARKERS)
    if not found:
        return ExpertRouteDecision(
            expert_id="web-search-expert",
            needed=False,
            reason="no_relevant_gap",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    if available_tools.get("web-search-expert", False):
        return ExpertRouteDecision(
            expert_id="web-search-expert",
            needed=True,
            reason="real_tool_wired",
            required_inputs=["clinical_question"],
            available_inputs=["chart_excerpt"],
            execution_mode="REAL_TOOL",
            priority="medium",
            expected_value=f"current guidance for '{marker}'",
        )
    # §6.2: "没有真实 Web 工具时, 必须跳过或标记 TOOL_UNAVAILABLE."
    # We mark TOOL_UNAVAILABLE rather than LLM_KNOWLEDGE_ONLY because
    # guideline knowledge has time-sensitivity that LLM training data
    # cannot honestly represent.
    return ExpertRouteDecision(
        expert_id="web-search-expert",
        needed=True,
        reason="no_real_tool_wired",
        required_inputs=["clinical_question", "current_date"],
        available_inputs=["chart_excerpt"],
        missing_inputs=["real_web_search"],
        execution_mode="TOOL_UNAVAILABLE",
        priority="medium",
        expected_value=f"current guidance for '{marker}' — unavailable without real web tool",
    )


def _route_medical_calculator_expert(
    case: CDICase, *, available_tools: dict[str, bool]
) -> ExpertRouteDecision:
    if not _chart_has_substrate(case.chart_excerpt):
        return ExpertRouteDecision(
            expert_id="medical-calculator-expert",
            needed=False,
            reason="empty_chart",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    text = _case_text(case)
    found, marker = _has_any_marker(text, _CALCULATOR_MARKERS)
    if not found:
        return ExpertRouteDecision(
            expert_id="medical-calculator-expert",
            needed=False,
            reason="no_relevant_gap",
            execution_mode="SKIPPED_NOT_NEEDED",
        )
    # Calculator needs parameters — check the chart for numeric/vital hints.
    has_params, param_hit = _has_any_marker(case.chart_excerpt, _CALCULATOR_PARAM_HINTS)
    if not has_params:
        return ExpertRouteDecision(
            expert_id="medical-calculator-expert",
            needed=True,
            reason="calculator_params_missing",
            required_inputs=["score_name", "clinical_parameters"],
            available_inputs=["chart_excerpt"],
            missing_inputs=["clinical_parameters"],
            execution_mode="SKIPPED_MISSING_INPUTS",
            priority="medium",
            expected_value=f"'{marker}' score — parameters absent from chart",
        )
    if available_tools.get("medical-calculator-expert", False):
        return ExpertRouteDecision(
            expert_id="medical-calculator-expert",
            needed=True,
            reason="real_tool_wired",
            required_inputs=["score_name", "clinical_parameters"],
            available_inputs=["chart_excerpt", "clinical_parameters"],
            execution_mode="REAL_TOOL",
            priority="medium",
            expected_value=f"'{marker}' score via deterministic calculator",
        )
    # §6.2: "不得用普通 LLM 猜测评分". Without a real calculator tool we
    # must NOT fall back to LLM_KNOWLEDGE_ONLY for a numeric score.
    return ExpertRouteDecision(
        expert_id="medical-calculator-expert",
        needed=True,
        reason="no_real_tool_wired",
        required_inputs=["score_name", "clinical_parameters", "deterministic_formula"],
        available_inputs=["chart_excerpt"],
        missing_inputs=["deterministic_formula"],
        execution_mode="TOOL_UNAVAILABLE",
        priority="medium",
        expected_value=f"'{marker}' score — no deterministic calculator wired",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def route_experts(
    case: CDICase,
    *,
    available_tools: dict[str, bool] | None = None,
) -> ExpertRouteResult:
    """Route all 4 Experts for ``case``. Pure-logic — no LLM calls.

    ``available_tools`` lets callers advertise real MCP tool wiring.
    Defaults to all-False (Phase 5 Track D P0.5 has no real Expert tools).

    Returns one ``ExpertRouteDecision`` per Expert in declaration order.
    """
    tools = {**_DEFAULT_AVAILABLE_TOOLS, **(available_tools or {})}
    decisions: list[ExpertRouteDecision] = [
        _route_coding_expert(case, available_tools=tools),
        _route_pubmed_expert(case, available_tools=tools),
        _route_web_search_expert(case, available_tools=tools),
        _route_medical_calculator_expert(case, available_tools=tools),
    ]
    return ExpertRouteResult(decisions=decisions)


def should_invoke(decision: ExpertRouteDecision) -> bool:
    """Runner-side predicate: should the LLM/tool actually be called?"""
    return decision.execution_mode in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY")


__all__ = [
    "ExpertExecutionMode",
    "ExpertId",
    "ExpertRouteDecision",
    "ExpertRouteResult",
    "RouteReason",
    "route_experts",
    "should_invoke",
]
