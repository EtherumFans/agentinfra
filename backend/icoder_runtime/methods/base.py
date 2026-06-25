"""CodingMethod — abstract base class + MethodResult contract.

A coding method is a first-class runtime entity that converts EMR text
into structured ICD codes. Subclasses set class-level metadata and
implement :meth:`CodingMethod.run`.

The :class:`MethodResult` shape is the canonical return value — every
method, regardless of family, must produce one. This lets the
MethodSwitcher, the API layer, and the frontend treat all methods
uniformly for comparison + trace rendering.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enums ──


class MethodFamily(str, Enum):
    """Top-level coding method family.

    Used by the registry for filtering and by the frontend to render
    family-specific badges (medcoder / legacy / noop).
    """

    MEDCODER = "medcoder"
    LEGACY = "legacy"
    NOOP = "noop"


class MethodCapability(str, Enum):
    """External capability required by a method.

    The runtime answers ``available.get(capability.value, False)`` to
    decide whether to fall back to a degraded path or return
    status="unavailable". Adding a new capability here requires updating
    :func:`MethodSwitcher._probe_capabilities`.
    """

    LLM = "llm"                  # LLM gateway (DeepSeek V4 or fallback)
    RETRIEVER = "retriever"      # BGE-M3 + FAISS retriever
    RULE_SET = "rule_set"        # MedCodERRetrievalRuleSet or MedicalCodingRuleSet


# ── Result / trace dataclasses ──


@dataclass
class MethodStageTraceEntry:
    """One entry in a method's per-stage execution trace.

    The frontend renders this as a horizontal timeline. ``latency_ms``
    is wall-clock for the stage, ``output_size`` is a method-specific
    count (# codes / # diagnoses / # issues), and ``notes`` is free-form.
    """

    stage_name: str = ""
    status: str = "ok"  # ok | skipped | failed | noop
    latency_ms: int = 0
    output_size: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "output_size": self.output_size,
            "notes": self.notes,
        }


@dataclass
class MethodResult:
    """Canonical structured output of any CodingMethod.run() invocation.

    Method-agnostic: every method returns one of these. The legacy
    ``MedicalCodingOutputSchema.mode`` field is preserved alongside
    ``method_id`` for back-compat (existing persisted JSON), but
    ``method_id`` is the new SSOT.
    """

    method_id: str = ""
    method_name: str = ""
    method_family: str = ""  # medcoder | legacy | noop
    status: str = "ok"       # ok | unavailable | error
    reason: str = ""

    # Codes (flattened from MedicalCodingOutputSchema for easy comparison)
    primary_code: str = ""
    primary_name: str = ""
    primary_confidence: float = 0.0
    secondary_codes: list[dict] = field(default_factory=list)
    procedure_codes: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    manual_review_required: bool = False
    confidence: float = 0.0

    # Trace
    stage_trace: list[MethodStageTraceEntry] = field(default_factory=list)
    processing_time_ms: int = 0

    # Full structured schema dump (MedicalCodingOutputSchema.to_dict())
    # Preserved so callers can access mode / extracted_diagnoses / etc.
    full_schema: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "method_name": self.method_name,
            "method_family": self.method_family,
            "status": self.status,
            "reason": self.reason,
            "primary_code": self.primary_code,
            "primary_name": self.primary_name,
            "primary_confidence": self.primary_confidence,
            "secondary_codes": self.secondary_codes,
            "procedure_codes": self.procedure_codes,
            "issues": self.issues,
            "manual_review_required": self.manual_review_required,
            "confidence": self.confidence,
            "stage_trace": [e.to_dict() for e in self.stage_trace],
            "processing_time_ms": self.processing_time_ms,
        }


# ── ABC ──


class CodingMethod(ABC):
    """Abstract base class for any coding method.

    Subclasses MUST set class-level metadata:
      - ``method_id`` (canonical ID like "medcoder.full")
      - ``method_name`` (display name, may include Chinese)
      - ``method_family`` ("medcoder" / "legacy" / "noop")
      - ``stage_count`` (number of pipeline stages)
      - ``required_capabilities`` (tuple of MethodCapability)
      - ``description`` (1-2 sentence summary)

    Subclasses implement :meth:`run` which must return a :class:`MethodResult`
    even on expected failures (``status="unavailable"`` or
    ``status="error"``). Raising is reserved for programmer errors
    (e.g., misconfigured required_capabilities).
    """

    method_id: str = ""
    method_name: str = ""
    method_family: str = ""
    stage_count: int = 0
    required_capabilities: tuple[MethodCapability, ...] = ()
    description: str = ""

    @abstractmethod
    async def run(
        self,
        emr_text: str,
        ctx: dict[str, Any] | None = None,
    ) -> MethodResult:
        """Execute the method on the given EMR text.

        Must return a :class:`MethodResult` (never raise on expected
        failures — use status="unavailable"/"error" + reason).
        """
        ...

    def capabilities_check(
        self,
        available: dict[str, bool] | None = None,
    ) -> dict[str, bool]:
        """Return which required capabilities are available.

        ``available`` is a dict like ``{"llm": True, "retriever": True,
        "rule_set": True}``. Missing keys are treated as unavailable
        (returns False for that capability).
        """
        available = available or {}
        return {
            cap.value: bool(available.get(cap.value, False))
            for cap in self.required_capabilities
        }

    def to_meta(self) -> dict[str, Any]:
        """Return registry-safe metadata (no runtime state, no PII)."""
        return {
            "method_id": self.method_id,
            "method_name": self.method_name,
            "method_family": self.method_family,
            "stage_count": self.stage_count,
            "required_capabilities": [c.value for c in self.required_capabilities],
            "description": self.description,
        }


__all__ = [
    "CodingMethod",
    "MethodCapability",
    "MethodFamily",
    "MethodResult",
    "MethodStageTraceEntry",
]
