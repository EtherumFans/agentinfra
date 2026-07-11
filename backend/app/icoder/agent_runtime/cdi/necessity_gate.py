"""Phase 5 Track D P0.5 Gate 2 — Query Necessity Gate.

PDF §3.2 — a Provider Query is *necessary* if and only if:

  (a) the chart evidence is genuinely insufficient to answer the
      documentation question (real gap), AND
  (b) the clinician's answer would actually change the documented
      record or downstream coding (documentation impact).

Unnecessary queries violate PDF §4.3 ("CDI must not generate
diagnoses") by asking the clinician to invent content the chart never
supported. They also inflate chart-review workload without improving
coding accuracy.

Five-dimension evaluation (NQ-001..NQ-005):

  NQ-001  evidence_sufficiency    Is chart evidence really insufficient?
                                  Hard-fail if the chart already answers.
  NQ-002  clinical_relevance     Would the answer affect care or coding?
                                  Soft-fail if topic is purely academic.
  NQ-003  answerability           Can a clinician realistically answer?
                                  Soft-fail if question asks for info the
                                  clinician cannot know at this visit.
  NQ-004  documentation_impact   Would the answer change the record?
                                  Soft-fail if the chart already documents
                                  the topic at the level the query seeks.
  NQ-005  redundancy_risk         Is this query redundant with another in
                                  the same case? Hard-fail on duplicate.

Per-case over-query guard (NQ-006, separate from per-query rules):
  NQ-006  overquery_per_case      If the case produced ≥5 queries, the
                                  case is flagged for over-query review.
                                  (Does not block — but tags the case.)

Implementation strategy
=======================

Rules NQ-001..NQ-005 are pure-regex / lexical where possible. A
separate semantic reviewer (``necessity_semantic.py``) provides
LLM-based judgment for ambiguous cases; on provider failure it
returns DEGRADED (does not block — same pattern as NLQ semantic).

The gate runs in the orchestrator AFTER query_generation and BEFORE
query_compliance_gate (NLQ). Unnecessary queries are dropped from
``case.proposed_provider_queries`` before NLQ sees them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.icoder.agent_runtime.cdi.domain import CDICase, ProviderQuery


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NecessityRuleResult:
    """Outcome of one NQ-XXX rule on a single query."""
    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    severity: Literal["hard", "soft"] = "hard"  # hard = drop, soft = flag


@dataclass
class NecessityGateResult:
    """Aggregate outcome for all 5 rules on a single query."""
    verdict: Literal["NECESSARY", "UNNECESSARY", "DEGRADED"]
    rules_evaluated: int
    rules_passed: int
    rules_failed: list[NecessityRuleResult] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    flag_reasons: list[str] = field(default_factory=list)


@dataclass
class CaseNecessityResult:
    """Per-case aggregate including the over-query guard NQ-006."""
    per_query: dict[str, NecessityGateResult] = field(default_factory=dict)
    overquery_triggered: bool = False
    overquery_count: int = 0
    overquery_threshold: int = 4  # cases with ≥5 queries are flagged


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# NQ-001 — chart-already-answers heuristics. If the topic phrase already
# appears verbatim in the chart with a value, the query is unnecessary.
_CHART_ANSWERS_PATTERNS = [
    # 体温/血压 already numeric → severity graded
    (r"体温\s*[Tt]?\s*[\d.]+\s*[°℃C]", "体温值已记录"),
    (r"血压\s*(BP)?\s*\d+\s*/\s*\d+\s*mm?Hg", "血压值已记录"),
    (r"糖化血红蛋白\s*\(HbA1c\)\s*[\d.]+\s*%", "HbA1c已记录"),
    # Diagnosis with explicit type/site/severity already specified
    (r"急性[^,。、\s]{0,8}(?:心肌梗死|阑尾炎|胆囊炎|胰腺炎|肺炎|胃肠炎)", "急性类型已明确"),
    (r"慢性[^,。、\s]{0,8}(?:阻塞性肺疾病|肺疾病|肾脏病|心力衰竭)", "慢性类型已明确"),
    (r"(?:前壁|下壁|侧壁|前间壁)ST段抬高", "部位已明确"),
    #PCI/手术 explicit
    (r"PCI.*植入.*支架", "PCI 手术细节已记录"),
    (r"腹腔镜.*切除", "腹腔镜手术已记录"),
]

# NQ-003 — unanswerable patterns (clinician cannot know)
_UNANSWERABLE_PATTERNS = [
    r"未来.{0,8}预后",
    r"预后.{0,8}预测",
    r"假如.{0,8}如果.{0,8}是否",
    r"如果.{0,8}病程.{0,8}变化",
]

# NQ-005 — redundancy: queries with identical topic are duplicates
# (Match is done at the case level, not pattern level.)


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _check_chart_already_answers(query: ProviderQuery, chart: str) -> tuple[bool, str]:
    """Return (matches, evidence) if chart already answers the query."""
    topic = query.topic or ""
    for pat, label in _CHART_ANSWERS_PATTERNS:
        if not re.search(pat, chart, flags=re.IGNORECASE):
            continue
        # Only flag if the query topic is what the chart pattern answers.
        if "体温值" in label and any(k in topic for k in ["体温", "发热程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "血压值" in label and "血压" in topic:
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "HbA1c" in label and any(k in topic for k in ["HbA1c", "糖化", "血糖控制"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "急性类型" in label and any(k in topic for k in ["类型", "急慢性", "病程", "严重程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "慢性类型" in label and any(k in topic for k in ["类型", "急慢性", "病程", "严重程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "部位已明确" in label and any(k in topic for k in ["部位", "具体位置", "解剖"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "PCI" in label and any(k in topic for k in ["支架", "PCI", "手术细节", "支架类型"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "腹腔镜" in label and any(k in topic for k in ["手术方式", "腹腔镜", "术式"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
    return False, ""


def _rule_nq_001(query: ProviderQuery, chart: str) -> NecessityRuleResult:
    matched, evidence = _check_chart_already_answers(query, chart)
    return NecessityRuleResult(
        rule_id="NQ-001",
        name="evidence_sufficiency",
        description="Chart already contains the requested information",
        passed=not matched,
        evidence=evidence,
        severity="hard",
    )


def _rule_nq_002(query: ProviderQuery) -> NecessityRuleResult:
    """Clinical relevance — drop pure-academic or family-history-only queries."""
    # Family-history-only topic is not clinically actionable for THIS patient
    fam_only = re.search(r"家族史.*具体类型|父亲.*糖尿病.*类型|母亲.*高血压.*类型",
                         query.query_text + query.topic, flags=re.IGNORECASE)
    if fam_only:
        return NecessityRuleResult(
            rule_id="NQ-002",
            name="clinical_relevance",
            description="Family-history-only detail does not change THIS patient's documentation",
            passed=False,
            evidence=f"family-history-only: '{fam_only.group(0)}'",
            severity="soft",
        )
    return NecessityRuleResult(
        rule_id="NQ-002",
        name="clinical_relevance",
        description="Family-history-only detail does not change THIS patient's documentation",
        passed=True,
        evidence="topic is clinically actionable",
        severity="soft",
    )


def _rule_nq_003(query: ProviderQuery) -> NecessityRuleResult:
    """Answerability — drop queries no clinician can answer at this visit."""
    for pat in _UNANSWERABLE_PATTERNS:
        m = re.search(pat, query.query_text, flags=re.IGNORECASE)
        if m:
            return NecessityRuleResult(
                rule_id="NQ-003",
                name="answerability",
                description="Query asks for prognosis / hypothetical the clinician cannot answer",
                passed=False,
                evidence=f"matched /{pat}/ : '{m.group(0)}'",
                severity="soft",
            )
    return NecessityRuleResult(
        rule_id="NQ-003",
        name="answerability",
        description="Query asks for prognosis / hypothetical the clinician cannot answer",
        passed=True,
        evidence="answerable",
        severity="soft",
    )


def _rule_nq_004(query: ProviderQuery, chart: str) -> NecessityRuleResult:
    """Documentation impact — drop queries whose answer is already in chart at the requested level."""
    # If chart has "肺炎链球菌" and query asks for "病原体" → already documented
    if "病原体" in query.topic or "病原学" in query.topic:
        if re.search(r"(?:培养|阳性|检出).{0,15}(?:链球菌|葡萄球菌|大肠杆菌|克雷伯|铜绿)",
                     chart, flags=re.IGNORECASE):
            return NecessityRuleResult(
                rule_id="NQ-004",
                name="documentation_impact",
                description="Chart already documents pathogen culture result",
                passed=False,
                evidence="culture result present in chart",
                severity="hard",
            )
    return NecessityRuleResult(
        rule_id="NQ-004",
        name="documentation_impact",
        description="Chart already documents pathogen culture result",
        passed=True,
        evidence="topic is not redundant with existing documentation",
        severity="hard",
    )


def _rule_nq_005(query: ProviderQuery, all_queries: list[ProviderQuery]) -> NecessityRuleResult:
    """Redundancy — keep the FIRST query per topic; mark duplicates redundant.

    A query is redundant if another query with the same topic appears
    earlier in the case list (i.e. there exists an earlier q whose
    topic equals this query's topic). The first occurrence passes.
    """
    for earlier in all_queries:
        if earlier is query:
            break  # query is the first occurrence — pass
        if earlier.topic == query.topic:
            return NecessityRuleResult(
                rule_id="NQ-005",
                name="redundancy_risk",
                description="Another earlier query in this case has the same topic",
                passed=False,
                evidence=f"earlier query '{earlier.query_id}' already asks topic='{query.topic}'",
                severity="hard",
            )
    return NecessityRuleResult(
        rule_id="NQ-005",
        name="redundancy_risk",
        description="Another earlier query in this case has the same topic",
        passed=True,
        evidence="topic is unique among earlier queries",
        severity="hard",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_necessity(
    query: ProviderQuery,
    *,
    chart: str,
    all_queries: list[ProviderQuery],
) -> NecessityGateResult:
    """Run NQ-001..NQ-005 on a single query.

    Returns verdict:
      - NECESSARY   — no hard-fail; query survives
      - UNNECESSARY — at least one hard-fail; query should be dropped
      - DEGRADED    — provider/reviewer unavailable; default to NECESSARY
                      (do not block on degraded necessity)
    """
    rules: list[NecessityRuleResult] = [
        _rule_nq_001(query, chart),
        _rule_nq_002(query),
        _rule_nq_003(query),
        _rule_nq_004(query, chart),
        _rule_nq_005(query, all_queries),
    ]

    hard_fails = [r for r in rules if not r.passed and r.severity == "hard"]
    soft_fails = [r for r in rules if not r.passed and r.severity == "soft"]

    if hard_fails:
        return NecessityGateResult(
            verdict="UNNECESSARY",
            rules_evaluated=len(rules),
            rules_passed=len(rules) - len(hard_fails) - len(soft_fails),
            rules_failed=rules,
            drop_reasons=[f"{r.rule_id}: {r.evidence}" for r in hard_fails],
            flag_reasons=[f"{r.rule_id}: {r.evidence}" for r in soft_fails],
        )
    return NecessityGateResult(
        verdict="NECESSARY",
        rules_evaluated=len(rules),
        rules_passed=len(rules) - len(soft_fails),
        rules_failed=rules,
        drop_reasons=[],
        flag_reasons=[f"{r.rule_id}: {r.evidence}" for r in soft_fails],
    )


def evaluate_case_necessity(case: CDICase) -> CaseNecessityResult:
    """Run necessity evaluation on every query in the case + over-query guard.

    Side-effect-free — does NOT mutate ``case.proposed_provider_queries``.
    Caller (orchestrator) decides whether to drop queries based on verdicts.
    """
    result = CaseNecessityResult()
    queries = list(case.proposed_provider_queries)
    for q in queries:
        result.per_query[q.query_id] = evaluate_necessity(
            q,
            chart=case.chart_excerpt,
            all_queries=queries,
        )

    # NQ-006 — over-query per case
    result.overquery_count = len(queries)
    result.overquery_triggered = len(queries) > result.overquery_threshold
    return result


def apply_necessity_to_case(case: CDICase) -> CaseNecessityResult:
    """Evaluate necessity AND drop UNNECESSARY queries from the case.

    This is the orchestrator-friendly entry point — it mutates
    ``case.proposed_provider_queries`` in place by removing queries
    that hard-failed NQ-001, NQ-004, or NQ-005.

    Returns the full evaluation result (including soft-fails) for
    traceability; the dropped queries are recorded in the result.
    """
    result = evaluate_case_necessity(case)
    survivors: list[ProviderQuery] = []
    for q in case.proposed_provider_queries:
        verdict = result.per_query.get(q.query_id)
        if verdict is None or verdict.verdict != "UNNECESSARY":
            survivors.append(q)
    case.proposed_provider_queries = survivors
    return result


__all__ = [
    "NecessityRuleResult",
    "NecessityGateResult",
    "CaseNecessityResult",
    "evaluate_necessity",
    "evaluate_case_necessity",
    "apply_necessity_to_case",
]
