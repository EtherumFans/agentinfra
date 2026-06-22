"""Aggregator — combine Expert results into final OrchestratorMessage (SPEC §7.4).

Phase 1 simple version:
  1. Sort by Plan step priority (stable on agent-declaration order)
  2. For each result, append a ``data`` Part with the expert's structured output
  3. If multiple experts touch the same field with different values,
     mark ``conflicted: true`` + list conflict pairs
  4. If any critical expert failed, raise AggregatorError (Q-S4: no
     LLM re-ranking in Phase 1 — defer to Phase 5)

The Aggregator is pure logic — no I/O, no LLM, no clock. Deterministic
given the same inputs.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .errors import OrchestratorError
from .run_context import ExpertResult, OrchestratorMessage

logger = logging.getLogger(__name__)


class AggregatorError(OrchestratorError):
    """Raised when aggregation cannot complete (critical expert missing)."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "aggregation_failed",
        stage: str = "aggregating",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            stage=stage,
            retryable=False,
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AggregatorConfig:
    """Tunables for the Aggregator."""

    # If True, a missing critical expert => AggregatorError
    fail_on_critical_missing: bool = True
    # If True, expert failures are still aggregated (with an "error" part)
    # so the caller can surface them in the final message. If False, they
    # are dropped.
    include_failed_experts: bool = True
    # Conflict detection — fields whose values disagree across experts
    # are flagged. Map of (field_path) → [list of (expert_id, value)].
    conflict_field_paths: tuple[str, ...] = (
        "primary_diagnosis.code",
        "primary_diagnosis.description",
        "drg_code",
        "dip_code",
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class Aggregator:
    """Combine expert results into a single OrchestratorMessage.

    No LLM, no I/O. Deterministic.
    """

    def __init__(self, *, config: AggregatorConfig | None = None) -> None:
        self._config = config or AggregatorConfig()

    def aggregate(
        self,
        *,
        plan_steps: list[dict],
        expert_results: list[ExpertResult],
        reason: str = "",
    ) -> OrchestratorMessage:
        """Return a final OrchestratorMessage.

        ``plan_steps`` carries priority + critical + expert_id (from the Planner).
        ``expert_results`` is in plan-execution order; we sort by priority here.
        """
        cfg = self._config

        # ── 1. Plan metadata lookup
        step_by_id = {s.get("expert_id", ""): s for s in plan_steps}
        priority_by_id = {
            eid: step.get("priority", 999)
            for eid, step in step_by_id.items()
        }
        critical_by_id = {
            eid: bool(step.get("critical", True))
            for eid, step in step_by_id.items()
        }

        # ── 2. Order by priority, stable on declaration order
        declared_order = [s.get("expert_id", "") for s in plan_steps]
        ordered = sorted(
            expert_results,
            key=lambda r: (
                priority_by_id.get(r.expert_id, 999),
                declared_order.index(r.expert_id)
                if r.expert_id in declared_order
                else 999,
            ),
        )

        # ── 3. Critical expert gate
        missing_critical: list[str] = []
        for eid, critical in critical_by_id.items():
            if not critical:
                continue
            if not any(r.expert_id == eid and not r.error for r in ordered):
                missing_critical.append(eid)
        if missing_critical and cfg.fail_on_critical_missing:
            raise AggregatorError(
                f"critical expert(s) failed or missing: {sorted(missing_critical)}"
            )

        # ── 4. Build parts
        parts: list[dict] = []
        for r in ordered:
            if r.error and not cfg.include_failed_experts:
                continue
            part = {
                "kind": "data",
                "data": {
                    "expert_id": r.expert_id,
                    "priority": priority_by_id.get(r.expert_id, 999),
                    "critical": critical_by_id.get(r.expert_id, True),
                    "attempt": r.attempt,
                    "latency_ms": r.latency_ms,
                    "ok": not bool(r.error),
                    "result": r.result if not r.error else None,
                    "error": r.error or None,
                },
            }
            parts.append(part)

        # ── 5. Conflict detection across successful experts
        conflicts = self._detect_conflicts(ordered, cfg)
        if conflicts:
            logger.info(
                "aggregator.conflicts detected=%d fields=%s",
                len(conflicts),
                sorted(conflicts.keys()),
            )

        # ── 6. Final summary data Part (text-style)
        summary = {
            "expert_count": len(ordered),
            "succeeded": sum(1 for r in ordered if not r.error),
            "failed": sum(1 for r in ordered if r.error),
            "conflicted": bool(conflicts),
            "conflicts": conflicts,
            "reason": reason,
        }
        parts.append({"kind": "data", "data": {"summary": summary}})
        parts.append(
            {
                "kind": "text",
                "text": self._build_text_summary(summary, ordered),
            }
        )

        return OrchestratorMessage(
            role="agent",
            parts=parts,
        )

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(
        self,
        ordered: list[ExpertResult],
        cfg: AggregatorConfig,
    ) -> dict[str, list[dict]]:
        """For each configured field path, collect (expert_id, value) pairs.

        Returns a dict: path → [{"expert_id": str, "value": Any}, ...]
        A path is conflicted iff ≥2 distinct values appear among successful experts.
        """
        by_path: dict[str, list[dict]] = defaultdict(list)
        for r in ordered:
            if r.error or not isinstance(r.result, dict):
                continue
            for path in cfg.conflict_field_paths:
                v = _dig(r.result, path)
                if v is None:
                    continue
                by_path[path].append({"expert_id": r.expert_id, "value": v})

        out: dict[str, list[dict]] = {}
        for path, entries in by_path.items():
            values = {e["value"] for e in entries}
            if len(values) >= 2:
                out[path] = entries
        return out

    @staticmethod
    def _build_text_summary(
        summary: dict,
        ordered: list[ExpertResult],
    ) -> str:
        ok = summary["succeeded"]
        failed = summary["failed"]
        total = summary["expert_count"]
        head = f"Orchestrator aggregated {ok}/{total} expert result(s)"
        if failed:
            head += f" ({failed} failed)"
        if summary["conflicted"]:
            head += "; conflicts detected (see summary.conflicts)"
        return head


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dig(d: Any, dotted: str) -> Any:
    """Resolve a dotted path against a nested dict. Returns None if missing."""
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


__all__ = [
    "Aggregator",
    "AggregatorConfig",
    "AggregatorError",
]