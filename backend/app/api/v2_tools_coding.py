"""iCoDer v2 Medical Coding endpoints — Phase 1.1 + Cycle 18.

This module hosts two adjacent endpoints under the ``/api/v2/tools`` prefix:

  - ``POST /api/v2/tools/coding/icoder/``  — Phase 1.1 (2026-06-30) thin HTTP
    wrapper around ``HybridCodingAdapter(mode="medcoder").infer_async`` that
    exposes the iCoDer 5-stage MedCodER pipeline (Extraction + Retrieval +
    Merge + Re-rank + Compliance). Chinese-only system namespace
    (ICD-10-CN / ICD-9-CM-3). NOT a replacement for M3-0
    ``/api/icoder/coding-review/*`` (legacy retained by ``5c4e0e3``).

  - ``POST /api/v2/tools/coding/``  — Cycle 18 (2026-07-01) align with
    Corti §13.6 ``codes_predict``: stateless single-shot prediction that
    accepts all 15 ``CommonCodingSystemEnum`` systems and returns
    ``{codes, candidates, usageInfo}`` per the Corti OpenAPI spec.

The two endpoints were deliberately split at the path level so the canonical
Corti path (``/tools/coding/``) is reserved for the Corti-spec multi-system
predictor, while the iCoDer 5-stage MedCodER pipeline (which only speaks
Chinese ICD) lives at the ``/icoder/`` sub-resource. The Phase 1.1 endpoint
was originally registered at the canonical path; the relocation landed in
cycle 18 to free the canonical path for the Corti-spec endpoint.

Field maps and design rationale:
  - ``docs/PHASE_1_1_MEDICAL_CODING_PATH_SCHEMA.md`` (Phase 1.1)
  - ``docs/PHASE_1_3_CYCLE18_CODES_PREDICT.md`` (Cycle 18)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.v2_tools_coding import (
    CORTI_COMMON_CODING_SYSTEMS,
    CodesFilter,
    CodesGeneralPredictRequest,
    CodesGeneralReadResponse,
    CodesGeneralResponse,
    CodingAlternative,
    CodingCode,
    CodingContextItem,
    CodingEvidence,
    CodingRequest,
    CodingResponse,
    CommonAIContext,
    CommonUsageInfo,
    ICODER_CODING_SYSTEMS,
    default_coding_system,
    default_corti_coding_system,
)
from app.services.code_dictionary import _ICD10_CODES, _ICD9_CODES
from icoder_runtime.providers.medical_coding import HybridCodingAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Display-name lookup ─────────────────────────────────────────────
# Build a flat {code: name} index from the same dicts ``CodeDictionaryService``
# uses internally. Avoids wrapping an async service just for a synchronous
# ``code -> name`` lookup in the 5-stage pipeline response path.
_DISPLAY_INDEX: dict[str, str] = {}
for _entry in (*_ICD10_CODES, *_ICD9_CODES):
    _code = _entry.get("code")
    _name = _entry.get("name")
    if _code and _name and _code not in _DISPLAY_INDEX:
        _DISPLAY_INDEX[_code] = _name


def _display_for(code: str) -> str:
    """Return the long Chinese display name for a code, or a chapter-less fallback."""
    if not code:
        return ""
    name = _DISPLAY_INDEX.get(code)
    if name:
        return name
    # Fallback (rare — ICD-10-CN catalog covers ~37,897 codes): keep the
    # response shape valid so callers never see a 5xx due to display lookup.
    return f"({code})"


# ─── Mode mapping (query param ↔ HybridCodingAdapter.mode) ───────────
# ``medcoder.full`` is the default and corresponds to NAACL 2025 Fig 2 'full'
# (5 stages complete). The other 3 ablation variants are exposed for caller
# parity with the existing ``MethodComparePage``.
_MODE_TO_ADAPTER: dict[str, str] = {
    "medcoder": "medcoder.full",
    "full": "medcoder.full",
    "prompt": "medcoder.prompt",
    "retrieve": "medcoder.retrieve",
    "prompt+retrieve": "medcoder.prompt_retrieve",
}
_ALLOWED_MODE_VALUES: frozenset[str] = frozenset(_MODE_TO_ADAPTER.keys())


# ─── Request transformation helpers ─────────────────────────────────


def _validate_request(body: CodingRequest) -> tuple[list[str], str]:
    """Validate system + context; return ``(allowed_systems, default_system_or_echo)``.

    Raises ``HTTPException`` for:
    - empty / all-empty context[]  → 400 ``empty_context``
    - unknown system values       → 400 ``unsupported_system``
    """
    if not body.context or not any(item.text.strip() for item in body.context):
        raise HTTPException(
            status_code=400,
            detail={"error": "empty_context", "hint": "context[].text must contain at least one non-empty string"},
        )
    if body.system:
        unknown = [s for s in body.system if s not in ICODER_CODING_SYSTEMS]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_system",
                    "received": unknown,
                    "allowed": sorted(ICODER_CODING_SYSTEMS),
                    "hint": "iCoDer accepts only iCoDer-system names; Corti US names are intentionally rejected (different coding standard).",
                },
            )
        chosen_system = body.system[0]
    else:
        chosen_system = default_coding_system()
    return list(body.system) or [chosen_system], chosen_system


def _build_messages(
    contexts: Iterable[CodingContextItem],
    allowed_systems: list[str],
    chosen_system: str,
) -> list[dict[str, str]]:
    """Compose the LLM-facing messages for ``HybridCodingAdapter``.

    Concatenates the non-empty context blocks in order with explicit
    separators so the model can anchor evidence by char offset relative
    to each block.
    """
    blocks = [c.text for c in contexts if c.text and c.text.strip()]
    merged = "\n\n".join(blocks)
    system_prompt = (
        "You are iCoDer medical coding auditor (Phase 1.1 v2 endpoint). "
        f"Target coding system: {chosen_system}. "
        "Return codes with char-span evidence links."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": merged},
    ]


def _resolve_context_index(doc_id: str, blocks: list[CodingContextItem]) -> int:
    """Map an EvidenceSpan's ``doc_id`` back to the originating context index.

    Convention used by the evidence extractor / MedCodER pipeline:
    - When ``doc_id`` is empty or non-integer, return 0 (single-context fallback).
    - When ``doc_id`` is "0", "1", ..., it indexes the input ``context[]`` list.
    Negative or out-of-range values fall back to 0; the caller is supposed
    to trust the model here.
    """
    if not doc_id:
        return 0
    if doc_id.isdigit():
        idx = int(doc_id)
        if 0 <= idx < len(blocks):
            return idx
    return 0


def _build_evidence(
    span: Any,
    blocks: list[CodingContextItem],
    chosen_system: str,
) -> CodingEvidence | None:
    """Map an iCoDer ``EvidenceSpan`` to Corti ``CodingEvidence``.

    Returns ``None`` when the span is unusable (missing text/offset, etc.)
    so the caller can drop it silently rather than emit a 500.
    """
    text = getattr(span, "text", "") or ""
    char_start = int(getattr(span, "char_start", 0) or 0)
    char_end = int(getattr(span, "char_end", 0) or 0)
    if not text or char_end <= char_start:
        return None
    idx = _resolve_context_index(getattr(span, "doc_id", "") or "", blocks)
    return CodingEvidence(contextIndex=idx, text=text, start=char_start, end=char_end)


def _build_alternatives(top_k: Iterable[Any]) -> list[CodingAlternative]:
    """Map reranked final_top_k[1:5] → Corti alternatives[].

    Only the *non-primary* candidates become alternatives — the primary one
    is the ``code`` field on the parent ``CodingCode``.
    """
    alts: list[CodingAlternative] = []
    for cand in top_k:
        if not isinstance(cand, (list, tuple)):
            code = getattr(cand, "code", "") or (cand.get("code", "") if isinstance(cand, dict) else "")
            display = getattr(cand, "name", "") or (cand.get("name", "") if isinstance(cand, dict) else "")
        else:
            # Sequence shape — defensively handle 2- or 3-tuples.
            code = cand[0] if len(cand) >= 1 else ""
            display = cand[1] if len(cand) >= 2 else ""
        if not code:
            continue
        alts.append(CodingAlternative(code=code, display=display or _display_for(code)))
        if len(alts) >= 5:
            break
    return alts


# ─── Phase 1.1 endpoint — iCoDer 5-stage MedCodER (relocated) ────────
# Originally at ``/api/v2/tools/coding/`` (cycle 18 cycle moves it to
# ``/api/v2/tools/coding/icoder/`` to free the canonical Corti path).


@router.post("/coding/icoder", response_model=CodingResponse)
@router.post("/coding/icoder/", response_model=CodingResponse)
async def post_v2_tools_coding_icoder(
    body: CodingRequest,
    mode: str = Query(
        "full",
        description=(
            "Pipeline variant. Default ``full`` (5 stages). Other variants "
            "follow MedCodER ablation: ``prompt`` | ``retrieve`` | "
            "``prompt+retrieve``."
        ),
    ),
    current_user: User = Depends(get_current_user),
):
    """Phase 1.1 iCoDer 5-stage MedCodER pipeline (Chinese-only).

    Returns a list of disease / procedure codes with char-span evidence and
    reranked alternatives. Authentication is via session JWT (consistent
    with M3-0 ``/api/icoder/coding-review/run``); OAuth capability scope
    wiring lands in Phase 1.2.

    NOTE: This endpoint accepts only the iCoDer Chinese-system namespace
    (``icd10cn-*`` / ``icd9cm3-*``). For the canonical Corti §13.6
    multi-system predictor (15 systems), use
    ``POST /api/v2/tools/coding/`` instead.
    """
    # ── 1. Hospital-pilot / M3-0 gate (don't fake-model in production) ──
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": "llm_credential_missing",
                    "hint": (
                        "Set ICODER_CREDENTIAL_LLM (DeepSeek API key) before calling /api/v2/tools/coding/icoder. "
                        "Set ICODER_ALLOW_DEGRADED_NO_KEY=1 ONLY for local dev (returns a single mocked code)."
                    ),
                },
            )

    # ── 2. Validate system + context; fail fast on bad request ─────────
    try:
        allowed_systems, chosen_system = _validate_request(body)
    except HTTPException:
        raise
    if mode not in _ALLOWED_MODE_VALUES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_mode",
                "received": mode,
                "allowed": sorted(_ALLOWED_MODE_VALUES),
            },
        )
    adapter_mode = _MODE_TO_ADAPTER[mode]

    blocks = [c for c in body.context if c.text and c.text.strip()]
    messages = _build_messages(blocks, allowed_systems, chosen_system)

    # ── 3. PII redaction (best-effort; never blocks) ───────────────────
    try:
        from app.main import app as _app
        _data_policy = getattr(_app.state, "data_policy", None) if _app else None
    except Exception:
        _data_policy = None
    if _data_policy is not None and getattr(_data_policy, "pii_redaction_required", False):
        try:
            from icoder_runtime.core.pii_redaction import PIIRedactor
            redactor = PIIRedactor(enabled=True)
            messages, _ = redactor.redact_messages(messages)
        except Exception as _pii_err:
            logger.warning(f"PII redaction skipped (non-fatal): {_pii_err!r}")

    # ── 4. Run the 5-stage MedCodER pipeline ───────────────────────────
    adapter = HybridCodingAdapter(mode=adapter_mode)
    try:
        result = await adapter.infer_async(messages)
    except Exception as exc:
        logger.error(f"/api/v2/tools/coding/icoder adapter.infer_async failed: {exc!r}")
        raise HTTPException(status_code=502, detail={"error": "coding_pipeline_failed", "reason": str(exc)[:200]})

    # ── 5. Corti-shape projection ──────────────────────────────────────
    extracted = list(getattr(result, "extracted_diagnoses", []) or [])
    if not extracted:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "empty_extracted_diagnoses",
                "reason": (
                    "MedCodER pipeline returned no extracted_diagnoses; cannot project to Corti shape. "
                    "Verify ICODER_CREDENTIAL_LLM is set and the encounter text is non-trivial."
                ),
            },
        )

    # Sort by final_confidence desc so the principal diagnosis surfaces first.
    extracted.sort(key=lambda d: float(getattr(d, "final_confidence", 0.0) or 0.0), reverse=True)

    codes: list[CodingCode] = []
    for diag in extracted:
        top_k = list(getattr(diag, "final_top_k", []) or [])
        if not top_k:
            continue
        primary = top_k[0]
        primary_code = (
            getattr(primary, "code", "")
            if not isinstance(primary, (list, tuple))
            else (primary[0] if len(primary) >= 1 else "")
        )
        if isinstance(primary, dict):
            primary_code = primary.get("code", "")
        if not primary_code:
            continue
        primary_display = (
            getattr(primary, "name", "")
            if hasattr(primary, "name")
            else (primary.get("name", "") if isinstance(primary, dict) else "")
        )
        evidences: list[CodingEvidence] = []
        for span in getattr(diag, "supporting_evidence", []) or []:
            ev = _build_evidence(span, blocks, chosen_system)
            if ev is not None:
                evidences.append(ev)
        codes.append(
            CodingCode(
                system=chosen_system,
                code=primary_code,
                display=primary_display or _display_for(primary_code),
                evidences=evidences,
                alternatives=_build_alternatives(top_k[1:]),
            )
        )

    return CodingResponse(codes=codes)


# ─── Cycle 18 endpoint — Corti §13.6 codes_predict (canonical) ───────
# Aligned with ``docs/corti-reverse-engineered/codes-predict-codes.md``.
# Accepts all 15 Corti CommonCodingSystemEnum values; no LLM dependency
# (stateless stub; real data wiring is out of scope for cycle 18).


def _resolve_evidence_text(blocks: list[CommonAIContext]) -> tuple[int, str, int, int] | None:
    """Return (contextIndex, text, start, end) for the first non-empty text
    context block, or None if all blocks are documentId / empty.

    Used as the single source of stub evidence text in the canonical
    Corti predictor (no real LLM; deterministic stub).
    """
    for idx, ctx in enumerate(blocks):
        if ctx.type == "text" and ctx.text and ctx.text.strip():
            text = ctx.text
            return (idx, text, 0, min(len(text), 256))
    return None


def _stub_corti_coding(
    body: CodesGeneralPredictRequest,
) -> CodesGeneralResponse:
    """Deterministic Corti-spec code prediction stub.

    The iCoDer runtime does not yet have a real LLM-backed predictor for the
    14 non-Chinese Corti systems (icd10cm, icd10pcs, cpt, icd10int, icd10uk,
    cim10fr, icd10gm, opcs4, ops, ccam). Per cycle 18 plan, the endpoint
    projects a deterministic, spec-shaped response so the wire contract is
    end-to-end green even without a real model behind it. The projection
    follows these invariants (enforced by the 回环 tests):

      1. ``codes[]`` and ``candidates[]`` are **always present** (per spec
         — both are required response fields).
      2. ``codes[].system`` echoes the request's first valid system.
      3. ``candidates[].system`` echoes the same system (or a related
         sibling system when filter is present).
      4. Each code's ``evidences[]`` is the (single) char-span of the
         first non-empty text context block, with ``contextIndex`` mapping
         1:1 to the input.
      5. ``usageInfo.creditsConsumed`` is deterministic from the request
         shape (1 credit per context block + 1 credit per system).
    """
    # Default system (per spec: empty system[] is invalid, but our stub
    # is more forgiving than the spec to keep green-path tests simple).
    if body.system:
        chosen_system = body.system[0]
    else:
        chosen_system = default_corti_coding_system()

    blocks = list(body.context or [])
    evidence = _resolve_evidence_text(blocks)

    # Filter handling: if include is non-empty, derive a "candidate" code
    # from the first included token (just to honor the surface).
    candidate_code_token = ""
    if body.filter and body.filter.include:
        candidate_code_token = body.filter.include[0]

    # Build the primary code: deterministic, derived from system + first
    # context block (so the same input always returns the same response).
    primary_code = "EXAMPLE-" + chosen_system.split("-")[0].upper() + "-001"
    if evidence is not None:
        primary_display = f"Stub {chosen_system} code for context block {evidence[0]}"
    else:
        primary_display = f"Stub {chosen_system} code (no text context)"

    # Candidate code: distinct from primary, derived from filter or system.
    if candidate_code_token:
        cand_code = candidate_code_token
        cand_display = f"Filter-anchored candidate ({chosen_system})"
    else:
        cand_code = "EXAMPLE-" + chosen_system.split("-")[0].upper() + "-002"
        cand_display = f"Lower-confidence candidate ({chosen_system})"

    # Build evidence list for primary code.
    evidences: list[CodingEvidence] = []
    if evidence is not None:
        ctx_idx, text, start, end = evidence
        evidences.append(CodingEvidence(
            contextIndex=ctx_idx,
            text=text[start:end],
            start=start,
            end=end,
        ))

    # Build primary code.
    primary = CodesGeneralReadResponse(
        system=chosen_system,
        code=primary_code,
        display=primary_display,
        evidences=evidences,
        alternatives=[],
    )

    # Build candidate(s) (lower-confidence codes the model considered).
    candidates: list[CodesGeneralReadResponse] = []
    if evidence is not None:
        ctx_idx, text, start, end = evidence
        # Mirror the primary evidence on the candidate so 回环 tests can
        # verify the char-span invariant on both lists.
        cand_evidence = CodingEvidence(
            contextIndex=ctx_idx,
            text=text[start:end],
            start=start,
            end=end,
        )
    else:
        cand_evidence = None
    candidates.append(CodesGeneralReadResponse(
        system=chosen_system,
        code=cand_code,
        display=cand_display,
        evidences=[cand_evidence] if cand_evidence is not None else [],
        alternatives=[],
    ))

    # Credits consumed: 1 per context block + 1 per system, deterministic.
    credits = float(len(blocks) + max(1, len(body.system)))

    return CodesGeneralResponse(
        codes=[primary],
        candidates=candidates,
        usageInfo=CommonUsageInfo(creditsConsumed=credits),
    )


@router.post("/coding", response_model=CodesGeneralResponse)
@router.post("/coding/", response_model=CodesGeneralResponse)
async def post_v2_tools_coding(
    body: CodesGeneralPredictRequest,
    current_user: User = Depends(get_current_user),
):
    """Cycle 18 — Corti §13.6 ``codes_predict`` canonical endpoint.

    Stateless single-shot code prediction. Accepts any of the 15
    ``CommonCodingSystemEnum`` values and returns the spec-defined
    ``{codes, candidates, usageInfo}`` envelope. No LLM dependency in the
    stub — the iCoDer runtime does not yet have a real predictor for the
    14 non-Chinese Corti systems; the deterministic stub keeps the wire
    contract end-to-end green until cycle 18+ wiring lands.
    """
    # ── 1. Hospital-pilot gate (consistent with other v2 endpoints) ───
    # Cycle 18 stub does NOT need an LLM credential; the gate is removed
    # for this endpoint to keep the wire contract green in dev. A real
    # predictor will re-introduce it as 503 when wired.
    _ = os.environ.get("ICODER_CREDENTIAL_LLM", "")

    # ── 2. Validate request shape (per-spec invariants) ──────────────
    if not body.context:
        # Per spec, ``context: []`` is implicitly invalid; the iCoDer
        # stub surfaces this as 400 ``empty_context`` to match the
        # Phase 1.1 endpoint's contract.
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_context",
                "hint": "context[] must contain at least one item (text or documentId).",
            },
        )
    if not body.system:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_system",
                "hint": "system[] must contain at least one CommonCodingSystemEnum value.",
            },
        )
    # Spec invariant: system must be from the 15-value enum.
    unknown = [s for s in body.system if s not in CORTI_COMMON_CODING_SYSTEMS]
    if unknown:
        # Spec lists 400 as one of the error codes; treat unknown systems
        # as 400 to surface the contract violation.
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_system",
                "received": unknown,
                "allowed": sorted(CORTI_COMMON_CODING_SYSTEMS),
            },
        )
    # Spec invariant: at least one text context block (documentId alone
    # is not yet supported by the iCoDer stub).
    has_text = any(
        (c.type == "text" and (c.text or "").strip())
        for c in body.context
    )
    if not has_text:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_text_context",
                "hint": "iCoDer stub requires at least one text context block (documentId-only is a future cycle).",
            },
        )

    # ── 3. Build deterministic stub response ─────────────────────────
    return _stub_corti_coding(body)
