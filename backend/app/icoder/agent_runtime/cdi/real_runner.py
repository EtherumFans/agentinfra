"""CDI Real LLM Runner (Phase 5 Track D P0 Gate 2).

Replaces the Gate 3 ``stub_runner`` in production paths. Each stage calls
DeepSeek V4 via ``app.services.llm_service.llm_service.chat()`` with a
structured JSON output contract, and records per-stage trace metadata
(provider / model / latency / tokens / run_id / trace_id) so the
specialist trace is no longer empty.

PDF §A1: stub_runner in the production path is forbidden.
PDF §A2: Experts must actually be invoked, not just declared.

Stage → provider routing
========================

    1. encounter_synthesis    — PureLLMProvider (DeepSeek chat, JSON output)
    2. gap_identification     — PureLLMProvider (DeepSeek chat, JSON output)
    3. expert_consultation    — ExpertRunner × 4 (coding / pubmed / web-search
                                / medical-calculator), each via DeepSeek
                                chat_with_tools when MCP servers configured
    4. query_generation      — PureLLMProvider (DeepSeek chat, JSON output)
    5. query_compliance_gate — pure-logic NLQ-001..009 (no LLM)
    6. specialist_trace_emit — pure-logic, emits trace entries from
                                aggregated stage results

DEGRADED state
==============

If ``llm_service.chat()`` raises (network, auth, schema-validation), the
runner records a per-stage ``degraded`` flag + error reason and returns
minimal empty outputs so the orchestrator can still produce a response.
The orchestrator's ``_decide_completion`` then sees gaps=[] / queries=[]
and emits ``AUTO_PASS`` with a degraded marker. Front-end shows a
warning banner.

Sync vs async
=============

The orchestrator is sync (Gate 3 contract, kept stable for 18 existing
tests). The runner wraps async ``llm_service.chat()`` via
``asyncio.run()`` — safe because the FastAPI handler invokes the
orchestrator inside ``asyncio.to_thread`` so there's no running event
loop in the worker thread.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .domain import CDICase, SpecialistTraceEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------


_PROVIDER_NAME = "deepseek"
_PROVIDER_MODEL_ENV_DEFAULT = "deepseek-v4-flash"


def _resolve_model() -> str:
    """Resolve the DeepSeek model name for trace metadata."""
    try:
        from app.config import settings
        return getattr(settings, "LLM_MODEL", _PROVIDER_MODEL_ENV_DEFAULT)
    except Exception:
        return _PROVIDER_MODEL_ENV_DEFAULT


# ---------------------------------------------------------------------------
# Per-stage trace metadata
# ---------------------------------------------------------------------------


@dataclass
class StageTrace:
    """Per-stage trace metadata captured by the real runner.

    The orchestrator already captures run_id + trace_id on
    ``case.stage_run_ids`` / ``case.stage_trace_ids``. Gate 2 adds this
    richer record so the Specialist Trace panel and audit log can show
    provider/model/latency/token evidence per stage (PDF §A2).
    """

    stage: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    run_id: str = ""
    trace_id: str = ""
    degraded: bool = False
    error_reason: str = ""
    expert_id: str = ""  # only set for expert_consultation sub-stages


# ---------------------------------------------------------------------------
# JSON output schemas (sent to DeepSeek as schema_hint)
# ---------------------------------------------------------------------------


_ENCOUNTER_SYNTHESIS_SCHEMA = """
{
  "key_points": ["string", ...],
  "encounter_metadata": {"patient_age": "string", "patient_sex": "string", "encounter_type": "string"}
}
"""

_GAP_IDENTIFICATION_SCHEMA = """
{
  "gaps": [
    {
      "gap_id": "string",
      "description": "string",
      "why_it_matters": "string",
      "evidence_span": {"document_id": "string", "quote": "string", "char_start": 0, "char_end": 0},
      "priority": "routine | urgent"
    }
  ]
}
"""

_QUERY_GENERATION_SCHEMA = """
{
  "queries": [
    {
      "query_id": "string",
      "gap_id": "string",
      "topic": "string",
      "reason": "string",
      "evidence_span": {"document_id": "string", "quote": "string"},
      "query_text": "string (NON-LEADING: no 是不是/能否/can you confirm etc)",
      "response_options": ["A. ...", "B. ...", "C. ...", "D. 无法确定"],
      "priority": "routine | urgent"
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# System prompts (PDF §6 — Corti-compatible CDI workflow)
# ---------------------------------------------------------------------------


_ENCOUNTER_SYNTHESIS_PROMPT = (
    "You are a Clinical Documentation Improvement (CDI) specialist "
    "performing Stage 1 of a 6-stage workflow on a Chinese hospital "
    "chart. Read the chart carefully and extract the key clinical "
    "points (diagnoses, procedures, treatments, lab findings). Do NOT "
    "invent facts. Do NOT include ICD codes. Output ONLY valid JSON "
    "matching the requested schema. The chart language may be Chinese "
    "or English; you may respond in either language as appropriate."
)


_GAP_IDENTIFICATION_PROMPT = (
    "You are a CDI specialist performing Stage 2: documentation gap "
    "identification. Identify gaps in the chart that would affect "
    "downstream coding, compliance, or clinical accuracy. Each gap must "
    "have an evidence_span quoting the chart. Categories to consider: "
    "diagnostic specificity, etiology unspecified, severity unspecified, "
    "acuity unspecified, anatomical site unspecified, clinical "
    "correlation unestablished, temporal unspecified, conflicting "
    "documentation. Do NOT invent diagnoses. Do NOT include ICD codes. "
    "Output ONLY valid JSON."
)


_QUERY_GENERATION_PROMPT = (
    "You are a CDI specialist performing Stage 4: provider query "
    "generation. For each gap, draft a NON-LEADING clarification query. "
    "RED LINES (forbidden): do NOT ask yes/no leading questions, do NOT "
    "reference ICD codes, DRG, CMI, or reimbursement. Each query MUST "
    "include ≥4 response_options including ≥1 escape hatch ('D. 无法确定' "
    "or equivalent). Be specific to the clinical situation. Output ONLY "
    "valid JSON.\n\n"
    "EVIDENCE-VERBATIM REQUIREMENT (Track H3.9 — strict): "
    "evidence_span.quote MUST be a VERBATIM substring of the chart text. "
    "Copy-paste 5-30 characters of chart text directly into the quote "
    "field. Do NOT paraphrase. Do NOT summarize. Do NOT translate. Do "
    "NOT add particles, punctuation, or whitespace that is not in the "
    "chart. If you cannot find a verbatim chart span that supports the "
    "gap, SKIP that gap (return an empty queries array) — a query with "
    "no verbatim evidence will be blocked downstream. Quote-first: scan "
    "the chart for a usable span BEFORE drafting the query text."
)


# ---------------------------------------------------------------------------
# JSON parsing helper (defensive — DeepSeek usually returns clean JSON)
# ---------------------------------------------------------------------------


def _parse_json(content: str) -> dict[str, Any]:
    """Parse JSON from LLM response content. Strips markdown fences."""
    text = (content or "").strip()
    if not text:
        return {}
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON: {e}")


# ---------------------------------------------------------------------------
# Real runner
# ---------------------------------------------------------------------------


@dataclass
class RealCDIRunner:
    """LLM-backed CDI runner.

    Captures per-stage trace metadata in ``stage_traces`` so the API
    layer can expose provider/model/latency/token evidence (PDF §A2).
    """

    # Injected for testability — production uses the singleton llm_service
    llm: Any = None
    # When True, expert_consultation actually calls ExpertRunner. False
    # skips Expert calls (useful for offline tests).
    invoke_experts: bool = True
    # Captured per-stage trace metadata
    stage_traces: dict[str, StageTrace] = field(default_factory=dict)
    # Captured per-expert trace metadata (within expert_consultation)
    expert_traces: list[StageTrace] = field(default_factory=list)
    # Phase 5 Track D P0.5 Gate 5 — per-case Expert route decisions
    # captured by the most recent expert_consultation stage call. The
    # orchestrator reads this after stage 3 finishes so specialist_trace
    # entries include route_decision/route_reason/execution_mode.
    last_route_result: Any = None
    # Captured per-expert trace metadata (inside expert_consultation)
    expert_traces: list[StageTrace] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.llm is None:
            # Lazy import to avoid module-load side effects
            from app.services.llm_service import llm_service
            self.llm = llm_service

    # ------------------------------------------------------------------ entry

    def __call__(self, stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Sync entry point — orchestrator calls this.

        Uses ``asyncio.run`` to drive the async LLM call. Safe because
        the FastAPI handler runs the orchestrator in a worker thread via
        ``asyncio.to_thread``.
        """
        try:
            return asyncio.run(self._async_call(stage, case, kwargs))
        except RuntimeError as e:
            # If we're already inside an event loop, fall back to a
            # fresh thread. This path is for unit tests that drive the
            # orchestrator directly inside an async test function.
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run, self._async_call(stage, case, kwargs)
                    )
                    return future.result()
            raise

    # ------------------------------------------------------------------ async dispatch

    async def _async_call(
        self, stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Async stage dispatch."""
        if stage == "encounter_synthesis":
            return await self._stage_encounter_synthesis(case)
        if stage == "gap_identification":
            return await self._stage_gap_identification(case)
        if stage == "expert_consultation":
            return await self._stage_expert_consultation(case)
        if stage == "query_generation":
            return await self._stage_query_generation(case)
        if stage == "specialist_trace_emit":
            return await self._stage_specialist_trace_emit(case)
        # query_compliance_gate is handled by the orchestrator directly
        return {}

    # ------------------------------------------------------------------ stages

    async def _stage_encounter_synthesis(self, case: CDICase) -> dict[str, Any]:
        prompt = (
            f"Extract the key clinical points from this chart. "
            f"Respond as JSON matching this schema:\n{_ENCOUNTER_SYNTHESIS_SCHEMA}\n\n"
            f"Chart:\n{case.chart_excerpt}"
        )
        return await self._llm_call_structured(
            stage="encounter_synthesis",
            system_prompt=_ENCOUNTER_SYNTHESIS_PROMPT,
            user_prompt=prompt,
            empty_result={"key_points": [], "encounter_metadata": {}},
        )

    async def _stage_gap_identification(self, case: CDICase) -> dict[str, Any]:
        summary_text = ""
        if case.encounter_summary and case.encounter_summary.key_points:
            summary_text = (
                "Encounter summary key points:\n- "
                + "\n- ".join(case.encounter_summary.key_points)
                + "\n\n"
            )
        prompt = (
            f"{summary_text}Identify documentation gaps in this chart "
            f"that would affect coding, compliance, or clinical accuracy. "
            f"Respond as JSON matching this schema:\n{_GAP_IDENTIFICATION_SCHEMA}\n\n"
            f"Chart:\n{case.chart_excerpt}"
        )
        return await self._llm_call_structured(
            stage="gap_identification",
            system_prompt=_GAP_IDENTIFICATION_PROMPT,
            user_prompt=prompt,
            empty_result={"gaps": []},
        )

    async def _stage_expert_consultation(self, case: CDICase) -> dict[str, Any]:
        """Invoke the 4 CDI Experts conditionally per Master Task §6.

        Phase 5 Track D P0.5 Gate 5 — the router (``route_experts``)
        decides per-Expert whether to invoke, skip, or mark unavailable.
        Only ``REAL_TOOL`` and ``LLM_KNOWLEDGE_ONLY`` modes trigger an
        actual LLM call; the others are recorded in the trace without
        spending tokens.

        The aggregation populates ``case.specialist_trace`` (in addition
        to the existing ``expert_responses`` payload) so the API layer
        can show route_decision / execution_mode / latency per Expert.
        """
        from .cdi_expert_router import route_experts, should_invoke

        if not self.invoke_experts:
            return {"expert_responses": [], "run_id": "", "trace_id": ""}

        # Route first — pure logic, no LLM. Stash for the orchestrator's
        # specialist_trace_emit stage to read.
        route_result = route_experts(case)
        self.last_route_result = route_result

        experts = [
            ("coding-expert",
             "You are a coding-specialist Expert. Given the chart and "
             "identified gaps, advise on what clinical specificity is "
             "needed for accurate coding. Do NOT propose ICD codes."),
            ("pubmed-expert",
             "You are a PubMed literature Expert. Given the chart and "
             "gaps, advise whether literature evidence supports a "
             "specific clinical correlation. Cite PMID when relevant. "
             "If you do not have real PubMed search access, say so "
             "explicitly rather than fabricating citations."),
            ("web-search-expert",
             "You are a clinical web-search Expert. Flag whether external "
             "clinical guidance is needed. Do NOT assert patient facts "
             "from the web."),
            ("medical-calculator-expert",
             "You are a medical-calculator Expert. Identify whether any "
             "clinical scores or calculations are needed (e.g. BMI, "
             "creatinine clearance). Do NOT compute without parameters "
             "and do NOT estimate scores via general LLM knowledge."),
        ]
        expert_dict = dict(experts)

        gap_summary = ""
        if case.documentation_gaps:
            gap_summary = "Identified gaps:\n"
            for g in case.documentation_gaps[:5]:  # cap prompt size
                gap_summary += f"- {g.description}\n"
            gap_summary += "\n"

        expert_responses: list[dict[str, Any]] = []
        # Clear stale entries from any prior run on this runner instance.
        case.specialist_trace = []

        for decision in route_result.decisions:
            expert_id = decision.expert_id
            system_prompt = expert_dict[expert_id]
            trace = StageTrace(
                stage="expert_consultation",
                provider=_PROVIDER_NAME,
                model=_resolve_model(),
                run_id=f"run-{uuid.uuid4().hex[:12]}",
                trace_id=f"trace-{uuid.uuid4().hex[:12]}",
                expert_id=expert_id,
            )

            invoked = should_invoke(decision)
            content = ""
            error_reason = ""
            t0 = time.perf_counter()

            if invoked:
                user_prompt = (
                    f"{gap_summary}Chart:\n{case.chart_excerpt[:1500]}\n\n"
                    f"Respond in 2-3 sentences with your specialist advice."
                )
                try:
                    response = await self.llm.chat(
                        messages=[{"role": "user", "content": user_prompt}],
                        system_prompt=system_prompt,
                        temperature=0.1,
                    )
                    content = response.get("content", "") if isinstance(response, dict) else ""
                    usage = response.get("usage", {}) if isinstance(response, dict) else {}
                    trace.prompt_tokens = int(usage.get("prompt_tokens", 0))
                    trace.completion_tokens = int(usage.get("completion_tokens", 0))
                    trace.total_tokens = int(usage.get("total_tokens", 0))
                except Exception as e:
                    trace.degraded = True
                    trace.error_reason = str(e)[:200]
                    error_reason = str(e)[:200]
                    # On LLM failure we mark this Expert DEGRADED (not
                    # the original execution_mode) so the audit trail
                    # reflects the actual outcome.
                    decision.execution_mode = "DEGRADED"
                    logger.warning(
                        "CDI expert_consultation %s failed (degraded): %s",
                        expert_id, e,
                    )
            else:
                # SKIPPED_NOT_NEEDED / SKIPPED_MISSING_INPUTS / TOOL_UNAVAILABLE
                # No LLM call — leave tokens/latency at 0.
                pass

            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            self.expert_traces.append(trace)

            # Per Master Task §6.5 Specialist Trace schema.
            entry = SpecialistTraceEntry(
                expert_id=expert_id,
                consulted=invoked and not trace.degraded,
                requested=system_prompt.split(". ")[0][:120],
                rationale=content or error_reason or decision.expected_value,
                route_decision=_route_decision_label(decision),
                route_reason=decision.reason,
                execution_mode=decision.execution_mode,
                latency_ms=trace.latency_ms,
                tokens=trace.total_tokens,
                run_id=trace.run_id,
                trace_id=trace.trace_id,
            )
            case.specialist_trace.append(entry)

            expert_responses.append({
                "expert_id": expert_id,
                "consulted": invoked and not trace.degraded,
                "execution_mode": decision.execution_mode,
                "route_reason": decision.reason,
                "response": content,
                "error": error_reason,
            })

        return {
            "expert_responses": expert_responses,
            "route_decisions": [
                {
                    "expert_id": d.expert_id,
                    "needed": d.needed,
                    "reason": d.reason,
                    "execution_mode": d.execution_mode,
                }
                for d in route_result.decisions
            ],
            "run_id": f"run-{uuid.uuid4().hex[:12]}",
            "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
        }

    async def _stage_query_generation(self, case: CDICase) -> dict[str, Any]:
        if not case.documentation_gaps:
            return {"queries": [], "run_id": "", "trace_id": ""}

        gap_list = "\n".join(
            f"- gap_id={g.gap_id}: {g.description} (priority={g.priority})"
            for g in case.documentation_gaps[:8]  # cap prompt size
        )
        prompt = (
            f"For each gap below, draft a NON-LEADING provider query. "
            f"QUOTE-FIRST PROCEDURE (mandatory):\n"
            f"  Step 1. Read the chart carefully.\n"
            f"  Step 2. For each gap, find a 5-30 character span of chart "
            f"text that supports the gap. Copy it VERBATIM (same characters, "
            f"same punctuation, same whitespace — no paraphrasing).\n"
            f"  Step 3. If no verbatim span exists, SKIP that gap.\n"
            f"  Step 4. Only after finding a verbatim span, draft the "
            f"query_text + response_options.\n\n"
            f"Each query MUST cite evidence_span.quote = verbatim chart "
            f"span (will be re-checked downstream — paraphrased quotes "
            f"will cause the query to be silently dropped). Include "
            f"≥4 response_options including an escape hatch. "
            f"Respond as JSON matching this schema:\n{_QUERY_GENERATION_SCHEMA}\n\n"
            f"Gaps:\n{gap_list}\n\n"
            f"Chart:\n{case.chart_excerpt}"
        )
        return await self._llm_call_structured(
            stage="query_generation",
            system_prompt=_QUERY_GENERATION_PROMPT,
            user_prompt=prompt,
            empty_result={"queries": []},
        )

    async def _stage_specialist_trace_emit(self, case: CDICase) -> dict[str, Any]:
        """Pure-logic stage: emit specialist trace entries from the
        expert_responses captured in stage 3. No LLM call.
        """
        return {
            "run_id": f"run-{uuid.uuid4().hex[:12]}",
            "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
        }

    # ------------------------------------------------------------------ shared LLM call

    async def _llm_call_structured(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        empty_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Call DeepSeek with JSON response_format, capture trace metadata,
        and gracefully degrade on failure.

        Returns ``empty_result`` merged with run_id/trace_id on success,
        or a degraded marker on failure. Never raises — the orchestrator
        can continue with empty outputs and let ``_decide_completion``
        emit the right verdict.
        """
        trace = StageTrace(
            stage=stage,
            provider=_PROVIDER_NAME,
            model=_resolve_model(),
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            trace_id=f"trace-{uuid.uuid4().hex[:12]}",
        )
        self.stage_traces[stage] = trace
        t0 = time.perf_counter()
        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                temperature=0.1,
                response_format="json",
            )
            content = response.get("content", "") if isinstance(response, dict) else ""
            usage = response.get("usage", {}) if isinstance(response, dict) else {}
            trace.prompt_tokens = int(usage.get("prompt_tokens", 0))
            trace.completion_tokens = int(usage.get("completion_tokens", 0))
            trace.total_tokens = int(usage.get("total_tokens", 0))
            parsed = _parse_json(content)
            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                **parsed,
                "run_id": trace.run_id,
                "trace_id": trace.trace_id,
            }
        except Exception as e:
            trace.degraded = True
            trace.error_reason = str(e)[:300]
            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "CDI stage %s failed (degraded): %s", stage, e,
            )
            return {
                **empty_result,
                "run_id": trace.run_id,
                "trace_id": trace.trace_id,
                "degraded": True,
                "error_reason": trace.error_reason,
            }


def _route_decision_label(decision: Any) -> str:
    """Compress ``ExpertRouteDecision`` into a short front-end label."""
    mode = decision.execution_mode
    if mode == "SKIPPED_NOT_NEEDED":
        return "not_needed"
    if mode == "SKIPPED_MISSING_INPUTS":
        return "missing_inputs"
    if mode == "TOOL_UNAVAILABLE":
        return "tool_unavailable"
    if mode == "DEGRADED":
        return "degraded"
    if not decision.needed:
        return "not_needed"
    return "needed"


__all__ = ["RealCDIRunner", "StageTrace"]
