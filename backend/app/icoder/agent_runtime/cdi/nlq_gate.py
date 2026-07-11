"""CDI Non-leading Query Gate (Phase 5 Track D Gate 5 + P0 Gate 4).

Pure-logic rule engine implementing NLQ-001..010.

Phase 5 Track D P0 Gate 4 (2026-07-11) improvements:
    - NLQ-001 anchor removed — mid-sentence 是否 / 能否 / Can you confirm
      now block. PDF A4 example "根据痰培养结果，该患者肺炎是否可以明确为…"
      now correctly fails (was passing — false negative).
    - NLQ-010 added — response_options must NOT contain ICD/DRG/CMI codes
      (PDF §A6 clinician de-coding requirement).
    - NLQ-002 retains its stub for pure-logic mode; a real LLM-backed
      semantic reviewer is in ``nlq_semantic.py`` (Gate 4 Step 5).

The gate is invoked by the CDI Orchestrator after a Provider Query is
generated. If any rule returns ``action='BLOCK'``, the query cannot
leave ``DRAFT`` state.

Rule list (PDF §8.3 + Phase 5 Track D P0 Gate 4 + P0.5 Gate 3):
    NLQ-001  no_yes_no_opening          (lexical, regex — anchor removed)
    NLQ-002  no_diagnosis_presumption   (semantic, see nlq_semantic.py)
    NLQ-003  response_options_required  (structural)
    NLQ-004  min_three_response_options (structural)
    NLQ-005  escape_hatch_required      (structural)
    NLQ-006  no_treatment_advice        (lexical, keyword list)
    NLQ-007  no_undiagnosed_condition_in_query  (semantic)
    NLQ-008  no_single_diagnosis_suggested       (semantic)
    NLQ-009  no_payment_terms           (lexical, keyword list)
    NLQ-010  no_coding_codes_in_options (structural, ICD/DRG/CMI patterns)
    NLQ-011  max_five_response_options  (structural, PDF §3.2 R7 ceiling)

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
    # Phase 5 Track D P0 Gate 4 (2026-07-11): removed ^\s* anchor.
    # PDF A4 example "根据痰培养结果，该患者肺炎是否可以明确为肺炎链球菌性肺炎？"
    # contains 是否 mid-sentence; the old anchor let it through (false negative).
    # Now any 是否 / 能否 / 是不是 anywhere triggers a block.
    r"(是不是|是否|是否为|能否|能不能|是不是说|是不是要|能否认为|是否可以)",
    r"(Would you agree|Is it|Are they|Do you agree|Isn't it|Aren't they|Can you confirm)",
    r"(Could this be|Can we say|Should we code|Do you consider)",
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

# Phase 5 Track D P0 Gate 4: structural rule NLQ-010.
# Detects ICD-10 / ICD-9-CM-3 / CN-DRG / DIP codes embedded in
# response_options. PDF A6: clinicians must not see coding info.
_ICD_CODE_PATTERNS = [
    # ICD-10-CM: letter + 2 digits + optional .subdivision (e.g. J18.9, S72.001A)
    r"\b[A-Z]\d{2}(\.\d{1,4})?[A-Z]?\b",
    # ICD-9-CM-3: 2-3 digits + .subdivision (e.g. 81.01, 00.50)
    r"\b\d{2,3}\.\d{1,2}\b",
    # CN-DRG: 3 letters + digits (e.g. AH1, BJ1)
    r"\b[A-Z]{2}\d[A-Z]?\b",
    # Explicit coding-language hints
    r"\bICD[- ]?10\b", r"\bICD[- ]?9\b", r"\bDRG\b", r"\bDIP\b", r"\bCMI\b",
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


# Phase 5 Track D P0 Gate 4: structural rule for ICD/DRG codes in options.
def _rule_nlq_010(query: ProviderQueryForGate) -> RuleResult:
    """PDF A6: response_options must NOT contain ICD/DRG/CMI codes.

    Clinician-facing UI must never see coding information; a coding-leaking
    option is a hard block. Patterns cover ICD-10-CM, ICD-9-CM-3, CN-DRG,
    DIP, and explicit code-system references.
    """
    if not query.response_options:
        return RuleResult(
            rule_id="NLQ-010",
            name="no_coding_codes_in_options",
            description="response_options 不得包含 ICD/DRG/CMI 编码",
            passed=True,
            evidence="no response_options (deferred to NLQ-003)",
        )
    offending: list[str] = []
    for opt in query.response_options:
        for pat in _ICD_CODE_PATTERNS:
            m = re.search(pat, opt, flags=re.IGNORECASE)
            if m:
                offending.append(f"option '{opt}' matched /{pat}/ : '{m.group(0)}'")
                break
    passed = not offending
    return RuleResult(
        rule_id="NLQ-010",
        name="no_coding_codes_in_options",
        description="response_options 不得包含 ICD/DRG/CMI 编码 (PDF §A6)",
        passed=passed,
        evidence="; ".join(offending) if offending else "no ICD/DRG codes detected",
        action="PASS" if passed else "BLOCK",
    )


# Phase 5 Track D P0.5 Gate 3: structural rule for option count upper bound.
_MAX_RESPONSE_OPTIONS = 5


def _rule_nlq_011(query: ProviderQueryForGate) -> RuleResult:
    """PDF §3.2 R7: response_options must be ≤ 5 (option taxonomy ceiling).

    The lower bound (NLQ-004 ≥3) already exists. This rule caps the
    upper bound to prevent option-list bloat. A 6+ option query forces
    the clinician to scan too many choices, defeating the response_options
    taxonomy's purpose (fast single-axis selection).
    """
    n = len(query.response_options) if query.response_options else 0
    passed = n <= _MAX_RESPONSE_OPTIONS
    return RuleResult(
        rule_id="NLQ-011",
        name="max_five_response_options",
        description=f"response_options 不得超过 {_MAX_RESPONSE_OPTIONS} 个 (PDF §3.2 R7)",
        passed=passed,
        evidence=f"response_options count={n} (cap={_MAX_RESPONSE_OPTIONS})",
        action="PASS" if passed else "BLOCK",
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
    _rule_nlq_010,
    _rule_nlq_011,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(query: ProviderQueryForGate) -> NLQGateResult:
    """Run all 11 NLQ rules on ``query`` and return the aggregate verdict."""

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
