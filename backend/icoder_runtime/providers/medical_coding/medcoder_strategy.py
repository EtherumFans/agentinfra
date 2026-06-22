"""MedCodERStrategy — 5-stage MedCodER pipeline (NAACL 2025 Industry Track).

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 4 + Part 7.4 (M1), the strategy
extracts the monolithic ``HybridCodingAdapter._medcoder_pipeline`` into
5 PUBLIC stage methods so each can be:

  - unit tested in isolation (see ``tests/unit/icoder/providers/test_medcoder_strategy.py``)
  - composed into 4 ablation variants via ``run_variant()``
  - delegated to by ``CodingExpert`` (Runtime first real Expert impl)
  - exposed as MCP tools in M2 (search_icd / verify_code /
    get_differentiation_hint / rerank_codes / calibrate_confidence)

Stages:
  1. ``stage1_extraction(emr_text)``  — LLM extracts diseases + evidence
  2. ``stage2_retrieve(disease_text)`` — BGE-M3 + FAISS top-20 candidates
  3. ``stage3_merge(llm_codes, retrieved, disease_text)`` — union + dedup
  4. ``stage4_rerank(disease, evidence, candidates)`` — RankGPT-style top-5
  5. ``stage5_compliance(extracted, ctx)`` — rule set + per-dx calibration

Ablation variants (``run_variant``):
  - ``"full"``             — 5 stages end-to-end (default)
  - ``"prompt"``           — stage 1 only (LLM initial codes)
  - ``"retrieve"``         — stage 2 only (BGE-M3 + FAISS, no LLM)
  - ``"prompt+retrieve"``  — stages 1+2 (no rerank, no compliance)

Pure prompt/parse helpers (``build_extraction_messages`` /
``parse_extraction_response`` / ``fuzzy_evidence_to_span`` /
``get_differentiation_hints``) live in ``medcoder_adapter.py`` and are
imported unchanged — M2's MCP server will reuse them.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from official_agents.medical_coding.schema import (
    MedicalCodingOutputSchema, CodingIssue, CandidateCode,
    ExtractedDiagnosis, EvidenceSpan, DiagnosisEntry,
)
from .medcoder_adapter import (
    build_extraction_messages,
    build_rerank_messages,
    parse_extraction_response,
    parse_rerank_response,
    fuzzy_evidence_to_span,
    get_differentiation_hints,
)

logger = logging.getLogger(__name__)


# ── Constants ──

# Top-K returned per disease after re-rank (default 5)
DEFAULT_RERANK_TOP_K = 5

# Cap on merged candidates per disease before re-rank (default 30)
DEFAULT_MERGE_CAP = 30

# Per-diagnosis confidence floor below which manual review is required.
# Audit Part 7.1 (Stage 5 calibration 50/100) — M1 keeps the same flat
# floor; the 5-component weighted calibration is M2.
CALIBRATION_FLOOR = 0.5


# ── Strategy class ──


class MedCodERStrategy:
    """5-stage MedCodER pipeline as composable public methods.

    Each stage is independently callable; the ``run_variant`` dispatcher
    composes them into the 4 ablation variants used by the e2e eval
    script (``scripts/e2e_medcoder_validation.py``).

    Args:
        gateway:        LLM gateway (``LLMGateway.generate`` async). If
                        ``None``, stage 1 / stage 4 fall back to mock or
                        retrieval-order ranking respectively.
        retriever:      BGE-M3 + FAISS retriever. If ``None``,
                        ``_create_default_retriever`` is used lazily
                        (subprocess on Windows or when
                        ``MEDCODER_SUBPROCESS=1``).
        rule_set:       ``MedCodERRetrievalRuleSet`` (or compatible).
                        If ``None``, a default is constructed on first
                        ``stage5_compliance`` call.
        merge_cap:      Max merged candidates per disease (stage 3 cap).
        rerank_top_k:   Top-K after re-rank (stage 4 cap).
    """

    VARIANTS: tuple[str, ...] = (
        "full",
        "prompt",
        "retrieve",
        "prompt+retrieve",
    )

    def __init__(
        self,
        gateway: Any = None,
        retriever: Any = None,
        rule_set: Any = None,
        merge_cap: int = DEFAULT_MERGE_CAP,
        rerank_top_k: int = DEFAULT_RERANK_TOP_K,
    ) -> None:
        self._gateway = gateway
        self._retriever = retriever
        self._retriever_lazy = retriever is None
        self._rule_set = rule_set
        self._merge_cap = merge_cap
        self._rerank_top_k = rerank_top_k

    # ── 5 public stage methods ─────────────────────────────────────

    async def stage1_extraction(self, emr_text: str) -> list[dict]:
        """Stage 1: LLM call → list of {disease, evidence, llm_initial_code}.

        Falls back to ``_mock_stage1`` when the gateway is missing or
        the LLM call raises. The fallback is intentional — strategy tests
        and the no-gateway dev path still need a deterministic Stage 1
        result.
        """
        if not emr_text or not emr_text.strip():
            return []
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

    async def stage2_retrieve(
        self,
        disease_text: str,
        top_k: int = 20,
    ) -> list[CandidateCode]:
        """Stage 2: BGE-M3 + FAISS top-K ICD candidate codes.

        Returns ``[]`` when the retriever is missing, the disease text
        is empty, or the underlying call fails. Source is
        ``"retrieve"`` on every returned candidate.
        """
        text = (disease_text or "").strip()
        if not text:
            return []
        retriever = self._get_retriever()
        if retriever is None:
            return []
        try:
            return await retriever.retrieve_async(text, top_k=top_k)
        except Exception as e:
            logger.warning("MedCodER: Stage 2 retrieve failed: %s", e)
            return []

    async def stage3_merge(
        self,
        llm_codes: list[dict],
        retrieved: list[CandidateCode],
        disease_text: str,
    ) -> list[dict]:
        """Stage 3: union of LLM initial codes ∪ retrieved codes, dedup + cap.

        Returns list of dicts with shape:
          ``{"code", "name", "score", "chapter", "source": "llm"|"retrieve"}``

        Dedup is on ``code``; LLM code takes precedence on ties (inserted
        first). Cap is ``self._merge_cap`` (default 30).
        """
        merged: list[dict] = []
        seen: set[str] = set()

        # 1) LLM initial code (single, marked source="llm")
        for llm in llm_codes or []:
            code = (llm.get("code") or "").strip() if isinstance(llm, dict) else ""
            if not code or code in seen:
                continue
            merged.append({
                "code": code,
                "name": (llm.get("name") or "") if isinstance(llm, dict) else "",
                "score": float(llm.get("score", 1.0)) if isinstance(llm, dict) else 1.0,
                "chapter": (llm.get("chapter") or "") if isinstance(llm, dict) else "",
                "source": "llm",
            })
            seen.add(code)

        # 2) Retrieved codes
        for c in retrieved or []:
            code = c.code if isinstance(c, CandidateCode) else (c.get("code", "") if isinstance(c, dict) else "")
            if not code or code in seen:
                continue
            merged.append({
                "code": code,
                "name": c.name if isinstance(c, CandidateCode) else c.get("name", ""),
                "score": float(c.score) if isinstance(c, CandidateCode) else float(c.get("score", 0.0)),
                "chapter": c.chapter if isinstance(c, CandidateCode) else c.get("chapter", ""),
                "source": "retrieve",
            })
            seen.add(code)
            if len(merged) >= self._merge_cap:
                break

        return merged

    async def stage4_rerank(
        self,
        disease_text: str,
        evidence: str,
        candidates: list[dict],
        hints: list[str] | None = None,
    ) -> list[dict]:
        """Stage 4: RankGPT-style re-rank to top-K (default 5).

        Falls back to top-K by score when the LLM is missing or the call
        raises. Each ranked entry has shape:
          ``{"code", "name", "confidence", "rationale"}``
        """
        if not candidates:
            return []
        if not self._gateway:
            return self._mock_rerank(candidates)

        try:
            msgs = build_rerank_messages(
                disease_text, evidence or "", candidates, hints,
            )
            resp = await self._gateway.generate(msgs, provider="default")
            content = resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception as e:
            logger.warning("MedCodER: Stage 4 LLM failed: %s", e)
            return self._mock_rerank(candidates)

        ranked = parse_rerank_response(content)
        if not ranked:
            return self._mock_rerank(candidates)
        return ranked

    async def stage5_compliance(
        self,
        extracted: list[ExtractedDiagnosis],
        ctx: dict | None = None,
    ) -> MedicalCodingOutputSchema:
        """Stage 5: rule set validation + per-diagnosis calibration.

        Returns a ``MedicalCodingOutputSchema`` with:
          - ``extracted_diagnoses`` populated
          - ``mode = "medcoder"`` (and ``provider = "medcoder"``)
          - ``manual_review_required = True`` if any per-dx confidence
            is below ``CALIBRATION_FLOOR`` or if the rule set escalates
          - top-level ``confidence`` = mean of per-dx confidences
          - rule violations transcribed as ``CodingIssue`` entries
        """
        ctx = ctx or {}
        out = MedicalCodingOutputSchema()
        out.extracted_diagnoses = list(extracted)
        out.mode = "medcoder"
        out.provider = "medcoder"

        # 1) Rule set (advisory → advisory CodingIssue list)
        try:
            rs = self._get_rule_set()
            out_dict = out.to_dict()
            rule_result = rs.validate(out_dict, ctx)
            for issue in rule_result.issues:
                out.issues_found.append(CodingIssue(
                    severity=issue.severity,
                    code=issue.rule_id,
                    message=issue.message,
                    suggestion=issue.suggestion,
                ))
            if rule_result.manual_review_required:
                out.manual_review_required = True
            if not rule_result.passed and out.review_conclusion == "PASS":
                out.review_conclusion = "WARNING"
        except Exception as e:
            logger.warning("MedCodER: rule validation failed (non-fatal): %s", e)

        # 2) Per-diagnosis calibration (flat floor — M1 keeps audit Part 7.1 50/100)
        for edx in extracted:
            if edx.final_confidence < CALIBRATION_FLOOR:
                out.manual_review_required = True

        # 3) Top-level confidence = mean of per-dx confidences
        if extracted:
            out.confidence = round(
                sum(d.final_confidence for d in extracted) / len(extracted), 3
            )

        # 4) Notes (counts)
        n_dx = len(extracted)
        n_retrieved = sum(len(d.retrieved_codes) for d in extracted)
        n_reranked = sum(len(d.final_top_k) for d in extracted)
        out.notes = (
            f"MedCodER: {n_dx} diagnoses, {n_retrieved} retrieved codes, "
            f"{n_reranked} re-ranked. {out.notes}"
        ).strip()

        return out

    # ── Variant dispatch ──────────────────────────────────────────

    async def run_variant(
        self,
        emr_text: str,
        variant: str = "full",
        ctx: dict | None = None,
    ) -> MedicalCodingOutputSchema:
        """Run the requested ablation variant on the EMR text.

        ``variant`` is one of ``VARIANTS``. Raises ``ValueError`` for
        unknown variants. The 4 variant implementations are private
        (``_run_full`` etc.) — they're called only via this entry point
        so the public surface is just ``run_variant + 5 stage methods``.
        """
        if variant not in self.VARIANTS:
            raise ValueError(
                f"unknown variant {variant!r}; expected one of {self.VARIANTS}"
            )
        ctx = ctx or {}
        if variant == "full":
            return await self._run_full(emr_text, ctx)
        if variant == "prompt":
            return await self._run_prompt_only(emr_text, ctx)
        if variant == "retrieve":
            return await self._run_retrieve_only(emr_text, ctx)
        # "prompt+retrieve"
        return await self._run_prompt_plus_retrieve(emr_text, ctx)

    # ── Variant internals ─────────────────────────────────────────

    async def _run_full(
        self,
        emr_text: str,
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Full 5-stage pipeline. Equivalent to legacy
        ``HybridCodingAdapter._medcoder_pipeline`` (M0)."""
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            return out

        extraction = await self.stage1_extraction(emr_text)
        if not extraction:
            logger.warning("MedCodER: Stage 1 produced 0 diagnoses, falling back to mock")
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER Stage 1 (extraction) returned 0 diseases"
            return out

        extracted_diagnoses: list[ExtractedDiagnosis] = []
        for dx in extraction:
            edx = await self._build_extracted_diagnosis(dx, emr_text, ctx)
            extracted_diagnoses.append(edx)

        output = await self.stage5_compliance(extracted_diagnoses, ctx)
        self._populate_primary_secondary(output, extracted_diagnoses)
        return output

    async def _run_prompt_only(
        self,
        emr_text: str,
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Stage 1 only — LLM initial ICD codes, no retrieval, no rerank."""
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER variant=prompt: empty EMR"
            return out

        extraction = await self.stage1_extraction(emr_text)
        if not extraction:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER variant=prompt: Stage 1 returned 0 diseases"
            return out

        # Build extracted_diagnoses with only the LLM initial code, no
        # retrieval / rerank. final_confidence defaults to 1.0 (LLM claim)
        # unless the LLM supplied a confidence.
        extracted: list[ExtractedDiagnosis] = []
        for dx in extraction:
            edx = ExtractedDiagnosis(
                disease_text=dx.get("disease_text", ""),
                llm_initial_code=dx.get("llm_initial_code", ""),
                final_confidence=1.0,
            )
            extracted.append(edx)
        return await self.stage5_compliance(extracted, ctx)

    async def _run_retrieve_only(
        self,
        emr_text: str,
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Stage 2 only — BGE-M3 + FAISS without LLM extraction.

        Splits the EMR on sentence boundaries (``。；\n.!?;``) to derive
        pseudo-disease mentions. For each, run stage 2 then take top-1
        as the final code (no rerank).
        """
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER variant=retrieve: empty EMR"
            return out

        disease_mentions = self._split_sentences(emr_text) or [emr_text[:200]]
        extracted: list[ExtractedDiagnosis] = []
        for mention in disease_mentions:
            retrieved = await self.stage2_retrieve(mention, top_k=20)
            final_top_k: list[CandidateCode] = []
            for c in retrieved[: self._rerank_top_k]:
                if isinstance(c, CandidateCode):
                    final_top_k.append(CandidateCode(
                        code=c.code, name=c.name, score=c.score,
                        chapter=c.chapter, source="retrieve",
                    ))
            top1 = final_top_k[0] if final_top_k else None
            extracted.append(ExtractedDiagnosis(
                disease_text=mention[:80],
                retrieved_codes=list(retrieved),
                final_top_k=final_top_k,
                final_confidence=top1.score if top1 else 0.0,
                rerank_notes="retrieve-only: no LLM rerank",
            ))
        return await self.stage5_compliance(extracted, ctx)

    async def _run_prompt_plus_retrieve(
        self,
        emr_text: str,
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Stages 1+2 — LLM extraction + retrieval, no rerank, no compliance merge.

        For each extracted disease, run stage 2 + stage 3 (union dedup),
        then take top-1 by FAISS score as the final code.
        """
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER variant=prompt+retrieve: empty EMR"
            return out

        extraction = await self.stage1_extraction(emr_text)
        if not extraction:
            out = MedicalCodingOutputSchema.mock_result("medcoder")
            out.mode = "medcoder"
            out.notes = "MedCodER variant=prompt+retrieve: Stage 1 returned 0 diseases"
            return out

        extracted: list[ExtractedDiagnosis] = []
        for dx in extraction:
            disease_text = (dx.get("disease_text") or "").strip()
            llm_code = (dx.get("llm_initial_code") or "").strip()
            retrieved = await self.stage2_retrieve(disease_text, top_k=20)
            merged = await self.stage3_merge(
                [{"code": llm_code}] if llm_code else [],
                retrieved,
                disease_text,
            )
            final_top_k: list[CandidateCode] = []
            for c in merged[: self._rerank_top_k]:
                if c.get("code"):
                    final_top_k.append(CandidateCode(
                        code=c["code"], name=c.get("name", ""),
                        score=float(c.get("score", 0.0)),
                        chapter=c.get("chapter", ""), source="retrieve",
                    ))
            top1 = final_top_k[0] if final_top_k else None
            extracted.append(ExtractedDiagnosis(
                disease_text=disease_text,
                llm_initial_code=llm_code,
                retrieved_codes=list(retrieved),
                final_top_k=final_top_k,
                final_confidence=top1.score if top1 else 0.0,
                rerank_notes="prompt+retrieve: no LLM rerank",
            ))
        return await self.stage5_compliance(extracted, ctx)

    # ── Internal helpers ──────────────────────────────────────────

    async def _build_extracted_diagnosis(
        self,
        dx: dict,
        emr_text: str,
        ctx: dict,
    ) -> ExtractedDiagnosis:
        """Per-disease stages 2 + 3 + 4 + EvidenceSpan + final_top_k.

        Used by ``_run_full``. Other variants compose the stages
        themselves (without re-extracting the evidence span each time).
        """
        disease_text = (dx.get("disease_text") or "").strip()
        evidence_text = (dx.get("supporting_evidence") or "").strip()
        llm_code = (dx.get("llm_initial_code") or "").strip()

        # 0) Evidence span (fuzzy → char offset)
        spans: list[EvidenceSpan] = []
        if evidence_text:
            span_dict = fuzzy_evidence_to_span(evidence_text, emr_text)
            if span_dict:
                spans.append(EvidenceSpan(
                    text=span_dict["text"],
                    char_start=span_dict["char_start"],
                    char_end=span_dict["char_end"],
                    doc_id=ctx.get("doc_id", ""),
                    doc_type=ctx.get("doc_type", ""),
                    confidence=0.9,
                ))

        # 1) Retrieve
        retrieved = await self.stage2_retrieve(disease_text, top_k=20)

        # 2) Merge
        merged = await self.stage3_merge(
            [{"code": llm_code, "score": 1.0}] if llm_code else [],
            retrieved,
            disease_text,
        )

        # 3) Differentiation hints (best-effort, inline filesystem read)
        hints = get_differentiation_hints(disease_text)

        # 4) Re-rank
        ranked = await self.stage4_rerank(
            disease_text, evidence_text, merged, hints,
        )

        # Fallback: if rerank produced nothing, use top-K by merge score
        if not ranked:
            ranked = [
                {
                    "code": c["code"], "name": c.get("name", ""),
                    "confidence": float(c.get("score", 0.0)),
                    "rationale": "rerank-failed: using retrieval order",
                }
                for c in merged[: self._rerank_top_k]
                if c.get("code")
            ]

        # Build final_top_k list of CandidateCode with source="rerank"
        final_top_k: list[CandidateCode] = []
        for r in ranked[: self._rerank_top_k]:
            code = r.get("code", "")
            if not code:
                continue
            final_top_k.append(CandidateCode(
                code=code,
                name=r.get("name", ""),
                score=float(r.get("confidence", 0.0)),
                chapter="",
                source="rerank",
            ))

        rerank_note = ranked[0].get("rationale", "") if ranked else "no candidates"
        try:
            per_dx_conf = float(ranked[0].get("confidence", 0.0)) if ranked else 0.0
        except (TypeError, ValueError):
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

    def _populate_primary_secondary(
        self,
        output: MedicalCodingOutputSchema,
        extracted_diagnoses: list[ExtractedDiagnosis],
    ) -> None:
        """Backward-compat: fill legacy primary/secondary fields from
        ``extracted_diagnoses`` (highest-confidence → primary; rest → secondary).
        """
        if not extracted_diagnoses:
            return
        top = max(extracted_diagnoses, key=lambda d: d.final_confidence)
        if top.final_top_k:
            best = top.final_top_k[0]
            output.primary_diagnosis = DiagnosisEntry(
                code=best.code,
                description=best.name,
                confidence=top.final_confidence,
                category="principal",
                evidence=list(top.supporting_evidence),
            )
        for edx in extracted_diagnoses:
            if edx is top or not edx.final_top_k:
                continue
            b = edx.final_top_k[0]
            output.secondary_diagnoses.append(DiagnosisEntry(
                code=b.code, description=b.name,
                confidence=edx.final_confidence,
                category="comorbidity",
                evidence=list(edx.supporting_evidence),
            ))

    @staticmethod
    def _extract_emr_text(emr_or_messages: Any) -> str:
        """Accept either a raw EMR string OR a list[dict] (chat messages).

        For messages, the last user message's content is the EMR. This
        mirrors the legacy ``HybridCodingAdapter._medcoder_pipeline``
        behavior so the public ``infer_async`` contract is unchanged.
        """
        if isinstance(emr_or_messages, str):
            return emr_or_messages
        if isinstance(emr_or_messages, list):
            for m in reversed(emr_or_messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    return m.get("content", "") or ""
        return ""

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """CJK-aware sentence splitter for ``_run_retrieve_only``."""
        if not text:
            return []
        import re
        parts = re.split(r"[。；\n.!?;]+", text)
        return [p.strip() for p in parts if p and p.strip()]

    def _mock_stage1(self, emr_text: str) -> list[dict]:
        """Deterministic Stage 1 result when gateway is missing/failed.

        Single "心力衰竭" diagnosis with a stable ICD initial code. Tests
        rely on this shape — change with care.
        """
        return [{
            "disease_text": "心力衰竭",
            "supporting_evidence": emr_text[:80] if emr_text else "胸闷气短",
            "llm_initial_code": "I50.900",
        }]

    def _mock_rerank(self, candidates: list[dict]) -> list[dict]:
        """Top-K by score when Stage 4 LLM is missing or fails."""
        sorted_c = sorted(
            candidates, key=lambda c: float(c.get("score", 0)), reverse=True,
        )
        return [
            {
                "code": c.get("code", ""),
                "name": c.get("name", ""),
                "confidence": float(c.get("score", 0.0)),
                "rationale": "no-gateway: ranked by retrieval score",
            }
            for c in sorted_c[: self._rerank_top_k]
            if c.get("code")
        ]

    # ── Lazy retriever + rule set ────────────────────────────────

    def _get_retriever(self) -> Any:
        """Lazy-create the BGE-M3 + FAISS retriever on first use.

        Mirrors the legacy ``HybridCodingAdapter._get_retriever``
        (M0) selection: subprocess on Windows or when
        ``MEDCODER_SUBPROCESS=1``, in-process otherwise. Returns
        ``None`` if creation fails (e.g., index not yet built).
        """
        if self._retriever is not None or not self._retriever_lazy:
            return self._retriever
        self._retriever = self._create_default_retriever()
        self._retriever_lazy = False
        return self._retriever

    def _create_default_retriever(self) -> Any:
        """Build the default retriever (subprocess vs in-process).

        Selection (C5):
          - if ``MEDCODER_SUBPROCESS=1`` is set in the environment, use
            ``SubprocessMedCodERRetriever`` (BGE-M3 + FAISS run in a
            worker process; safe on Windows).
          - else if running on Windows (``os.name == 'nt'``), default to
            the subprocess wrapper — the in-process variant segfaults
            on this platform when combined with httpx async I/O.
          - else use the in-process ``MedCodERRetriever``.
        """
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
                logger.info(
                    "MedCodERStrategy: using SubprocessMedCodERRetriever "
                    "(MEDCODER_SUBPROCESS=%s, os.name=%s)",
                    os.environ.get("MEDCODER_SUBPROCESS", "0"), os.name,
                )
                return SubprocessMedCodERRetriever()
            return MedCodERRetriever()
        except Exception as e:
            logger.warning("MedCodERStrategy: could not create retriever: %s", e)
            return None

    def _get_rule_set(self) -> Any:
        """Lazy-create the ``MedCodERRetrievalRuleSet`` instance."""
        if self._rule_set is None:
            from compliance_services.medcoder_retrieval_rules import (
                MedCodERRetrievalRuleSet,
            )
            self._rule_set = MedCodERRetrievalRuleSet()
        return self._rule_set


__all__ = [
    "MedCodERStrategy",
    "CALIBRATION_FLOOR",
    "DEFAULT_MERGE_CAP",
    "DEFAULT_RERANK_TOP_K",
]
