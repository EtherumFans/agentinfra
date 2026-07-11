"""CDI Clinician-View De-Coding Transform (Phase 5 Track D P0 Gate 4 / PDF §A6).

PDF §A6 hard requirement: clinicians must not see coding information
(ICD-10, ICD-9-CM-3, CN-DRG, DIP, CMI). Coding info is internal to the
CDI/coding team. This module produces a clinician-safe projection of a
``ProviderQuery`` by:

    1. Stripping ICD/DRG/CMI code patterns from each response_option.
    2. Stripping code-system references (ICD-10, DRG, DIP, CMI) from the
       query body.
    3. Removing per-option ``icd_code_hint`` fields.
    4. Refusing to emit a query whose topic is itself a code (returns None
       so the orchestrator can drop the query).

The transform is a one-way projection: the original query stays intact
in the audit trail; only the clinician-facing copy is sanitized.

Public API:
    strip_codes_from_text(text) -> str
    to_clinician_view(query) -> ProviderQuery | None
    is_safe_for_clinician(query) -> bool
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .domain import ProviderQuery


# ---------------------------------------------------------------------------
# Code patterns (kept in sync with nlq_gate._ICD_CODE_PATTERNS)
# ---------------------------------------------------------------------------

_CODE_PATTERNS = [
    # ICD-10-CM: letter + 2 digits + optional .subdivision + optional alpha
    re.compile(r"\s*[\(\<\[]?\s*[A-Z]\d{2}(?:\.\d{1,4})?[A-Z]?\s*[\)\>\]]?\s*"),
    # ICD-9-CM-3: 2-3 digits + .subdivision
    re.compile(r"\s*[\(\<\[]?\s*\d{2,3}\.\d{1,2}\s*[\)\>\]]?\s*"),
    # CN-DRG: 2-3 letters + digits, e.g. AH1, BJ1
    re.compile(r"\s*[\(\<\[]?\s*[A-Z]{2}\d[A-Z]?\s*[\)\>\]]?\s*"),
    # Explicit code-system references
    re.compile(r"\bICD[- ]?10\b", flags=re.IGNORECASE),
    re.compile(r"\bICD[- ]?9\b", flags=re.IGNORECASE),
    re.compile(r"\bDRG\b", flags=re.IGNORECASE),
    re.compile(r"\bDIP\b", flags=re.IGNORECASE),
    re.compile(r"\bCMI\b", flags=re.IGNORECASE),
    # Chinese payment/system terms
    re.compile(r"编码(为|到)?[A-Z0-9.\s]*"),
    re.compile(r"(对应|进入|分入)(DRG|DIP|CMI)?\s*[A-Z]{0,3}\d*[A-Z]?\s*组"),
    re.compile(r"(权重|支付|报销|医保结算|病例混合指数)"),
]

# Topic-level patterns — if the query topic is itself a code, the query
# is fundamentally unsafe for clinician view and must be dropped.
_TOPIC_CODE_PATTERN = re.compile(
    r"^([A-Z]\d{2}(\.\d{1,4})?[A-Z]?|\d{2,3}\.\d{1,2}|[A-Z]{2}\d[A-Z]?)$"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def strip_codes_from_text(text: str) -> str:
    """Remove ICD/DRG/CMI code substrings from ``text``.

    Collapses double-spaces and trims trailing punctuation left by removal
    (e.g. "A. 肺炎链球菌 (J13)" → "A. 肺炎链球菌").
    """

    cleaned = text
    for pat in _CODE_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    # Cleanup whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Trim trailing separators like " -" or ":"
    cleaned = re.sub(r"[\s\-:.,]+$", "", cleaned).strip()
    # Trim leading separators
    cleaned = re.sub(r"^[\s\-:.,]+", "", cleaned).strip()
    return cleaned


def is_safe_for_clinician(query: "ProviderQuery") -> bool:
    """Return True iff the query topic is not itself a bare code."""

    if not query.topic or not query.topic.strip():
        return True
    return not _TOPIC_CODE_PATTERN.match(query.topic.strip())


def to_clinician_view(query: "ProviderQuery") -> "ProviderQuery | None":
    """Project ``query`` to a clinician-safe copy.

    Returns a new ProviderQuery with response_options and query_text
    de-coded. Returns None if the query is fundamentally unsafe for
    clinician view (e.g. topic is itself an ICD code).

    The original query is NOT mutated — the audit trail keeps the
    original coding context for CDI/coding team review.
    """

    from .domain import ProviderQuery as _PQ  # local import for runtime

    if not is_safe_for_clinician(query):
        return None

    sanitized_options = [strip_codes_from_text(opt) for opt in query.response_options]
    sanitized_text = strip_codes_from_text(query.query_text)

    # Copy with sanitized fields — everything else preserved as-is
    return _PQ(
        query_id=query.query_id,
        gap_id=query.gap_id,
        topic=query.topic,
        reason=query.reason,
        evidence_span=query.evidence_span,
        query_text=sanitized_text,
        response_options=sanitized_options,
        priority=query.priority,
        lifecycle_state=query.lifecycle_state,
        nlq_gate_verdict=query.nlq_gate_verdict,
        nlq_gate_block_reasons=list(query.nlq_gate_block_reasons),
    )


__all__ = [
    "is_safe_for_clinician",
    "strip_codes_from_text",
    "to_clinician_view",
]
