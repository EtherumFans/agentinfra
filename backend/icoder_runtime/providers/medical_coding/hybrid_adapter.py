"""HybridCodingAdapter — DeepSeekCodingAdapter → RuleEngineAdapter → validated output.

Pipeline (modes: deepseek | prompt_llm | hybrid | no_repair):
  1. DeepSeekCodingAdapter (or PromptLLMAdapter as fallback): generate candidate codes
  2. RuleEngineAdapter: validate against local rules
  3. Merge rule issues into coding output
  4. Return MedicalCodingOutputSchema with quality flags

Pipeline (medcoder modes — NAACL 2025 Industry Track, delegated to
:class:`MedCodERStrategy` per M1):
  - mode="medcoder"               → variant="full"  (5-stage end-to-end)
  - mode="medcoder_full"          → variant="full"
  - mode="medcoder_prompt"        → variant="prompt"
  - mode="medcoder_retrieve"      → variant="retrieve"
  - mode="medcoder_prompt+retrieve" → variant="prompt+retrieve"

The 5 stages (Extraction / Retrieval / Merge / Re-rank / Compliance) live
in :class:`MedCodERStrategy` and are tested independently. This module
only owns the legacy (DeepSeek + RuleEngine) pipeline and the dispatcher.
"""

from __future__ import annotations

import logging
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
)
from official_agents.medical_coding.modes import (
    Mode, MEDCODER_MODES, LEGACY_MODES, coerce,
)
from .deepseek_coding_adapter import DeepSeekCodingAdapter
from .prompt_llm_adapter import PromptLLMAdapter
from .rule_engine_adapter import RuleEngineAdapter
from .medcoder_strategy import MedCodERStrategy

logger = logging.getLogger(__name__)


# MedCodER modes are centralized in :mod:`official_agents.medical_coding.modes`
# (M2 — StrEnum SSOT). Re-exported here for back-compat with imports like
# ``from .hybrid_adapter import MEDCODER_MODES``. The values are :class:`Mode`
# enum members; comparisons (``mode in MEDCODER_MODES``) coerce the LHS via
# :func:`coerce` before the check.

__all__ = ["MEDCODER_MODES", "LEGACY_MODES", "Mode", "coerce"]


def _mode_to_variant(mode: Mode) -> str:
    """Map a medcoder mode (already coerced to :class:`Mode`) to a
    ``MedCodERStrategy.run_variant`` variant name.

    ``Mode.MEDCODER`` is the canonical alias for ``Mode.MEDCODER_FULL``; all
    other values follow the ``medcoder_<variant>`` naming convention.

    Accepts ``Mode`` (preferred) or ``str`` (legacy callers; coerced
    defensively).
    """
    m = mode if isinstance(mode, Mode) else coerce(mode)
    if m == Mode.MEDCODER or m == Mode.MEDCODER_FULL:
        return "full"
    if m.value.startswith("medcoder_"):
        return m.value[len("medcoder_"):]
    # Defensive: only reachable if a new Mode was added to MEDCODER_MODES but
    # not to this dispatcher. Log and fall back to "full".
    logger.warning("HybridCodingAdapter: unknown medcoder mode %r; using 'full'", m)
    return "full"


class HybridCodingAdapter(CodingEngineAdapter):
    """Orchestrates coding inference and rule validation.

    Modes:
      - "deepseek": DeepSeek V4 inference + rule validation (production)
      - "prompt_llm": Generic LLM inference + rule validation (fallback)
      - "hybrid": Auto-select (default)
      - "no_repair": Same as hybrid but repair loop disabled (tests/ablation)
      - "medcoder" (and 4 explicit variants): NAACL 2025 5-stage pipeline

    Pipeline (legacy modes — deepseek/prompt_llm/hybrid/no_repair):
      Stage 1: Coding inference (DeepSeekCodingAdapter or PromptLLMAdapter)
      Stage 2: Rule validation (RuleEngineAdapter)
      Stage 3: Merge results with quality flags

    Pipeline (medcoder modes, M1 — delegated to :class:`MedCodERStrategy`):
      Stage 1: Extraction (LLM)
      Stage 2: Retrieval (BGE-M3 + FAISS, no LLM)
      Stage 3: Merge (in-process)
      Stage 4: Re-rank (LLM, RankGPT)
      Stage 5: Compliance + Calibration

    MedCodER mode → variant dispatch (``_mode_to_variant``):
      ``"medcoder"`` → ``"full"`` (canonical alias, backward compat)
      ``"medcoder_full"`` → ``"full"``
      ``"medcoder_prompt"`` → ``"prompt"``
      ``"medcoder_retrieve"`` → ``"retrieve"``
      ``"medcoder_prompt+retrieve"`` → ``"prompt+retrieve"``
    """

    name = "hybrid_coding_adapter"

    def __init__(self, gateway=None, mode: str | Mode = "hybrid", retriever=None, recorder=None):
        self._gateway = gateway
        # M2: coerce once at the boundary so every downstream comparison
        # (``mode in MEDCODER_MODES`` etc.) uses the StrEnum SSOT. Unknown
        # values fall back to ``Mode.UNSET`` rather than raising — keeps
        # back-compat with persisted JSON from older versions.
        self._mode = coerce(mode)
        self._rule_adapter = RuleEngineAdapter()
        # Repair is on by default; off in "no_repair" mode (tests + opt-out)
        # Medcoder modes have their own retry strategy, so repair loop is off.
        self._repair_enabled = (
            self._mode != Mode.NO_REPAIR and self._mode not in MEDCODER_MODES
        )

        # Resolve inference adapter (legacy pipeline only — medcoder modes
        # bypass this via the strategy).
        if self._mode == Mode.DEEPSEEK or self._mode == Mode.NO_REPAIR:
            self._inference = DeepSeekCodingAdapter(gateway=gateway)
        elif self._mode == Mode.PROMPT_LLM:
            self._inference = PromptLLMAdapter(gateway=gateway)
        else:  # hybrid / medcoder_*: default to DeepSeek (only used in hybrid)
            self._inference = DeepSeekCodingAdapter(gateway=gateway)

        self._fallback_inference = PromptLLMAdapter(gateway=gateway)

        # MedCodER strategy (M1). Lazy-constructed when mode ∈ MEDCODER_MODES
        # so legacy modes don't pay the BGE-M3 / FAISS import cost.
        if self._mode in MEDCODER_MODES:
            self._strategy: MedCodERStrategy | None = MedCodERStrategy(
                gateway=gateway,
                retriever=retriever,
            )
        else:
            self._strategy = None

        # Backward-compat: ``_retriever`` and ``_retriever_lazy`` remain
        # attributes so existing tests that probe them (e.g.
        # ``adapter._retriever is None``) keep working. In medcoder modes
        # the retriever is owned by the strategy; here we just expose the
        # constructor argument for visibility.
        self._retriever = retriever
        self._retriever_lazy = retriever is None

        # M2aRecorder (M3-0 集成): 当 recorder 提供时, infer_async 会用
        # recorder.inference() 上下文 + ctx.stage() 自动记录 trace 到
        # production_runs.jsonl. M2a test contract 要求 adapter 接受 recorder
        # 并暴露 _recorder 属性 (None = inactive, 显式提供 = active).
        self._recorder = recorder

    def _build_repair_messages(
        self, original_messages: list, issues: list,
    ) -> list:
        """Build a follow-up message that includes the rule violations and
        asks the LLM to correct its output. Returns original_messages plus
        a single new user message (so the LLM sees its own prior assistant
        turn + the violation feedback).
        """
        issue_text = "; ".join(
            f"[{i.severity}] {i.code}: {i.message}" for i in issues[:5]
        )
        repair_user = (
            f"你之前的编码输出触发了以下规则违规：\n{issue_text}\n\n"
            f"请重新审查原始病历，输出修正后的 JSON (MedicalCodingOutputSchema 格式)，"
            f"避免重复违规。如果仍不确定，请设置 manual_review_required=true。"
        )
        return list(original_messages) + [{"role": "user", "content": repair_user}]

    def _calibration_input(self, result: MedicalCodingOutputSchema) -> tuple:
        """Convert MedicalCodingOutputSchema to calibrate_all()'s input shape.

        Returns: (diag_candidates, proc_candidates, primary_diagnosis, ...)
        """
        diag_candidates: list[dict] = []
        if result.primary_diagnosis.code:
            diag_candidates.append({
                "code": result.primary_diagnosis.code,
                "name": result.primary_diagnosis.description,
                "score": result.primary_diagnosis.confidence,
                "negation": False,
            })
        for d in result.secondary_diagnoses:
            if d.code:
                diag_candidates.append({
                    "code": d.code,
                    "name": d.description,
                    "score": d.confidence,
                    "negation": False,
                })
        proc_candidates = [
            {
                "code": p.code,
                "name": p.description,
                "score": p.confidence,
                "negation": False,
            }
            for p in result.procedures if p.code
        ]
        primary_diagnosis = {
            "code": result.primary_diagnosis.code,
            "name": result.primary_diagnosis.description,
            "rule_basis": [i.code for i in result.issues_found],
        }
        return diag_candidates, proc_candidates, primary_diagnosis, {}, {}, primary_diagnosis

    def _apply_calibration(self, result: MedicalCodingOutputSchema) -> None:
        """Run calibrate_all and update result.manual_review_required based on
        routing tier. Non-fatal: if calibration fails, log warning and keep
        the result unchanged.
        """
        try:
            from app.services.confidence_calibrator import calibrate_all
            diag_c, proc_c, pd, ev_rank, disagr, pd_reason = self._calibration_input(result)
            cal = calibrate_all(diag_c, proc_c, pd, ev_rank, disagr, pd_reason)
            # Tier check
            escalate = any(r.get("tier") == "escalate" for r in cal.get("routing_decisions", []))
            if escalate:
                result.manual_review_required = True
            # Notes summary
            m = cal.get("metrics", {})
            if m:
                cal_summary = (
                    f"calibration: {m.get('auto_count', 0)}A/"
                    f"{m.get('review_count', 0)}R/"
                    f"{m.get('escalate_count', 0)}E"
                )
                if result.notes:
                    result.notes = f"{result.notes} | {cal_summary}"
                else:
                    result.notes = cal_summary
            # Update confidence with the highest calibrated score across codes
            confs = [c.get("calibrated_score", 0) for c in cal.get("coding_confidences", [])]
            if confs:
                result.confidence = round(max(confs), 3)
        except Exception as e:
            logger.warning(f"HybridCodingAdapter: calibration failed (non-fatal): {e}")

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        # MedCodER pipeline (M1): delegate the 5 stages to
        # MedCodERStrategy. Each MEDCODER_MODES value maps to one of the
        # 4 ablation variants (full / prompt / retrieve / prompt+retrieve).
        if self._mode in MEDCODER_MODES and self._strategy is not None:
            return await self._strategy.run_variant(
                messages,
                variant=_mode_to_variant(self._mode),
                ctx=context,
            )

        # M2aRecorder (M3-0 集成): 当 recorder 提供时, 包 3 个 stage 到 trace —
        # "inference" (Stage 1 primary+fallback) / "rule_validation" (Stage 2-4 validate/merge/repair)
        # / "calibration" (Stage 5 calibrate). 当 recorder=None, 走原始 1 段流程.
        if self._recorder is None:
            return await self._infer_pipeline_inner(
                messages, tools, response_schema, context
            )

        with self._recorder.inference(
            agent_ref=f"hybrid_coding_adapter:{self._mode.value if hasattr(self._mode, 'value') else self._mode}"
        ) as inf_ctx:
            with inf_ctx.stage("inference"):
                result, rule_result = await self._stage_inference(
                    messages, tools, response_schema, context
                )
                if result is None:  # inference hard-failed (mock fallback)
                    return MedicalCodingOutputSchema.mock_result()
            with inf_ctx.stage("rule_validation"):
                result = await self._stage_rule_validation(result, rule_result, messages, tools, response_schema, context)
            with inf_ctx.stage("calibration"):
                self._apply_calibration(result)
        return result

    # ── Pipeline stages (split out so the recorder can wrap them) ──

    async def _stage_inference(
        self, messages, tools, response_schema, context,
    ) -> tuple[MedicalCodingOutputSchema | None, object]:
        """Stage 1: Coding inference (primary + fallback). Returns (result, rule_result_placeholder)."""
        logger.info(f"HybridCodingAdapter: Stage 1 — {self._inference.name}")
        try:
            result = await self._inference.infer_async(messages, tools, response_schema, context)
        except Exception as e:
            logger.warning(f"Primary inference failed ({self._inference.name}): {e}, trying fallback")
            try:
                result = await self._fallback_inference.infer_async(messages, tools, response_schema, context)
            except Exception as e2:
                logger.error(f"Fallback inference also failed: {e2}")
                return None, None
        return result, None

    async def _stage_rule_validation(
        self, result, _placeholder, messages, tools, response_schema, context,
    ) -> MedicalCodingOutputSchema:
        """Stage 2-4: Rule validation + merge + repair. Returns the final result
        (which may be ``repaired`` if repair succeeded)."""
        # Stage 2: Rule validation
        logger.info("HybridCodingAdapter: Stage 2 — RuleEngineAdapter")
        rule_result = self._rule_adapter.validate(result)

        # Stage 3: Merge rule issues into output
        result.issues_found = rule_result.issues
        result.manual_review_required = (
            result.manual_review_required or rule_result.manual_review_required
        )

        # Update review_conclusion based on validation
        if rule_result.quality_flags.get("primary_diagnosis_missing"):
            result.review_conclusion = "FAIL"
        elif rule_result.quality_flags.get("invalid_code_format"):
            result.review_conclusion = "FAIL"
        elif rule_result.issues and not result.review_conclusion == "FAIL":
            result.review_conclusion = "WARNING"

        # Annotate notes
        notes_parts = [result.notes] if result.notes else []
        notes_parts.append(f"Rules fired: {len(rule_result.rules_fired)}")
        if rule_result.quality_flags:
            flags_str = ", ".join(f"{k}={v}" for k, v in rule_result.quality_flags.items() if v)
            notes_parts.append(f"Quality flags: {flags_str}")
        result.notes = "; ".join(notes_parts)

        # Stage 4 (Phase 2 of F1 0.76→0.85+): In-process repair loop.
        # The declared MC-R-REPAIR-001 rule says rule violations should
        # trigger a re-prompt. We do one bounded retry when severity in
        # (critical, high) and the LLM produced a non-trivial output.
        # Cap is 1 retry (no infinite loop).
        SEVERE = ("critical", "high")
        severe_issues = [i for i in rule_result.issues if i.severity in SEVERE]
        if self._repair_enabled and severe_issues and not result.is_mock:
            result.repair_attempted = True
            result.repair_rounds = 1
            try:
                repair_messages = self._build_repair_messages(messages, severe_issues)
                repaired = await self._inference.infer_async(
                    repair_messages, tools, response_schema, context,
                )
                repaired_rules = self._rule_adapter.validate(repaired)
                still_severe = [i for i in repaired_rules.issues if i.severity in SEVERE]
                if not still_severe:
                    # Repair cleared the severe issues → accept the new output
                    result = repaired
                    result.repair_attempted = True
                    result.repair_success = True
                    result.repair_rounds = 1
                    result.issues_found = repaired_rules.issues
                    result.manual_review_required = (
                        result.manual_review_required or repaired_rules.manual_review_required
                    )
                    if repaired_rules.quality_flags.get("primary_diagnosis_missing") \
                            or repaired_rules.quality_flags.get("invalid_code_format"):
                        result.review_conclusion = "FAIL"
                    elif repaired_rules.issues:
                        result.review_conclusion = "WARNING"
                    else:
                        result.review_conclusion = "PASS"
                    logger.info(
                        f"HybridCodingAdapter: repair succeeded "
                        f"(severe issues: {len(severe_issues)} → 0)"
                    )
                else:
                    logger.info(
                        f"HybridCodingAdapter: repair did not clear severe issues "
                        f"({len(still_severe)} still severe)"
                    )
            except Exception as e:
                logger.warning(f"HybridCodingAdapter: repair attempt failed: {e}")
        return result

    async def _infer_pipeline_inner(
        self, messages, tools, response_schema, context,
    ) -> MedicalCodingOutputSchema:
        """Original (no-recorder) 5-stage pipeline. M2aRecorder=None 时走这里."""
        result, _ = await self._stage_inference(messages, tools, response_schema, context)
        if result is None:
            return MedicalCodingOutputSchema.mock_result()
        result = await self._stage_rule_validation(
            result, None, messages, tools, response_schema, context
        )
        self._apply_calibration(result)
        return result

    # ── MedCodER 5-stage pipeline (M1 — delegated to MedCodERStrategy) ──
    #
    # The 5 stage methods + the lazy retriever factory that used to live
    # here have moved to :class:`MedCodERStrategy`. The legacy
    # ``_medcoder_pipeline`` / ``_stage1_extraction`` / ``_mock_stage1`` /
    # ``_stage234_per_disease`` / ``_stage4_rerank`` / ``_stage5_build_output``
    # / ``_get_retriever`` methods were removed in M1 commit 3 (2026-06-22).
    # See ``icoder_runtime/providers/medical_coding/medcoder_strategy.py``.

    def health_check(self) -> dict:
        return {
            "engine": self.name,
            "mode": self._mode,
            "active_inference": self._inference.name,
            "rule_engine": self._rule_adapter.health_check(),
            "status": "healthy",
        }

    @property
    def current_mode(self) -> str:
        return self._mode
