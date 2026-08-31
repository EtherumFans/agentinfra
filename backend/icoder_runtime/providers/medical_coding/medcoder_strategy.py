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
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from official_agents.medical_coding.schema import (
    MedicalCodingOutputSchema, CodingIssue, CandidateCode,
    ExtractedDiagnosis, EvidenceSpan, DiagnosisEntry,
)
from official_agents.medical_coding.modes import Mode
from .medcoder_adapter import (
    build_extraction_messages,
    build_rerank_messages,
    parse_extraction_response,
    parse_rerank_response,
    fuzzy_evidence_to_span,
    get_differentiation_hints,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


# Sentinel for ``__init__``: distinguishes "no retriever argument provided"
# (use lazy default-retriever creation) from "retriever=None passed
# explicitly" (caller has no retriever at all — surface the failure).
# E1.1 (2026-06-26) — needed to make
# ``test_stage2_retrieve_no_retriever_returns_structured_degraded`` pass
# without breaking the M1 ``MedCodERStrategy(retriever=...)`` callers
# that do want lazy creation.
_NO_RETRIEVER = object()


# Stage 2 (retrieve) error codes — explicit contract for graceful degradation.
# E1.1 (2026-06-26): silent ``return []`` was a pre-existing failure
# (test_stage2_retrieve_no_retriever_returns_empty). Now we surface the
# failure mode via a structured ``Stage2Result`` so downstream code
# (MCP ``search_icd``, D2 ``index_navigator_expert``, the orchestrator
# Aggregator) can route / display / log the degraded state.
STAGE2_OK = "MEDCODER_RETRIEVE_OK"
STAGE2_RETRIEVER_UNAVAILABLE = "MEDCODER_RETRIEVER_UNAVAILABLE"
STAGE2_RETRIEVE_FAILED = "MEDCODER_RETRIEVE_FAILED"
STAGE2_EMPTY_INPUT = "MEDCODER_RETRIEVE_EMPTY_INPUT"


def _bounded_confidence(value: Any) -> float:
    """Convert an untrusted/raw score to the public confidence domain.

    FAISS inner-product scores are ranking signals and can be negative (or
    exceed one when vectors are not normalized). Provider responses can also
    contain NaN/Infinity. None of those values are valid clinical confidence
    values, so every boundary from retrieval/rerank into output schemas uses
    this helper.
    """

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return max(0.0, min(1.0, parsed))


@dataclass
class Stage2Result:
    """Stage 2 (retrieve) result with explicit degradation semantics.

    E1.1: replaces the legacy ``list[CandidateCode]`` return shape with
    a structured envelope so callers can distinguish:

      - happy path  → ``candidates=[...]``, ``degraded=False``,
        ``error_code=MEDCODER_RETRIEVE_OK``
      - no retriever → ``candidates=[]``, ``degraded=True``,
        ``error_code=MEDCODER_RETRIEVER_UNAVAILABLE``
      - runtime failure → ``candidates=[]``, ``degraded=True``,
        ``error_code=MEDCODER_RETRIEVE_FAILED``
      - empty input → ``candidates=[]``, ``degraded=False``,
        ``error_code=MEDCODER_RETRIEVE_EMPTY_INPUT``
        (NOT a failure; just nothing to retrieve)

    The ``candidates`` field stays a list so ``for c in result.candidates``
    still works for M1 callers.
    """

    candidates: list[CandidateCode] = field(default_factory=list)
    degraded: bool = False
    error_code: str = STAGE2_OK
    error_detail: str = ""

    @property
    def is_ok(self) -> bool:
        return not self.degraded and self.error_code == STAGE2_OK

    def to_dict(self) -> dict:
        return {
            "candidates": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in self.candidates
            ],
            "degraded": self.degraded,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


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
        retriever: Any = _NO_RETRIEVER,
        rule_set: Any = None,
        merge_cap: int = DEFAULT_MERGE_CAP,
        rerank_top_k: int = DEFAULT_RERANK_TOP_K,
        procedure_retriever: Any = None,
    ) -> None:
        # E1.1: explicit ``retriever=None`` is now distinct from "not
        # provided" (default). The latter uses lazy auto-creation; the
        # former tells the strategy "I have no retriever" — surface the
        # failure via ``Stage2Result`` rather than silently faking one.
        if retriever is _NO_RETRIEVER:
            self._retriever: Any = None
            self._retriever_lazy = True
        elif retriever is None:
            self._retriever = None
            self._retriever_lazy = False  # do NOT lazy-create
        else:
            self._retriever = retriever
            self._retriever_lazy = False
        # E1.3: parallel procedure retriever (ICD-9-CM-3). No
        # sentinel dance — the procedure retriever is an opt-in
        # sidecar used by callers that want to enrich Stage 2 with
        # procedure RAG. ``procedure_retriever=None`` (default)
        # lazy-creates a subprocess-isolated wrapper on Windows; an
        # explicit instance (test injection) skips lazy creation.
        if procedure_retriever is not None:
            self._proc_retriever: Any = procedure_retriever
            self._proc_retriever_lazy = False
        else:
            self._proc_retriever = None
            self._proc_retriever_lazy = True
        self._gateway = gateway
        self._rule_set = rule_set
        self._merge_cap = merge_cap
        self._rerank_top_k = rerank_top_k

    # ── 5 public stage methods ─────────────────────────────────────

    async def stage1_extraction(
        self,
        emr_text: str,
        project_policy: str = "",
    ) -> Any:
        """Stage 1: LLM call → :class:`ExtractionResult`.

        E1.4: returns ``ExtractionResult`` (diseases + procedure_mentions)
        instead of a raw disease list. ``ExtractionResult`` is iterable
        over diseases so existing ``for dx in extraction`` callers keep
        working. Use ``extraction.diseases`` for explicit access or
        ``extraction.procedure_mentions`` for the new procedure list.

        Missing, degraded, invalid, or failed LLM calls return an empty
        extraction. The variant runner converts that to an explicit failed
        schema; synthetic diagnoses are never produced in a runtime path.
        """
        if not emr_text or not emr_text.strip():
            return ExtractionResult()
        ext_messages = build_extraction_messages(emr_text, project_policy)
        if not self._gateway:
            logger.warning("MedCodER: Stage 1 gateway unavailable")
            return ExtractionResult()
        try:
            resp = await self._gateway.generate(ext_messages, provider="default")
            if not isinstance(resp, dict) or resp.get("degraded") or resp.get("is_mock"):
                logger.warning("MedCodER: Stage 1 gateway degraded")
                return ExtractionResult()
            content = resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception as exc:
            logger.warning(
                "MedCodER: Stage 1 LLM failed error_type=%s",
                type(exc).__name__,
            )
            return ExtractionResult()
        return parse_extraction_response(content)

    async def stage2_retrieve(
        self,
        disease_text: str,
        top_k: int = 20,
    ) -> Stage2Result:
        """Stage 2: BGE-M3 + FAISS top-K ICD candidate codes.

        E1.1 (2026-06-26): returns a ``Stage2Result`` with explicit
        ``degraded`` / ``error_code`` so the silent ``return []`` failure
        mode is no longer invisible. The 4 cases:

          - empty input  → ``Stage2Result(candidates=[], degraded=False,
                            error_code=MEDCODER_RETRIEVE_EMPTY_INPUT)``
          - no retriever → ``Stage2Result(candidates=[], degraded=True,
                            error_code=MEDCODER_RETRIEVER_UNAVAILABLE)``
          - exception    → ``Stage2Result(candidates=[], degraded=True,
                            error_code=MEDCODER_RETRIEVE_FAILED, error_detail=str(e))``
          - happy path   → ``Stage2Result(candidates=[...], degraded=False,
                            error_code=MEDCODER_RETRIEVE_OK)``

        M1 callers that iterate ``for c in stage2_retrieve(...).candidates``
        keep working unchanged; M1 callers that did
        ``stage2_retrieve(...) == []`` should be migrated to check
        ``result.is_ok`` and ``result.degraded`` (see
        ``stage2_retrieve_legacy`` for the raw-list shim).
        """
        text = (disease_text or "").strip()
        if not text:
            return Stage2Result(
                candidates=[],
                degraded=False,
                error_code=STAGE2_EMPTY_INPUT,
                error_detail="empty disease_text",
            )
        retriever = self._get_retriever()
        if retriever is None:
            logger.warning(
                "MedCodER: Stage 2 retriever unavailable (no FAISS index loaded)"
            )
            return Stage2Result(
                candidates=[],
                degraded=True,
                error_code=STAGE2_RETRIEVER_UNAVAILABLE,
                error_detail="BGE-M3 + FAISS retriever not initialized",
            )
        try:
            candidates = await retriever.retrieve_async(text, top_k=top_k)
            return Stage2Result(
                candidates=candidates,
                degraded=False,
                error_code=STAGE2_OK,
            )
        except Exception as e:
            logger.warning("MedCodER: Stage 2 retrieve failed: %s", e)
            return Stage2Result(
                candidates=[],
                degraded=True,
                error_code=STAGE2_RETRIEVE_FAILED,
                error_detail=str(e),
            )

    def stage2_retrieve_legacy(self, *args, **kwargs) -> list[CandidateCode]:
        """Back-compat shim — sync wrapper that returns raw ``candidates`` list.

        E1.1: replaces the old ``stage2_retrieve`` signature
        (``list[CandidateCode]``) for any caller that hasn't migrated
        to ``Stage2Result`` yet. Prefer the new structured return.
        """
        import asyncio
        result = asyncio.run(self.stage2_retrieve(*args, **kwargs))
        return result.candidates

    async def stage2_retrieve_procedure(
        self,
        procedure_text: str,
        top_k: int = 20,
    ) -> Stage2Result:
        """Stage 2 (procedure sidecar): BGE-M3 + FAISS over ICD-9-CM-3.

        E1.3: closes the procedure-side retrieval gap (the 53 MB
        ``faiss_icd9cm3.index`` was built but never consumed). Same
        :class:`Stage2Result` envelope as the diagnosis retriever so
        callers handle both the same way. ``candidates`` are
        :class:`CandidateCode` with ``source="retrieve"`` and the
        ICD-9-CM-3 chapter name in ``chapter``.

        Used by callers that already have a procedure mention (e.g.
        from a structured EMR field, or a follow-up call after the
        diagnosis retriever finds a procedure-like candidate). The
        main 5-stage pipeline does not call this method yet — wiring
        it into the LLM extraction prompt is a follow-up task
        (E1.4: extract ``procedure_mentions`` alongside
        ``disease_mentions``).
        """
        text = (procedure_text or "").strip()
        if not text:
            return Stage2Result(
                candidates=[],
                degraded=False,
                error_code=STAGE2_OK,
            )
        proc_retriever = self._get_procedure_retriever()
        if proc_retriever is None:
            logger.warning(
                "MedCodER: procedure retriever unavailable "
                "(no ICD-9-CM-3 FAISS index loaded)"
            )
            return Stage2Result(
                candidates=[],
                degraded=True,
                error_code=STAGE2_RETRIEVER_UNAVAILABLE,
                error_detail="ICD-9-CM-3 retriever not initialized",
            )
        try:
            candidates = await proc_retriever.retrieve_async(text, top_k=top_k)
            return Stage2Result(
                candidates=candidates,
                degraded=False,
                error_code=STAGE2_OK,
            )
        except Exception as e:
            logger.warning("MedCodER: procedure retrieve failed: %s", e)
            return Stage2Result(
                candidates=[],
                degraded=True,
                error_code=STAGE2_RETRIEVE_FAILED,
                error_detail=str(e),
            )

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
        project_policy: str = "",
    ) -> list[dict]:
        """Stage 4: RankGPT-style re-rank to top-K (default 5).

        Falls back to top-K by score when the LLM is missing or the call
        raises. Each ranked entry has shape:
          ``{"code", "name", "confidence", "rationale"}``
        """
        if not candidates:
            return []
        if not self._gateway:
            return self._deterministic_rerank(candidates)

        try:
            msgs = build_rerank_messages(
                disease_text,
                evidence or "",
                candidates,
                hints,
                project_policy,
            )
            resp = await self._gateway.generate(msgs, provider="default")
            content = resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception as e:
            logger.warning("MedCodER: Stage 4 LLM failed: %s", e)
            return self._deterministic_rerank(candidates)

        ranked = parse_rerank_response(content)
        if not ranked:
            return self._deterministic_rerank(candidates)
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
        out.mode = Mode.MEDCODER
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
        ``HybridCodingAdapter._medcoder_pipeline`` (M0).

        E1.4: also runs procedure RAG (Stage 2 over ICD-9-CM-3) for each
        mention in ``extraction.procedure_mentions``. Populates
        ``output.procedures`` with one :class:`ProcedureEntry` per
        mention (top-1 by retrieval score).
        """
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="empty_emr"
            )
            out.mode = Mode.MEDCODER
            return out

        project_policy = str(ctx.get("project_policy") or "")
        extraction = (
            await self.stage1_extraction(emr_text, project_policy)
            if project_policy
            else await self.stage1_extraction(emr_text)
        )
        if not extraction:
            logger.warning("MedCodER: Stage 1 produced 0 diagnoses; failing closed")
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="stage1_empty"
            )
            out.mode = Mode.MEDCODER
            out.notes = "MedCodER Stage 1 (extraction) returned 0 diseases"
            return out

        extracted_diagnoses: list[ExtractedDiagnosis] = []
        for dx in extraction:
            edx = await self._build_extracted_diagnosis(dx, emr_text, ctx)
            extracted_diagnoses.append(edx)

        output = await self.stage5_compliance(extracted_diagnoses, ctx)
        self._populate_primary_secondary(output, extracted_diagnoses)
        # E1.4: procedure RAG sidecar (ICD-9-CM-3)
        await self._populate_procedures(output, list(extraction.procedure_mentions), emr_text=emr_text)
        return output

    async def _run_prompt_only(
        self,
        emr_text: str,
        ctx: dict,
    ) -> MedicalCodingOutputSchema:
        """Stage 1 only — LLM initial ICD codes, no retrieval, no rerank."""
        emr_text = self._extract_emr_text(emr_text)
        if not emr_text:
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="empty_emr"
            )
            out.mode = Mode.MEDCODER
            out.notes = "MedCodER variant=prompt: empty EMR"
            return out

        project_policy = str(ctx.get("project_policy") or "")
        extraction = (
            await self.stage1_extraction(emr_text, project_policy)
            if project_policy
            else await self.stage1_extraction(emr_text)
        )
        if not extraction:
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="stage1_empty"
            )
            out.mode = Mode.MEDCODER
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
        output = await self.stage5_compliance(extracted, ctx)
        # E1.4: procedure RAG sidecar (ICD-9-CM-3) — same as ``full`` but
        # without LLM rerank on the diagnosis side. Procedure candidates
        # still go through :meth:`stage2_retrieve_procedure`.
        await self._populate_procedures(output, list(extraction.procedure_mentions), emr_text=emr_text)
        return output

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
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="empty_emr"
            )
            out.mode = Mode.MEDCODER
            out.notes = "MedCodER variant=retrieve: empty EMR"
            return out

        disease_mentions = self._split_sentences(emr_text) or [emr_text[:200]]
        extracted: list[ExtractedDiagnosis] = []
        for mention in disease_mentions:
            retrieved = (await self.stage2_retrieve(mention, top_k=20)).candidates
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
                final_confidence=(
                    _bounded_confidence(top1.score) if top1 else 0.0
                ),
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
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="empty_emr"
            )
            out.mode = Mode.MEDCODER
            out.notes = "MedCodER variant=prompt+retrieve: empty EMR"
            return out

        project_policy = str(ctx.get("project_policy") or "")
        extraction = (
            await self.stage1_extraction(emr_text, project_policy)
            if project_policy
            else await self.stage1_extraction(emr_text)
        )
        if not extraction:
            out = MedicalCodingOutputSchema.failure_result(
                "medcoder", reason="stage1_empty"
            )
            out.mode = Mode.MEDCODER
            out.notes = "MedCodER variant=prompt+retrieve: Stage 1 returned 0 diseases"
            return out

        extracted: list[ExtractedDiagnosis] = []
        for dx in extraction:
            disease_text = (dx.get("disease_text") or "").strip()
            llm_code = (dx.get("llm_initial_code") or "").strip()
            retrieved = (await self.stage2_retrieve(disease_text, top_k=20)).candidates
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
                final_confidence=(
                    _bounded_confidence(top1.score) if top1 else 0.0
                ),
                rerank_notes="prompt+retrieve: no LLM rerank",
            ))
        output = await self.stage5_compliance(extracted, ctx)
        # E1.4: procedure RAG sidecar (ICD-9-CM-3) — same as ``full``.
        await self._populate_procedures(output, list(extraction.procedure_mentions), emr_text=emr_text)
        return output

    # ── Internal helpers ──────────────────────────────────────────

    async def _populate_procedures(
        self,
        out: MedicalCodingOutputSchema,
        mentions: list[str],
        emr_text: str = "",
    ) -> None:
        """E1.4: populate ``out.procedures`` from extracted procedure mentions.

        E1.6: for each mention, run a **catalog-mention pre-lookup** against
        the ICD-9-CM-3 catalog (substring match on ``name_cn`` /
        ``synonyms_cn``) before falling back to BGE-M3 retrieval.
        Catalog matches are guaranteed hits (score=1.0) and take priority
        over fuzzy retrieval when codes collide.

        E1.7: when ``emr_text`` is provided, also run a **catalog-text
        scan** to find procedure mentions the LLM may have missed
        (e.g., buried "脐动脉插管" inside a longer narrative). Catalog-scan
        mentions are appended to the LLM-extracted list before dedup.

        For each mention:
          1. Catalog lookup → list of "guaranteed" candidates (score=1.0).
          2. BGE-M3 + FAISS retrieval → top-K fuzzy candidates.
          3. Merge: union, dedup on code (catalog wins), take top-K.
        The top-1 of the merged list becomes a :class:`ProcedureEntry`.

        Dedup is on code (across mentions). Caps at 10 mentions per EMR.
        Failures are non-fatal: a degraded retriever + missing catalog
        leaves ``out.procedures`` empty. The diagnosis pipeline still
        completes — procedure is a sidecar.
        """
        from official_agents.medical_coding.schema import ProcedureEntry

        # E1.7: augment LLM-extracted mentions with a catalog-text scan.
        # The LLM extraction misses buried procedures (the realistic
        # smoke showed hit@1=0% even with oracle retriever — the gap
        # is upstream extraction completeness).
        all_mentions = list(mentions or [])
        if emr_text:
            scan_mentions = self._catalog_scan_emr_text(emr_text)
            # Append (not prepend) — LLM mentions are usually higher
            # signal. Dedup on case-insensitive exact match.
            seen_text = {m.strip().lower() for m in all_mentions if m and m.strip()}
            for sm in scan_mentions:
                key = sm.strip().lower()
                if key and key not in seen_text:
                    all_mentions.append(sm)
                    seen_text.add(key)

        if not all_mentions:
            return

        seen_codes: set[str] = set()
        procedures: list[ProcedureEntry] = []
        # Cap mentions to avoid blowing up the LLM-extracted list
        # (long EMRs with explicit "all procedures listed" sections
        # can produce 30+ mentions).
        for mention in all_mentions[:10]:
            text = (mention or "").strip()
            if not text:
                continue
            merged = await self._merge_procedure_candidates(text, top_k=5)
            if not merged:
                continue
            top = merged[0]
            code = (top.code or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            procedures.append(ProcedureEntry(
                code=code,
                description=top.name or "",
                confidence=_bounded_confidence(top.score),
                category="therapeutic",  # default; future work: classify
                evidence=[text],
            ))
        out.procedures = procedures

    def _catalog_scan_emr_text(
        self,
        text: str,
        min_name_len: int = 3,
        max_mentions: int = 20,
    ) -> list[str]:
        """E1.7: scan EMR text for all ICD-9-CM-3 catalog name matches.

        For each catalog entry whose ``name_cn`` (or any synonym) is a
        substring of ``text`` and has length ≥ ``min_name_len``, return
        the matched name as a procedure mention. This supplements LLM
        extraction by catching buried procedure names the LLM may have
        missed.

        Args:
          text: EMR text to scan.
          min_name_len: minimum catalog name length to consider. Lower
            values increase recall but add noise (single Chinese chars
            match too broadly).
          max_mentions: cap on returned mentions.

        Returns:
          List of matched catalog names (in catalog iteration order).
        """
        if not text or not text.strip():
            return []

        try:
            from app.services.icd9cm3_loader import get_loader
            loader = get_loader()
            loader.ensure_loaded()
        except Exception:
            return []

        out: list[str] = []
        seen: set[str] = set()
        # Linear scan: 13.6k entries × EMR text length. For each entry,
        # check name_cn + synonyms for substring containment.
        #
        # Catalog names are often long with qualifiers (e.g. "古典式剖宫产"
        # is 5 chars, "剖宫产术，子宫下段横切口" is 10 chars). EMR text
        # rarely contains the full qualified name verbatim — usually
        # just the short core fragment (e.g. "剖宫产"). We use
        # bidirectional substring matching as the workhorse:
        #   1) name in text  (full catalog name appears in EMR) → match
        #   2) text-fragment in name (EMR fragment inside long catalog
        #      name) → not useful: text is the whole EMR, longer than
        #      almost any name. The right direction is short-prefix
        #      matching: take the first min_name_len chars of each
        #      catalog name and check if that prefix is in the EMR.
        # This catches "剖宫产" (3-char prefix) in "古典式剖宫产" when
        # the EMR says "行剖宫产术...".
        for entry in loader.all_codes():
            names_to_check = (entry.name_cn, *entry.synonyms_cn)
            matched = False
            for n in names_to_check:
                if not n or len(n) < min_name_len:
                    continue
                # Check 1: full name appears in EMR
                if n in text:
                    matched = True
                    break
                # Check 2: short prefix of name appears in EMR.
                # Use the first min_name_len chars of the name (3 by
                # default) — captures the meaningful core of the
                # procedure name regardless of trailing qualifiers.
                prefix = n[:min_name_len]
                if prefix != n and prefix in text:
                    matched = True
                    break
            if matched:
                canonical = entry.name_cn
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    out.append(canonical)
                    if len(out) >= max_mentions:
                        return out
        return out

    async def _merge_procedure_candidates(
        self,
        text: str,
        top_k: int = 5,
    ) -> list:
        """E1.6: merge catalog-mention pre-lookup ∪ BGE-M3 retrieval.

        Returns a list of ``CandidateCode`` (or compatible shape) sorted
        by descending score. Catalog matches score 1.0; retrieval
        candidates keep their FAISS inner-product scores.

        Either side can fail independently:
          - Catalog lookup: best-effort substring match, no exceptions.
          - BGE-M3 retrieval: may degrade (FAISS missing, embed failed).

        Returns ``[]`` if both sides produce nothing. The caller treats
        empty as "no procedure" — non-fatal.
        """
        from official_agents.medical_coding.schema import CandidateCode

        catalog_candidates = self._catalog_lookup_procedure(text)
        retrieved = await self.stage2_retrieve_procedure(text, top_k=top_k)

        # Merge: keyed by code, max score wins, catalog always at 1.0.
        merged: dict[str, CandidateCode] = {}
        for c in catalog_candidates:
            if c.code and c.code not in merged:
                merged[c.code] = c
        for c in (retrieved.candidates or []):
            if not c.code:
                continue
            existing = merged.get(c.code)
            if existing is None or (c.score or 0.0) > (existing.score or 0.0):
                merged[c.code] = c

        # Sort by score desc, then by code for deterministic ordering.
        return sorted(
            merged.values(),
            key=lambda c: (-(c.score or 0.0), c.code),
        )

    def _catalog_lookup_procedure(self, text: str) -> list:
        """E1.6: substring match ``text`` against ICD-9-CM-3 catalog entries.

        Returns a list of ``CandidateCode`` with ``score=1.0`` (catalog
        match is a guaranteed hit). Searches ``name_cn`` and
        ``synonyms_cn`` for substring containment in either direction:

          - mention ⊂ name (e.g. "剖宫产" in "剖宫产术") → match
          - name ⊂ mention (e.g. mention "剖宫产术" matches catalog "剖宫产") → match

        Best-effort: returns ``[]`` if the loader is unavailable. Caps at
        10 candidates to bound work per mention.
        """
        from official_agents.medical_coding.schema import CandidateCode

        if not text or not text.strip():
            return []
        needle = text.strip()
        try:
            from app.services.icd9cm3_loader import get_loader
            loader = get_loader()
            loader.ensure_loaded()
        except Exception:
            return []

        out: list[CandidateCode] = []
        # Linear scan: 13.6k entries × 10 mentions ≈ 136k comparisons per
        # case. Fast enough in Python (~10 ms). A precomputed index would
        # trade memory for speed; deferred until profiling shows it's
        # worth it.
        for entry in loader.all_codes():
            name_cn = entry.name_cn or ""
            synonyms_cn = entry.synonyms_cn or ()
            haystacks = (name_cn, *synonyms_cn)
            if not any(hay for hay in haystacks):
                continue
            matched = False
            for hay in haystacks:
                if not hay:
                    continue
                if needle in hay or hay in needle:
                    matched = True
                    break
            if matched:
                out.append(CandidateCode(
                    code=entry.code,
                    name=entry.name_cn,
                    score=1.0,
                    chapter=entry.chapter_name or "",
                    source="catalog",
                ))
                if len(out) >= 10:
                    break
        return out

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

        # 1) Retrieve (E1.1: stage2_retrieve returns Stage2Result envelope)
        retrieved = (await self.stage2_retrieve(disease_text, top_k=20)).candidates

        # 2) Merge
        merged = await self.stage3_merge(
            [{"code": llm_code, "score": 1.0}] if llm_code else [],
            retrieved,
            disease_text,
        )

        # 3) Differentiation hints (best-effort, inline filesystem read)
        hints = get_differentiation_hints(disease_text)

        # 4) Re-rank
        project_policy = str(ctx.get("project_policy") or "")
        ranked = (
            await self.stage4_rerank(
                disease_text,
                evidence_text,
                merged,
                hints,
                project_policy,
            )
            if project_policy
            else await self.stage4_rerank(
                disease_text,
                evidence_text,
                merged,
                hints,
            )
        )

        # Fallback: if rerank produced nothing, use top-K by merge score
        if not ranked:
            ranked = [
                {
                    "code": c["code"], "name": c.get("name", ""),
                    "confidence": _bounded_confidence(c.get("score", 0.0)),
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
                score=_bounded_confidence(r.get("confidence", 0.0)),
                chapter="",
                source="rerank",
            ))

        rerank_note = ranked[0].get("rationale", "") if ranked else "no candidates"
        try:
            per_dx_conf = (
                _bounded_confidence(ranked[0].get("confidence", 0.0))
                if ranked
                else 0.0
            )
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
                confidence=_bounded_confidence(top.final_confidence),
                category="principal",
                evidence=list(top.supporting_evidence),
            )
        for edx in extracted_diagnoses:
            if edx is top or not edx.final_top_k:
                continue
            b = edx.final_top_k[0]
            output.secondary_diagnoses.append(DiagnosisEntry(
                code=b.code, description=b.name,
                confidence=_bounded_confidence(edx.final_confidence),
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

    def _deterministic_rerank(self, candidates: list[dict]) -> list[dict]:
        """Degraded Top-K using only real retrieval scores."""
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
        remote_url = os.environ.get("MEDCODER_RETRIEVER_URL", "").strip()
        if remote_url:
            try:
                from .remote_retriever import RemoteMedCodERRetriever

                logger.info("MedCodERStrategy: using isolated remote ICD-10-CN retriever")
                return RemoteMedCodERRetriever.from_env(code_system="ICD-10-CN")
            except Exception as exc:
                logger.error(
                    "MedCodERStrategy: remote retriever configuration invalid: %s",
                    type(exc).__name__,
                )
                return None

        from .runtime_safety import assess_bge_runtime_safety

        safety = assess_bge_runtime_safety()
        if not safety.safe:
            logger.error("MedCodERStrategy: local BGE disabled: %s", safety.reason)
            return None
        use_subprocess = (
            os.environ.get("MEDCODER_SUBPROCESS") == "1"
            or os.name == "nt"
        )
        try:
            # E1.9 (2026-06-27): pin BGE-M3 to fp16 BEFORE constructing the
            # retriever. The in-process path constructs BGEEmbedder at
            # construction time (via ``_get_embedder`` → BGEEmbedder(**kwargs)
            # → reads MEDCODER_BGE_DTYPE / DEVICE env). The subprocess path
            # spawns a child that inherits parent env at start time, so
            # setdefault before subprocess.start() means the child loads fp16.
            os.environ.setdefault("MEDCODER_BGE_DTYPE", "float16")
            os.environ.setdefault("MEDCODER_BGE_DEVICE", "cpu")
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

    def _get_procedure_retriever(self) -> Any:
        """Lazy-create the ICD-9-CM-3 procedure retriever (E1.3).

        Mirrors :meth:`_get_retriever` but for the procedure index.
        Returns ``None`` if creation fails (index not built, FAISS
        missing, etc.) — the caller surfaces the failure via
        ``Stage2Result(error_code=STAGE2_RETRIEVER_UNAVAILABLE)``.
        """
        if not self._proc_retriever_lazy:
            return self._proc_retriever
        self._proc_retriever = self._create_default_procedure_retriever()
        self._proc_retriever_lazy = False
        return self._proc_retriever

    def _create_default_procedure_retriever(self) -> Any:
        """Build the default ICD-9-CM-3 procedure retriever (E1.3).

        Same subprocess-vs-in-process selection as
        :meth:`_create_default_retriever`. The procedure index
        (``faiss_icd9cm3.index``) is loaded by
        ``MedCodERICD9CM3Retriever``; the subprocess wrapper
        ``SubprocessMedCodERICD9CM3Retriever`` isolates BGE-M3 from
        the parent's httpx async loop on Windows.
        """
        remote_url = os.environ.get("MEDCODER_RETRIEVER_URL", "").strip()
        if remote_url:
            try:
                from .remote_retriever import RemoteMedCodERRetriever

                logger.info(
                    "MedCodERStrategy: using isolated remote ICD-9-CM-3-CN retriever"
                )
                return RemoteMedCodERRetriever.from_env(
                    code_system="ICD-9-CM-3-CN"
                )
            except Exception as exc:
                logger.error(
                    "MedCodERStrategy: remote procedure retriever configuration invalid: %s",
                    type(exc).__name__,
                )
                return None

        from .runtime_safety import assess_bge_runtime_safety

        safety = assess_bge_runtime_safety()
        if not safety.safe:
            logger.error(
                "MedCodERStrategy: local procedure BGE disabled: %s",
                safety.reason,
            )
            return None
        use_subprocess = (
            os.environ.get("MEDCODER_SUBPROCESS") == "1"
            or os.name == "nt"
        )
        try:
            # E1.9: same fp16 env pin as above (see _create_default_retriever).
            os.environ.setdefault("MEDCODER_BGE_DTYPE", "float16")
            os.environ.setdefault("MEDCODER_BGE_DEVICE", "cpu")
            from .medcoder_retriever import (
                MedCodERICD9CM3Retriever,
                SubprocessMedCodERICD9CM3Retriever,
            )
            if use_subprocess:
                logger.info(
                    "MedCodERStrategy: using SubprocessMedCodERICD9CM3Retriever "
                    "(MEDCODER_SUBPROCESS=%s, os.name=%s)",
                    os.environ.get("MEDCODER_SUBPROCESS", "0"), os.name,
                )
                return SubprocessMedCodERICD9CM3Retriever()
            return MedCodERICD9CM3Retriever()
        except Exception as e:
            logger.warning(
                "MedCodERStrategy: could not create procedure retriever: %s", e,
            )
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
