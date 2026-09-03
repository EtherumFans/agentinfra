"""POST /api/v1/coding/predict — unified medical coding prediction entry.

Per G001 refactor (2026-07-09), this is the default product entry point
for medical coding. Replaces the A2A flow as the primary frontend target
for the MedicalCodingPage Predict button.

Request:
  POST /api/v1/coding/predict
  {
    "text": "患者男性,78岁...",
    "mode": "corti_like_fast",         # or "medcoder_deep"
    "coding_systems": ["icd10cn", "icd9cm3"],
    "include_evidence": true,
    "include_trace": true,
    "filter": {"include": ["E11"], "exclude": [], "expand": true}
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
    "cost": { "amount": 0.0, "currency": "CNY", "source": "not_reported" },
    "raw_schema": {...},                  # original MedicalCodingOutputSchema dict
    "trace_events": [...],                # 7-step (Fast) or 5-stage+2 (Deep) trace
    "error": false,
    "error_reason": "",
    "filter_applied": {"include": ["E11"], "exclude": [], "expand": true},
    "coding_systems_applied": ["icd10cn", "icd9cm3"]
  }

Auth: session JWT (same as /api/v2/tools/coding/icoder).
Timeout: 30s for Fast, 90s for Deep — enforced inside the runtime, never
silently timed out by axios.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.coding_runtime import (
    CodingRequest,
    CodingResult,
    RuntimeMode,
    get_dispatcher,
)
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.v2_tools_coding import CodesFilter
from app.services.coding_filter import code_allowed_by_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coding", tags=["coding-predict"])

ChinaCodingSystem = Literal["icd10cn", "icd9cm3"]


# ─── Pydantic request/response models ─────────────────────────────────


class CodingPredictRequest(BaseModel):
    """POST /api/v1/coding/predict request body."""

    text: str = Field(..., min_length=1, max_length=16000,
                      description="Clinical encounter text (Chinese or English).")
    mode: Literal["corti_like_fast", "medcoder_deep"] = Field(
        "corti_like_fast",
        description=(
            "Coding runtime mode. ``corti_like_fast`` (default) = single-stage "
            "LLM call (~7-12s). ``medcoder_deep`` = 5-stage MedCodER pipeline "
            "(30-60s+, advanced/research use)."
        ),
    )
    coding_system: ChinaCodingSystem | None = Field(
        default=None,
        description="Legacy single-system field. Prefer coding_systems.",
    )
    coding_systems: list[ChinaCodingSystem] | None = Field(
        default=None,
        min_length=1,
        max_length=2,
        description=(
            "One or both Chinese coding systems. icd10cn returns diagnoses; "
            "icd9cm3 returns procedures. Defaults to [icd10cn]."
        ),
    )
    include_evidence: bool = Field(
        True,
        description="Whether to include evidence spans in the response.",
    )
    include_trace: bool = Field(
        True,
        description="Whether to include trace events in the response.",
    )
    filter: CodesFilter | None = Field(
        default=None,
        description=(
            "Optional Corti-style code filter. expand=true applies category "
            "prefix matching; expand=false requires exact code matches."
        ),
    )

    @model_validator(mode="after")
    def _validate_system_selection(self) -> "CodingPredictRequest":
        if self.coding_system is not None and self.coding_systems is not None:
            raise ValueError("Use coding_system or coding_systems, not both")
        if self.coding_systems is not None:
            normalized = list(dict.fromkeys(self.coding_systems))
            if len(normalized) != len(self.coding_systems):
                raise ValueError("coding_systems must not contain duplicates")
            self.coding_systems = normalized
        return self

    def requested_coding_systems(self) -> list[ChinaCodingSystem]:
        if self.coding_systems is not None:
            return list(self.coding_systems)
        return [self.coding_system or "icd10cn"]


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
    filter_applied: CodesFilter | None = None
    coding_systems_applied: list[ChinaCodingSystem] = Field(default_factory=list)


def _allowed(code: str, code_filter: CodesFilter | None) -> bool:
    if code_filter is None:
        return True
    return code_allowed_by_filter(
        code,
        include=code_filter.include,
        exclude=code_filter.exclude,
        expand=code_filter.expand is not False,
    )


def _filter_alternatives(
    alternatives: list[dict[str, Any]],
    code_filter: CodesFilter | None,
) -> list[dict[str, Any]]:
    if code_filter is None:
        return alternatives
    return [
        item
        for item in alternatives
        if isinstance(item, dict) and _allowed(str(item.get("code") or ""), code_filter)
    ]


def _code_system(system: str, code_type: str = "") -> ChinaCodingSystem:
    """Normalize runtime display names to the public China system enum."""

    normalized = "".join(ch for ch in system.lower() if ch.isalnum())
    if code_type == "procedure" or "icd9cm3" in normalized:
        return "icd9cm3"
    return "icd10cn"


def _system_allowed(
    system: str,
    code_type: str,
    requested_systems: set[ChinaCodingSystem],
) -> bool:
    return _code_system(system, code_type) in requested_systems


def _scrub_raw_schema(
    value: Any,
    code_filter: CodesFilter | None,
    *,
    include_evidence: bool,
    include_trace: bool,
    requested_systems: set[ChinaCodingSystem],
) -> Any:
    """Apply response controls to the compatibility response surface."""

    if isinstance(value, list):
        scrubbed = [
            _scrub_raw_schema(
                item,
                code_filter,
                include_evidence=include_evidence,
                include_trace=include_trace,
                requested_systems=requested_systems,
            )
            for item in value
        ]
        return [item for item in scrubbed if item is not None]
    if isinstance(value, dict):
        code = value.get("code")
        if (
            code_filter is not None
            and isinstance(code, str)
            and code.strip()
            and not _allowed(code, code_filter)
        ):
            return None
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = key.lower().replace("-", "_")
            if normalized_key in {
                "primary_diagnosis",
                "secondary_diagnoses",
                "extracted_diagnoses",
            } and "icd10cn" not in requested_systems:
                continue
            if normalized_key == "procedures" and "icd9cm3" not in requested_systems:
                continue
            if not include_evidence and "evidence" in normalized_key:
                continue
            if not include_trace and "trace" in normalized_key:
                continue
            scrubbed = _scrub_raw_schema(
                item,
                code_filter,
                include_evidence=include_evidence,
                include_trace=include_trace,
                requested_systems=requested_systems,
            )
            if scrubbed is not None:
                result[key] = scrubbed
        return result
    return value


class CodingPricingEstimateResponse(BaseModel):
    """Auditable pre-run cost range based on server-side pricing settings.

    This is deliberately a range rather than a fake exact quote. Final cost is
    computed from the provider's returned token usage after a successful run.
    """

    input_chars: int
    runtime_mode: str
    currency: str = "CNY"
    estimated_input_tokens_min: int
    estimated_input_tokens_max: int
    estimated_output_tokens_min: int
    estimated_output_tokens_max: int
    estimated_model_calls_min: int
    estimated_model_calls_max: int
    estimated_cost_min: float
    estimated_cost_max: float
    input_price_per_1m: float
    output_price_per_1m: float
    price_source: str = "server_configuration"
    billing_authoritative: bool = False
    disclaimer: str = (
        "Pre-run estimate only. Final billable cost must use provider-reported "
        "token usage from the completed run."
    )


# ─── Endpoint ─────────────────────────────────────────────────────────


@router.get("/pricing", response_model=CodingPricingEstimateResponse)
async def get_coding_pricing_estimate(
    input_chars: int = Query(0, ge=0, le=16000),
    mode: Literal["corti_like_fast", "medcoder_deep"] = Query(
        "corti_like_fast"
    ),
    current_user: User = Depends(get_current_user),
) -> CodingPricingEstimateResponse:
    """Return a conservative, configuration-backed pre-run cost range.

    Tokenization and model output length cannot be known before execution, so
    this endpoint reports explicit lower/upper assumptions. It never reads or
    requires an LLM credential and must not be used as the billing ledger.
    """
    del current_user  # Authentication is the boundary; no user data is needed.

    input_price = max(float(settings.LLM_PRICE_INPUT_PER_1M), 0.0)
    output_price = max(float(settings.LLM_PRICE_OUTPUT_PER_1M), 0.0)

    if input_chars == 0:
        return CodingPricingEstimateResponse(
            input_chars=0,
            runtime_mode=mode,
            estimated_input_tokens_min=0,
            estimated_input_tokens_max=0,
            estimated_output_tokens_min=0,
            estimated_output_tokens_max=0,
            estimated_model_calls_min=0,
            estimated_model_calls_max=0,
            estimated_cost_min=0.0,
            estimated_cost_max=0.0,
            input_price_per_1m=input_price,
            output_price_per_1m=output_price,
        )

    # Latin-heavy notes often approach four characters/token, while Chinese
    # clinical text can approach one character/token. Prompt overhead is kept
    # explicit so short notes do not misleadingly estimate to zero.
    single_input_min = math.ceil(input_chars / 4) + 192
    single_input_max = input_chars + 512
    max_tokens = max(int(settings.LLM_MAX_TOKENS), 1)

    if mode == "medcoder_deep":
        calls_min, calls_max = 3, 7
        output_per_call_min = 256
        output_per_call_max = max_tokens
    else:
        calls_min = calls_max = 1
        output_per_call_min = 128
        output_per_call_max = min(max_tokens, 2048)

    input_tokens_min = single_input_min * calls_min
    input_tokens_max = single_input_max * calls_max
    output_tokens_min = output_per_call_min * calls_min
    output_tokens_max = output_per_call_max * calls_max
    cost_min = (
        input_tokens_min * input_price + output_tokens_min * output_price
    ) / 1_000_000
    cost_max = (
        input_tokens_max * input_price + output_tokens_max * output_price
    ) / 1_000_000

    return CodingPricingEstimateResponse(
        input_chars=input_chars,
        runtime_mode=mode,
        estimated_input_tokens_min=input_tokens_min,
        estimated_input_tokens_max=input_tokens_max,
        estimated_output_tokens_min=output_tokens_min,
        estimated_output_tokens_max=output_tokens_max,
        estimated_model_calls_min=calls_min,
        estimated_model_calls_max=calls_max,
        estimated_cost_min=round(cost_min, 6),
        estimated_cost_max=round(cost_max, 6),
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
    )


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
    coding_systems = body.requested_coding_systems()
    request = CodingRequest(
        text=body.text,
        mode=mode,
        coding_system=coding_systems[0],
        coding_systems=tuple(coding_systems),
        include_evidence=body.include_evidence,
        include_trace=body.include_trace,
        user_id=str(getattr(current_user, "id", "") or ""),
        tenant_id=str(getattr(current_user, "tenant_id", "") or ""),
    )

    # ── 3. Dispatch to runtime ──────────────────────────────────────────
    dispatcher = get_dispatcher()
    result: CodingResult = await dispatcher.dispatch(request)

    # ── 4. Project to response model ────────────────────────────────────
    requested_systems = set(coding_systems)
    codes = [
        CodingPredictCode(
            code=c.code,
            system=_code_system(c.system, c.type),
            display=c.display,
            type=c.type,
            confidence=c.confidence,
            evidence=c.evidence if body.include_evidence else "",
            rationale=c.rationale,
            warnings=list(c.warnings),
            alternatives=_filter_alternatives(list(c.alternatives), body.filter),
        )
        for c in result.codes
        if _system_allowed(c.system, c.type, requested_systems)
        and _allowed(c.code, body.filter)
    ]
    trace_events = list(result.trace_events) if body.include_trace else []
    if body.include_trace:
        trace_events.append({
            "step": "coding_system_projection",
            "status": "ok",
            "metadata": {
                "systems": coding_systems,
                "input_code_count": len(result.codes),
                "returned_code_count": len(codes),
            },
        })
    if body.include_trace and body.filter is not None:
        trace_events.append({
            "step": "code_filter",
            "status": "ok",
            "metadata": {
                "include_count": len(body.filter.include),
                "exclude_count": len(body.filter.exclude),
                "expand": body.filter.expand is not False,
                "input_code_count": len(result.codes),
                "returned_code_count": len(codes),
            },
        })

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
        raw_schema=(
            _scrub_raw_schema(
                dict(result.raw_schema),
                body.filter,
                include_evidence=body.include_evidence,
                include_trace=body.include_trace,
                requested_systems=requested_systems,
            )
            if result.raw_schema
            else {}
        ),
        trace_events=trace_events,
        error=result.error,
        error_reason=result.error_reason,
        filter_applied=body.filter,
        coding_systems_applied=coding_systems,
    )
