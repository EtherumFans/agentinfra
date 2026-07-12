"""CDI Orchestrator (Phase 5 Track D Gate 6 — minimal slice for Gate 3).

Pure-logic orchestrator that threads a ``CDICase`` through CDI workflow
stages. Mirrors the structure of Track C's ``CodingComplianceOrchestrator``.

Stages (Corti-compatible 5-step CDI workflow, see agent_pack.json):
    1. encounter_synthesis
    2. gap_identification
    3. expert_consultation
    4. query_generation
    5. query_necessity_gate         (Phase 5 Track D P0.5 Gate 2)
    6. query_single_dimension_gate  (Phase 5 Track D P0.5 Gate 3)
    7. claim_evidence_alignment_gate (Phase 5 Track D P0.5 Gate 4)
    8. semantic_necessity_gate       (Phase 5 Track D P0.5 Gate 4)
    9. query_compliance_gate         (NLQ-001..011)
   10. specialist_trace_emit

Gate 3 ships a runnable skeleton. The runner is a callable — for now
the skeleton uses a no-op runner that produces empty stage outputs,
which is enough to validate the wiring. Gate 6 replaces the runner
with a real DeepSeek-backed implementation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .domain import CDICase, DocumentationGap, EvidenceSpan, ProviderQuery
from .nlq_gate import ProviderQueryForGate, evaluate as evaluate_nlq

logger = logging.getLogger(__name__)


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
# Async-from-sync helper (for gate-internal LLM calls)
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Run a coroutine from sync code, handling nested event loops.

    Mirrors the pattern in ``real_runner.py`` — safe because FastAPI
    runs orchestrator stages inside ``asyncio.to_thread`` (a worker
    thread without a running loop). Tests that drive the orchestrator
    directly inside an async function fall through to the
    ``ThreadPoolExecutor`` path.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" in str(exc):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        raise


# ---------------------------------------------------------------------------
# Stage list (Corti-compatible, PDF §6)
# ---------------------------------------------------------------------------


STAGES: tuple[str, ...] = (
    "encounter_synthesis",
    "gap_identification",
    "expert_consultation",
    "query_generation",
    "query_eligibility_gate",         # Phase 5 Track H3.5 — chart-completeness + topic-gap relevance
    "query_necessity_gate",           # Phase 5 Track D P0.5 Gate 2
    "query_single_dimension_gate",    # Phase 5 Track D P0.5 Gate 3
    "claim_evidence_alignment_gate",  # Phase 5 Track D P0.5 Gate 4
    "semantic_necessity_gate",        # Phase 5 Track D P0.5 Gate 4
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
    # Optional LLM override for gate-internal calls (extract_claims,
    # review_necessity). When None, _get_llm() resolves in order:
    #   1. self.llm (if explicitly set)
    #   2. self.runner.llm (test fixtures using RealCDIRunner(llm=mock))
    #   3. app.services.llm_service.llm_service (production singleton)
    llm: Any = None

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
        elif stage == "query_eligibility_gate":
            self._stage_query_eligibility_gate(case)
        elif stage == "query_necessity_gate":
            self._stage_query_necessity_gate(case)
        elif stage == "query_single_dimension_gate":
            self._stage_query_single_dimension_gate(case)
        elif stage == "claim_evidence_alignment_gate":
            self._stage_claim_evidence_alignment_gate(case)
        elif stage == "semantic_necessity_gate":
            self._stage_semantic_necessity_gate(case)
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

    def _stage_query_eligibility_gate(self, case: CDICase) -> None:
        """Phase 5 Track H3.5 — drop queries that have no eligible gap.

        Two checks per PDF §3.2 + Track H3.5:
          QE-001  chart_completeness_drops_all  — if chart documents
                  ≥6/8 dimensions (type/site/severity/etiology/procedure/
                  pathology/complications/course) AND no ambiguity markers,
                  all candidate queries are spurious → drop.
          QE-002  query_topic_has_matching_gap  — each query's topic must
                  intersect an identified documentation_gap; off-topic
                  queries are dropped.
        """
        from .query_eligibility_gate import apply_eligibility_to_case
        result = apply_eligibility_to_case(case)
        dims_summary = ",".join(
            f"{dim}={'Y' if hit else 'N'}" for dim, hit in result.dimensions_detected.items()
        )
        case.stage_run_ids["query_eligibility_gate"] = (
            f"chart_complete={result.chart_complete};"
            f"completeness_score={result.chart_completeness_score:.2f};"
            f"dimensions={dims_summary};"
            f"dropped={result.dropped_count};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["query_eligibility_gate"] = ""

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

    def _stage_claim_evidence_alignment_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 4 — every claim must be chart-evidenced.

        Per Master Task §五: for each Provider Query, extract atomic
        clinical claims (LLM-backed), map each to a chart-verbatim
        EvidenceSpan, and run 9 deterministic CEA-XXX rules. Critical
        claims with no chart support are diagnosis-invention → BLOCK.

        On LLM extraction failure, the gate returns DEGRADED per query
        (no claims to validate) — those queries are kept; the
        semantic_necessity_gate downstream is the second line of defense.
        """
        from .claim_evidence_gate import extract_claims, apply_claim_evidence_to_case

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"

        # Skip LLM extraction entirely if there are no queries to check
        queries_snapshot = list(case.proposed_provider_queries)
        if queries_snapshot and case.chart_excerpt:
            try:
                llm = self._resolve_llm()
                coro = self._extract_claims_bulk(queries_snapshot, case.chart_excerpt, llm)
                per_query_results = _run_async(coro)
                for q, (claims, aligns) in zip(queries_snapshot, per_query_results):
                    q.claims = claims
                    q.claim_evidence_alignments = aligns
            except Exception as exc:  # DEGRADED — do not crash orchestrator
                logger.warning("claim_evidence_alignment_gate LLM bulk failed: %s", exc)
                for q in queries_snapshot:
                    q.claims = []
                    q.claim_evidence_alignments = []

        result = apply_claim_evidence_to_case(case)
        claims_extracted = sum(len(q.claims) for q in queries_snapshot)
        case.stage_run_ids["claim_evidence_alignment_gate"] = (
            f"claims_extracted={claims_extracted};"
            f"blocked={len(result.blocked_query_ids)};"
            f"flagged={len(result.flagged_query_ids)};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["claim_evidence_alignment_gate"] = trace_id
        # Stash run_id in the parallel dict for downstream visibility
        case.stage_run_ids["claim_evidence_alignment_gate::run_id"] = run_id

    def _stage_semantic_necessity_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 4 — LLM semantic necessity reviewer.

        Per Master Task §5.6: catches empty-chart diagnosis-invention
        (C09 pathology), symptom-only-no-evidence, no-imaging-no-site,
        no-severity-indicator-no-grade, lab-positive-not-equals-diagnosis,
        and complete-chart redundancy. BLOCK verdicts drop the query.

        On LLM failure per query, ``degraded=True`` and verdict="PASS"
        — the query survives so downstream NLQ gate can still run.
        """
        from .necessity_semantic import review_necessity

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"

        queries_snapshot = list(case.proposed_provider_queries)
        blocked_count = 0
        flagged_count = 0
        degraded_count = 0

        if queries_snapshot and case.chart_excerpt:
            try:
                llm = self._resolve_llm()
                coro = self._review_necessity_bulk(queries_snapshot, case.chart_excerpt, llm)
                per_query_results = _run_async(coro)
            except Exception as exc:  # DEGRADED — keep all queries
                logger.warning("semantic_necessity_gate LLM bulk failed: %s", exc)
                per_query_results = [None] * len(queries_snapshot)

            survivors: list[ProviderQuery] = []
            for q, res in zip(queries_snapshot, per_query_results):
                if res is None:
                    q.semantic_necessity_verdict = "DEGRADED"
                    q.semantic_necessity_degraded = True
                    degraded_count += 1
                    survivors.append(q)
                    continue
                q.semantic_necessity_verdict = res.verdict
                q.semantic_necessity_reason_codes = list(res.reason_codes)
                q.semantic_necessity_degraded = res.degraded
                if res.degraded:
                    degraded_count += 1
                if res.verdict == "BLOCK" and not res.degraded:
                    blocked_count += 1
                    continue  # drop
                if res.verdict == "REVIEW_REQUIRED":
                    flagged_count += 1
                survivors.append(q)
            case.proposed_provider_queries = survivors

        case.stage_run_ids["semantic_necessity_gate"] = (
            f"blocked={blocked_count};flagged={flagged_count};degraded={degraded_count};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["semantic_necessity_gate"] = trace_id
        case.stage_run_ids["semantic_necessity_gate::run_id"] = run_id

    # ------------------------------------------------------------------ LLM helpers

    @staticmethod
    def _get_llm() -> Any:
        """Lazy-import the singleton LLM service."""
        from app.services.llm_service import llm_service
        return llm_service

    def _resolve_llm(self) -> Any:
        """Resolve the LLM to use for gate-internal calls.

        Order of precedence:
          1. ``self.llm`` if explicitly injected
          2. ``self.runner.llm`` if the runner exposes one (test fixtures
             using ``RealCDIRunner(llm=mock)`` propagate it through)
          3. Production singleton ``llm_service``
        """
        if self.llm is not None:
            return self.llm
        runner_llm = getattr(self.runner, "llm", None)
        if runner_llm is not None:
            return runner_llm
        from app.services.llm_service import llm_service
        return llm_service

    @staticmethod
    async def _extract_claims_bulk(
        queries: list[ProviderQuery], chart: str, llm: Any
    ) -> list[tuple[list, list]]:
        """Run extract_claims concurrently across all queries."""
        from .claim_evidence_gate import extract_claims
        return await asyncio.gather(
            *(extract_claims(q, chart=chart, llm=llm) for q in queries)
        )

    @staticmethod
    async def _review_necessity_bulk(
        queries: list[ProviderQuery], chart: str, llm: Any
    ) -> list[Any]:
        """Run review_necessity concurrently across all queries."""
        from .necessity_semantic import review_necessity
        return await asyncio.gather(
            *(review_necessity(q, chart=chart, llm=llm) for q in queries)
        )

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
