"""iCoDer Coding Runtime — multi-runtime dispatch layer.

Product positioning (per G001 refactor brief, 2026-07-09):

  iCoDer = Corti-like Medical AI Studio + China Revenue Compliance Coding Runtime

The default medical coding flow is the Corti-like Fast Coding Runtime
(``mode=corti_like_fast``): a single LLM call with a Chinese medical coding
prompt, dictionary-RAG-assisted candidate injection, and fault-tolerant JSON
parsing. The MedCodER 5-stage pipeline (extract / retrieve / merge / rerank
/ compliance) is preserved as ``mode=medcoder_deep`` for advanced /
research / complex-case use, but is no longer the default.

Runtimes:
  - :class:`FastCodingRuntime`   — single-stage LLM, ~7-12s latency
  - :class:`MedCoderRuntime`     — 5-stage MedCodER pipeline, 30-60s+ latency

Dispatch:
  - :class:`CodingRuntimeDispatcher` routes a :class:`CodingRequest` to the
    appropriate runtime based on ``request.mode``.

This module is the SSOT for the CodingRuntime abstraction. Existing
endpoints (``/api/v2/tools/coding/icoder``) and A2A flows continue to call
the MedCodER pipeline directly for back-compat; new code should go through
:class:`CodingRuntimeDispatcher`.
"""
from .base import (
    CodingRequest,
    CodingResult,
    CodingResultCode,
    CodingRuntime,
    RuntimeMode,
)
from .dispatcher import CodingRuntimeDispatcher, get_dispatcher, reset_dispatcher
from .fast_runtime import FastCodingRuntime
from .medcoder_runtime import MedCoderRuntime

__all__ = [
    "CodingRequest",
    "CodingResult",
    "CodingResultCode",
    "CodingRuntime",
    "RuntimeMode",
    "CodingRuntimeDispatcher",
    "get_dispatcher",
    "reset_dispatcher",
    "FastCodingRuntime",
    "MedCoderRuntime",
]
