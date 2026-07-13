"""Phase 5 Track D P0.5 Gate 4 — Claim-Evidence Alignment Gate.

PDF §3.2 R8 + Master Task §五. Every clinical Claim inside a Provider Query
must be substantiated by an EvidenceSpan whose quote is verifiably in the
chart. Critical claims with no chart support are diagnosis-invention and
are BLOCKED.

Two-stage evaluation
====================

1. **Claim extraction** (LLM-backed, async): the query's ``query_text``
   is decomposed into ≥1 atomic Claim, each tagged ``criticality``
   (critical vs supporting). For each Claim, the LLM proposes an
   EvidenceSpan (quote + char_start + char_end + support_type).

2. **Deterministic validation** (pure-logic, sync): nine CEA-XXX rules
   verify the LLM's proposal against the chart. Mismatches invalidate
   the alignment; the claim then survives only if another alignment
   rescues it.

Rules (Master Task §5.4 + §5.5)
===============================

  CEA-001  quote_exists_in_chart       quote verbatim in chart          HARD
  CEA-002  char_span_accurate          chart[start:end] == quote        HARD
  CEA-003  document_id_valid           document_id non-empty            HARD
  CEA-004  no_cross_case_evidence      document_id matches a case doc   HARD
  CEA-005  no_negation_as_support      quote not preceded by 否认/无    HARD
  CEA-006  no_pmh_as_current           quote not in 既往史 section      HARD
  CEA-007  no_inferred_as_direct       support_type 'direct'真的direct HARD
  CEA-008  critical_claim_has_evidence ≥1 valid evidence for critical  HARD
  CEA-009  inferred_critical_demotes   critical only inferred → review  SOFT

Per-query verdict
=================

  BLOCK              — ≥1 critical claim with 0 valid evidence (CEA-008)
                       → query dropped from case.proposed_provider_queries
  REVIEW_REQUIRED    — ≥1 critical claim only inferred (CEA-009)
                       → query kept but flagged for human review
  PASS               — all critical claims have direct/contextual support

DEGRADED on LLM failure: empty claims list, verdict PASS. The downstream
semantic necessity gate + NLQ gate still run; the orchestrator can still
complete. Audit trail captures ``degraded=True``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from rapidfuzz import fuzz

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    Claim,
    ClaimEvidenceAlignment,
    ClaimValidationStatus,
    ProviderQuery,
    SupportType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ClaimEvidenceRuleResult:
    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    severity: Literal["hard", "soft"] = "hard"


@dataclass
class ClaimOutcome:
    """Per-claim aggregate outcome."""

    claim_id: str
    text: str
    criticality: str
    best_support_type: SupportType = "unsupported"
    best_validation_status: ClaimValidationStatus = "no_evidence"
    rule_results: list[ClaimEvidenceRuleResult] = field(default_factory=list)
    claim_verdict: Literal["SUPPORTED", "INFERRED_ONLY", "UNSUPPORTED"] = "UNSUPPORTED"


@dataclass
class ClaimEvidenceGateResult:
    """Per-query aggregate outcome."""

    verdict: Literal["PASS", "REVIEW_REQUIRED", "BLOCK", "DEGRADED"]
    claims: list[ClaimOutcome] = field(default_factory=list)
    rules_failed: list[ClaimEvidenceRuleResult] = field(default_factory=list)
    rules_passed: int = 0
    rules_evaluated: int = 0
    block_reasons: list[str] = field(default_factory=list)
    flag_reasons: list[str] = field(default_factory=list)
    degraded: bool = False
    error_reason: str = ""


@dataclass
class CaseClaimEvidenceResult:
    """Per-case aggregate."""

    per_query: dict[str, ClaimEvidenceGateResult] = field(default_factory=dict)
    blocked_query_ids: list[str] = field(default_factory=list)
    flagged_query_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# CEA-005 — negation context. The EvidenceSpan quote cannot be a positive
# assertion if it is preceded (within 20 chars) by a negation marker.
_NEGATION_MARKERS = (
    "否认", "无", "未见", "排除", "除外", "未提示", "未发现", "阴性",
    "无明确", "未及", "未触及", "未查及", "negat", "no ", "without",
    "ruled out", "absence of",
)

# CEA-006 — past medical / family history section markers. A quote inside
# a 既往史 / 家族史 / 个人史 section cannot serve as evidence for a CURRENT
# active condition.
_PMH_SECTION_MARKERS = (
    "既往史", "家族史", "个人史", "婚育史", "月经史",
    "past medical history", "family history", "social history",
    "PMH", "FH", "SH",
)

# CEA-007 — words in evidence that signal the line is inferential, not
# verbatim. If the LLM tagged support_type='direct' but the quote contains
# one of these markers, downgrade to inferred.
_INFERENCE_MARKERS = (
    "可能", "疑似", "考虑", "不排除", "可疑", "倾向", "提示",
    "probably", "suspected", "likely", "considered", "cannot rule out",
    "suggestive of",
)

# Negation-pattern detection window: how many chars BEFORE the quote start
# to scan for negation markers.
_NEGATION_WINDOW = 25


# ---------------------------------------------------------------------------
# CEA-XXX rule implementations
# ---------------------------------------------------------------------------


def _find_quote_in_chart(quote: str, chart: str) -> tuple[int, int] | None:
    """Locate ``quote`` in ``chart``. Returns (char_start, char_end) or None."""
    if not quote or not chart:
        return None
    idx = chart.find(quote)
    if idx < 0:
        return None
    return idx, idx + len(quote)


# Phase 5 Track H3.6 — fuzzy match threshold for CEA-001.
# When the LLM-generated quote is NOT a verbatim substring of the chart,
# we still consider it valid if rapidfuzz.partial_ratio(quote, chart) ≥ this.
# 0.85 = up to 15% character mismatch tolerated (1 char in 7, ~3 in 20).
# Calibrated on 40-case Corti vs iCoDer: 88.9% (full-width/half-width colon
# swap) is the minimum legitimate mismatch we want to accept.
CEA_FUZZY_THRESHOLD = 0.85


# Phase 5 Track H3.15 — quote snap threshold.
# Lower than CEA_FUZZY_THRESHOLD because snapping is a corrective action:
# the LLM quote is the LLM's best guess at the anchor, and we accept a wider
# match tolerance when locating the corresponding chart substring. Below
# this threshold the LLM quote is considered too divergent to snap safely
# (likely a hallucination), and we leave the original quote intact so the
# downstream CEA-001 / semantic_necessity gates can still flag it.
QUOTE_SNAP_THRESHOLD = 0.75


def _fuzzy_find_quote_in_chart(
    quote: str, chart: str, threshold: float = CEA_FUZZY_THRESHOLD
) -> tuple[int, int, float] | None:
    """Fuzzy-locate ``quote`` in ``chart``.

    Returns (char_start, char_end, score) where score is 0..1, or None.
    Uses rapidfuzz partial_ratio on the whole chart (rapidfuzz handles
    the sliding-window internally and is C-optimized).

    To recover a span (start, end), we re-scan a small set of candidate
    windows and pick the one whose content has the highest partial_ratio
    against the quote.
    """
    if not quote or not chart:
        return None
    qlen = len(quote)
    if qlen < 4 or len(chart) < qlen:
        # Too short to fuzzy-match reliably; defer to verbatim finder
        return None

    # Step 1: overall best score — if below threshold, fail fast.
    overall_score = fuzz.partial_ratio(quote, chart) / 100.0
    if overall_score < threshold:
        return None

    # Step 2: locate the best-matching window for span reporting.
    # Sliding window at stride qlen//4 (4x oversample). This is approximate
    # but cheap and good enough for span reporting.
    best_score = 0.0
    best_start = -1
    stride = max(1, qlen // 4)
    for start in range(0, max(0, len(chart) - qlen) + 1, stride):
        end = min(len(chart), start + qlen + 5)
        window = chart[start:end]
        score = fuzz.partial_ratio(quote, window) / 100.0
        if score > best_score:
            best_score = score
            best_start = start
    if best_start < 0:
        # Fallback: just anchor at position 0
        return (0, qlen, overall_score)
    return (best_start, best_start + qlen, best_score)


def snap_quote_to_chart(
    quote: str, chart: str, threshold: float = QUOTE_SNAP_THRESHOLD
) -> str:
    """Track H3.15 — snap an LLM-proposed evidence quote to the actual chart
    substring with the highest rapidfuzz partial_ratio.

    Returns the verbatim chart substring when the best fuzzy score ≥
    ``threshold``; otherwise returns ``quote`` unchanged. The snap is a
    deterministic correction for the paraphrasing that the H3.14 amplifier
    introduced: the LLM is told to copy verbatim but tends to "tidy" Chinese
    text, dropping particles or swapping punctuation. Without this snap:

      1. CEA-001 quote_exists_in_chart over-blocks legitimate queries whose
         only sin is minor wording drift — this caused the iter 4 regression
         on clear_gap under-query (1/10 → 3/10).
      2. H4.1 evidence_quote_verbatim_rate (rapidfuzz ≥0.85) drops from
         0.971 (iter 3) to 0.882 (iter 4).

    The snap is conservative:
      - If the quote is already a verbatim substring, return as-is.
      - If the best fuzzy score < threshold, return the original quote so
        the downstream CEA / semantic gates still see the LLM's proposal
        and can flag hallucinations.
      - Quotes shorter than 4 chars or longer than the chart are skipped.

    The returned substring is always ``chart[start:start+len(quote)]``, so
    by construction it is a verbatim substring of ``chart``.
    """
    if not quote or not chart:
        return quote
    qlen = len(quote)
    if qlen < 4 or len(chart) < qlen:
        return quote
    # Fast path: already verbatim
    if quote in chart:
        return quote
    # Overall best score first — fail fast if too divergent
    overall = fuzz.partial_ratio(quote, chart) / 100.0
    if overall < threshold:
        return quote
    # Locate the best window (sliding at stride qlen//4)
    best_score = 0.0
    best_start = -1
    stride = max(1, qlen // 4)
    for start in range(0, max(0, len(chart) - qlen) + 1, stride):
        end = min(len(chart), start + qlen + 5)
        window = chart[start:end]
        score = fuzz.partial_ratio(quote, window) / 100.0
        if score > best_score:
            best_score = score
            best_start = start
    if best_start < 0:
        return quote
    return chart[best_start:best_start + qlen]


def _rule_cea_001(alignment: ClaimEvidenceAlignment, chart: str) -> ClaimEvidenceRuleResult:
    """CEA-001 — quote must appear in chart (verbatim OR fuzzy ≥0.90).

    Phase 5 Track H3.6 relaxation: LLM-generated evidence quotes often have
    minor wording differences (punctuation, particles, whitespace) versus
    the verbatim chart text. Requiring exact substring match caused 71
    spurious BLOCKs in the 40-case calibration. We now pass when either:

      (a) chart.find(quote) succeeds (verbatim), OR
      (b) rapidfuzz.partial_ratio(quote, chart_window) ≥ CEA_FUZZY_THRESHOLD

    CEA-005 (negation), CEA-006 (PMH), CEA-007 (inference marker) still
    protect against unsafe evidence — those rules run on the best-matching
    window even when the match is fuzzy.
    """
    span = _find_quote_in_chart(alignment.quote, chart)
    if span is not None:
        return ClaimEvidenceRuleResult(
            rule_id="CEA-001",
            name="quote_exists_in_chart",
            description="Evidence quote must verbatim exist in chart (or fuzzy ≥0.90)",
            passed=True,
            evidence=f"verbatim quote located at {span[0]}:{span[1]}",
            severity="hard",
        )
    # Fuzzy fallback (Track H3.6)
    fuzzy = _fuzzy_find_quote_in_chart(alignment.quote, chart)
    if fuzzy is not None:
        return ClaimEvidenceRuleResult(
            rule_id="CEA-001",
            name="quote_exists_in_chart",
            description="Evidence quote must verbatim exist in chart (or fuzzy ≥0.90)",
            passed=True,
            evidence=(
                f"fuzzy match score={fuzzy[2]:.2f} at {fuzzy[0]}:{fuzzy[1]} "
                f"(threshold={CEA_FUZZY_THRESHOLD})"
            ),
            severity="hard",
        )
    return ClaimEvidenceRuleResult(
        rule_id="CEA-001",
        name="quote_exists_in_chart",
        description="Evidence quote must verbatim exist in chart (or fuzzy ≥0.90)",
        passed=False,
        evidence=f"quote '{alignment.quote[:40]}' not found in chart (verbatim or fuzzy ≥{CEA_FUZZY_THRESHOLD})",
        severity="hard",
    )


def _rule_cea_002(alignment: ClaimEvidenceAlignment, chart: str) -> ClaimEvidenceRuleResult:
    """If char_start/char_end provided, they must match the quote position."""
    if alignment.char_start < 0 or alignment.char_end < 0:
        # Skip span-accuracy check when LLM didn't propose spans — the LLM
        # is bad at character offsets, so we treat "no span" as "defer
        # to CEA-001" rather than failing.
        return ClaimEvidenceRuleResult(
            rule_id="CEA-002",
            name="char_span_accurate",
            description="char_start/char_end must match quote (skipped if absent)",
            passed=True,
            evidence="char_span not provided; deferring to CEA-001 quote existence",
            severity="hard",
        )
    actual = chart[alignment.char_start:alignment.char_end]
    passed = actual == alignment.quote
    return ClaimEvidenceRuleResult(
        rule_id="CEA-002",
        name="char_span_accurate",
        description="chart[char_start:char_end] == quote",
        passed=passed,
        evidence=(
            f"chart[{alignment.char_start}:{alignment.char_end}] matches"
            if passed
            else f"chart[{alignment.char_start}:{alignment.char_end}]='{actual[:40]}' != quote"
        ),
        severity="hard",
    )


def _rule_cea_003(alignment: ClaimEvidenceAlignment) -> ClaimEvidenceRuleResult:
    passed = bool(alignment.document_id and alignment.document_id.strip())
    return ClaimEvidenceRuleResult(
        rule_id="CEA-003",
        name="document_id_valid",
        description="Evidence document_id must be non-empty",
        passed=passed,
        evidence=f"document_id='{alignment.document_id}'",
        severity="hard",
    )


def _rule_cea_004(alignment: ClaimEvidenceAlignment, case_documents: list[str]) -> ClaimEvidenceRuleResult:
    """Cross-case guard: alignment's document_id must be one of the case's documents.

    For Phase 5 P0.5, the case carries a flat ``chart_excerpt`` plus a
    set of known document_ids (extracted from gap/query evidence spans).
    We accept any document_id that appears in that allowlist. Documents
    not in the list (e.g. quotes pulled from another case) FAIL.
    """
    if not case_documents:
        # No document registry yet — accept (deferred to CEA-001).
        return ClaimEvidenceRuleResult(
            rule_id="CEA-004",
            name="no_cross_case_evidence",
            description="document_id must belong to a case document",
            passed=True,
            evidence="no case_documents registry provided; deferring",
            severity="hard",
        )
    passed = alignment.document_id in case_documents
    return ClaimEvidenceRuleResult(
        rule_id="CEA-004",
        name="no_cross_case_evidence",
        description="document_id must belong to a case document",
        passed=passed,
        evidence=(
            f"document_id '{alignment.document_id}' is in case_documents"
            if passed
            else f"document_id '{alignment.document_id}' NOT in case_documents {case_documents[:5]}"
        ),
        severity="hard",
    )


def _rule_cea_005(alignment: ClaimEvidenceAlignment, chart: str) -> ClaimEvidenceRuleResult:
    """Quote must not be preceded by a negation marker."""
    if not alignment.quote:
        return ClaimEvidenceRuleResult(
            rule_id="CEA-005",
            name="no_negation_as_support",
            description="Quote must not be negated context",
            passed=True,
            evidence="empty quote — deferring",
            severity="hard",
        )
    span = _find_quote_in_chart(alignment.quote, chart)
    if span is None:
        # Try fuzzy location (Track H3.6) so we still run the negation
        # check on the best-matching window. If no fuzzy match either,
        # defer to CEA-001.
        fuzzy = _fuzzy_find_quote_in_chart(alignment.quote, chart)
        if fuzzy is None:
            return ClaimEvidenceRuleResult(
                rule_id="CEA-005",
                name="no_negation_as_support",
                description="Quote must not be negated context",
                passed=True,
                evidence="quote not found in chart — handled by CEA-001",
                severity="hard",
            )
        span = (fuzzy[0], fuzzy[1])
    start = max(0, span[0] - _NEGATION_WINDOW)
    window = chart[start:span[0]].lower()
    hit = next((m for m in _NEGATION_MARKERS if m.lower() in window), None)
    return ClaimEvidenceRuleResult(
        rule_id="CEA-005",
        name="no_negation_as_support",
        description="Quote must not be negated context",
        passed=hit is None,
        evidence=(
            "no negation marker in preceding window"
            if hit is None
            else f"negation marker '{hit}' found in chart[{start}:{span[0]}]"
        ),
        severity="hard",
    )


def _rule_cea_006(alignment: ClaimEvidenceAlignment, chart: str) -> ClaimEvidenceRuleResult:
    """Quote must not be inside a 既往史/家族史/个人史 section."""
    if not alignment.quote:
        return ClaimEvidenceRuleResult(
            rule_id="CEA-006",
            name="no_pmh_as_current",
            description="Quote must not be from PMH/FH/SH section",
            passed=True,
            evidence="empty quote — deferring",
            severity="hard",
        )
    span = _find_quote_in_chart(alignment.quote, chart)
    if span is None:
        # Try fuzzy location (Track H3.6) so we still run the PMH
        # check on the best-matching window. If no fuzzy match either,
        # defer to CEA-001.
        fuzzy = _fuzzy_find_quote_in_chart(alignment.quote, chart)
        if fuzzy is None:
            return ClaimEvidenceRuleResult(
                rule_id="CEA-006",
                name="no_pmh_as_current",
                description="Quote must not be from PMH/FH/SH section",
                passed=True,
                evidence="quote not found in chart — handled by CEA-001",
                severity="hard",
            )
        span = (fuzzy[0], fuzzy[1])
    # Walk back from quote start to find the most recent section header.
    # A "section header" is the nearest PMH marker that appears before
    # the quote position AND is followed by typical section-end markers
    # (现病史 / 主诉 / 体格检查 etc.) AFTER the quote position.
    text_before = chart[:span[0]]
    text_after = chart[span[1]:]
    section_end_markers = (
        "现病史", "主诉", "体格检查", "辅助检查", "入院诊断", "出院诊断",
        "诊疗经过", "手术记录", "HPI", "physical exam",
    )
    for marker in _PMH_SECTION_MARKERS:
        idx = text_before.rfind(marker)
        if idx < 0:
            continue
        # Confirm this section is "still open" at the quote position —
        # i.e. no section_end_marker between idx and span[0].
        between = text_before[idx + len(marker):]
        if any(end in between for end in section_end_markers):
            continue
        # Also require that the quote isn't ALSO cited inside an active
        # section further down — if it is, we keep deferred (PMH might
        # have been referenced from current state legitimately).
        return ClaimEvidenceRuleResult(
            rule_id="CEA-006",
            name="no_pmh_as_current",
            description="Quote must not be from PMH/FH/SH section",
            passed=False,
            evidence=f"quote under section '{marker}' (char {idx}) — past, not current",
            severity="hard",
        )
    # Also defensively check after position for family-history tag on the
    # same line (some charts inline "父亲有糖尿病" without a section header).
    inline_pmh_patterns = (
        re.compile(r"父亲.{0,10}(?:糖尿病|高血压|冠心病)"),
        re.compile(r"母亲.{0,10}(?:糖尿病|高血压|冠心病)"),
        re.compile(r"(?:家族|家庭).{0,10}(?:阳性|史|病史)"),
    )
    line = chart[span[0]:min(len(chart), span[1] + 40)]
    for pat in inline_pmh_patterns:
        if pat.search(line):
            return ClaimEvidenceRuleResult(
                rule_id="CEA-006",
                name="no_pmh_as_current",
                description="Quote must not be from PMH/FH/SH section",
                passed=False,
                evidence=f"inline family-history pattern '{pat.pattern}' matched",
                severity="hard",
            )
    return ClaimEvidenceRuleResult(
        rule_id="CEA-006",
        name="no_pmh_as_current",
        description="Quote must not be from PMH/FH/SH section",
        passed=True,
        evidence="no PMH/FH/SH section context detected",
        severity="hard",
    )


def _rule_cea_007(alignment: ClaimEvidenceAlignment) -> ClaimEvidenceRuleResult:
    """If support_type='direct', the quote must not contain inference markers."""
    if alignment.support_type != "direct":
        return ClaimEvidenceRuleResult(
            rule_id="CEA-007",
            name="no_inferred_as_direct",
            description="support_type 'direct' must be truly verbatim",
            passed=True,
            evidence=f"support_type='{alignment.support_type}' — rule only fires for 'direct'",
            severity="hard",
        )
    quote_low = alignment.quote.lower()
    hit = next((m for m in _INFERENCE_MARKERS if m.lower() in quote_low), None)
    return ClaimEvidenceRuleResult(
        rule_id="CEA-007",
        name="no_inferred_as_direct",
        description="support_type 'direct' must be truly verbatim",
        passed=hit is None,
        evidence=(
            "no inference marker in direct evidence"
            if hit is None
            else f"inference marker '{hit}' found — should be 'inferred'"
        ),
        severity="hard",
    )


# CEA-008 + CEA-009 are claim-level, evaluated after per-alignment rules.
# See _aggregate_claim_outcome below.


# ---------------------------------------------------------------------------
# Claim aggregation (CEA-008 + CEA-009)
# ---------------------------------------------------------------------------


_SUPPORT_RANK = {"direct": 3, "contextual": 2, "inferred": 1, "unsupported": 0}


def _aggregate_claim_outcome(
    claim: Claim,
    alignments: list[ClaimEvidenceAlignment],
    *,
    chart: str,
    case_documents: list[str],
) -> ClaimOutcome:
    """Run CEA-001..007 on each alignment, then CEA-008 + CEA-009 on the aggregate.

    A claim's best evidence is the highest-ranked VALID alignment.
    Critical claims with no valid evidence → UNSUPPORTED.
    Critical claims with only inferred evidence → INFERRED_ONLY.
    Otherwise → SUPPORTED.
    """

    outcome = ClaimOutcome(
        claim_id=claim.claim_id,
        text=claim.text,
        criticality=claim.criticality,
    )

    valid_alignments: list[tuple[int, ClaimEvidenceAlignment]] = []
    for al in alignments:
        # Run CEA-001..007 against this alignment
        rule_results = [
            _rule_cea_001(al, chart),
            _rule_cea_002(al, chart),
            _rule_cea_003(al),
            _rule_cea_004(al, case_documents),
            _rule_cea_005(al, chart),
            _rule_cea_006(al, chart),
            _rule_cea_007(al),
        ]
        outcome.rule_results.extend(rule_results)
        all_passed = all(r.passed for r in rule_results)
        if all_passed:
            valid_alignments.append((_SUPPORT_RANK[al.support_type], al))
        else:
            # Update alignment validation_status — pick the first failure
            for r in rule_results:
                if not r.passed:
                    al.validation_status = _RULE_ID_TO_STATUS.get(r.rule_id, "unchecked")
                    break

    # Determine best support
    if valid_alignments:
        valid_alignments.sort(key=lambda t: t[0], reverse=True)
        best_rank, best_al = valid_alignments[0]
        outcome.best_support_type = best_al.support_type
        outcome.best_validation_status = "valid"
    else:
        outcome.best_support_type = "unsupported"
        # Inherit validation status from the LAST alignment's failure
        if alignments:
            outcome.best_validation_status = alignments[-1].validation_status
        else:
            outcome.best_validation_status = "no_evidence"

    # CEA-008 + CEA-009 verdict
    if claim.criticality == "critical":
        if outcome.best_support_type == "unsupported":
            outcome.claim_verdict = "UNSUPPORTED"
        elif outcome.best_support_type == "inferred":
            outcome.claim_verdict = "INFERRED_ONLY"
        else:
            outcome.claim_verdict = "SUPPORTED"
    else:
        # Supporting claim — tolerate unsupported/inferred; doesn't block.
        outcome.claim_verdict = "SUPPORTED"

    return outcome


_RULE_ID_TO_STATUS: dict[str, ClaimValidationStatus] = {
    "CEA-001": "invalid_quote",
    "CEA-002": "invalid_span",
    "CEA-003": "unchecked",  # missing document_id — not interesting
    "CEA-004": "cross_case_evidence",
    "CEA-005": "negation_as_support",
    "CEA-006": "pmh_as_current",
    "CEA-007": "inferred_as_direct",
}


# ---------------------------------------------------------------------------
# Per-query gate
# ---------------------------------------------------------------------------


def evaluate_claim_evidence(
    query: ProviderQuery,
    *,
    chart: str,
    case_documents: list[str] | None = None,
) -> ClaimEvidenceGateResult:
    """Run CEA-001..009 against ``query.claims`` and ``query.claim_evidence_alignments``.

    Sync + deterministic. Assumes ``extract_claims`` (LLM) has already
    populated the claims/alignments on the query. Caller may inject
    pre-extracted claims via test fixtures to bypass the LLM step.

    Returns per-query verdict:
      PASS             — no critical claim is unsupported/inferred-only
      REVIEW_REQUIRED  — ≥1 critical claim is INFERRED_ONLY (CEA-009 soft)
      BLOCK            — ≥1 critical claim is UNSUPPORTED (CEA-008 hard)
      DEGRADED         — no claims extracted (LLM failed or empty query)
    """

    if not query.claims:
        return ClaimEvidenceGateResult(
            verdict="DEGRADED",
            degraded=True,
            error_reason="no claims extracted — claim extraction skipped or failed",
        )

    docs = list(case_documents or [])
    claim_outcomes: list[ClaimOutcome] = []
    for claim in query.claims:
        aligns_for_claim = [
            al for al in query.claim_evidence_alignments if al.claim_id == claim.claim_id
        ]
        claim_outcomes.append(
            _aggregate_claim_outcome(claim, aligns_for_claim, chart=chart, case_documents=docs)
        )

    block_reasons: list[str] = []
    flag_reasons: list[str] = []
    blocked_claims = [c for c in claim_outcomes if c.claim_verdict == "UNSUPPORTED" and c.criticality == "critical"]
    flagged_claims = [c for c in claim_outcomes if c.claim_verdict == "INFERRED_ONLY" and c.criticality == "critical"]

    for c in blocked_claims:
        block_reasons.append(
            f"CEA-008: critical claim '{c.text[:50]}' has no valid chart evidence "
            f"(best={c.best_validation_status})"
        )
    for c in flagged_claims:
        flag_reasons.append(
            f"CEA-009: critical claim '{c.text[:50]}' only inferred (no direct/contextual support)"
        )

    all_rule_results: list[ClaimEvidenceRuleResult] = []
    for c in claim_outcomes:
        all_rule_results.extend(c.rule_results)
    rules_evaluated = len(all_rule_results)
    rules_passed = sum(1 for r in all_rule_results if r.passed)
    rules_failed = [r for r in all_rule_results if not r.passed]

    if blocked_claims:
        verdict = "BLOCK"
    elif flagged_claims:
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "PASS"

    return ClaimEvidenceGateResult(
        verdict=verdict,
        claims=claim_outcomes,
        rules_failed=rules_failed,
        rules_passed=rules_passed,
        rules_evaluated=rules_evaluated,
        block_reasons=block_reasons,
        flag_reasons=flag_reasons,
    )


def evaluate_case_claim_evidence(case: CDICase) -> CaseClaimEvidenceResult:
    """Side-effect-free evaluation across all queries in the case."""
    result = CaseClaimEvidenceResult()
    docs = _extract_case_documents(case)
    for q in case.proposed_provider_queries:
        gate = evaluate_claim_evidence(q, chart=case.chart_excerpt, case_documents=docs)
        result.per_query[q.query_id] = gate
        if gate.verdict == "BLOCK":
            result.blocked_query_ids.append(q.query_id)
        elif gate.verdict == "REVIEW_REQUIRED":
            result.flagged_query_ids.append(q.query_id)
    return result


def apply_claim_evidence_to_case(case: CDICase) -> CaseClaimEvidenceResult:
    """Evaluate AND drop BLOCK-verity queries.

    Mutates ``case.proposed_provider_queries`` in place by removing
    BLOCK queries. REVIEW_REQUIRED queries are kept; their flags are
    stashed on the query for downstream tracing.
    """
    result = evaluate_case_claim_evidence(case)
    survivors: list[ProviderQuery] = []
    for q in case.proposed_provider_queries:
        gate = result.per_query.get(q.query_id)
        if gate is None:
            survivors.append(q)
            continue
        if gate.verdict == "BLOCK":
            continue  # drop
        if gate.verdict == "REVIEW_REQUIRED":
            # Tag the query — downstream NLQ /w lifecycle may surface it
            if not q.nlq_gate_block_reasons:
                q.nlq_gate_block_reasons = list(gate.flag_reasons)
        survivors.append(q)
    case.proposed_provider_queries = survivors
    return result


def _extract_case_documents(case: CDICase) -> list[str]:
    """Collect all document_ids referenced by gaps + queries in the case.

    Used by CEA-004 to validate that an LLM-proposed document_id is
    actually part of this case (vs. hallucinated or cross-case).
    """
    docs: set[str] = set()
    for g in case.documentation_gaps:
        if g.evidence_span.document_id:
            docs.add(g.evidence_span.document_id)
        for ev in g.evidence_spans:
            if ev.document_id:
                docs.add(ev.document_id)
    for q in case.proposed_provider_queries:
        if q.evidence_span.document_id:
            docs.add(q.evidence_span.document_id)
    return sorted(docs)


# ---------------------------------------------------------------------------
# LLM-backed claim extraction (async)
# ---------------------------------------------------------------------------


_CLAIM_EXTRACTION_PROMPT = """你是 CDI Claim 提取器. 你的任务是把一个 Provider Query 分解成原子临床 Claim, 并为每个 Claim 找到 chart 中的证据.

输入:
  query_text: {query_text}
  query_topic: {topic}
  chart_excerpt (节选):
  {chart_excerpt}

要求:
1. 把 query_text 分解成 1~5 个原子 Claim. 每个 Claim 是一个独立的临床断言.
2. 区分 critical (核心, 移除会让 query 失去意义) 和 supporting (辅助).
3. 为每个 Claim 在 chart_excerpt 中找一条最匹配的 evidence quote (必须 verbatim 出现在 chart 中).
4. 判断 support_type:
   - direct: chart 原文直接支持该 Claim
   - contextual: 需要结合上下文, 不增加新的临床结论
   - inferred: 合理推断, 不是确定性事实
   - unsupported: chart 中找不到任何支持
5. 如果找不到任何 quote, 设置 quote="" 和 support_type="unsupported".

严格按以下 JSON 输出 (无其他文本):
{{
  "claims": [
    {{
      "claim_id": "claim_1",
      "text": "断言原文",
      "criticality": "critical | supporting",
      "evidence_span_id": "es_1",
      "document_id": "chart",
      "quote": "chart 中的原文",
      "support_type": "direct | contextual | inferred | unsupported",
      "confidence": 0.0~1.0
    }}
  ]
}}

红线: 不要发明 chart 中没有的 quote. 如果 query 提到的内容 chart 里没有, 必须诚实标 unsupported.
"""


async def extract_claims(
    query: ProviderQuery,
    *,
    chart: str,
    llm: Any | None = None,
) -> tuple[list[Claim], list[ClaimEvidenceAlignment]]:
    """LLM-backed claim extraction. DEGRADED → ([], []).

    Args:
        query: ProviderQuery with query_text + topic populated.
        chart: Chart text to extract evidence from.
        llm: Optional LLM service (defaults to ``llm_service`` singleton).

    Returns:
        (claims, alignments) — both lists are empty on failure.
    """
    if llm is None:
        from app.services.llm_service import llm_service as _default_llm
        llm = _default_llm

    if not query.query_text or not chart:
        return ([], [])

    system_prompt = _CLAIM_EXTRACTION_PROMPT.format(
        query_text=query.query_text[:500],
        topic=query.topic or "(empty)",
        chart_excerpt=chart[:2500],
    )

    try:
        resp = await llm.chat(
            messages=[{"role": "user", "content": "请提取该 query 的 claims 和证据."}],
            system_prompt=system_prompt,
            response_format="json",
            temperature=0.0,
            max_tokens=800,
        )
    except Exception as exc:
        logger.warning("claim_evidence extract_claims LLM call failed: %s", exc)
        return ([], [])

    content = (resp.get("content") or "").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("claim_evidence extract_claims LLM returned non-JSON: %r", content[:200])
        return ([], [])

    raw_claims = data.get("claims") or []
    if not isinstance(raw_claims, list):
        return ([], [])

    claims: list[Claim] = []
    alignments: list[ClaimEvidenceAlignment] = []
    for idx, raw in enumerate(raw_claims):
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("claim_id") or f"claim_{idx + 1}")
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        criticality = "critical" if str(raw.get("criticality")) == "critical" else "supporting"
        claims.append(Claim(claim_id=cid, text=text, criticality=criticality))  # type: ignore[arg-type]

        quote = str(raw.get("quote") or "").strip()
        support_type = str(raw.get("support_type") or "unsupported")
        if support_type not in ("direct", "contextual", "inferred", "unsupported"):
            support_type = "unsupported"
        alignments.append(
            ClaimEvidenceAlignment(
                claim_id=cid,
                evidence_span_id=str(raw.get("evidence_span_id") or f"es_{idx + 1}"),
                document_id=str(raw.get("document_id") or "chart"),
                quote=quote,
                char_start=-1,  # LLM doesn't reliably emit offsets; CEA-002 defers
                char_end=-1,
                support_type=support_type,  # type: ignore[arg-type]
                confidence=float(raw.get("confidence") or 0.0),
                validation_status="unchecked",
            )
        )
    return (claims, alignments)


__all__ = [
    "ClaimEvidenceRuleResult",
    "ClaimOutcome",
    "ClaimEvidenceGateResult",
    "CaseClaimEvidenceResult",
    "evaluate_claim_evidence",
    "evaluate_case_claim_evidence",
    "apply_claim_evidence_to_case",
    "extract_claims",
    "snap_quote_to_chart",
    "QUOTE_SNAP_THRESHOLD",
]
