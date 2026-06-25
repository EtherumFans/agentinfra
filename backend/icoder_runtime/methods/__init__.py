"""Coding Method Runtime — first-class "coding method" abstraction.

A *coding method* is any implementation that converts EMR text into
structured ICD codes. Phase B elevates these from a free-form ``mode``
string (per ``official_agents.medical_coding.modes.Mode``) into a
discoverable, traceable, comparable runtime entity.

Public surface:
  - :class:`CodingMethod` (ABC) — subclass to add a new method
  - :class:`MethodResult` — canonical return shape
  - :class:`CodingMethodRegistry` — SSOT, import the global instance
  - :class:`MethodSwitcher` — single entry point for dispatch

Built-in methods (registered automatically on import):
  - ``medcoder.full``           — 5-stage full pipeline (NAACL 2025)
  - ``medcoder.prompt``         — Stage 1 only (LLM initial codes)
  - ``medcoder.retrieve``       — Stage 2 only (BGE-M3 + FAISS, no LLM)
  - ``medcoder.prompt+retrieve``— Stages 1+2 (no rerank, no compliance)
  - ``legacy.deepseek``         — DeepSeek V4 + RuleEngine
  - ``legacy.prompt_llm``       — Generic LLM + RuleEngine
  - ``legacy.hybrid``           — Auto-select (default legacy)
  - ``legacy.no_repair``        — Hybrid with repair loop off
  - ``noop.unavailable``        — Returns empty result for empty input
"""

from .base import (
    CodingMethod,
    MethodCapability,
    MethodFamily,
    MethodResult,
    MethodStageTraceEntry,
)
from .registry import CodingMethodRegistry, GLOBAL_REGISTRY, get_registry
from .builtin import register_builtin_methods

# Auto-register built-in methods on package import. Side-effect-free
# for the rest of the codebase — downstream modules can rely on
# ``get_registry()`` always returning the populated global instance.
register_builtin_methods()


__all__ = [
    "CodingMethod",
    "MethodCapability",
    "MethodFamily",
    "MethodResult",
    "MethodStageTraceEntry",
    "CodingMethodRegistry",
    "GLOBAL_REGISTRY",
    "get_registry",
]
