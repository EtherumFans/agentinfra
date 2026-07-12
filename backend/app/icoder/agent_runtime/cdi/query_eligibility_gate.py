"""Phase 5 Track H3.5 — Query Eligibility Gate.

PDF §3.2 + Master Task Track H3.5 — A Provider Query is ELIGIBLE only if
the chart has a real documentation gap that this query can address. On
charts where the documentation is already complete (type/site/severity/
etiology/procedure/pathology/complications/course all explicit), all
candidate queries are spurious and must be dropped before necessity/CEA
gates waste work on them.

This gate sits between query_generation and query_necessity_gate. It
implements two checks:

1. **Chart-completeness signal** (case-level):
   Detect whether the chart has the 8 explicit documentation dimensions
   that make a CDI query unnecessary in aggregate. If ≥6 of 8 dimensions
   are explicit AND no real ambiguity markers (可疑/疑似/可能/不排除),
   the case is marked CHART_COMPLETE and ALL queries are dropped.

2. **Per-query topic-gap relevance** (query-level):
   For each surviving query, check whether its topic intersects any
   documentation_gap identified by gap_identification. Queries with no
   matching gap are dropped as off-topic.

Eight documentation dimensions
==============================

  D1  type            急/慢/亚急性 + 类型 (e.g. 急性化脓性)
  D2  site            解剖部位 (e.g. 阑尾, 下壁)
  D3  severity        轻度/中度/重度 or 范围 (e.g. 局限性)
  D4  etiology        病因 (e.g. 链球菌感染, 接触史)
  D5  procedure       手术/操作 (e.g. 腹腔镜阑尾切除术)
  D6  pathology       病理确诊 (e.g. 病理:急性化脓性)
  D7  complications   并发症 (e.g. 无 / 局限性腹膜炎)
  D8  course          病程/出院 (e.g. 3天出院, 治愈)

Ambiguity markers
=================

  可疑 疑似 可能 不排除 考虑 倾向 提示 待排除 待查
  suspected probable likely possible
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.icoder.agent_runtime.cdi.domain import CDICase, ProviderQuery


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EligibilityRuleResult:
    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    severity: Literal["hard", "soft"] = "hard"


@dataclass
class QueryEligibilityResult:
    verdict: Literal["ELIGIBLE", "INELIGIBLE"]
    rules_evaluated: int
    rules_passed: int
    rules_failed: list[EligibilityRuleResult] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    chart_completeness_score: float = 0.0  # 0..1, dimensions detected / 8


@dataclass
class CaseEligibilityResult:
    per_query: dict[str, QueryEligibilityResult] = field(default_factory=dict)
    chart_complete: bool = False
    chart_completeness_score: float = 0.0
    dimensions_detected: dict[str, bool] = field(default_factory=dict)
    dropped_count: int = 0


# ---------------------------------------------------------------------------
# Documentation dimension patterns
# ---------------------------------------------------------------------------

# D1 — type markers. Need explicit acute/chronic + subtype.
_D1_TYPE_PATTERNS = [
    r"急性[^,。、\s]{0,8}(?:化脓性|链球菌|卡他性|单纯性|坏疽性|穿孔性|浆液性|纤维素性)",
    r"慢性[^,。、\s]{0,8}(?:阻塞性|肺疾病|肾脏病|心力衰竭|炎症|炎症性)",
    r"亚急性[^,。、\s]{0,8}(?:感染|心内膜炎|脑膜炎)",
    r"acute[^,.\s]{0,15}(?:suppurative|streptococcal|catarrhal|simple|gangrenous)",
    r"chronic[^,.\s]{0,15}(?:obstructive|kidney|heart|inflammation)",
]

# D2 — site markers. Anatomical location must be explicit.
_D2_SITE_KEYWORDS = (
    "阑尾", "心肌", "心包", "心房", "心室", "肺炎", "肺", "肝", "胆", "胰腺",
    "肾", "胃肠", "胃", "肠", "脑", "脑膜", "胸膜", "腹膜", "皮肤", "关节",
    "前壁", "下壁", "侧壁", "前间壁", "右心", "左心", "二尖瓣", "主动脉瓣",
    "appendix", "myocard", "periocard", "atrium", "ventricle", "liver",
    "gallbladder", "pancrea", "kidney", "gastric", "intestinal",
)

# D3 — severity markers.
_D3_SEVERITY_PATTERNS = [
    r"轻度|中度|重度|危重|极重",
    r"局限性|弥漫性|广泛性",
    r"mild|moderate|severe|critical",
    r"NYHA\s*[IiＩ]{1,4}|NYHA\s*[1-4]级",
    r"Killip\s*[IiＩ]{1,4}|Killip\s*[1-4]级",
    r"[IiＩ]{1,4}\s*级|[1-4]\s*级",
]

# D4 — etiology markers.
_D4_ETIOLOGY_PATTERNS = [
    r"(?:感染|接触史|传染源|流行病学)",
    r"(?:链球菌|葡萄球菌|大肠杆菌|克雷伯|铜绿|支原体|衣原体|病毒|真菌)",
    r"(?:培养|检出|阳性).{0,15}(?:链球菌|葡萄球菌|大肠杆菌|克雷伯|铜绿)",
    r"(?:病因|诱因).{0,30}(?:明确|确诊|检出)",
    r"etiology|pathogen|cause",
]

# D5 — procedure markers.
_D5_PROCEDURE_PATTERNS = [
    r"(?:腹腔镜|开腹|经皮|内镜).{0,10}(?:切除|摘除|吻合|造瘘|修补)",
    r"(?:PCI|介入|支架植入|球囊扩张|消融|起搏器)",
    r"(?:手术|操作).{0,15}(?:成功|完成|顺利)",
    r"(?:阑尾切除|胆囊切除|胃肠切除|肝切除)",
    r"(?:术后|围术期|术中)",
    r"PCI|stent|ablation|pacemaker|surgery|operation",
]

# D6 — pathology markers.
_D6_PATHOLOGY_PATTERNS = [
    r"病理(?:报告|结果|确诊|诊断)?[:：].{0,30}(?:急性|慢性|恶性|良性|炎症|癌|瘤)",
    r"(?:活检|穿刺|切除).{0,15}(?:病理|镜下|组织学)",
    r"pathology|biopsy|histolog",
]

# D7 — complications markers.
_D7_COMPLICATIONS_PATTERNS = [
    r"并发症[:：].{0,15}(?:无|未见|未发生|none)",
    r"(?:局限性|弥漫性).{0,5}腹膜炎",
    r"(?:胸腔积液|腹腔脓肿|吻合口瘘|出血|感染|败血症)",
    r"无.{0,5}(?:并发症|后遗症|不良反应)",
    r"complications?[:：].{0,15}(?:none|no|absent)",
]

# D8 — course / disposition markers.
_D8_COURSE_PATTERNS = [
    r"(?:治愈|好转|稳定|出院|转出|死亡)",
    r"\d+\s*[天日周]\s*(?:出院|好转|治愈|住院|病程)",
    r"(?:住院|就诊|入院).{0,10}\d+\s*[天日]",
    r"discharge|course|recovery",
]

_DIMENSION_PATTERNS: dict[str, list[str]] = {
    "D1_type": _D1_TYPE_PATTERNS,
    "D2_site": [],  # keyword-based, see _check_d2
    "D3_severity": _D3_SEVERITY_PATTERNS,
    "D4_etiology": _D4_ETIOLOGY_PATTERNS,
    "D5_procedure": _D5_PROCEDURE_PATTERNS,
    "D6_pathology": _D6_PATHOLOGY_PATTERNS,
    "D7_complications": _D7_COMPLICATIONS_PATTERNS,
    "D8_course": _D8_COURSE_PATTERNS,
}

# Ambiguity markers — if present, chart is NOT complete regardless of dimensions
_AMBIGUITY_MARKERS = (
    "可疑", "疑似", "可能", "不排除", "考虑", "倾向", "提示",
    "待排除", "待查", "未明确", "未确定", "未分级", "未分期",
    "suspected", "probable", "likely", "possible", "cannot rule out",
)

# Threshold: how many of 8 dimensions must be explicit for chart_complete
_COMPLETENESS_THRESHOLD = 6


# ---------------------------------------------------------------------------
# Dimension detection
# ---------------------------------------------------------------------------


def _check_dimension(dim_name: str, chart: str) -> bool:
    """Return True if the chart explicitly documents this dimension."""
    chart_low = chart.lower()
    if dim_name == "D2_site":
        return any(kw.lower() in chart_low for kw in _D2_SITE_KEYWORDS)
    patterns = _DIMENSION_PATTERNS.get(dim_name, [])
    return any(re.search(p, chart, flags=re.IGNORECASE) for p in patterns)


def _has_ambiguity(chart: str) -> tuple[bool, str]:
    """Return (has_ambiguity, marker_found)."""
    chart_low = chart.lower()
    for m in _AMBIGUITY_MARKERS:
        if m.lower() in chart_low:
            return True, m
    return False, ""


def detect_chart_completeness(chart: str) -> tuple[float, dict[str, bool], bool]:
    """Compute chart completeness score.

    Returns:
      (score, dimensions_detected, chart_complete)

      score           — fraction of dimensions detected (0.0..1.0)
      dimensions      — per-dimension detection map
      chart_complete  — True iff score*8 ≥ threshold AND no ambiguity
    """
    if not chart or len(chart) < 50:
        return (0.0, {}, False)

    dims: dict[str, bool] = {}
    for dim in _DIMENSION_PATTERNS:
        dims[dim] = _check_dimension(dim, chart)

    explicit_count = sum(1 for v in dims.values() if v)
    score = explicit_count / len(_DIMENSION_PATTERNS)

    has_amb, _ = _has_ambiguity(chart)
    chart_complete = (explicit_count >= _COMPLETENESS_THRESHOLD) and not has_amb
    return (score, dims, chart_complete)


def _case_has_contradiction(case: CDICase) -> bool:
    """Track H3.10 — detect document_conflict via risk_flags.

    When the case carries a ``contradiction`` risk_flag, the chart has
    an internal conflict that needs clarification — even if all 8
    dimensions are explicit. The eligibility gate must NOT mark such
    charts as complete.
    """
    for flag in case.risk_flags or []:
        if flag.category == "contradiction":
            return True
    return False


# ---------------------------------------------------------------------------
# Per-query topic-gap relevance
# ---------------------------------------------------------------------------


def _query_topic_matches_gap(query: ProviderQuery, case: CDICase) -> bool:
    """Check whether the query's topic intersects any gap in the case."""
    topic = (query.topic or "").strip()
    qtext = (query.query_text or "").strip()
    if not topic and not qtext:
        return False

    for gap in case.documentation_gaps:
        gap_desc = (gap.description or "").strip()
        gap_clar = (gap.minimal_clarification_needed or "").strip()
        gap_text_combined = f"{gap_desc} {gap_clar}"

        # Direct gap_id linkage
        if query.gap_id and query.gap_id == gap.gap_id:
            return True

        # Topic overlap: substring match in either direction (handles short topics)
        if topic and (
            topic in gap_desc
            or topic in gap_clar
            or any(kw in gap_text_combined for kw in topic.split() if len(kw) >= 2)
        ):
            return True

        # Query-text ↔ gap-desc overlap on tokens ≥2 chars
        q_tokens = {t for t in qtext.split() if len(t) >= 2}
        g_tokens = {t for t in gap_desc.split() if len(t) >= 2}
        if q_tokens and g_tokens and (q_tokens & g_tokens):
            return True

    return False


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def evaluate_query_eligibility(
    query: ProviderQuery,
    *,
    chart: str,
    case: CDICase,
    chart_complete: bool,
) -> QueryEligibilityResult:
    """Run eligibility checks on a single query.

    Verdict:
      ELIGIBLE   — query proceeds to necessity gate
      INELIGIBLE — query dropped before necessity
    """
    rules: list[EligibilityRuleResult] = []

    # QE-001 — chart_completeness_drops_all
    if chart_complete:
        rules.append(EligibilityRuleResult(
            rule_id="QE-001",
            name="chart_completeness_drops_all",
            description="Chart documents ≥6/8 dimensions; queries are spurious",
            passed=False,
            evidence=f"chart_completeness_score≥{_COMPLETENESS_THRESHOLD}/8 and no ambiguity",
            severity="hard",
        ))
    else:
        rules.append(EligibilityRuleResult(
            rule_id="QE-001",
            name="chart_completeness_drops_all",
            description="Chart documents ≥6/8 dimensions; queries are spurious",
            passed=True,
            evidence="chart not marked complete",
            severity="hard",
        ))

    # QE-002 — query_topic_has_matching_gap
    has_gap = _query_topic_matches_gap(query, case)
    rules.append(EligibilityRuleResult(
        rule_id="QE-002",
        name="query_topic_has_matching_gap",
        description="Query topic must intersect a documentation_gap",
        passed=has_gap,
        evidence=(
            f"query topic='{(query.topic or '')[:40]}' matches gap_id={query.gap_id}"
            if has_gap
            else f"query topic='{(query.topic or '')[:40]}' has no matching gap"
        ),
        severity="hard",
    ))

    hard_fails = [r for r in rules if not r.passed and r.severity == "hard"]
    score, _, _ = detect_chart_completeness(chart)

    if hard_fails:
        return QueryEligibilityResult(
            verdict="INELIGIBLE",
            rules_evaluated=len(rules),
            rules_passed=len(rules) - len(hard_fails),
            rules_failed=rules,
            drop_reasons=[f"{r.rule_id}: {r.evidence}" for r in hard_fails],
            chart_completeness_score=score,
        )
    return QueryEligibilityResult(
        verdict="ELIGIBLE",
        rules_evaluated=len(rules),
        rules_passed=len(rules),
        rules_failed=rules,
        chart_completeness_score=score,
    )


def evaluate_case_eligibility(case: CDICase) -> CaseEligibilityResult:
    """Side-effect-free evaluation across all queries in the case."""
    score, dims, complete = detect_chart_completeness(case.chart_excerpt)
    # Track H3.10 — if the case has a contradiction risk_flag, the chart
    # is NOT complete regardless of dimension count: a conflict needs
    # clarification. Override chart_complete to False so queries survive.
    has_contradiction = _case_has_contradiction(case)
    if has_contradiction and complete:
        complete = False
    result = CaseEligibilityResult(
        chart_complete=complete,
        chart_completeness_score=score,
        dimensions_detected=dims,
    )
    for q in case.proposed_provider_queries:
        result.per_query[q.query_id] = evaluate_query_eligibility(
            q,
            chart=case.chart_excerpt,
            case=case,
            chart_complete=complete,
        )
    return result


def apply_eligibility_to_case(case: CDICase) -> CaseEligibilityResult:
    """Evaluate AND drop INELIGIBLE queries from the case.

    Mutates ``case.proposed_provider_queries`` in place.
    """
    result = evaluate_case_eligibility(case)
    survivors: list[ProviderQuery] = []
    for q in case.proposed_provider_queries:
        verdict = result.per_query.get(q.query_id)
        if verdict is None or verdict.verdict != "INELIGIBLE":
            survivors.append(q)
    result.dropped_count = len(case.proposed_provider_queries) - len(survivors)
    case.proposed_provider_queries = survivors
    return result


__all__ = [
    "EligibilityRuleResult",
    "QueryEligibilityResult",
    "CaseEligibilityResult",
    "detect_chart_completeness",
    "evaluate_query_eligibility",
    "evaluate_case_eligibility",
    "apply_eligibility_to_case",
]
