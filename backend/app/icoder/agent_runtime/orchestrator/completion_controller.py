"""CompletionController — decides when a run is "done" (§8.1).

The Aggregator produces a final message, but that doesn't mean the run
is semantically complete. Examples:
  - All Experts succeeded but no ICD codes were emitted (case too thin)
  - Primary diagnosis conflict deferred to human
  - Required sections missing from note-completeness output
  - compliance-guardrail raised a critical violation

The CompletionController inspects the normalized expert results +
conflict resolutions and emits a CompletionDecision:

  CompletionDecision.status ∈ {
    COMPLETED,                  — clean finish, ship the message
    COMPLETED_WITH_WARNINGS,    — ship but flag for review
    NEEDS_HUMAN_REVIEW,         — surface in workbench
    INCOMPLETE,                 — re-plan or fail
  }

This is the explicit gate between Aggregator and the final
``COMPLETION`` trace event. Previously this logic was implicit
(critical-expert-failure = fail, everything else = pass).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .conflict_resolver import ConflictResolution
from .result_normalizer import NormalizedExpertResult

logger = logging.getLogger(__name__)


# Status enum
STATUS_COMPLETED = "COMPLETED"
STATUS_COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
STATUS_NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
STATUS_INCOMPLETE = "INCOMPLETE"


@dataclass
class CompletionDecision:
    """What the Orchestrator should do after aggregation."""

    status: str = STATUS_COMPLETED
    reasons: list[str] = field(default_factory=list)
    must_replan: bool = False
    blocked_codes: list[str] = field(default_factory=list)
    review_required: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionControllerConfig:
    """Tunables."""

    require_any_code_emitted: bool = True
    require_no_critical_violations: bool = True
    require_no_missing_required_sections: bool = True  # for note-completeness
    critical_violation_rule_ids: tuple[str, ...] = (
        "R001", "R002", "R004", "R009", "R010",  # coding compliance P0
    )


class CompletionController:
    """Decide whether an aggregated run is truly complete."""

    def __init__(self, *, config: CompletionControllerConfig | None = None) -> None:
        self._config = config or CompletionControllerConfig()

    def evaluate(
        self,
        *,
        normalized: list[NormalizedExpertResult],
        conflicts: list[ConflictResolution] | None = None,
        critical_expert_failed: bool = False,
    ) -> CompletionDecision:
        reasons: list[str] = []
        review_required = False
        blocked_codes: list[str] = []

        if critical_expert_failed:
            reasons.append("critical_expert_failed")
            return CompletionDecision(
                status=STATUS_INCOMPLETE,
                reasons=reasons,
                must_replan=True,
                blocked_codes=blocked_codes,
                review_required=True,
            )

        # Did any expert emit codes at all?
        all_codes: list[str] = []
        all_procedures: list[str] = []
        for n in normalized:
            all_codes.extend(n.codes_emitted)
            all_procedures.extend(n.procedures_emitted)
        if self._config.require_any_code_emitted and not all_codes and not all_procedures:
            reasons.append("no_codes_or_procedures_emitted")

        # Critical violations?
        if self._config.require_no_critical_violations:
            for n in normalized:
                for issue in n.issues:
                    rid = str(issue.get("rule_id") or issue.get("id") or "")
                    sev = str(issue.get("severity") or "").lower()
                    if rid in self._config.critical_violation_rule_ids and sev in ("high", "critical"):
                        blocked_codes.append(rid)
                        reasons.append(f"critical_violation:{rid}")

        # Note-completeness: required sections missing?
        if self._config.require_no_missing_required_sections:
            for n in normalized:
                missing = n.raw.get("missing_sections") if isinstance(n.raw, dict) else None
                if isinstance(missing, list) and missing:
                    reasons.append(f"missing_sections:{n.expert_id}:{len(missing)}")

        # Conflicts deferred to human?
        for c in conflicts or []:
            if c.deferred_to_human:
                review_required = True
                reasons.append(f"conflict_deferred:{c.field_path}")

        # Final status
        if reasons and any(r.startswith("critical_violation") for r in reasons):
            status = STATUS_NEEDS_HUMAN_REVIEW
            review_required = True
        elif reasons and any(r.startswith("conflict_deferred") for r in reasons):
            status = STATUS_NEEDS_HUMAN_REVIEW
        elif reasons:
            status = STATUS_COMPLETED_WITH_WARNINGS
        else:
            status = STATUS_COMPLETED

        return CompletionDecision(
            status=status,
            reasons=reasons,
            must_replan=False,
            blocked_codes=blocked_codes,
            review_required=review_required,
        )


__all__ = [
    "CompletionController",
    "CompletionControllerConfig",
    "CompletionDecision",
    "STATUS_COMPLETED",
    "STATUS_COMPLETED_WITH_WARNINGS",
    "STATUS_NEEDS_HUMAN_REVIEW",
    "STATUS_INCOMPLETE",
]
