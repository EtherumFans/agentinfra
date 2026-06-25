"""MethodSwitcher — single entry point for dispatching coding methods.

The switcher is intentionally thin: look up the method in the registry,
probe capabilities, and run. All method-specific logic lives in the
registered :class:`CodingMethod` subclass — the switcher does NOT
duplicate dispatch logic.

Capability probing
------------------
The switcher probes three external capabilities before invoking a
method:

  - ``llm``        — whether ``LLMGateway`` is configured (env or app state)
  - ``retriever``  — whether the FAISS index is healthy
  - ``rule_set``   — always ``True`` (rule sets are local code)

If a required capability is missing the switcher returns
``status="unavailable"`` rather than silently degrading the result.
The caller can then either surface the unavailability to the user or
substitute a different method (e.g. ``noop.unavailable``).

Back-compat ``mode`` argument
-----------------------------
The legacy ``mode`` strings (``deepseek`` / ``prompt_llm`` / ``hybrid``
/ ``no_repair`` / ``medcoder`` / ``medcoder_full`` / ``medcoder_prompt``
/ ``medcoder_retrieve`` / ``medcoder_prompt+retrieve``) are still
accepted via :func:`mode_to_method_id`. New code should pass
``method_id`` directly. ``mode`` is retained only for existing API
consumers — Phase B does not expand legacy paths.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from official_agents.medical_coding.modes import (
    LEGACY_MODES,
    MEDCODER_MODES,
    Mode,
    coerce,
)
from .base import CodingMethod, MethodResult
from .registry import GLOBAL_REGISTRY, get_registry

logger = logging.getLogger(__name__)


# ── Capability probing ──


def probe_capabilities() -> dict[str, bool]:
    """Return which external capabilities are currently available.

    ``llm``        — True iff ``ICODER_CREDENTIAL_LLM`` env var is set
                     (matches the dev-env convention used everywhere
                     else in the codebase; explicit empty string counts
                     as missing).
    ``retriever``  — True iff ``app.services.medcoder_index_health.index_health_check``
                     reports ``status="ok"`` for ``data/medcoder``.
                     Falls back to False if the health-check module is
                     unavailable — never raises.
    ``rule_set``   — Always True. Rule sets are local Python modules,
                     no I/O required.

    Cached per-process? No — every call re-probes. The cost is a few
    file-stat + pickle-load operations and keeps the switcher simple.
    Callers that need a stable view should snapshot the result.
    """
    llm = bool(os.environ.get("ICODER_CREDENTIAL_LLM", "").strip())
    retriever = False
    try:
        from app.services.medcoder_index_health import index_health_check
        h = index_health_check("data/medcoder")
        retriever = h.get("status") == "ok"
    except Exception as e:
        logger.debug("MethodSwitcher: retriever probe failed: %s", e)
        retriever = False
    return {"llm": llm, "retriever": retriever, "rule_set": True}


# ── Mode ↔ method_id mapping ──


_LEGACY_MODE_TO_METHOD_ID = {
    Mode.DEEPSEEK: "legacy.deepseek",
    Mode.PROMPT_LLM: "legacy.prompt_llm",
    Mode.HYBRID: "legacy.hybrid",
    Mode.NO_REPAIR: "legacy.no_repair",
}

_MEDCODER_MODE_TO_METHOD_ID = {
    Mode.MEDCODER: "medcoder.full",
    Mode.MEDCODER_FULL: "medcoder.full",
    Mode.MEDCODER_PROMPT: "medcoder.prompt",
    Mode.MEDCODER_RETRIEVE: "medcoder.retrieve",
    Mode.MEDCODER_PROMPT_RETRIEVE: "medcoder.prompt+retrieve",
    Mode.MEDCODER_CODE_LIKE_HUMANS: "medcoder.code_like_humans",
}


def mode_to_method_id(mode: str | Mode) -> str | None:
    """Map a legacy ``mode`` value to its canonical ``method_id``.

    Returns ``None`` for unknown values. The reverse mapping is NOT
    provided because multiple methods may share the same legacy mode
    (e.g. ``medcoder`` and ``medcoder_full`` both map to ``medcoder.full``).
    """
    m = coerce(mode)
    if m in _MEDCODER_MODE_TO_METHOD_ID:
        return _MEDCODER_MODE_TO_METHOD_ID[m]
    if m in _LEGACY_MODE_TO_METHOD_ID:
        return _LEGACY_MODE_TO_METHOD_ID[m]
    return None


# ── Switcher ──


class MethodSwitcher:
    """Dispatch coding methods by ``method_id`` (preferred) or legacy ``mode``.

    Stateless — all state lives in the registry. Construct freely; the
    singleton ``GLOBAL_SWITCHER`` is also exported for callers that
    prefer module-level access.
    """

    def __init__(self, registry=None) -> None:
        self._registry = registry if registry is not None else GLOBAL_REGISTRY

    async def run(
        self,
        method_id: str,
        emr_text: str,
        ctx: dict[str, Any] | None = None,
    ) -> MethodResult:
        """Run the given method on the EMR text.

        Capability check first: if any required capability is missing,
        return ``status="unavailable"`` with a descriptive reason rather
        than invoking the method. Empty ``emr_text`` short-circuits to
        the noop method.
        """
        method = self._registry.get(method_id)
        if method is None:
            return MethodResult(
                method_id=method_id,
                method_name="(unknown)",
                method_family="",
                status="unavailable",
                reason=f"unknown method_id={method_id!r}; available: {self._registry.method_ids()}",
            )

        if not (emr_text or "").strip():
            return MethodResult(
                method_id=method.method_id,
                method_name=method.method_name,
                method_family=method.method_family,
                status="unavailable",
                reason="empty emr_text",
            )

        # Capability check
        caps = probe_capabilities()
        missing = [
            c.value for c in method.required_capabilities
            if not caps.get(c.value, False)
        ]
        if missing:
            return MethodResult(
                method_id=method.method_id,
                method_name=method.method_name,
                method_family=method.method_family,
                status="unavailable",
                reason=f"missing required capabilities: {missing}",
                stage_trace=[],
            )

        try:
            return await method.run(emr_text, ctx)
        except Exception as e:
            logger.exception("MethodSwitcher: method=%s crashed", method_id)
            return MethodResult(
                method_id=method.method_id,
                method_name=method.method_name,
                method_family=method.method_family,
                status="error",
                reason=f"method crashed: {e!r}",
            )

    async def compare(
        self,
        method_ids: list[str],
        emr_text: str,
        ctx: dict[str, Any] | None = None,
    ) -> list[MethodResult]:
        """Run multiple methods on the same EMR text (sequentially).

        Sequential for Phase B (simpler error attribution + trace
        timing). Parallel execution is a Phase C optimization. Returns
        the list of results in the same order as ``method_ids`` —
        callers that want comparison grouping should sort by
        ``primary_code`` / ``confidence`` / ``processing_time_ms``.
        """
        out: list[MethodResult] = []
        for mid in method_ids:
            out.append(await self.run(mid, emr_text, ctx))
        return out

    def describe(self, method_id: str) -> dict[str, Any] | None:
        """Return registry-safe metadata for one method, or None."""
        m = self._registry.get(method_id)
        if m is None:
            return None
        meta = m.to_meta()
        meta["available"] = self._is_method_available(m)
        return meta

    def _is_method_available(self, method: CodingMethod) -> bool:
        caps = probe_capabilities()
        return all(
            caps.get(c.value, False) for c in method.required_capabilities
        )


# Singleton — used by app/api/icoder_coding_methods.py.
GLOBAL_SWITCHER = MethodSwitcher()


__all__ = [
    "MethodSwitcher",
    "GLOBAL_SWITCHER",
    "probe_capabilities",
    "mode_to_method_id",
]
