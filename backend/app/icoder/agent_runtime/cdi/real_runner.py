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
minimal empty outputs so the orchestrator can finish local audit state.
Public REST/A2A adapters inspect both these traces and the orchestrator's
required safety-gate degradation state, then return 503 without publishing,
persisting, or signing a clinical result.

Sync vs async
=============

The orchestrator is sync (Gate 3 contract, kept stable for existing tests).
Production creates one request-scoped LLM client and one event-loop bridge for
the complete CDI run. Reusing a global ``AsyncOpenAI`` connection pool across
the short-lived loops created by repeated ``asyncio.run()`` calls causes
intermittent ``APIConnectionError`` failures on Windows/httpx.
"""

from __future__ import annotations

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
    provider_error_category: str = ""
    provider_http_status: int | None = None
    provider_attempt_count: int | None = None
    provider_retryable: bool | None = None
    expert_id: str = ""  # only set for expert_consultation sub-stages


_SAFE_PROVIDER_ERROR_CATEGORIES = frozenset({
    "authentication", "permission", "bad_request", "rate_limit", "timeout",
    "connection", "server_error", "circuit_open", "invalid_response", "unknown",
})


class _CDIStructuredResponseError(ValueError):
    """Content-free marker for an exhausted structured-output repair retry."""

    category = "invalid_response"
    status_code = None
    retryable = False

    def __init__(self, attempts: int) -> None:
        self.attempts = attempts
        super().__init__("CDI provider response did not satisfy the JSON contract.")


def _record_provider_failure(trace: StageTrace, exc: Exception) -> None:
    """Copy only bounded provider failure attributes into a stage trace."""
    category = str(getattr(exc, "category", "") or "").strip().lower()
    if category not in _SAFE_PROVIDER_ERROR_CATEGORIES:
        category = ""
    status = getattr(exc, "status_code", None)
    attempts = getattr(exc, "attempts", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError, OverflowError):
        status = None
    try:
        attempts = int(attempts) if attempts is not None else None
    except (TypeError, ValueError, OverflowError):
        attempts = None
    trace.provider_error_category = category
    trace.provider_http_status = status if status is not None and 100 <= status <= 599 else None
    trace.provider_attempt_count = attempts if attempts is not None and 0 <= attempts <= 10 else None
    retryable = getattr(exc, "retryable", None)
    trace.provider_retryable = retryable if isinstance(retryable, bool) else None
    trace.error_reason = (
        f"llm_call_failed:{category}" if category
        else f"llm_call_failed:{type(exc).__name__}"
    )


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
  ],
  "risk_flags": [
    {
      "category": "contradiction | unsupported_diagnosis | ambiguous_term | copied_forward_indicator",
      "description": "string",
      "evidence_span": {"document_id": "string", "quote": "string"}
    }
  ],
  "chart_completeness": {
    "is_complete": true,
    "reasoning": "string (1-2 sentences explaining why the chart is or isn't clinically complete for CDI purposes)",
    "missing_dimensions": ["type | site | severity | etiology | procedure | pathology | complications | course"]
  }
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
      "evidence_spans": [
        {"document_id": "string", "quote": "one VERBATIM contiguous chart span"}
      ],
      "query_text": "string (NON-LEADING: no 是不是/能否/can you confirm etc)",
      "response_options": ["A. ...", "B. ...", "C. ...", "D. 无法确定"],
      "priority": "routine | urgent"
    }
  ]
}
"""

_QUERY_DIMENSION_REWRITE_SCHEMA = """
{
  "queries": [
    {
      "source_query_id": "string (must match the supplied compound draft)",
      "query_id": "string",
      "gap_id": "string (must remain unchanged)",
      "topic": "string (one clinical dimension only)",
      "reason": "string",
      "evidence_span": {"document_id": "string", "quote": "string"},
      "evidence_spans": [
        {"document_id": "string", "quote": "one VERBATIM contiguous chart span"}
      ],
      "query_text": "string (one NON-LEADING clinical dimension only)",
      "response_options": ["A. ...", "B. ...", "C. ...", "D. unable to determine"],
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
    "Output ONLY valid JSON.\n\n"
    "Track H3.13 — RISK_FLAGS EMISSION (mandatory): In addition to gaps, "
    "you MUST scan the chart for the following risk signals and emit them "
    "in the ``risk_flags`` array:\n"
    "  - contradiction: the chart contains INTERNAL CONFLICT — e.g. "
    "diagnosis A stated in one place but contradicted elsewhere; "
    "lab/treatment inconsistent with documented diagnosis; conflicting "
    "descriptions of the same finding.\n"
    "  - unsupported_diagnosis: a diagnosis is asserted with NO clinical "
    "evidence in the chart (no symptoms, labs, imaging, or pathology).\n"
    "  - ambiguous_term: hedging language ('疑似', '可能', '待排除', "
    "'不排除') used in a way that obscures the final clinical conclusion.\n"
    "  - copied_forward_indicator: text suggesting copy-forward from "
    "prior encounter without update (e.g. identical phrasing across "
    "multiple days, stale timestamps).\n"
    "For each risk_flag, provide a verbatim evidence_span.quote from the "
    "chart. If the chart has no risk signals, emit an empty risk_flags "
    "array. Most clean charts will have 0 risk_flags.\n\n"
    "Track H3.13 — CHART_COMPLETENESS VERDICT (mandatory): In the "
    "``chart_completeness`` object, judge whether the chart is clinically "
    "complete FOR CDI PURPOSES — meaning it documents enough specificity "
    "(type, site, severity, etiology, procedure, pathology, complications, "
    "course) that NO clarification query would be needed before coding. "
    "Set ``is_complete=true`` ONLY when the chart's clinical scenario is "
    "fully specified for its category (e.g. a normal-delivery obstetric "
    "case doesn't need severity/etiology — it IS complete; a pneumonia "
    "case without pathogen or severity is NOT complete). Provide concise "
    "``reasoning`` and list any ``missing_dimensions``. When "
    "is_complete=true, the downstream eligibility gate will drop all "
    "candidate queries as spurious — so be conservative but accurate.\n\n"
    "Track H3.16 — LAB-POSITIVE UNCERTAIN (mandatory): A chart with an "
    "ABNORMAL lab value (e.g. \"便隐血阳性\", \"CA-125 升高\", \"HBsAg 阳性\", "
    "\"OGTT 异常\", \"血脂升高\") is NOT clinically complete solely because "
    "the lab is documented — the chart must also state the etiology / "
    "clinical correlation / planned workup. If the chart records an "
    "abnormal lab WITHOUT a corresponding etiology statement or explicit "
    "clinical-correlation, emit a ``clinical_correlation`` gap (category = "
    "\"clinical correlation unestablished\") asking the provider to clarify "
    "the clinical significance. Do NOT mark the chart is_complete=true in "
    "this scenario. The gap's evidence_span.quote should anchor on the "
    "abnormal lab value itself (e.g. \"CA-125 65 U/mL\"), and the "
    "minimal_clarification_needed should ask for clinical correlation, "
    "NOT for a specific diagnosis."
)


_QUERY_GENERATION_PROMPT = (
    "You are a CDI specialist performing Stage 4: provider query "
    "generation. Draft each query for exactly ONE gap and ONE clinical "
    "dimension. Normally emit exactly one NON-LEADING query per gap. "
    "Never merge separate gap_ids (for example severity and etiology) "
    "into one query; keep them as separate provider tasks. A contradiction "
    "may require separate branch queries for the same gap, but each branch "
    "must still remain single-dimension. "
    "RED LINES (forbidden): do NOT ask yes/no leading questions, do NOT "
    "reference ICD codes, DRG, CMI, or reimbursement. Each query MUST "
    "include ≥4 response_options including ≥1 escape hatch ('D. 无法确定' "
    "or equivalent). Be specific to the clinical situation. Output ONLY "
    "valid JSON.\n\n"
    "QUOTE-ANCHOR REQUIREMENT (Track H3.9 + H3.12 — strict substring, "
    "soft scope): evidence_span.quote MUST be a VERBATIM substring of "
    "the chart text — same characters, punctuation, and whitespace, no "
    "paraphrasing. The quote ANCHORS the gap (marks the chart location "
    "where the missing/ambiguous info should live); it does NOT need to "
    "contain the missing piece itself. For absence gaps (e.g. '病原体 "
    "未明确'), the anchor is the surrounding clinical context (e.g. "
    "'入院诊断:肺炎' or '痰培养阳性'). Reuse the gap's existing "
    "evidence_span.quote when present. Do NOT skip gaps just because "
    "the missing piece is not in the chart — that is the nature of an "
    "absence gap. Only skip a gap if the chart truly has no surrounding "
    "context for it."
)

_QUERY_DIMENSION_REWRITE_PROMPT = (
    "You are a CDI specialist repairing provider-query drafts that were "
    "withheld because they combined multiple clinical dimensions. For each "
    "supplied draft, emit AT MOST ONE replacement. The replacement must keep "
    "the exact source_query_id and gap_id, address only the clinical dimension "
    "named in target_axis, and MUST NOT use keywords from any other clinical "
    "axis in its topic or query text. The server will reject any result whose "
    "detected axis set is not exactly {target_axis}. Keep it non-leading, and "
    "include at least four "
    "response options with an unable-to-determine escape hatch. Do not add a "
    "new diagnosis, new gap, ICD code, DRG, CMI, or reimbursement language. "
    "Every evidence quote must be copied verbatim from the chart; use separate "
    "evidence_spans for non-contiguous facts. If a safe single-dimension rewrite "
    "cannot be produced from chart context, omit that draft. Output only JSON."
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

    # Injected for testability. Production creates a request-scoped client
    # lazily on the CDI bridge loop.
    llm: Any = None
    # When True, expert_consultation actually calls ExpertRunner. False
    # skips Expert calls (useful for offline tests).
    invoke_experts: bool = True
    # Captured per-stage trace metadata
    stage_traces: dict[str, StageTrace] = field(default_factory=dict)
    # Captured per-expert trace metadata (within expert_consultation)
    expert_traces: list[StageTrace] = field(default_factory=list)
    _owns_llm: bool = field(default=False, init=False, repr=False)
    # Phase 5 Track D P0.5 Gate 5 — per-case Expert route decisions
    # captured by the most recent expert_consultation stage call. The
    # orchestrator reads this after stage 3 finishes so specialist_trace
    # entries include route_decision/route_reason/execution_mode.
    last_route_result: Any = None
    # Captured per-expert trace metadata (inside expert_consultation)
    expert_traces: list[StageTrace] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.llm is None:
            self._owns_llm = True

    def begin_run(self) -> None:
        if self._owns_llm and self.llm is None:
            async def create_client() -> Any:
                # Construct AsyncOpenAI on the same running event loop that
                # will own every request and the final close operation.
                from app.services.llm_service import LLMService
                return LLMService()

            from .orchestrator import _run_async
            self.llm = _run_async(create_client())

    def end_run(self) -> None:
        if not self._owns_llm or self.llm is None:
            return
        close = getattr(self.llm, "aclose", None)
        if callable(close):
            from .orchestrator import _run_async
            _run_async(close())
        self.llm = None

    # ------------------------------------------------------------------ entry

    def __call__(self, stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Sync entry point — orchestrator calls this.

        Uses the CDI orchestrator's request-scoped event-loop bridge. The
        FastAPI handler runs the sync orchestrator in a worker thread.
        """
        from .orchestrator import _run_async
        return _run_async(self._async_call(stage, case, kwargs))

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
        if stage == "query_dimension_rewrite":
            return await self._stage_query_dimension_rewrite(case, kwargs)
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
                    _record_provider_failure(trace, e)
                    error_reason = trace.error_reason
                    # On LLM failure we mark this Expert DEGRADED (not
                    # the original execution_mode) so the audit trail
                    # reflects the actual outcome.
                    decision.execution_mode = "DEGRADED"
                    logger.warning(
                        "CDI expert_consultation %s failed (degraded): %s",
                        expert_id, type(e).__name__,
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
            f"- gap_id={g.gap_id}: {g.description} (priority={g.priority}) "
            f"[gap_type={g.gap_type or 'unspecified'}] "
            f"[anchor_hint={g.evidence_span.quote!r}]"
            for g in case.documentation_gaps[:8]  # cap prompt size
        )

        # Track H3.14 — Contradiction / uncertainty amplifier.
        #
        # When the case carries a contradiction or ambiguous_term risk_flag,
        # the chart has internal conflict or hedged conclusions that need
        # disambiguation. A single consolidated query typically picks one
        # side and drops the other. The amplifier instructs the LLM to
        # emit TWO queries per conflict — one for each side — so the
        # clinician can clarify both branches.
        #
        # This lifts the document_conflict and lab_positive_uncertain
        # categories from ~0.6 avg queries/case toward the Corti baseline
        # (2.4 / 2.2).
        rf_categories = {rf.category for rf in (case.risk_flags or [])}
        has_contradiction = "contradiction" in rf_categories
        has_ambiguity = "ambiguous_term" in rf_categories
        amplifier_hint = ""
        if has_contradiction or has_ambiguity:
            signal_label = []
            if has_contradiction:
                signal_label.append("contradiction")
            if has_ambiguity:
                signal_label.append("ambiguity")
            amplifier_hint = (
                f"\n\n"
                f"AMPLIFIER (Track H3.14 — mandatory when risk_flags "
                f"present): This case carries risk_flag category="
                f"{'+'.join(signal_label)}. For each gap that touches the "
                f"conflicting/ambiguous clinical fact, emit TWO queries — "
                f"one exploring each branch of the conflict. Example: if "
                f"the chart says both '肺炎' and '肺部感染待查', emit one "
                f"query asking whether bacterial pneumonia is confirmed "
                f"and a second query asking whether alternative diagnoses "
                f"were considered. Do NOT consolidate conflicting branches "
                f"into a single multi-axis query — single-dimension "
                f"queries are required by the downstream gate.\n"
            )

        prompt = (
            f"For each gap below, draft a NON-LEADING provider query as a "
            f"separate task. "
            f"GAP COVERAGE (mandatory): each output query must reference exactly "
            f"one listed gap_id and must ask only about that gap's single clinical "
            f"dimension. Do not combine content from another gap into its topic, "
            f"query_text, or response_options. Unless the risk-flag branch rule "
            f"below applies, emit exactly one query for every listed gap that has "
            f"chart context. "
            f"QUOTE-ANCHOR PROCEDURE (Track H3.12 — mandatory):\n"
            f"  Step 1. Identify the gap type: absence (missing info), "
            f"ambiguity (unclear info), or contradiction (conflicting info).\n"
            f"  Step 2. Find a 5-30 character span of chart text that "
            f"ANCHORS the gap — i.e. the chart location where the missing/"
            f"ambiguous/contradictory info should live. The anchor does NOT "
            f"need to contain the missing piece itself. For absence gaps "
            f"('X 未明确' / 'X not documented'), use the surrounding "
            f"clinical context as the anchor.\n"
            f"  Step 3. Copy the anchor span VERBATIM (same characters, "
            f"punctuation, whitespace — no paraphrasing). If the gap's "
            f"anchor_hint is non-empty, prefer reusing it.\n"
            f"  Step 4. Draft the query_text + ≥4 response_options "
            f"(including an escape hatch). Never introduce a numeric clinical "
            f"threshold, dose, measurement, or time window unless that exact "
            f"quantity appears verbatim in the chart.\n"
            f"  Step 5. Only skip a gap if the chart has NO surrounding "
            f"context for it at all (very rare)."
            f"{amplifier_hint}\n\n"
            f"Each query MUST cite evidence_span.quote = verbatim anchor "
            f"span. If one query relies on facts from non-contiguous chart "
            f"locations, set evidence_spans to one separate VERBATIM item per "
            f"location and set evidence_span equal to the first item. Never "
            f"concatenate separated chart fragments into one quote. "
            f"Paraphrased or concatenated quotes will fail closed. "
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

    async def _stage_query_dimension_rewrite(
        self, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Make one bounded repair attempt for withheld compound drafts."""

        items = list(kwargs.get("rewrite_items") or [])[:8]
        if not items:
            return {"queries": [], "run_id": "", "trace_id": ""}
        prompt = (
            "Repair the compound drafts below. Each item includes the only gap "
            "its replacement may address and one server-selected target_axis. "
            "Return at most one replacement per "
            "source_query_id.\n\n"
            f"Schema:\n{_QUERY_DIMENSION_REWRITE_SCHEMA}\n\n"
            f"Rewrite items:\n{json.dumps(items, ensure_ascii=False)}\n\n"
            f"Chart:\n{case.chart_excerpt}"
        )
        return await self._llm_call_structured(
            stage="query_dimension_rewrite",
            system_prompt=_QUERY_DIMENSION_REWRITE_PROMPT,
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
            for structured_attempt in range(2):
                repair_instruction = (
                    "\n\nYour prior response did not satisfy the JSON contract. "
                    "Return exactly one valid JSON object matching the schema; "
                    "do not add markdown or prose."
                    if structured_attempt else ""
                )
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt + repair_instruction,
                    temperature=0.1,
                    response_format="json",
                )
                content = response.get("content", "") if isinstance(response, dict) else ""
                usage = response.get("usage", {}) if isinstance(response, dict) else {}
                trace.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
                trace.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
                trace.total_tokens += int(usage.get("total_tokens", 0) or 0)
                try:
                    parsed = _parse_json(content)
                except (TypeError, ValueError) as exc:
                    if structured_attempt == 0:
                        logger.warning(
                            "CDI stage %s returned invalid structured output; "
                            "performing one bounded repair retry",
                            stage,
                        )
                        continue
                    raise _CDIStructuredResponseError(attempts=2) from exc
                trace.latency_ms = int((time.perf_counter() - t0) * 1000)
                return {
                    **parsed,
                    "run_id": trace.run_id,
                    "trace_id": trace.trace_id,
                }
            raise _CDIStructuredResponseError(attempts=2)  # pragma: no cover
        except Exception as e:
            trace.degraded = True
            _record_provider_failure(trace, e)
            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "CDI stage %s failed (degraded): %s", stage, type(e).__name__,
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
