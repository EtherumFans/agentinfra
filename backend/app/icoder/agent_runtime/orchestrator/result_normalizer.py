"""ResultNormalizer — projects expert raw outputs into common shape (§8.1).

Each Expert in iCoDer returns its own raw shape:
  - evidence-extractor → ``supported_codes / uncertain_candidates / rejected_candidates``
  - procedure-extractor → ``procedures / non_billable_mentions``
  - principal-dx-review → ``recommended / coding_draft_consistent``
  - note-completeness → ``required_sections / missing_sections / incomplete_sections``
  - code-validation → ``validation_results / overall_valid``
  - drg-analyzer → ``risk_points / drg_dip_rule_reservation_note``
  - compliance-guardrail → ``risk_points / violations / compliant``
  - medical-coding-agent → ``extracted_diagnoses / procedures``

The Aggregator just merges these as separate Parts. Downstream consumers
(Gate 4 coding-compliance orchestrator + UI workbenches) want a
normalized view per capability:

  NormalizedExpertResult = {
      "expert_id": str,
      "ok": bool,
      "codes_emitted": list[str],          # all ICD codes this expert surfaced
      "procedures_emitted": list[str],     # all procedure codes
      "issues": list[dict],                # rule violations / risks / deficits
      "confidence": float | None,
      "raw": dict,                         # original result preserved
      "error": str | None,
  }

This lets the ConflictResolver compare apples-to-apples and the
CompletionController check "did every required expert emit ≥1 code?".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NormalizedExpertResult:
    """Common-shape projection of one Expert's output."""

    expert_id: str
    ok: bool = True
    codes_emitted: list[str] = field(default_factory=list)
    procedures_emitted: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_id": self.expert_id,
            "ok": self.ok,
            "codes_emitted": list(self.codes_emitted),
            "procedures_emitted": list(self.procedures_emitted),
            "issues": list(self.issues),
            "confidence": self.confidence,
            "error": self.error,
        }


def _collect_codes(obj: Any) -> list[str]:
    """Walk a nested object and collect any 'code'-keyed string values."""
    out: list[str] = []
    seen: set[int] = set()
    _walk_collect(obj, "code", out, seen)
    # Also pick up 'principal_dx' / 'principal_diagnosis' string values.
    _walk_collect(obj, "principal_dx", out, seen)
    _walk_collect(obj, "principal_diagnosis", out, seen)
    return out


def _walk_collect(obj: Any, key: str, out: list[str], seen: set[int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str) and v:
                out.append(v)
            else:
                _walk_collect(v, key, out, seen)
    elif isinstance(obj, list):
        for item in obj:
            _walk_collect(item, key, out, seen)


def _collect_procedures(obj: Any) -> list[str]:
    out: list[str] = []
    seen: set[int] = set()
    if isinstance(obj, dict):
        procs = obj.get("procedures") or []
        if isinstance(procs, list):
            for p in procs:
                if isinstance(p, dict):
                    code = p.get("code") or p.get("procedure_code")
                    if isinstance(code, str) and code:
                        out.append(code)
    return out


def _collect_issues(obj: Any) -> list[dict[str, Any]]:
    """Collect issue-shaped dicts from common expert outputs."""
    out: list[dict[str, Any]] = []
    if not isinstance(obj, dict):
        return out
    for key in (
        "issues", "violations", "risk_points", "missing_sections",
        "incomplete_sections", "conflicts", "rejected_candidates",
        "uncertain_candidates",
    ):
        val = obj.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    out.append({"source": key, **item})
                elif isinstance(item, str):
                    out.append({"source": key, "text": item})
    return out


def _extract_confidence(obj: Any) -> float | None:
    """Best-effort extraction of an overall confidence score."""
    if not isinstance(obj, dict):
        return None
    for key in ("overall_confidence", "overall_strength", "confidence"):
        v = obj.get(key)
        if isinstance(v, (int, float)) and 0 <= v <= 1:
            return float(v)
    return None


def normalize_expert_result(
    expert_id: str,
    raw_result: dict[str, Any] | None,
    *,
    error: str | None = None,
) -> NormalizedExpertResult:
    """Project one Expert's raw output into NormalizedExpertResult."""
    raw = raw_result if isinstance(raw_result, dict) else {}
    return NormalizedExpertResult(
        expert_id=expert_id,
        ok=not error,
        codes_emitted=_collect_codes(raw),
        procedures_emitted=_collect_procedures(raw),
        issues=_collect_issues(raw),
        confidence=_extract_confidence(raw),
        raw=raw,
        error=error,
    )


def normalize_batch(
    expert_results: list,  # list[ExpertResult] from Delegator
) -> list[NormalizedExpertResult]:
    """Normalize a batch of ExpertResult dataclasses."""
    out: list[NormalizedExpertResult] = []
    for r in expert_results:
        eid = getattr(r, "expert_id", "")
        raw = getattr(r, "result", None)
        err = getattr(r, "error", "") or None
        out.append(normalize_expert_result(eid, raw, error=err))
    return out


__all__ = [
    "NormalizedExpertResult",
    "normalize_batch",
    "normalize_expert_result",
]
