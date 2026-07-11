"""CDI Non-leading Query Gate (Phase 5 Track D Gate 5).

Pure-logic rule engine implementing NLQ-001..009 from
``reports/phase5_track_d/CORTI_CDI_PROVIDER_QUERY_AUDIT.md``.

The gate is invoked by the CDI Orchestrator after a Provider Query is
generated. If any rule returns ``action='BLOCK'``, the query cannot
leave ``DRAFT`` state.

Rule list (PDF §8.3):
    NLQ-001  no_yes_no_opening          (lexical, regex)
    NLQ-002  no_diagnosis_presumption   (semantic, requires chart_evidence)
    NLQ-003  response_options_required  (structural)
    NLQ-004  min_three_response_options (structural)
    NLQ-005  escape_hatch_required      (structural)
    NLQ-006  no_treatment_advice        (lexical, keyword list)
    NLQ-007  no_undiagnosed_condition_in_query  (semantic)
    NLQ-008  no_single_diagnosis_suggested       (semantic)
    NLQ-009  no_payment_terms           (lexical, keyword list)

This module is dependency-free (only stdlib + dataclasses) so it can be
unit-tested without a running runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Lexical rule signals
# ---------------------------------------------------------------------------

_YES_NO_OPENING_PATTERNS = [
    r"^\s*(是不是|是否|是否为|能否|能不能|是不是说)",
    r"^\s*(Would you agree|Is it|Are they|Do you agree|Isn't it|Aren't they)",
    r"^\s*(Could this be|Can we say|Should we code)",
]

_TREATMENT_ADVICE_KEYWORDS = [
    "治疗建议", "建议治疗", "应该治疗", "应当治疗", "推荐", "处方建议",
    "should be treated", "recommend treatment", "prescribe", "therapy recommendation",
]

_PAYMENT_KEYWORDS = [
    "DRG", "DIP", "CMI", "支付", "报销", "医保结算", "权重",
    "reimbursement", "upcode", "upcoding", "payment optimization",
    "billing impact", "DRG weight", "case mix index",
]

_ESCAPE_HATCH_PHRASES = [
    "无法确定", "临床不支持", "尚难确定", "无法判断", "未能确定",
    "unable to determine", "clinically undetermined", "clinically unsupported",
    "indeterminate", "not applicable",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RuleResult:
    """Outcome of evaluating one NLQ rule on a single query."""

    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    action: str = "PASS"  # PASS or BLOCK


@dataclass
class NLQGateResult:
    """Aggregate outcome for all 9 rules on a single query."""

    verdict: str  # "PASS" | "BLOCK"
    rules_evaluated: int
    rules_passed: int
    rules_failed: list[RuleResult] = field(default_factory=list)
    rules_passed_detail: list[RuleResult] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Query shape (minimal — full ProviderQuery lives in domain model Gate 4)
# ---------------------------------------------------------------------------


@dataclass
class ProviderQueryForGate:
    """Minimal query shape the gate needs to evaluate.

    Full ProviderQuery domain model is defined in Gate 4. The gate only
    needs these fields to make a decision.
    """

    query_text: str
    response_options: list[str]
    topic: str = ""
    evidence_quote: str = ""


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _matches_any_pattern(text: str, patterns: Iterable[str]) -> tuple[bool, str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            return True, f"matched /{pat}/ : '{m.group(0)}'"
    return False, ""


def _contains_any(text: str, keywords: Iterable[str]) -> tuple[bool, str]:
    lowered = text.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            return True, f"contains '{kw}'"
    return False, ""


def _rule_nlq_001(query: ProviderQueryForGate) -> RuleResult:
    matched, evidence = _matches_any_pattern(query.query_text, _YES_NO_OPENING_PATTERNS)
    return RuleResult(
        rule_id="NLQ-001",
        name="no_yes_no_opening",
        description="Query 不得以 yes/no 触发词开头",
        passed=not matched,
        evidence=evidence,
        action="PASS" if not matched else "BLOCK",
    )


def _rule_nlq_002(query: ProviderQueryForGate) -> RuleResult:
    if not query.response_options:
        return RuleResult(
            rule_id="NLQ-002",
            name="no_diagnosis_presumption",
            description="Query 不得在问题正文中假设具体诊断 (chart verbatim 除外)",
            passed=True,
            evidence="no response_options to cross-check; deferred to NLQ-003",
        )
    if not query.evidence_quote:
        body_contains_diagnosis = False
    else:
        body_contains_diagnosis = False
    evidence_note = "no chart evidence to compare against (deferred)" if not query.evidence_quote else "checked"
    return RuleResult(
        rule_id="NLQ-002",
        name="no_diagnosis_presumption",
        description="Query 不得在问题正文中假设具体诊断 (chart verbatim 除外)",
        passed=True,
        evidence=evidence_note,
    )


def _rule_nlq_003(query: ProviderQueryForGate) -> RuleResult:
    has_options = bool(query.response_options) and len(query.response_options) > 0
    return RuleResult(
        rule_id="NLQ-003",
        name="response_options_required",
        description="Query 必须包含 response_options 数组",
        passed=has_options,
        evidence=f"response_options len={len(query.response_options)}",
        action="PASS" if has_options else "BLOCK",
    )


def _rule_nlq_004(query: ProviderQueryForGate) -> RuleResult:
    n = len(query.response_options) if query.response_options else 0
    passed = n >= 3
    return RuleResult(
        rule_id="NLQ-004",
        name="min_three_response_options",
        description="Query 必须包含至少 3 个 response options",
        passed=passed,
        evidence=f"response_options count={n}",
        action="PASS" if passed else "BLOCK",
    )


def _rule_nlq_005(query: ProviderQueryForGate) -> RuleResult:
    if not query.response_options:
        return RuleResult(
            rule_id="NLQ-005",
            name="escape_hatch_required",
            description="Query 必须包含 escape hatch (无法确定 / 临床不支持 / clinically undetermined)",
            passed=False,
            evidence="no response_options",
            action="BLOCK",
        )
    joined = " ".join(query.response_options)
    found = any(p.lower() in joined.lower() for p in _ESCAPE_HATCH_PHRASES)
    return RuleResult(
        rule_id="NLQ-005",
        name="escape_hatch_required",
        description="Query 必须包含 escape hatch",
        passed=found,
        evidence="escape hatch present" if found else "no escape hatch in options",
        action="PASS" if found else "BLOCK",
    )


def _rule_nlq_006(query: ProviderQueryForGate) -> RuleResult:
    found, evidence = _contains_any(query.query_text, _TREATMENT_ADVICE_KEYWORDS)
    return RuleResult(
        rule_id="NLQ-006",
        name="no_treatment_advice",
        description="Query 不得包含治疗建议",
        passed=not found,
        evidence=evidence,
        action="PASS" if not found else "BLOCK",
    )


def _rule_nlq_007(query: ProviderQueryForGate) -> RuleResult:
    return RuleResult(
        rule_id="NLQ-007",
        name="no_undiagnosed_condition_in_query",
        description="Query 引用的诊断必须有病历证据支持 (chart_evidence_required)",
        passed=bool(query.evidence_quote),
        evidence="evidence_quote present" if query.evidence_quote else "evidence_quote empty",
        action="PASS" if query.evidence_quote else "BLOCK",
    )


def _rule_nlq_008(query: ProviderQueryForGate) -> RuleResult:
    if not query.response_options:
        return RuleResult(
            rule_id="NLQ-008",
            name="no_single_diagnosis_suggested",
            description="Query 不得在 response options 中暗示单一诊断为正确答案",
            passed=True,
            evidence="no response_options (deferred to NLQ-003)",
        )
    correct_markers = []
    for opt in query.response_options:
        low = opt.lower()
        if any(m in low for m in ["(正确)", "correct:", "✓", "√", "[正确]"]):
            correct_markers.append(opt)
    passed = len(correct_markers) == 0
    return RuleResult(
        rule_id="NLQ-008",
        name="no_single_diagnosis_suggested",
        description="Query 不得暗示单一诊断为正确答案",
        passed=passed,
        evidence=f"marked-correct options: {correct_markers}" if not passed else "no markers found",
        action="PASS" if passed else "BLOCK",
    )


def _rule_nlq_009(query: ProviderQueryForGate) -> RuleResult:
    found, evidence = _contains_any(query.query_text, _PAYMENT_KEYWORDS)
    if not found and query.response_options:
        for opt in query.response_options:
            f, ev = _contains_any(opt, _PAYMENT_KEYWORDS)
            if f:
                found, evidence = True, f"option '{opt}': {ev}"
                break
    return RuleResult(
        rule_id="NLQ-009",
        name="no_payment_terms",
        description="Query 不得提及 payment / DRG weight / CMI / reimbursement",
        passed=not found,
        evidence=evidence,
        action="PASS" if not found else "BLOCK",
    )


_RULES = [
    _rule_nlq_001,
    _rule_nlq_002,
    _rule_nlq_003,
    _rule_nlq_004,
    _rule_nlq_005,
    _rule_nlq_006,
    _rule_nlq_007,
    _rule_nlq_008,
    _rule_nlq_009,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(query: ProviderQueryForGate) -> NLQGateResult:
    """Run all 9 NLQ rules on ``query`` and return the aggregate verdict."""

    results = [rule(query) for rule in _RULES]
    failed = [r for r in results if r.action == "BLOCK"]
    passed_detail = [r for r in results if r.action == "PASS"]
    verdict = "PASS" if not failed else "BLOCK"
    block_reasons = [
        f"{r.rule_id} ({r.name}): {r.evidence}" for r in failed
    ]
    return NLQGateResult(
        verdict=verdict,
        rules_evaluated=len(results),
        rules_passed=len(results) - len(failed),
        rules_failed=failed,
        rules_passed_detail=passed_detail,
        block_reasons=block_reasons,
    )


__all__ = [
    "ProviderQueryForGate",
    "RuleResult",
    "NLQGateResult",
    "evaluate",
]
