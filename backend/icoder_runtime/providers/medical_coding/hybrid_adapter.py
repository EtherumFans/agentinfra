"""HybridCodingAdapter — DeepSeekCodingAdapter → RuleEngineAdapter → validated output.

Pipeline (modes: deepseek | prompt_llm | hybrid | no_repair):
  1. DeepSeekCodingAdapter (or PromptLLMAdapter as fallback): generate candidate codes
  2. RuleEngineAdapter: validate against local rules
  3. Merge rule issues into coding output
  4. Return MedicalCodingOutputSchema with quality flags

Pipeline (mode: medcoder — NAACL 2025 Industry Track 3-stage):
  1. Extraction (LLM call #1) — extract diseases + supporting evidence
  2. Retrieval (BGE-M3 + FAISS) — top-20 ICD candidates per disease
  3. Merge — union of LLM + retrieved codes (cap 30)
  4. Re-rank (LLM call #2, RankGPT) — pick top-5 with per-dx confidence
  5. Compliance + Calibration — MedCodER rule set, per-diagnosis calibration
"""

from __future__ import annotations

import logging
import os
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema, CodingIssue,
    CandidateCode, ExtractedDiagnosis,
)
from .deepseek_coding_adapter import DeepSeekCodingAdapter
from .prompt_llm_adapter import PromptLLMAdapter
from .rule_engine_adapter import RuleEngineAdapter
from .medcoder_adapter import (
    build_extraction_messages,
    build_rerank_messages,
    parse_extraction_response,
    parse_rerank_response,
    fuzzy_evidence_to_span,
    get_differentiation_hints,
)

logger = logging.getLogger(__name__)


# Cap on merged candidates per disease (LLM ∪ Retrieved) before re-rank
MERGE_CANDIDATE_CAP = 30

# Top-K returned per disease after re-rank
RERANK_TOP_K = 5


class HybridCodingAdapter(CodingEngineAdapter):
    """Orchestrates coding inference and rule validation.

    Modes:
      - "deepseek": DeepSeek V4 inference + rule validation (production)
      - "prompt_llm": Generic LLM inference + rule validation (fallback)
      - "hybrid": Auto-select (default)
      - "no_repair": Same as hybrid but repair loop disabled (tests/ablation)
      - "medcoder": NAACL 2025 5-stage pipeline (BGE-M3 + FAISS + RankGPT)

    Pipeline (legacy modes — deepseek/prompt_llm/hybrid/no_repair):
      Stage 1: Coding inference (DeepSeekCodingAdapter or PromptLLMAdapter)
      Stage 2: Rule validation (RuleEngineAdapter)
      Stage 3: Merge results with quality flags

    Pipeline (medcoder mode):
      Stage 1: Extraction (LLM)
      Stage 2: Retrieval (BGE-M3 + FAISS, no LLM)
      Stage 3: Merge (in-process)
      Stage 4: Re-rank (LLM, RankGPT)
      Stage 5: Compliance + Calibration
    """

    name = "hybrid_coding_adapter"

    def __init__(self, gateway=None, mode: str = "hybrid", retriever=None, recorder=None):
        self._gateway = gateway
        self._mode = mode  # deepseek | prompt_llm | hybrid | no_repair | medcoder
        self._rule_adapter = RuleEngineAdapter()
        # Repair is on by default; off in "no_repair" mode (tests + opt-out)
        # Medcoder mode has its own retry strategy, so repair loop is also off.
        self._repair_enabled = mode not in ("no_repair", "medcoder")

        # Resolve inference adapter
        if mode in ("deepseek", "no_repair"):
            self._inference = DeepSeekCodingAdapter(gateway=gateway)
        elif mode == "prompt_llm":
            self._inference = PromptLLMAdapter(gateway=gateway)
        else:  # hybrid / medcoder: default to DeepSeek
            self._inference = DeepSeekCodingAdapter(gateway=gateway)

        self._fallback_inference = PromptLLMAdapter(gateway=gateway)

        # MedCodER retriever (lazy-initialized in medcoder_pipeline)
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
        # MedCodER pipeline: 5-stage Extraction→Retrieval→Merge→Re-rank→Compliance
        if self._mode == "medcoder":
            return await self._medcoder_pipeline(messages, context)

        # M2aRecorder (M3-0 集成): 当 recorder 提供时, 包 3 个 stage 到 trace —
        # "inference" (Stage 1 primary+fallback) / "rule_validation" (Stage 2-4 validate/merge/repair)
        # / "calibration" (Stage 5 calibrate). 当 recorder=None, 走原始 1 段流程.
        if self._recorder is None:
            return await self._infer_pipeline_inner(
                messages, tools, response_schema, context
            )

        with self._recorder.inference(
            agent_ref=f"hybrid_coding_adapter:{self._mode}"
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

    # ── MedCodER 5-stage pipeline (mode="medcoder") ──

    async def _medcoder_pipeline(
        self,
        messages: list[dict[str, str]],
        context: dict[str, Any] | None,
    ) -> MedicalCodingOutputSchema:
        """NAACL 2025 3-stage MedCodER + 2 post-stages (merge, compliance)."""
        ctx = context or {}

        # Extract the EMR text (the last user message is the EMR)
        emr_text = ""
        for m in reversed(messages or []):
            if m.get("role") == "user":
                emr_text = m.get("content", "")
                break
        if not emr_text:
            logger.warning("MedCodER: no user message in messages, using mock")
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            return out

        # ── Stage 1: Extraction (LLM) ──
        extraction = await self._stage1_extraction(emr_text)
        if not extraction:
            logger.warning("MedCodER: Stage 1 produced 0 diagnoses, falling back to mock")
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER Stage 1 (extraction) returned 0 diseases"
            return out

        # ── Stages 2 + 3 + 4: per-disease retrieve → merge → re-rank ──
        retriever = self._get_retriever()
        extracted_diagnoses: list[ExtractedDiagnosis] = []
        for dx in extraction:
            edx = await self._stage234_per_disease(dx, emr_text, retriever, ctx)
            extracted_diagnoses.append(edx)

        # ── Stage 5: Compliance (MedCodERRetrievalRuleSet) + per-dx calibration ──
        output = self._stage5_build_output(extracted_diagnoses, ctx)

        # Mark the mode discriminator
        output.mode = "medcoder"
        output.provider = "medcoder"
        # Backward-compat: populate primary_diagnosis from highest-confidence dx
        if extracted_diagnoses:
            top = max(extracted_diagnoses, key=lambda d: d.final_confidence)
            if top.final_top_k:
                best = top.final_top_k[0]
                output.primary_diagnosis.code = best.code
                output.primary_diagnosis.description = best.name
                output.primary_diagnosis.confidence = top.final_confidence
                output.primary_diagnosis.category = "principal"
                output.primary_diagnosis.evidence = list(top.supporting_evidence)
            # The rest become secondary
            for edx in extracted_diagnoses:
                if edx is top or not edx.final_top_k:
                    continue
                from official_agents.medical_coding.schema import DiagnosisEntry
                b = edx.final_top_k[0]
                output.secondary_diagnoses.append(DiagnosisEntry(
                    code=b.code, description=b.name, confidence=edx.final_confidence,
                    category="comorbidity", evidence=list(edx.supporting_evidence),
                ))

        return output

    async def _stage1_extraction(self, emr_text: str) -> list[dict]:
        """Stage 1: LLM call → list of {disease, evidence, llm_initial_code}."""
        ext_messages = build_extraction_messages(emr_text)
        if not self._gateway:
            return self._mock_stage1(emr_text)
        try:
            resp = await self._gateway.generate(ext_messages, provider="default")
            content = resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception as e:
            logger.warning("MedCodER: Stage 1 LLM failed: %s", e)
            return self._mock_stage1(emr_text)
        return parse_extraction_response(content)

    def _mock_stage1(self, emr_text: str) -> list[dict]:
        """Deterministic Stage 1 result for tests / no-gateway mode."""
        return [{
            "disease_text": "心力衰竭",
            "supporting_evidence": "胸闷气短",
            "llm_initial_code": "I50.900",
        }]

    async def _stage234_per_disease(
        self,
        dx: dict,
        emr_text: str,
        retriever,
        ctx: dict,
    ) -> ExtractedDiagnosis:
        """Stages 2 (retrieve) + 3 (merge) + 4 (re-rank) for one disease."""
        disease_text = (dx.get("disease_text") or "").strip()
        evidence_text = (dx.get("supporting_evidence") or "").strip()
        llm_code = (dx.get("llm_initial_code") or "").strip()

        # Fuzzy-match evidence → EvidenceSpan
        span_dict = fuzzy_evidence_to_span(evidence_text, emr_text) if evidence_text else None
        from official_agents.medical_coding.schema import EvidenceSpan
        spans: list[EvidenceSpan] = []
        if span_dict:
            spans.append(EvidenceSpan(
                text=span_dict["text"],
                char_start=span_dict["char_start"],
                char_end=span_dict["char_end"],
                doc_id=ctx.get("doc_id", ""),
                doc_type=ctx.get("doc_type", ""),
                confidence=0.9,
            ))

        # Stage 2: retrieve top-20 from FAISS
        retrieved: list[CandidateCode] = []
        if retriever is not None and disease_text:
            try:
                retrieved = await retriever.retrieve_async(disease_text, top_k=20)
            except Exception as e:
                logger.warning("MedCodER: Stage 2 retrieve failed: %s", e)

        # Stage 3: merge LLM code ∪ retrieved, cap 30
        merged: list[dict] = []
        seen_codes: set[str] = set()
        if llm_code:
            merged.append({
                "code": llm_code, "name": "",
                "score": 1.0, "chapter": "",
                "source": "llm",
            })
            seen_codes.add(llm_code)
        for c in retrieved:
            if c.code and c.code not in seen_codes:
                merged.append({
                    "code": c.code, "name": c.name,
                    "score": c.score, "chapter": c.chapter,
                    "source": "retrieve",
                })
                seen_codes.add(c.code)
            if len(merged) >= MERGE_CANDIDATE_CAP:
                break

        # Pull differentiation hints for this disease (best-effort)
        hints = get_differentiation_hints(disease_text)

        # Stage 4: re-rank via LLM
        ranked = await self._stage4_rerank(disease_text, evidence_text, merged, hints)

        # If rerank failed, fall back to retrieved order (top-5)
        if not ranked:
            ranked = [
                {"code": c["code"], "name": c["name"], "confidence": c["score"],
                 "rationale": "rerank-failed: using retrieval order"}
                for c in merged[:RERANK_TOP_K]
                if c.get("code")
            ]

        # Build final_top_k list of CandidateCode with source="rerank"
        final_top_k: list[CandidateCode] = []
        for r in ranked[:RERANK_TOP_K]:
            if r.get("code"):
                final_top_k.append(CandidateCode(
                    code=r["code"], name=r.get("name", ""),
                    score=float(r.get("confidence", 0.0)),
                    chapter="", source="rerank",
                ))

        # Re-rank note
        if ranked:
            rerank_note = ranked[0].get("rationale", "")
        else:
            rerank_note = "no candidates"
        # Per-diagnosis confidence = top-1's confidence, with a floor of 0
        try:
            per_dx_conf = float(ranked[0]["confidence"]) if ranked else 0.0
        except (KeyError, TypeError, ValueError):
            per_dx_conf = 0.0

        return ExtractedDiagnosis(
            disease_text=disease_text,
            supporting_evidence=spans,
            llm_initial_code=llm_code,
            retrieved_codes=list(retrieved),
            final_top_k=final_top_k,
            final_confidence=per_dx_conf,
            rerank_notes=rerank_note,
        )

    async def _stage4_rerank(
        self,
        disease_text: str,
        evidence_text: str,
        candidates: list[dict],
        differentiation_hints: list[str],
    ) -> list[dict]:
        """Stage 4: LLM RankGPT-style re-rank to top-5."""
        if not candidates:
            return []
        if not self._gateway:
            # Mock: just return top-5 by score
            sorted_c = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)
            return [
                {"code": c["code"], "name": c["name"], "confidence": c.get("score", 0),
                 "rationale": "no-gateway: ranked by retrieval score"}
                for c in sorted_c[:RERANK_TOP_K]
                if c.get("code")
            ]
        try:
            msgs = build_rerank_messages(disease_text, evidence_text, candidates, differentiation_hints)
            resp = await self._gateway.generate(msgs, provider="default")
            content = resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception as e:
            logger.warning("MedCodER: Stage 4 LLM failed: %s", e)
            sorted_c = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)
            return [
                {"code": c["code"], "name": c["name"], "confidence": c.get("score", 0),
                 "rationale": "rerank-llm-failed: using retrieval order"}
                for c in sorted_c[:RERANK_TOP_K]
                if c.get("code")
            ]
        return parse_rerank_response(content)

    def _stage5_build_output(
        self,
        extracted_diagnoses: list[ExtractedDiagnosis],
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Stage 5: build MedicalCodingOutputSchema + apply medcoder rules."""
        from compliance_services.medcoder_retrieval_rules import MedCodERRetrievalRuleSet

        out = MedicalCodingOutputSchema()
        out.extracted_diagnoses = list(extracted_diagnoses)

        # Compute top-level confidence = average of per-diagnosis confidences
        if extracted_diagnoses:
            out.confidence = round(
                sum(d.final_confidence for d in extracted_diagnoses) / len(extracted_diagnoses), 3
            )

        # Apply medcoder retrieval rule set (advisory)
        try:
            rs = MedCodERRetrievalRuleSet()
            out_dict = out.to_dict()
            rule_result = rs.validate(out_dict, ctx)
            # Translate to CodingIssue list
            for issue in rule_result.issues:
                out.issues_found.append(CodingIssue(
                    severity=issue.severity,
                    code=issue.rule_id,
                    message=issue.message,
                    suggestion=issue.suggestion,
                ))
            if rule_result.manual_review_required:
                out.manual_review_required = True
            if not rule_result.passed:
                if out.review_conclusion == "PASS":
                    out.review_conclusion = "WARNING"
        except Exception as e:
            logger.warning("MedCodER: rule validation failed (non-fatal): %s", e)

        # Per-diagnosis calibration (lightweight): if confidence < 0.5, escalate
        for edx in extracted_diagnoses:
            if edx.final_confidence < 0.5:
                out.manual_review_required = True

        # Notes
        n_dx = len(extracted_diagnoses)
        n_retrieved = sum(len(d.retrieved_codes) for d in extracted_diagnoses)
        n_reranked = sum(len(d.final_top_k) for d in extracted_diagnoses)
        out.notes = (
            f"MedCodER: {n_dx} diagnoses, {n_retrieved} retrieved codes, "
            f"{n_reranked} re-ranked. {out.notes}"
        ).strip()

        return out

    def _get_retriever(self):
        """Lazy-create a MedCodERRetriever on first use.

        Selection (C5):
          - if ``MEDCODER_SUBPROCESS=1`` is set in the environment, use
            ``SubprocessMedCodERRetriever`` (BGE-M3 + FAISS run in a
            worker process; safe on Windows).
          - else if running on Windows (``os.name == 'nt'``), default to
            the subprocess wrapper — the in-process variant segfaults
            on this platform when combined with httpx async I/O.
          - else use the in-process ``MedCodERRetriever``.
        """
        if self._retriever is not None or not self._retriever_lazy:
            return self._retriever

        use_subprocess = (
            os.environ.get("MEDCODER_SUBPROCESS") == "1"
            or os.name == "nt"
        )
        try:
            from .medcoder_retriever import (
                MedCodERRetriever,
                SubprocessMedCodERRetriever,
            )
            if use_subprocess:
                self._retriever = SubprocessMedCodERRetriever()
                logger.info(
                    "MedCodER: using SubprocessMedCodERRetriever "
                    "(MEDCODER_SUBPROCESS=%s, os.name=%s)",
                    os.environ.get("MEDCODER_SUBPROCESS", "0"), os.name,
                )
            else:
                self._retriever = MedCodERRetriever()
        except Exception as e:
            logger.warning("MedCodER: could not create retriever: %s", e)
            self._retriever = None
        self._retriever_lazy = False  # don't retry on next call
        return self._retriever

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
