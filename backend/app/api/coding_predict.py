"""POST /api/v1/coding/predict — unified medical coding prediction entry.

Per G001 refactor (2026-07-09), this is the default product entry point
for medical coding. Replaces the A2A flow as the primary frontend target
for the MedicalCodingPage Predict button.

Request:
  POST /api/v1/coding/predict
  {
    "text": "患者男性,78岁...",
    "mode": "corti_like_fast",         # or "medcoder_deep"
    "coding_system": "icd10cn",
    "include_evidence": true,
    "include_trace": true
  }

Response:
  {
    "codes": [{ "code": "...", "system": "...", "display": "...",
                "type": "...", "confidence": 0.86,
                "evidence": "...", "rationale": "...",
                "warnings": [...], "alternatives": [...] }],
    "summary": "...",
    "runtime_mode": "corti_like_fast",
    "latency_ms": 8230,
    "llm_provider": "deepseek",
    "trace_id": "...",
    "run_id": "...",
    "cost": { "amount": 0.0, "currency": "internal_credit" },
    "raw_schema": {...},                  # original MedicalCodingOutputSchema dict
    "trace_events": [...],                # 7-step (Fast) or 5-stage+2 (Deep) trace
    "error": false,
    "error_reason": ""
  }

Auth: session JWT (same as /api/v2/tools/coding/icoder).
Timeout: 30s for Fast, 90s for Deep — enforced inside the runtime, never
silently timed out by axios.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.coding_runtime import (
    CodingRequest,
    CodingResult,
    RuntimeMode,
    get_dispatcher,
)
from app.middleware.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coding", tags=["coding-predict"])


# ─── Pydantic request/response models ─────────────────────────────────


class CodingPredictRequest(BaseModel):
    """POST /api/v1/coding/predict request body."""

    text: str = Field(..., min_length=1, max_length=16000,
                      description="Clinical encounter text (Chinese or English).")
    mode: str = Field(
        "corti_like_fast",
        description=(
            "Coding runtime mode. ``corti_like_fast`` (default) = single-stage "
            "LLM call (~7-12s). ``medcoder_deep`` = 5-stage MedCodER pipeline "
            "(30-60s+, advanced/research use)."
        ),
    )
    coding_system: str = Field(
        "icd10cn",
        description="Coding system namespace. Default icd10cn (China ICD-10).",
    )
    include_evidence: bool = Field(
        True,
        description="Whether to include evidence spans in the response.",
    )
    include_trace: bool = Field(
        True,
        description="Whether to include trace events in the response.",
    )


class CodingPredictCode(BaseModel):
    code: str
    system: str = "ICD-10-CN"
    display: str = ""
    type: str = "primary_diagnosis"
    confidence: float = 0.0
    evidence: str = ""
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class CodingPredictResponse(BaseModel):
    codes: list[CodingPredictCode]
    summary: str = ""
    runtime_mode: str = "corti_like_fast"
    latency_ms: int = 0
    llm_provider: str = "deepseek"
    trace_id: str = ""
    run_id: str = ""
    cost: dict[str, Any] = Field(default_factory=dict)
    raw_schema: dict[str, Any] = Field(default_factory=dict)
    trace_events: list[dict[str, Any]] = Field(default_factory=list)
    error: bool = False
    error_reason: str = ""


# ─── Endpoint ─────────────────────────────────────────────────────────


@router.post("/predict", response_model=CodingPredictResponse)
async def post_coding_predict(
    body: CodingPredictRequest,
    current_user: User = Depends(get_current_user),
) -> CodingPredictResponse:
    """Unified medical coding prediction entry.

    Default mode is ``corti_like_fast`` (single LLM call, target <15s).
    Set ``mode=medcoder_deep`` for the 5-stage MedCodER pipeline (advanced).

    Never silently times out. On error, returns a :class:`CodingPredictResponse`
    with ``error=True`` + ``summary`` containing a user-visible message and
    a hint to retry or switch modes.
    """
    # ── 1. LLM credential gate (don't fake-model in production) ────────
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": "llm_credential_missing",
                    "hint": (
                        "Set ICODER_CREDENTIAL_LLM (DeepSeek API key) before "
                        "calling /api/v1/coding/predict. Set "
                        "ICODER_ALLOW_DEGRADED_NO_KEY=1 ONLY for local dev."
                    ),
                },
            )

    # ── 2. Coerce mode + build request ─────────────────────────────────
    mode = RuntimeMode.coerce(body.mode)
    request = CodingRequest(
        text=body.text,
        mode=mode,
        coding_system=body.coding_system,
        include_evidence=body.include_evidence,
        include_trace=body.include_trace,
        user_id=str(getattr(current_user, "id", "") or ""),
        tenant_id=str(getattr(current_user, "tenant_id", "") or ""),
    )

    # ── 3. Dispatch to runtime ──────────────────────────────────────────
    dispatcher = get_dispatcher()
    result: CodingResult = await dispatcher.dispatch(request)

    # ── 4. Project to response model ────────────────────────────────────
    codes = [
        CodingPredictCode(
            code=c.code,
            system=c.system,
            display=c.display,
            type=c.type,
            confidence=c.confidence,
            evidence=c.evidence if body.include_evidence else "",
            rationale=c.rationale,
            warnings=list(c.warnings),
            alternatives=list(c.alternatives),
        )
        for c in result.codes
    ]
    trace_events = list(result.trace_events) if body.include_trace else []

    # If runtime reported an error, return HTTP 200 with error=True so the
    # frontend can render a friendly retry UI (rather than catching a 5xx).
    # Hard errors (credential missing) already raised above.
    return CodingPredictResponse(
        codes=codes,
        summary=result.summary,
        runtime_mode=result.runtime_mode,
        latency_ms=result.latency_ms,
        llm_provider=result.llm_provider,
        trace_id=result.trace_id,
        run_id=result.run_id,
        cost=dict(result.cost),
        raw_schema=dict(result.raw_schema) if result.raw_schema else {},
        trace_events=trace_events,
        error=result.error,
        error_reason=result.error_reason,
    )
