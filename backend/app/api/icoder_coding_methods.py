"""iCoDer M3+ — Coding Method Registry + Compare API.

Phase B endpoint surface (new, parallel to existing
``/api/icoder/coding-review/*``):

  - ``GET  /api/icoder/coding-methods/list``
        → list all registered CodingMethod instances + availability
  - ``GET  /api/icoder/coding-methods/{method_id}``
        → describe a single method (caps, stages, family)
  - ``POST /api/icoder/coding-review/compare``
        → run N methods on the same EMR text, return side-by-side results

The compare endpoint is the new canonical entry point for
side-by-side method evaluation. The legacy
``/api/icoder/coding-review/run`` endpoint (which runs the 14-stage
homepage-coding-review pipeline) is preserved unchanged for back-compat;
``run-v2`` is the new method-aware entry. ``run-v2`` accepts
``method_id`` (canonical) or ``mode`` (legacy alias) — both resolve to
the same :class:`MethodSwitcher.run` call.

**Positioning**: these endpoints are part of the new Method Runtime
(M3+), not the M3-0 pipeline-validation surface. They produce real
results when capabilities are present; ``status="unavailable"`` with a
descriptive ``reason`` when capabilities are missing — no fake
degraded echo.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from icoder_runtime.methods import get_registry
from icoder_runtime.methods.base import MethodResult
from icoder_runtime.methods.switcher import (
    GLOBAL_SWITCHER,
    mode_to_method_id,
    probe_capabilities,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/coding-methods", tags=["icoder-coding-methods"])

# Compare endpoint lives under /api/icoder/coding-review/* so the URL
# group matches existing review endpoints. Imported and wired from
# app/api/icoder_coding_review.py (or mounted separately by the main
# app). Kept here to keep the related schema classes co-located.
compare_router = APIRouter(prefix="/api/icoder/coding-review", tags=["icoder-coding-methods"])


# ── Pydantic Schemas ──


class CodingMethodInfo(BaseModel):
    """Registry-safe metadata for one CodingMethod."""

    method_id: str
    method_name: str
    method_name_en: str = ""
    method_family: str  # "medcoder" | "legacy" | "noop"
    stage_count: int
    required_capabilities: list[str]
    description: str
    available: bool  # True iff all required_capabilities are present


class ListMethodsResponse(BaseModel):
    methods: list[CodingMethodInfo]
    capabilities: dict[str, bool]
    total: int


class CompareRequest(BaseModel):
    """POST /api/icoder/coding-review/compare 请求体."""

    emr_text: str = Field(default="", description="病历原文")
    method_ids: list[str] = Field(
        default_factory=lambda: ["medcoder.full", "medcoder.prompt+retrieve", "legacy.deepseek"],
        description="要对比的方法 ID 列表 (按 execution order)",
    )
    case_id: str = Field(default="", description="可选: 病例 ID")


class CompareResultEntry(BaseModel):
    method_id: str
    method_name: str
    method_family: str
    status: str
    reason: str = ""
    primary_code: str = ""
    primary_name: str = ""
    primary_confidence: float = 0.0
    secondary_codes: list[dict] = Field(default_factory=list)
    procedure_codes: list[dict] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    manual_review_required: bool = False
    confidence: float = 0.0
    stage_trace: list[dict] = Field(default_factory=list)
    processing_time_ms: int = 0
    # Phase D1: derived quality signal (0.0-1.0) for weighted consensus
    evidence_strength: float = 1.0


class CompareResponse(BaseModel):
    case_id: str = ""
    emr_chars: int = 0
    method_count: int
    capabilities: dict[str, bool]
    results: list[CompareResultEntry]
    consensus_primary_code: str = ""
    # Phase D1: weighted consensus score (sum of family_weight ×
    # confidence × evidence_strength per method that agreed on the
    # consensus primary). Replaces the Phase B simple count of agreeing
    # methods — weighted consensus lets MedCodER-family methods with
    # strong evidence outrank legacy-family votes even if fewer in number.
    consensus_score: float = 0.0


class RunV2Request(BaseModel):
    """POST /api/icoder/coding-review/run-v2 请求体."""

    emr_text: str = Field(default="", description="病历原文")
    method_id: str = Field(
        default="",
        description="canonical method_id (e.g. 'medcoder.full'); preferred over mode",
    )
    mode: str = Field(
        default="",
        description="legacy mode alias ('deepseek'/'prompt_llm'/'hybrid'/'no_repair'/'medcoder'/...) — translated to method_id",
    )
    case_id: str = Field(default="", description="可选: 病例 ID")


class RunV2Response(BaseModel):
    run_id: str
    method_id: str
    method_name: str
    method_family: str
    agent_ref: str
    status: str
    reason: str
    primary_code: str = ""
    primary_name: str = ""
    primary_confidence: float = 0.0
    secondary_codes: list[dict] = Field(default_factory=list)
    procedure_codes: list[dict] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    manual_review_required: bool = False
    confidence: float = 0.0
    stage_trace: list[dict] = Field(default_factory=list)
    processing_time_ms: int = 0


# ── /api/icoder/coding-methods/list ──


@router.get("/list", response_model=ListMethodsResponse)
async def list_coding_methods(
    family: Optional[str] = Query(default=None, description="过滤: 'medcoder' / 'legacy' / 'noop'"),
) -> ListMethodsResponse:
    """List all registered CodingMethod instances.

    ``family`` filters by MethodFamily value. ``available`` reflects
    current capability state — methods with missing capabilities are
    returned but flagged.
    """
    reg = get_registry()
    caps = probe_capabilities()
    methods: list[CodingMethodInfo] = []
    for m in reg.filter(family=family):
        available = all(
            caps.get(c.value, False) for c in m.required_capabilities
        )
        methods.append(CodingMethodInfo(
            method_id=m.method_id,
            method_name=m.method_name,
            method_name_en=getattr(m, "method_name_en", "") or "",
            method_family=m.method_family,
            stage_count=m.stage_count,
            required_capabilities=[c.value for c in m.required_capabilities],
            description=m.description,
            available=available,
        ))
    return ListMethodsResponse(
        methods=methods,
        capabilities=caps,
        total=len(methods),
    )


# ── /api/icoder/coding-methods/{method_id} ──


@router.get("/{method_id}", response_model=CodingMethodInfo)
async def get_coding_method(method_id: str) -> CodingMethodInfo:
    """Describe a single method by id. 404 if not registered."""
    reg = get_registry()
    m = reg.get(method_id)
    if m is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "method_not_found",
                "method_id": method_id,
                "available": reg.method_ids(),
            },
        )
    caps = probe_capabilities()
    available = all(caps.get(c.value, False) for c in m.required_capabilities)
    return CodingMethodInfo(
        method_id=m.method_id,
        method_name=m.method_name,
        method_name_en=getattr(m, "method_name_en", "") or "",
        method_family=m.method_family,
        stage_count=m.stage_count,
        required_capabilities=[c.value for c in m.required_capabilities],
        description=m.description,
        available=available,
    )


# ── /api/icoder/coding-review/compare ──


def _result_to_entry(result: MethodResult) -> CompareResultEntry:
    return CompareResultEntry(
        method_id=result.method_id,
        method_name=result.method_name,
        method_family=result.method_family,
        status=result.status,
        reason=result.reason,
        primary_code=result.primary_code,
        primary_name=result.primary_name,
        primary_confidence=result.primary_confidence,
        secondary_codes=list(result.secondary_codes),
        procedure_codes=list(result.procedure_codes),
        issues=list(result.issues),
        manual_review_required=result.manual_review_required,
        confidence=result.confidence,
        stage_trace=[e.to_dict() for e in result.stage_trace],
        processing_time_ms=result.processing_time_ms,
        evidence_strength=result.evidence_strength,
    )


# ── Phase D1 weighted consensus ──

# Method-family weight in consensus aggregation. Reflects the trust
# hierarchy we want the operator to see: a MedCodER variant with the
# 5-stage pipeline + re-rank + calibration is the strongest signal;
# legacy hybrid adapters are weaker; noop contributes nothing.
_FAMILY_WEIGHT: dict[str, float] = {
    "medcoder": 1.0,
    "legacy": 0.8,
    "noop": 0.0,
}


def _evidence_strength(result: MethodResult) -> float:
    """Derive a 0.0-1.0 evidence-quality signal from a single result.

    Heuristic — true Phase D future work would replace this with a
    learned quality model:

    - ``status != "ok"``            → 0.0  (unusable)
    - empty ``stage_trace``         → 0.5  (unknown; trust the basic confidence)
    - all stages ``ok`` + secondary → 1.0  (fully corroborated)
    - all stages ``ok`` (no secondary) → 0.8  (clean run but thin evidence)
    - any stage not ``ok``         → 0.5  (partial degradation)
    """
    if result.status != "ok":
        return 0.0
    trace = result.stage_trace or []
    if not trace:
        return 0.5
    all_ok = all(s.status == "ok" for s in trace)
    has_secondary = bool(result.secondary_codes)
    if all_ok and has_secondary:
        return 1.0
    if all_ok:
        return 0.8
    return 0.5


def _weighted_consensus(entries: list[CompareResultEntry]) -> tuple[str, float]:
    """Compute (consensus_code, consensus_score) from compare entries.

    Each method contributes ``family_weight × primary_confidence ×
    evidence_strength`` to the score for its ``primary_code``. The
    winning code is the one with the highest aggregated score; ties
    break by sum of ``primary_confidence`` (so a tied MedCodER vs
    legacy result still prefers MedCodER via the family weight).

    Returns ``("", 0.0)`` when no method produced an ``ok`` result with
    a non-empty ``primary_code``.
    """
    scores: dict[str, float] = {}
    confidences: dict[str, float] = {}
    for e in entries:
        if e.status != "ok" or not e.primary_code:
            continue
        family_w = _FAMILY_WEIGHT.get(e.method_family, 0.5)
        score = family_w * e.primary_confidence * e.evidence_strength
        scores[e.primary_code] = scores.get(e.primary_code, 0.0) + score
        confidences[e.primary_code] = (
            confidences.get(e.primary_code, 0.0) + e.primary_confidence
        )

    if not scores:
        return ("", 0.0)

    def _tiebreak_key(kv: tuple[str, float]) -> tuple[float, float]:
        return (kv[1], confidences.get(kv[0], 0.0))

    (consensus_code, consensus_score) = max(
        scores.items(),
        key=_tiebreak_key,
    )
    return (consensus_code, round(consensus_score, 6))


@compare_router.post("/compare", response_model=CompareResponse)
async def compare_methods(req: CompareRequest) -> CompareResponse:
    """Run multiple methods on the same EMR text and return side-by-side results.

    Methods run sequentially. The ``consensus_primary_code`` is the
    primary code produced by the most methods (ties broken by method
    order). Useful for ablation studies + shadow-comparison tests.
    """
    if not req.method_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "method_ids_empty", "message": "method_ids must be non-empty"},
        )
    if len(req.method_ids) > 8:
        # Cap to avoid pathological requests; matches the ablation
        # study budget (4 MedCodER + 4 legacy).
        raise HTTPException(
            status_code=400,
            detail={"error": "too_many_methods", "limit": 8, "got": len(req.method_ids)},
        )

    results = await GLOBAL_SWITCHER.compare(
        method_ids=req.method_ids,
        emr_text=req.emr_text,
        ctx={"case_id": req.case_id} if req.case_id else None,
    )
    entries = [_result_to_entry(r) for r in results]

    # Phase D1: weighted consensus (replaces simple max-count).
    consensus_code, consensus_score = _weighted_consensus(entries)

    return CompareResponse(
        case_id=req.case_id,
        emr_chars=len(req.emr_text or ""),
        method_count=len(entries),
        capabilities=probe_capabilities(),
        results=entries,
        consensus_primary_code=consensus_code,
        consensus_score=consensus_score,
    )


# ── /api/icoder/coding-review/run-v2 ──


@compare_router.post("/run-v2", response_model=RunV2Response)
async def run_v2(req: RunV2Request) -> RunV2Response:
    """New method-aware run endpoint (M3+).

    Accepts either ``method_id`` (canonical, preferred) or ``mode``
    (legacy alias). Both are translated to the same MethodSwitcher.run
    call — see ``mode_to_method_id`` for the mapping.

    Returns a flat MethodResult-shaped response (no nested schema).
    The 14-stage ``pipeline_stages_observed`` field is dropped in
    favour of ``stage_trace`` (per-stage timing + status).
    """
    import uuid as _uuid

    # Resolve method_id from either method_id or mode.
    if req.method_id:
        method_id = req.method_id
    elif req.mode:
        method_id = mode_to_method_id(req.mode) or ""
        if not method_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unknown_mode",
                    "mode": req.mode,
                    "valid_modes": [
                        "deepseek", "prompt_llm", "hybrid", "no_repair",
                        "medcoder", "medcoder_full", "medcoder_prompt",
                        "medcoder_retrieve", "medcoder_prompt+retrieve",
                    ],
                },
            )
    else:
        method_id = "medcoder.full"  # canonical default

    ctx: dict[str, Any] = {"case_id": req.case_id} if req.case_id else None
    result = await GLOBAL_SWITCHER.run(method_id, req.emr_text, ctx)

    agent_ref = f"method:{result.method_id}"
    return RunV2Response(
        run_id=_uuid.uuid4().hex,
        method_id=result.method_id,
        method_name=result.method_name,
        method_family=result.method_family,
        agent_ref=agent_ref,
        status=result.status,
        reason=result.reason,
        primary_code=result.primary_code,
        primary_name=result.primary_name,
        primary_confidence=result.primary_confidence,
        secondary_codes=list(result.secondary_codes),
        procedure_codes=list(result.procedure_codes),
        issues=list(result.issues),
        manual_review_required=result.manual_review_required,
        confidence=result.confidence,
        stage_trace=[e.to_dict() for e in result.stage_trace],
        processing_time_ms=result.processing_time_ms,
    )


__all__ = ["router", "compare_router"]
