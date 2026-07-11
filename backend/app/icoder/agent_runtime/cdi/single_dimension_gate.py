"""Phase 5 Track D P0.5 Gate 3 — Single-Dimension Query Gate.

PDF §3.2 (R6) — a Provider Query is *single-dimension* if it asks about
exactly ONE clinical axis. Queries that pack multiple orthogonal axes
into one sentence violate the contract because:

  (a) the clinician cannot answer cleanly (a 2-axis query forces a
      compound answer, defeating the response_options taxonomy);
  (b) downstream coding cannot consume the answer unambiguously;
  (c) NLQ-005 escape hatch becomes meaningless when 2 questions are
      crammed together — the clinician may be certain about one axis
      and uncertain about the other.

The gate uses **multi-label axis detection**: scan topic + query_text
for keywords from each axis, and drop queries that touch ≥2 different
axes. Axis membership is intentionally permissive (false-negative averse);
false positives are reduced by requiring the keywords to come from
*different* axes, not the same axis twice.

Axis taxonomy (extends ``_GAP_TYPE_KEYWORDS`` from ``domain.py``):

    type         类型 / 分型 / 病理分型 / 性质
    etiology     病因 / 病原体 / 原因 / 诱因
    severity     严重程度 / 分级 / 分期 / GOLD / Killip
    acuity       急慢性 / 急性或慢性 / 新鲜 / 陈旧
    site         部位 / 侧别 / 解剖部位 / 位置 / 肺叶
    course       病程 / 起病 / 持续时间 / 发病时间
    complication 并发症 / 合并症
    count        数量 / 数目 / 几处
    correlation  关联 / 相关性

Notes:
  - ``分级`` and ``分期`` BOTH map to ``severity`` (same axis, different
    facets). This makes "分级或分期" single-axis → PASS.
  - ``correlation`` is its own single axis. A query like "头晕与高血压
    的关联" is single-dim even though the word 与 appears, because the
    conjunction joins two clinical entities, not two axis keywords.

Three rules:

  SD-001  topic_multi_axis        Hard-fail if topic keywords span ≥2 axes
  SD-002  text_multi_axis         Hard-fail if query_text keywords span
                                  ≥2 axes within a 40-char window
  SD-003  axis_cluster            Tag-only if ≥3 queries in the same
                                  case touch the same axis (signal for
                                  possible over-clustering, not a block)

The gate runs in the orchestrator AFTER ``query_necessity_gate`` and
BEFORE ``query_compliance_gate`` (NLQ). Multi-dim queries are dropped
from ``case.proposed_provider_queries`` before NLQ sees them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.icoder.agent_runtime.cdi.domain import CDICase, ProviderQuery


# ---------------------------------------------------------------------------
# Axis taxonomy
# ---------------------------------------------------------------------------


AXIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "type":         ("类型", "分型", "病理分型", "性质"),
    "etiology":     ("病因", "病原体", "原因", "诱因"),
    "severity":     ("严重程度", "分级", "分期", "GOLD", "Killip"),
    "acuity":       ("急慢性", "急性或慢性", "新鲜", "陈旧"),
    "site":         ("部位", "侧别", "解剖部位", "位置", "肺叶"),
    "course":       ("病程", "起病", "持续时间", "发病时间"),
    "complication": ("并发症", "合并症"),
    "count":        ("数量", "数目", "几处"),
    "correlation":  ("关联", "相关性", "关系"),
}


def detect_axes(text: str) -> set[str]:
    """Return the set of axis names whose keywords appear in ``text``."""
    if not text:
        return set()
    found: set[str] = set()
    for axis, keywords in AXIS_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                found.add(axis)
                break
    return found


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SingleDimensionRuleResult:
    """Outcome of one SD-XXX rule on a single query."""
    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    severity: Literal["hard", "soft", "tag"] = "hard"


@dataclass
class SingleDimensionGateResult:
    """Aggregate outcome for all SD rules on a single query."""
    verdict: Literal["SINGLE_DIM", "MULTI_DIM", "DEGRADED"]
    axes_detected: list[str]
    rules_evaluated: int
    rules_passed: int
    rules_failed: list[SingleDimensionRuleResult] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    flag_reasons: list[str] = field(default_factory=list)


@dataclass
class CaseSingleDimensionResult:
    """Per-case aggregate including the cluster tag SD-003."""
    per_query: dict[str, SingleDimensionGateResult] = field(default_factory=dict)
    axis_cluster_triggered: bool = False
    axis_cluster_axis: str = ""
    axis_cluster_count: int = 0
    axis_cluster_threshold: int = 3  # ≥3 queries touching same axis


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _rule_sd_001(query: ProviderQuery) -> SingleDimensionRuleResult:
    """SD-001 — topic must not span ≥2 orthogonal axes."""
    axes = detect_axes(query.topic or "")
    passed = len(axes) < 2
    evidence = (
        f"topic axes = {sorted(axes)}" if axes else "topic has no axis keyword"
    )
    return SingleDimensionRuleResult(
        rule_id="SD-001",
        name="topic_single_axis",
        description="Topic must not span ≥2 orthogonal axes",
        passed=passed,
        evidence=evidence,
        severity="hard",
    )


def _rule_sd_002(query: ProviderQuery) -> SingleDimensionRuleResult:
    """SD-002 — query_text must not span ≥2 orthogonal axes within one clause.

    "Within one clause" is approximated by checking the full query_text —
    long queries naturally mention more axis keywords. The 40-char window
    is enforced by sliding over the text and checking each window.
    """
    text = query.query_text or ""
    if not text:
        return SingleDimensionRuleResult(
            rule_id="SD-002",
            name="text_single_axis",
            description="Query text must not span ≥2 orthogonal axes in one clause",
            passed=True,
            evidence="empty query_text",
            severity="hard",
        )

    # Sliding 40-char window. If any window contains ≥2 axes, fail.
    window = 40
    text_lower = text
    failed_axes: set[str] = set()
    for start in range(0, max(1, len(text_lower) - window + 1)):
        chunk = text_lower[start:start + window]
        axes = detect_axes(chunk)
        if len(axes) >= 2:
            failed_axes = axes
            break

    passed = not failed_axes
    evidence = (
        f"axes in 40-char window = {sorted(failed_axes)}"
        if failed_axes
        else "no 40-char window contained ≥2 axes"
    )
    return SingleDimensionRuleResult(
        rule_id="SD-002",
        name="text_single_axis",
        description="Query text must not span ≥2 orthogonal axes in one clause",
        passed=passed,
        evidence=evidence,
        severity="hard",
    )


def _rule_sd_003(all_queries: list[ProviderQuery]) -> tuple[bool, str, int]:
    """SD-003 — case-level cluster tag.

    Returns (triggered, axis_with_most_queries, count_on_that_axis).
    Triggered when ANY axis has ≥3 queries touching it.
    """
    axis_counts: dict[str, int] = {}
    for q in all_queries:
        for axis in detect_axes((q.topic or "") + " " + (q.query_text or "")):
            axis_counts[axis] = axis_counts.get(axis, 0) + 1
    if not axis_counts:
        return False, "", 0
    axis, count = max(axis_counts.items(), key=lambda kv: kv[1])
    return count >= 3, axis, count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_single_dimension(query: ProviderQuery) -> SingleDimensionGateResult:
    """Run SD-001 + SD-002 on a single query.

    Verdict:
      - SINGLE_DIM — no hard-fail; query survives
      - MULTI_DIM  — at least one hard-fail; query should be dropped
      - DEGRADED   — reserved for future LLM-reviewer fallback path
    """
    rules: list[SingleDimensionRuleResult] = [
        _rule_sd_001(query),
        _rule_sd_002(query),
    ]
    hard_fails = [r for r in rules if not r.passed and r.severity == "hard"]
    axes = detect_axes((query.topic or "") + " " + (query.query_text or ""))

    if hard_fails:
        return SingleDimensionGateResult(
            verdict="MULTI_DIM",
            axes_detected=sorted(axes),
            rules_evaluated=len(rules),
            rules_passed=len(rules) - len(hard_fails),
            rules_failed=rules,
            drop_reasons=[f"{r.rule_id}: {r.evidence}" for r in hard_fails],
            flag_reasons=[],
        )
    return SingleDimensionGateResult(
        verdict="SINGLE_DIM",
        axes_detected=sorted(axes),
        rules_evaluated=len(rules),
        rules_passed=len(rules),
        rules_failed=rules,
        drop_reasons=[],
        flag_reasons=[],
    )


def evaluate_case_single_dimension(case: CDICase) -> CaseSingleDimensionResult:
    """Run SD-001 + SD-002 per query, plus SD-003 case-level cluster tag.

    Side-effect-free — does NOT mutate ``case.proposed_provider_queries``.
    """
    result = CaseSingleDimensionResult()
    queries = list(case.proposed_provider_queries)
    for q in queries:
        result.per_query[q.query_id] = evaluate_single_dimension(q)

    triggered, axis, count = _rule_sd_003(queries)
    result.axis_cluster_triggered = triggered
    result.axis_cluster_axis = axis
    result.axis_cluster_count = count
    return result


def apply_single_dimension_to_case(case: CDICase) -> CaseSingleDimensionResult:
    """Evaluate AND drop MULTI_DIM queries from the case in place.

    Mirrors ``necessity_gate.apply_necessity_to_case``.
    Returns the full evaluation result for traceability.
    """
    result = evaluate_case_single_dimension(case)
    survivors: list[ProviderQuery] = []
    for q in case.proposed_provider_queries:
        verdict = result.per_query.get(q.query_id)
        if verdict is None or verdict.verdict != "MULTI_DIM":
            survivors.append(q)
    case.proposed_provider_queries = survivors
    return result


__all__ = [
    "AXIS_KEYWORDS",
    "detect_axes",
    "SingleDimensionRuleResult",
    "SingleDimensionGateResult",
    "CaseSingleDimensionResult",
    "evaluate_single_dimension",
    "evaluate_case_single_dimension",
    "apply_single_dimension_to_case",
]
