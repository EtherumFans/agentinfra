"""Built-in CodingMethod implementations.

10 methods are registered automatically by :func:`register_builtin_methods`
(imported from :mod:`icoder_runtime.methods.__init__`):

  MedCodER (NAACL 2025 Industry Track 5-stage pipeline):
    - medcoder.full             — 5-stage end-to-end
    - medcoder.prompt           — Stage 1 only (LLM initial codes)
    - medcoder.retrieve         — Stage 2 only (BGE-M3 + FAISS, no LLM)
    - medcoder.prompt+retrieve  — Stages 1+2 (no rerank, no compliance)
    - medcoder.code_like_humans — CLH 4-step (Triage→Index→Drill→Evidence)

  Legacy (pre-MedCodER pipelines, retained for back-compat):
    - legacy.deepseek   — DeepSeek V4 + RuleEngine (production default)
    - legacy.prompt_llm — Generic LLM + RuleEngine (fallback)
    - legacy.hybrid     — Auto-select (default legacy dispatch)
    - legacy.no_repair  — Hybrid with repair loop disabled

  No-op:
    - noop.unavailable  — Returns empty result for empty input

Each method delegates to the canonical strategy / adapter / experts
(no logic duplication) and converts the returned schema into a
:class:`MethodResult`. Per-stage timing is captured via a simple
monotonic clock so the trace viewer can render a timeline.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from official_agents.medical_coding.modes import Mode, MEDCODER_MODES, LEGACY_MODES
from official_agents.medical_coding.schema import (
    CodingIssue,
    DiagnosisEntry,
    ExtractedDiagnosis,
    MedicalCodingOutputSchema,
    ProcedureEntry,
)

from .base import (
    CodingMethod,
    MethodCapability,
    MethodFamily,
    MethodResult,
    MethodStageTraceEntry,
)
from .registry import GLOBAL_REGISTRY

logger = logging.getLogger(__name__)


# ── Helpers ──


def _emr_to_messages(emr_text: str) -> list[dict[str, str]]:
    """Wrap a raw EMR string in the message-list shape that
    ``CodingEngineAdapter.infer_async`` expects."""
    return [{"role": "user", "content": emr_text or ""}]


def _schema_to_method_result(
    method: "CodingMethod",
    schema: MedicalCodingOutputSchema,
    stage_trace: list[MethodStageTraceEntry],
    processing_time_ms: int,
    status: str = "ok",
    reason: str = "",
) -> MethodResult:
    """Convert a ``MedicalCodingOutputSchema`` to a :class:`MethodResult`.

    Centralized so all builtin methods produce identical flattening
    (frontend comparison depends on this shape being stable).
    """
    pd = schema.primary_diagnosis or DiagnosisEntry()
    secondary = [
        {
            "code": d.code,
            "name": d.description,
            "confidence": d.confidence,
            "category": d.category,
        }
        for d in (schema.secondary_diagnoses or [])
        if isinstance(d, DiagnosisEntry)
    ]
    procedures = [
        {
            "code": p.code,
            "name": p.description,
            "confidence": p.confidence,
            "category": p.category,
        }
        for p in (schema.procedures or [])
        if p.code
    ]
    issues = [
        {
            "severity": i.severity,
            "code": i.code,
            "message": i.message,
            "suggestion": i.suggestion,
        }
        for i in (schema.issues_found or [])
    ]
    return MethodResult(
        method_id=method.method_id,
        method_name=method.method_name,
        method_family=method.method_family,
        status=status,
        reason=reason or schema.notes or "",
        primary_code=pd.code or "",
        primary_name=pd.description or "",
        primary_confidence=pd.confidence,
        secondary_codes=secondary,
        procedure_codes=procedures,
        issues=issues,
        manual_review_required=bool(schema.manual_review_required),
        confidence=schema.confidence,
        stage_trace=stage_trace,
        processing_time_ms=processing_time_ms,
        full_schema=schema.to_dict(),
    )


def _stage(name: str, t0: float, status: str = "ok", output_size: int = 0, notes: str = "") -> MethodStageTraceEntry:
    """Build a stage trace entry from a monotonic start time."""
    return MethodStageTraceEntry(
        stage_name=name,
        status=status,
        latency_ms=int((time.monotonic() - t0) * 1000),
        output_size=output_size,
        notes=notes,
    )


# ── MedCodER methods (delegate to MedCodERStrategy) ──


class _MedCodERMethodBase(CodingMethod):
    """Shared scaffolding for the 4 MedCodER variants.

    Each subclass sets ``variant_name`` (one of ``MedCodERStrategy.VARIANTS``).
    The run() method is identical except for that variant, so the logic
    lives here to avoid 4x duplication.
    """

    method_family = MethodFamily.MEDCODER.value
    required_capabilities = (MethodCapability.LLM, MethodCapability.RETRIEVER, MethodCapability.RULE_SET)
    variant_name: str = "full"  # overridden by subclass

    def __init__(self, gateway=None, retriever=None) -> None:
        self._gateway = gateway
        self._retriever = retriever
        self._strategy = None  # lazy

    def _get_strategy(self):
        if self._strategy is None:
            from icoder_runtime.providers.medical_coding.medcoder_strategy import MedCodERStrategy
            self._strategy = MedCodERStrategy(
                gateway=self._gateway,
                retriever=self._retriever,
            )
        return self._strategy

    async def run(self, emr_text: str, ctx: dict[str, Any] | None = None) -> MethodResult:
        emr_text = (emr_text or "").strip()
        ctx = ctx or {}
        t_total = time.monotonic()
        trace: list[MethodStageTraceEntry] = []

        if not emr_text:
            trace.append(_stage("input_validation", time.monotonic(), status="noop", notes="empty emr_text"))
            res = _schema_to_method_result(
                self,
                MedicalCodingOutputSchema.mock_result("medcoder"),
                trace,
                processing_time_ms=int((time.monotonic() - t_total) * 1000),
                status="unavailable",
                reason="empty emr_text",
            )
            res.full_schema = None
            return res

        # Stage 1 — Extraction (LLM)
        t1 = time.monotonic()
        strategy = self._get_strategy()
        extraction = await strategy.stage1_extraction(emr_text)
        n_extracted = len(extraction or [])
        trace.append(_stage(
            "stage1_extraction", t1,
            status="ok" if n_extracted else "noop",
            output_size=n_extracted,
            notes=f"LLM call → {n_extracted} diseases",
        ))

        # For non-full variants we just dispatch and let the strategy
        # compose the stages; we record the variant name as a synthetic
        # single stage. Per-disease traces are visible in
        # ``full_schema.extracted_diagnoses[*].stage_trace`` if exposed.
        t_run = time.monotonic()
        schema = await strategy.run_variant(emr_text, variant=self.variant_name, ctx=ctx)
        trace.append(_stage(
            f"variant_{self.variant_name}", t_run,
            status="ok",
            output_size=n_extracted,
            notes=f"MedCodERStrategy.run_variant={self.variant_name}",
        ))

        # Stage 5 surface (always recorded; non-full variants use a
        # compliance-light version that still produces a schema)
        t5 = time.monotonic()
        n_issues = len(schema.issues_found)
        trace.append(_stage(
            "stage5_compliance", t5,
            status="ok",
            output_size=n_issues,
            notes=f"{n_issues} issues, review_conclusion={schema.review_conclusion}",
        ))

        processing_ms = int((time.monotonic() - t_total) * 1000)
        return _schema_to_method_result(self, schema, trace, processing_ms)


class MedCodERFullMethod(_MedCodERMethodBase):
    method_id = "medcoder.full"
    method_name = "MedCodER 完整管线"
    method_name_en = "MedCodER Full Pipeline"
    stage_count = 5
    variant_name = "full"
    description = "5 阶段完整管线 (NAACL 2025): Extraction → Retrieval → Merge → Re-rank → Compliance."


class MedCodERPromptMethod(_MedCodERMethodBase):
    method_id = "medcoder.prompt"
    method_name = "MedCodER 仅 Prompt"
    method_name_en = "MedCodER Prompt Only"
    stage_count = 1
    variant_name = "prompt"
    description = "仅 Stage 1 (LLM 初始编码), 不做检索/重排."


class MedCodERRetrieveMethod(_MedCodERMethodBase):
    method_id = "medcoder.retrieve"
    method_name = "MedCodER 仅检索"
    method_name_en = "MedCodER Retrieve Only"
    stage_count = 1
    variant_name = "retrieve"
    description = "仅 Stage 2 (BGE-M3 + FAISS), 无 LLM 抽取/重排."


class MedCodERPromptRetrieveMethod(_MedCodERMethodBase):
    method_id = "medcoder.prompt+retrieve"
    method_name = "MedCodER Prompt + 检索"
    method_name_en = "MedCodER Prompt + Retrieve"
    stage_count = 2
    variant_name = "prompt+retrieve"
    description = "Stage 1+2 (LLM 抽取 + 检索), 无重排/合规."


# ── Legacy methods (delegate to HybridCodingAdapter) ──


class _LegacyMethodBase(CodingMethod):
    """Shared scaffolding for the 4 legacy variants."""

    method_family = MethodFamily.LEGACY.value
    required_capabilities = (MethodCapability.LLM, MethodCapability.RULE_SET)
    mode_value: Mode = Mode.HYBRID  # overridden by subclass

    def __init__(self, gateway=None) -> None:
        self._gateway = gateway
        self._adapter = None  # lazy

    def _get_adapter(self):
        if self._adapter is None:
            from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
            self._adapter = HybridCodingAdapter(gateway=self._gateway, mode=self.mode_value)
        return self._adapter

    async def run(self, emr_text: str, ctx: dict[str, Any] | None = None) -> MethodResult:
        emr_text = (emr_text or "").strip()
        ctx = ctx or {}
        t_total = time.monotonic()
        trace: list[MethodStageTraceEntry] = []

        if not emr_text:
            trace.append(_stage("input_validation", time.monotonic(), status="noop", notes="empty emr_text"))
            res = _schema_to_method_result(
                self,
                MedicalCodingOutputSchema.mock_result(self.method_id),
                trace,
                processing_time_ms=int((time.monotonic() - t_total) * 1000),
                status="unavailable",
                reason="empty emr_text",
            )
            res.full_schema = None
            return res

        # Stage 1 — inference
        t1 = time.monotonic()
        adapter = self._get_adapter()
        messages = _emr_to_messages(emr_text)
        schema = await adapter.infer_async(messages, context=ctx)
        trace.append(_stage(
            "stage1_inference", t1,
            status="ok",
            output_size=1 if schema.primary_diagnosis.code else 0,
            notes=f"mode={self.mode_value.value}",
        ))

        # Stage 2 — rule_validation (already applied inside infer_async)
        t2 = time.monotonic()
        n_issues = len(schema.issues_found)
        trace.append(_stage(
            "stage2_rule_validation", t2,
            status="ok",
            output_size=n_issues,
            notes=f"{n_issues} issues, review_conclusion={schema.review_conclusion}",
        ))

        processing_ms = int((time.monotonic() - t_total) * 1000)
        return _schema_to_method_result(self, schema, trace, processing_ms)


class LegacyDeepSeekMethod(_LegacyMethodBase):
    method_id = "legacy.deepseek"
    method_name = "Legacy DeepSeek"
    method_name_en = "Legacy DeepSeek"
    stage_count = 2
    mode_value = Mode.DEEPSEEK
    description = "DeepSeek V4 + RuleEngine (生产默认 legacy 管线)."


class LegacyPromptLLMMethod(_LegacyMethodBase):
    method_id = "legacy.prompt_llm"
    method_name = "Legacy Prompt LLM"
    method_name_en = "Legacy Prompt LLM"
    stage_count = 2
    mode_value = Mode.PROMPT_LLM
    description = "通用 LLM + RuleEngine (legacy fallback, 无 DeepSeek)."


class LegacyHybridMethod(_LegacyMethodBase):
    method_id = "legacy.hybrid"
    method_name = "Legacy Hybrid"
    method_name_en = "Legacy Hybrid"
    stage_count = 2
    mode_value = Mode.HYBRID
    description = "HybridCodingAdapter auto-select 模式 (默认 legacy dispatch)."


class LegacyNoRepairMethod(_LegacyMethodBase):
    method_id = "legacy.no_repair"
    method_name = "Legacy No-Repair"
    method_name_en = "Legacy No-Repair"
    stage_count = 2
    mode_value = Mode.NO_REPAIR
    description = "Hybrid 但关闭 repair 循环 (用于 ablation 对照)."


# ── Noop method ──


class NoopUnavailableMethod(CodingMethod):
    """Returns status='unavailable' for any input. Used by the API layer
    when the input is empty / invalid."""

    method_id = "noop.unavailable"
    method_name = "无可用方法"
    method_name_en = "Noop Unavailable"
    method_family = MethodFamily.NOOP.value
    stage_count = 0
    required_capabilities = ()  # needs nothing
    description = "无输入或全部方法均不可用时的占位方法."

    async def run(self, emr_text: str, ctx: dict[str, Any] | None = None) -> MethodResult:
        return MethodResult(
            method_id=self.method_id,
            method_name=self.method_name,
            method_family=self.method_family,
            status="unavailable",
            reason="empty or invalid input — no coding method was invoked",
            stage_trace=[],
            processing_time_ms=0,
        )


# ── Code Like Humans method (Phase C) ──


class _CLHMethodBase(CodingMethod):
    """Wraps the existing ``app.agents.experts.{diagnosis,procedure}_expert``
    4-step methodology (Triage → Index Navigation → Specificity Iteration →
    Evidence Binding) as a Phase B :class:`CodingMethod`.

    Unlike the MedCodER 5-stage pipeline (which uses BGE-M3 + FAISS), CLH
    uses ``code_dict_service`` + LLM only — so its capability requirements
    are ``(LLM, RULE_SET)``, NOT ``RETRIEVER``. This means CLH works in
    development environments where BGE-M3+FAISS is not yet built (e.g. the
    MedCodER index is missing).

    The expert ``run()`` returns a candidates-shaped dict (not the flat
    MedicalCodingOutputSchema), so this base class flattens the result via
    :meth:`_aggregate_to_schema` — picks the highest-score dx candidate as
    primary, the rest as secondary, and surfaces per-candidate issues.
    """

    method_family = MethodFamily.MEDCODER.value
    required_capabilities = (MethodCapability.LLM, MethodCapability.RULE_SET)

    def __init__(self, gateway=None) -> None:
        self._gateway = gateway
        self._diagnosis_expert = None  # lazy
        self._procedure_expert = None  # lazy

    def _get_experts(self):
        if self._diagnosis_expert is None:
            from app.agents.experts.diagnosis_expert import ICDDiagnosisExpert
            from app.agents.experts.procedure_expert import ProcedureCodingExpert
            self._diagnosis_expert = ICDDiagnosisExpert()
            self._procedure_expert = ProcedureCodingExpert()
        return self._diagnosis_expert, self._procedure_expert

    async def run(self, emr_text: str, ctx: dict[str, Any] | None = None) -> MethodResult:
        emr_text = (emr_text or "").strip()
        ctx = ctx or {}
        t_total = time.monotonic()
        trace: list[MethodStageTraceEntry] = []

        if not emr_text:
            trace.append(_stage(
                "input_validation", time.monotonic(),
                status="noop", notes="empty emr_text",
            ))
            res = _schema_to_method_result(
                self,
                MedicalCodingOutputSchema.mock_result(self.method_id),
                trace,
                processing_time_ms=int((time.monotonic() - t_total) * 1000),
                status="unavailable",
                reason="empty emr_text",
            )
            res.full_schema = None
            return res

        clh_ctx = self._build_expert_context(emr_text, ctx)
        dx_expert, px_expert = self._get_experts()

        # Phase A: Clinical Triage (delegated to expert internally)
        t_a = time.monotonic()
        dx_result = await dx_expert.run(clh_ctx)
        trace.append(_stage(
            "phase_a_clinical_triage", t_a,
            status="ok",
            output_size=dx_result.get("candidate_count", 0),
            notes=f"dx candidates={dx_result.get('candidate_count', 0)}, "
                  f"triage={dx_result.get('triage_summary', {})}",
        ))

        # Phase B+C+D: Index + Specificity + Evidence (sequential, expert-internal)
        t_bcd = time.monotonic()
        px_result = await px_expert.run(clh_ctx)
        trace.append(_stage(
            "phase_bcd_index_drill_evidence", t_bcd,
            status="ok",
            output_size=px_result.get("candidate_count", 0),
            notes=f"px candidates={px_result.get('candidate_count', 0)}",
        ))

        # Phase E: Aggregation — pick primary / secondary / procedures from candidates
        t_e = time.monotonic()
        schema = self._aggregate_to_schema(dx_result, px_result)
        n_issues = len(schema.issues_found)
        trace.append(_stage(
            "phase_e_aggregation", t_e,
            status="ok",
            output_size=n_issues,
            notes=f"primary={schema.primary_diagnosis.code}, "
                  f"secondary={len(schema.secondary_diagnoses)}, "
                  f"procedures={len(schema.procedures)}, "
                  f"manual_review={schema.manual_review_required}",
        ))

        processing_ms = int((time.monotonic() - t_total) * 1000)
        return _schema_to_method_result(self, schema, trace, processing_ms)

    @staticmethod
    def _build_expert_context(emr_text: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Wrap raw EMR text into the shape CLH experts expect.

        Experts read ``evidence.diagnosis_facts`` / ``evidence.procedure_facts``
        first; if missing, they fall back to ``_build_full_text(context)`` which
        reads ``documents[].content``. We feed the raw EMR via documents so
        the expert's default path runs (no pre-triaged facts needed).
        """
        return {
            "evidence": ctx.get("evidence", {
                "diagnosis_facts": [],
                "procedure_facts": [],
            }),
            "documents": [{
                "content": emr_text,
                "doc_id": "input",
                "doc_type": "free_text",
            }],
            "admission_reason": ctx.get("admission_reason", ""),
            "existing_diagnosis_codes": ctx.get("existing_diagnosis_codes", []),
        }

    @staticmethod
    def _aggregate_to_schema(
        dx_result: dict,
        px_result: dict,
    ) -> MedicalCodingOutputSchema:
        """Flatten CLH expert output into MedicalCodingOutputSchema.

        CLH experts return candidates (not primary/secondary). Strategy:
          - Sort dx candidates by score desc → first = primary, rest = secondary.
          - Sort px candidates by score desc → first = principal, rest = secondary.
          - manual_review_required = any candidate score < LOW_CONF_FLOOR (0.7).
          - Issues collected from per-candidate ``issues`` field.
        """
        LOW_CONF_FLOOR = 0.7

        dx_cands = dx_result.get("diagnosis_candidates", []) or []
        px_cands = px_result.get("procedure_candidates", []) or []

        sorted_dx = sorted(dx_cands, key=lambda c: c.get("score", 0), reverse=True)
        sorted_px = sorted(px_cands, key=lambda c: c.get("score", 0), reverse=True)

        primary = (
            DiagnosisEntry(
                code=sorted_dx[0].get("code", ""),
                description=sorted_dx[0].get("name", ""),
                confidence=float(sorted_dx[0].get("score", 0.0)),
                category="principal",
                evidence=[{
                    "text": sorted_dx[0].get("evidence_text", ""),
                    "kind": "auto_bootstrap",
                }] if sorted_dx[0].get("evidence_text") else [],
            )
            if sorted_dx else DiagnosisEntry()
        )

        secondary = [
            DiagnosisEntry(
                code=c.get("code", ""),
                description=c.get("name", ""),
                confidence=float(c.get("score", 0.0)),
                category="secondary",
                evidence=[{
                    "text": c.get("evidence_text", ""),
                    "kind": "auto_bootstrap",
                }] if c.get("evidence_text") else [],
            )
            for c in sorted_dx[1:]
            if c.get("code")
        ]

        procedures = [
            ProcedureEntry(
                code=c.get("code", ""),
                description=c.get("name", ""),
                confidence=float(c.get("score", 0.0)),
                category="principal" if i == 0 else "secondary",
                evidence=[{
                    "text": c.get("evidence_text", ""),
                    "kind": "auto_bootstrap",
                }] if c.get("evidence_text") else [],
            )
            for i, c in enumerate(sorted_px)
            if c.get("code")
        ]

        all_codes = sorted_dx + sorted_px
        low_conf = any(c.get("score", 1.0) < LOW_CONF_FLOOR for c in all_codes)

        all_issues: list[CodingIssue] = []
        for c in all_codes:
            for issue_code in c.get("issues", []) or []:
                all_issues.append(CodingIssue(
                    severity="high" if "UNAVAILABLE" in str(issue_code) else "medium",
                    code=str(issue_code),
                    message=f"{c.get('finding', c.get('procedure_name', ''))}: {issue_code}",
                    suggestion="Verify with manual review",
                ))

        return MedicalCodingOutputSchema(
            review_conclusion="WARNING" if low_conf else "PASS",
            primary_diagnosis=primary,
            secondary_diagnoses=secondary,
            procedures=procedures,
            issues_found=all_issues,
            manual_review_required=low_conf,
            confidence=float(sorted_dx[0].get("score", 0.0)) if sorted_dx else 0.0,
            notes=(
                f"CLH 4-step: {len(sorted_dx)} dx + {len(sorted_px)} px candidates "
                f"(method={dx_result.get('method', 'code_like_humans_4step')})"
            ),
            provider="code_like_humans",
            model="deepseek-v4",
            is_mock=False,
            mode=Mode.MEDCODER_CODE_LIKE_HUMANS,
        )


class MedCodERCodeLikeHumansMethod(_CLHMethodBase):
    method_id = "medcoder.code_like_humans"
    method_name = "MedCodER Code Like Humans"
    method_name_en = "MedCodER Code Like Humans"
    stage_count = 4  # 4-step methodology: Triage + Index + Drill + Evidence
    description = (
        "CLH 4-step (Triage → Index Navigation → Specificity Iteration → "
        "Evidence Binding). 复用现有 diagnosis_expert + procedure_expert, "
        "不依赖 BGE-M3+FAISS (走 code_dict_service + LLM)."
    )


# ── Registration ──


_BUILTIN_FACTORIES = (
    MedCodERFullMethod,
    MedCodERPromptMethod,
    MedCodERRetrieveMethod,
    MedCodERPromptRetrieveMethod,
    MedCodERCodeLikeHumansMethod,
    LegacyDeepSeekMethod,
    LegacyPromptLLMMethod,
    LegacyHybridMethod,
    LegacyNoRepairMethod,
    NoopUnavailableMethod,
)


def register_builtin_methods(registry=None) -> int:
    """Instantiate + register all 10 built-in methods.

    Returns the count of methods registered (10 on first call, 0 on
    subsequent calls — the registry is idempotent for re-registration
    but does not de-dupe). Use ``registry`` arg for test isolation.
    """
    reg = registry if registry is not None else GLOBAL_REGISTRY
    for cls in _BUILTIN_FACTORIES:
        method = cls()
        reg.register(method)
    return len(_BUILTIN_FACTORIES)


__all__ = [
    "MedCodERFullMethod",
    "MedCodERPromptMethod",
    "MedCodERRetrieveMethod",
    "MedCodERPromptRetrieveMethod",
    "MedCodERCodeLikeHumansMethod",
    "_CLHMethodBase",
    "LegacyDeepSeekMethod",
    "LegacyPromptLLMMethod",
    "LegacyHybridMethod",
    "LegacyNoRepairMethod",
    "NoopUnavailableMethod",
    "register_builtin_methods",
]
