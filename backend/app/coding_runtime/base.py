"""CodingRuntime abstraction — Protocol + request/result dataclasses.

The CodingRuntime layer is intentionally thin: it wraps the existing
:class:`DeepSeekCodingAdapter` (Fast) and :class:`HybridCodingAdapter`
(Deep) under a uniform interface so the API layer can dispatch by
``mode`` without binding to a specific pipeline.

Design notes:
  - :class:`CodingResult` is a stable envelope around the existing
    :class:`MedicalCodingOutputSchema` so we don't break existing
    consumers (frontend DiagnosisCard, A2A flow, evaluation harness).
  - ``codes`` is a flat list of :class:`CodingResultCode` projected from
    primary_diagnosis + secondary_diagnoses + procedures, so the frontend
    gets the Corti-style "codes array with evidence/rationale" shape per
    the G001 refactor brief §5.1.
  - ``runtime_mode`` / ``latency_ms`` / ``llm_provider`` / ``trace_id``
    / ``cost`` are top-level so the frontend can render them without
    digging into the MedicalCodingOutputSchema.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class RuntimeMode(str, Enum):
    """Valid ``CodingRequest.mode`` values.

    The canonical product default is :attr:`CORTI_LIKE_FAST` — a single
    LLM call with a Chinese medical coding prompt (Corti-like UX).
    :attr:`MEDCODER_DEEP` retains the 5-stage MedCodER pipeline for
    advanced / research / complex-case use.
    """

    CORTI_LIKE_FAST = "corti_like_fast"
    MEDCODER_DEEP = "medcoder_deep"

    @classmethod
    def coerce(cls, value: Any) -> "RuntimeMode":
        if isinstance(value, RuntimeMode):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                return cls.CORTI_LIKE_FAST
        return cls.CORTI_LIKE_FAST


@dataclass
class CodingRequest:
    """Uniform input for any CodingRuntime."""

    text: str
    mode: RuntimeMode = RuntimeMode.CORTI_LIKE_FAST
    coding_system: str = "icd10cn"
    coding_systems: tuple[str, ...] = ("icd10cn",)
    include_evidence: bool = True
    include_trace: bool = True
    # Optional run_id for trace correlation. If absent, the runtime
    # generates one and returns it in :class:`CodingResult.trace_id`.
    run_id: str = ""
    # Optional user_id / tenant_id for cost attribution (filled by API layer).
    user_id: str = ""
    tenant_id: str = ""
    # Server-resolved project specialization for a dedicated clone. It is
    # appended under immutable source-runtime safeguards and is never copied
    # into response or trace metadata.
    project_policy: str = ""


@dataclass
class CodingResultCode:
    """Flat code entry projected from MedicalCodingOutputSchema.

    Each entry carries evidence + rationale + confidence + warnings so
    the frontend can render the Corti-style result card per G001 §6.2.
    """

    code: str
    system: str = "ICD-10-CN"
    display: str = ""
    type: str = "primary_diagnosis"  # primary_diagnosis | secondary_diagnosis | procedure | external_cause | aftercare | complication | other
    confidence: float = 0.0
    evidence: str = ""
    rationale: str = ""
    warnings: list[str] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CodingResult:
    """Uniform output envelope for any CodingRuntime.

    ``raw_schema`` retains the original :class:`MedicalCodingOutputSchema`
    dict so existing consumers (DiagnosisCard for MedCodER mode, evaluation
    harness) continue to work unchanged.
    """

    codes: list[CodingResultCode]
    summary: str = ""
    runtime_mode: str = "corti_like_fast"
    latency_ms: int = 0
    llm_provider: str = "deepseek"
    trace_id: str = ""
    run_id: str = ""
    cost: dict[str, Any] = field(default_factory=dict)
    # Original MedicalCodingOutputSchema as dict (for back-compat with
    # DiagnosisCard / evaluation harness).
    raw_schema: dict[str, Any] = field(default_factory=dict)
    # Optional 7-step (Fast) or 5-stage (Deep) trace events for RunTrace.
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    # Error flag — when True, ``codes`` may be empty and ``summary`` carries
    # the user-visible error message.
    error: bool = False
    error_reason: str = ""
    # B-003 layer 3: LLM-degraded marker. When True, the LLM gateway returned
    # a mock fallback envelope (no_api_key / provider_http_4xx / network_error /
    # 429_503 / circuit_open) and the runtime short-circuited without a real
    # LLM call. ``error_reason`` will be ``"llm_degraded"`` and
    # ``degraded_reason`` carries the gateway-side reason string. Per §二十六.24
    # ZERO TOLERANCE for false-success UI, this flag MUST surface end-to-end
    # as ``AgentRunResponse(error=True)`` so the existing frontend red-banner
    # path fires.
    degraded: bool = False
    degraded_reason: str = ""


@runtime_checkable
class CodingRuntime(Protocol):
    """Uniform runtime interface — ``predict`` takes a request, returns a result."""

    async def predict(self, request: CodingRequest) -> CodingResult:
        ...
