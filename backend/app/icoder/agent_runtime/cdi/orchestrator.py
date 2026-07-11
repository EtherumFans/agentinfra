"""CDI Orchestrator (Phase 5 Track D Gate 6 — minimal slice for Gate 3).

Pure-logic orchestrator that threads a ``CDICase`` through CDI workflow
stages. Mirrors the structure of Track C's ``CodingComplianceOrchestrator``.

Stages (Corti-compatible 5-step CDI workflow, see agent_pack.json):
    1. encounter_synthesis
    2. gap_identification
    3. expert_consultation
    4. query_generation
    5. query_compliance_gate   (NLQ-001..009)
    6. specialist_trace_emit

Gate 3 ships a runnable skeleton. The runner is a callable — for now
the skeleton uses a no-op runner that produces empty stage outputs,
which is enough to validate the wiring. Gate 6 replaces the runner
with a real DeepSeek-backed implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .domain import CDICase, DocumentationGap, EvidenceSpan, ProviderQuery
from .nlq_gate import ProviderQueryForGate, evaluate as evaluate_nlq


# ---------------------------------------------------------------------------
# Runner protocol — callable injected by the runtime layer
# ---------------------------------------------------------------------------

StageRunner = Callable[[str, CDICase, dict[str, Any]], dict[str, Any]]
"""Runner signature: ``(stage_name, case, kwargs) -> stage_result_dict``.

The runner is responsible for:
  - Invoking the underlying capability (LLM, Expert, tool)
  - Returning a dict with stage-specific keys

For Gate 3 the runtime injects a ``_StubRunner`` that returns minimal
empty outputs — enough to exercise the orchestrator path. Gate 6 wires
a real DeepSeek-backed runner.
"""


# ---------------------------------------------------------------------------
# Stage list (Corti-compatible, PDF §6)
# ---------------------------------------------------------------------------


STAGES: tuple[str, ...] = (
    "encounter_synthesis",
    "gap_identification",
    "expert_consultation",
    "query_generation",
    "query_necessity_gate",          # Phase 5 Track D P0.5 Gate 2
    "query_single_dimension_gate",   # Phase 5 Track D P0.5 Gate 3
    "query_compliance_gate",
    "specialist_trace_emit",
)


# ---------------------------------------------------------------------------
# Completion policy (PDF §10 — gates 5 blockers + 3 non-blocking outcomes)
# ---------------------------------------------------------------------------


def _decide_completion(case: CDICase) -> Literal["AUTO_PASS", "REVIEW_RECOMMENDED", "REVIEW_REQUIRED", "BLOCKED"]:
    """Decide final completion state for a CDI case.

    Mirror of Track C Human Review Gate matrix, adapted for CDI:
        BLOCKED           — any query failed NLQ gate (cannot send)
        REVIEW_REQUIRED   — gaps found but no queries yet generated, or
                            specialist trace has high-severity rejections
        REVIEW_RECOMMENDED — queries generated and all passed NLQ, but
                            chart has risk_flags
        AUTO_PASS          — no gaps found, no risk flags
    """

    if not case.documentation_gaps and not case.risk_flags:
        return "AUTO_PASS"

    if case.proposed_provider_queries:
        blocked = any(q.nlq_gate_verdict == "BLOCK" for q in case.proposed_provider_queries)
        if blocked:
            return "BLOCKED"

    if case.documentation_gaps and not case.proposed_provider_queries:
        return "REVIEW_REQUIRED"

    if case.risk_flags:
        return "REVIEW_RECOMMENDED"

    return "REVIEW_REQUIRED"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class CDIOrchestrator:
    """Pure-logic orchestrator. Holds no mutable state between runs."""

    runner: StageRunner

    # ------------------------------------------------------------------ run

    def run(
        self,
        case: CDICase,
        *,
        stages: tuple[str, ...] = STAGES,
    ) -> CDICase:
        """Thread ``case`` through ``stages`` in order. Returns the same case
        (mutated in place) so callers can chain."""

        for stage in stages:
            self._run_stage(stage, case)
        case.completion_state = _decide_completion(case)
        return case

    # ------------------------------------------------------------------ stage

    def _run_stage(self, stage: str, case: CDICase) -> None:
        if stage == "encounter_synthesis":
            self._stage_encounter_synthesis(case)
        elif stage == "gap_identification":
            self._stage_gap_identification(case)
        elif stage == "expert_consultation":
            self._stage_expert_consultation(case)
        elif stage == "query_generation":
            self._stage_query_generation(case)
        elif stage == "query_necessity_gate":
            self._stage_query_necessity_gate(case)
        elif stage == "query_single_dimension_gate":
            self._stage_query_single_dimension_gate(case)
        elif stage == "query_compliance_gate":
            self._stage_query_compliance_gate(case)
        elif stage == "specialist_trace_emit":
            self._stage_specialist_trace_emit(case)
        else:  # pragma: no cover — defensive
            raise ValueError(f"unknown CDI stage: {stage}")

    # ------------------------------------------------------------------ stages

    def _stage_encounter_synthesis(self, case: CDICase) -> None:
        result = self.runner("encounter_synthesis", case, {})
        case.stage_run_ids["encounter_synthesis"] = str(result.get("run_id", ""))
        case.stage_trace_ids["encounter_synthesis"] = str(result.get("trace_id", ""))
        from .domain import EncounterSummary
        case.encounter_summary = EncounterSummary(
            key_points=list(result.get("key_points", [])),
            encounter_metadata=dict(result.get("encounter_metadata", {})),
        )

    def _stage_gap_identification(self, case: CDICase) -> None:
        result = self.runner("gap_identification", case, {})
        case.stage_run_ids["gap_identification"] = str(result.get("run_id", ""))
        case.stage_trace_ids["gap_identification"] = str(result.get("trace_id", ""))
        for gap_dict in result.get("gaps", []):
            case.documentation_gaps.append(self._hydrate_gap(gap_dict))

    def _stage_expert_consultation(self, case: CDICase) -> None:
        result = self.runner("expert_consultation", case, {})
        case.stage_run_ids["expert_consultation"] = str(result.get("run_id", ""))
        case.stage_trace_ids["expert_consultation"] = str(result.get("trace_id", ""))

    def _stage_query_generation(self, case: CDICase) -> None:
        result = self.runner("query_generation", case, {})
        case.stage_run_ids["query_generation"] = str(result.get("run_id", ""))
        case.stage_trace_ids["query_generation"] = str(result.get("trace_id", ""))
        for q_dict in result.get("queries", []):
            case.proposed_provider_queries.append(self._hydrate_query(q_dict))

    def _stage_query_necessity_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 2 — drop queries that fail NQ-001..NQ-005.

        Runs the necessity gate (PDF §3.2) on every query in the case.
        Hard-failures (NQ-001 evidence_sufficiency, NQ-004 documentation_impact,
        NQ-005 redundancy_risk) drop the query. Soft-failures (NQ-002, NQ-003)
        are recorded in the trace but do not drop.

        Over-query guard NQ-006 tags the case (does not block).
        """
        from .necessity_gate import apply_necessity_to_case
        result = apply_necessity_to_case(case)
        # Stash summary in stage_run_ids for traceability
        case.stage_run_ids["query_necessity_gate"] = (
            f"necessary={sum(1 for v in result.per_query.values() if v.verdict == 'NECESSARY')};"
            f"unnecessary={sum(1 for v in result.per_query.values() if v.verdict == 'UNNECESSARY')};"
            f"overquery_triggered={result.overquery_triggered};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["query_necessity_gate"] = ""

    def _stage_query_single_dimension_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 3 — drop queries that mix ≥2 orthogonal axes.

        Runs the single-dimension gate (PDF §3.2 R6) on every query.
        Hard-failures (SD-001 topic_multi_axis, SD-002 text_multi_axis)
        drop the query. Cluster tag SD-003 records if ≥3 queries touch
        the same axis (no block).
        """
        from .single_dimension_gate import apply_single_dimension_to_case
        result = apply_single_dimension_to_case(case)
        case.stage_run_ids["query_single_dimension_gate"] = (
            f"single_dim={sum(1 for v in result.per_query.values() if v.verdict == 'SINGLE_DIM')};"
            f"multi_dim={sum(1 for v in result.per_query.values() if v.verdict == 'MULTI_DIM')};"
            f"axis_cluster_triggered={result.axis_cluster_triggered};"
            f"axis_cluster_axis={result.axis_cluster_axis};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["query_single_dimension_gate"] = ""

    def _stage_query_compliance_gate(self, case: CDICase) -> None:
        """Run NLQ-001..009 on every generated query. Mutates each query's
        ``nlq_gate_verdict`` and ``nlq_gate_block_reasons``."""

        run_id = ""
        trace_id = ""
        for q in case.proposed_provider_queries:
            gate_input = ProviderQueryForGate(
                query_text=q.query_text,
                response_options=list(q.response_options),
                topic=q.topic,
                evidence_quote=q.evidence_span.quote,
            )
            result = evaluate_nlq(gate_input)
            q.nlq_gate_verdict = result.verdict
            q.nlq_gate_block_reasons = list(result.block_reasons)
        case.stage_run_ids["query_compliance_gate"] = run_id
        case.stage_trace_ids["query_compliance_gate"] = trace_id

    def _stage_specialist_trace_emit(self, case: CDICase) -> None:
        result = self.runner("specialist_trace_emit", case, {})
        case.stage_run_ids["specialist_trace_emit"] = str(result.get("run_id", ""))
        case.stage_trace_ids["specialist_trace_emit"] = str(result.get("trace_id", ""))

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _hydrate_gap(gap_dict: dict[str, Any]) -> DocumentationGap:
        ev = gap_dict.get("evidence_span") or {}
        return DocumentationGap(
            gap_id=gap_dict.get("gap_id") or f"gap_{uuid.uuid4().hex[:8]}",
            description=gap_dict.get("description", ""),
            why_it_matters=gap_dict.get("why_it_matters", ""),
            evidence_span=EvidenceSpan(
                document_id=ev.get("document_id", ""),
                quote=ev.get("quote", ""),
                char_start=int(ev.get("char_start", 0)),
                char_end=int(ev.get("char_end", 0)),
                documented_at=ev.get("documented_at", ""),
            ),
            minimal_clarification_needed=gap_dict.get("minimal_clarification_needed", ""),
            priority=gap_dict.get("priority", "routine"),
        )

    @staticmethod
    def _hydrate_query(q_dict: dict[str, Any]) -> ProviderQuery:
        ev = q_dict.get("evidence_span") or {}
        return ProviderQuery(
            query_id=q_dict.get("query_id") or f"q_{uuid.uuid4().hex[:8]}",
            gap_id=q_dict.get("gap_id", ""),
            topic=q_dict.get("topic", ""),
            reason=q_dict.get("reason", ""),
            evidence_span=EvidenceSpan(
                document_id=ev.get("document_id", ""),
                quote=ev.get("quote", ""),
                char_start=int(ev.get("char_start", 0)),
                char_end=int(ev.get("char_end", 0)),
                documented_at=ev.get("documented_at", ""),
            ),
            query_text=q_dict.get("query_text", ""),
            response_options=list(q_dict.get("response_options", [])),
            priority=q_dict.get("priority", "routine"),
        )


# ---------------------------------------------------------------------------
# Stub runner (Gate 3 only — Gate 6 wires real DeepSeek runner)
# ---------------------------------------------------------------------------


def stub_runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Minimal runner that returns enough empty outputs to exercise the
    orchestrator path. Real LLM-backed runner arrives in Gate 6."""

    return {
        "encounter_synthesis": lambda: {"key_points": [], "encounter_metadata": {}},
        "gap_identification": lambda: {"gaps": []},
        "expert_consultation": lambda: {},
        "query_generation": lambda: {"queries": []},
        "specialist_trace_emit": lambda: {},
    }.get(stage, lambda: {})()


__all__ = ["CDIOrchestrator", "STAGES", "stub_runner", "StageRunner"]
