"""ConflictResolver — LLM-driven cross-expert conflict resolution (§8.1).

The Aggregator's ``_detect_conflicts`` finds raw field-level
disagreements (e.g. primary_diagnosis.code = "S22.000" vs "M80.900").
Phase 1 just surfaces them in the final message metadata.

§8.1 requires an explicit ConflictResolver that goes further:
  1. Collect conflicts from Aggregator.conflicts
  2. For each conflict, decide whether to:
     - AUTORESOLVE: pick one value deterministically (rule-based)
     - LLM_RESOLVE: ask the LLM to pick + emit rationale
     - DEFER_TO_HUMAN: mark manual_review_required=True
  3. Produce a ConflictResolution record per conflict

Phase 1 implementation: rule-based autoresolves only. LLM-resolve is
a TODO marker — the API surface is stable, the implementation is
deferred to Gate 4 (where it's actually needed for principal-dx
conflicts).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .result_normalizer import NormalizedExpertResult

logger = logging.getLogger(__name__)


# Resolution strategies
RESOLUTION_AUTORESOLVE = "autoresolve"
RESOLUTION_LLM = "llm_resolve"
RESOLUTION_DEFER = "defer_to_human"


@dataclass
class ConflictResolution:
    """One conflict + how it was resolved."""

    field_path: str
    strategy: str  # one of RESOLUTION_*
    resolved_value: Any = None
    rationale: str = ""
    deferred_to_human: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConflictResolverConfig:
    """When to auto-resolve vs defer."""

    autoresolve_first_wins_paths: tuple[str, ...] = (
        "drg_code", "dip_code",
    )
    defer_paths: tuple[str, ...] = (
        "primary_diagnosis.code",
        "primary_diagnosis.description",
    )


class ConflictResolver:
    """Resolve cross-expert conflicts.

    For Phase 1 we apply deterministic rules:
      - drg_code / dip_code → first wins (low-stakes metadata)
      - primary_diagnosis.* → defer to human (high-stakes)
      - everything else → defer to human (safe default)

    LLM_RESOLVE strategy is returned but not yet executed — Gate 4
    fills it in via the same LLMCall interface as the Planner.
    """

    def __init__(self, *, config: ConflictResolverConfig | None = None) -> None:
        self._config = config or ConflictResolverConfig()

    def resolve(
        self,
        conflicts: dict[str, list[dict]],
    ) -> list[ConflictResolution]:
        """Resolve a batch of conflicts. Returns one ConflictResolution per field."""
        out: list[ConflictResolution] = []
        for path, candidates in conflicts.items():
            if not candidates:
                continue
            if path in self._config.autoresolve_first_wins_paths:
                resolved = candidates[0]
                out.append(ConflictResolution(
                    field_path=path,
                    strategy=RESOLUTION_AUTORESOLVE,
                    resolved_value=resolved.get("value"),
                    rationale=f"first-wins autoresolve for {path}",
                    candidates=list(candidates),
                ))
            elif path in self._config.defer_paths:
                out.append(ConflictResolution(
                    field_path=path,
                    strategy=RESOLUTION_DEFER,
                    resolved_value=None,
                    rationale=f"{path} requires human review (high-stakes)",
                    deferred_to_human=True,
                    candidates=list(candidates),
                ))
            else:
                out.append(ConflictResolution(
                    field_path=path,
                    strategy=RESOLUTION_DEFER,
                    resolved_value=None,
                    rationale=f"unknown conflict path {path} — defer to human",
                    deferred_to_human=True,
                    candidates=list(candidates),
                ))
        return out

    def needs_human_review(self, resolutions: list[ConflictResolution]) -> bool:
        """True if any resolution is deferred."""
        return any(r.deferred_to_human for r in resolutions)


__all__ = [
    "ConflictResolution",
    "ConflictResolver",
    "ConflictResolverConfig",
    "RESOLUTION_AUTORESOLVE",
    "RESOLUTION_LLM",
    "RESOLUTION_DEFER",
]
