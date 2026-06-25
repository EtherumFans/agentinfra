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

import asyncio
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
        caps: dict[str, bool] | None = None,
    ) -> MethodResult:
        """Run the given method on the EMR text.

        Capability check first: if any required capability is missing,
        return ``status="unavailable"`` with a descriptive reason rather
        than invoking the method. Empty ``emr_text`` short-circuits to
        the noop method.

        ``caps`` is an optional pre-computed capability snapshot. When
        None (single-method call), a fresh probe is taken. When supplied
        (parallel-batch path inside :meth:`compare`), the shared snapshot
        is used — this avoids serializing on the FAISS health-check I/O
        inside the parallel fan-out.
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

        # Capability check — use the shared snapshot if supplied (parallel
        # compare-batch path), else probe fresh (single-method path).
        if caps is None:
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
        *,
        timeout_s: float | None = 60.0,
    ) -> list[MethodResult]:
        """Run multiple methods on the same EMR text in parallel.

        Phase D1 upgrade: replaced sequential for-loop with
        ``asyncio.gather`` so the wall-clock cost of comparing N methods
        is ``max(per-method latency)`` rather than ``sum``.

        Capability probing is performed ONCE up-front and shared across
        all tasks — the FAISS health check inside :func:`probe_capabilities`
        is synchronous file I/O and would otherwise block the event loop
        serially before each task reaches its ``await`` point.

        Each method is wrapped in :meth:`_run_with_timeout` so that:

        - A single method crashing does NOT fail the whole batch
          (the crash path inside ``run()`` already converts exceptions
          to ``status="error"`` MethodResults, so this is belt-and-suspenders).
        - A method exceeding ``timeout_s`` returns
          ``status="unavailable" reason="timeout after Xs"`` rather
          than hanging the entire ``/compare`` request.

        Results are returned in the same order as ``method_ids`` — gather
        preserves input order in its return tuple.

        ``timeout_s=None`` disables the per-method timeout (use only for
        offline batch jobs that are allowed to wait indefinitely).
        """
        # Probe capabilities ONCE — share across all tasks. The probe
        # does sync file I/O (FAISS health check ≈ 0.78s on a 148MB
        # index), so calling it per-task would serialize the parallel
        # fan-out before any task reaches its await point.
        shared_caps = probe_capabilities()
        tasks = [
            asyncio.create_task(
                self._run_with_timeout(mid, emr_text, ctx, timeout_s, shared_caps)
            )
            for mid in method_ids
        ]
        return list(await asyncio.gather(*tasks))

    async def _run_with_timeout(
        self,
        method_id: str,
        emr_text: str,
        ctx: dict[str, Any] | None,
        timeout_s: float | None,
        caps: dict[str, bool] | None = None,
    ) -> MethodResult:
        """Single-method wrapper used by :meth:`compare`.

        Translates ``asyncio.TimeoutError`` into a structured
        ``status="unavailable"`` result so the surrounding ``gather`` is
        never cancelled by one slow method.

        ``caps`` is the shared capability snapshot from the caller —
        when None (single-method ``run()`` path), a fresh probe is
        taken. Sharing the snapshot across the compare-batch lets
        parallel tasks skip the FAISS health-check round-trip.

        ``run()`` itself catches domain exceptions and returns
        ``status="error"`` — the outer ``try`` is a last-resort guard so
        even an ``asyncio.CancelledError`` injected from outside (e.g.
        the FastAPI client disconnecting) doesn't crash the comparison.
        """
        method = self._registry.get(method_id)
        if timeout_s is None:
            return await self.run(method_id, emr_text, ctx)
        try:
            return await asyncio.wait_for(
                self.run(method_id, emr_text, ctx, caps=caps),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return MethodResult(
                method_id=method.method_id if method else method_id,
                method_name=method.method_name if method else "(unknown)",
                method_family=method.method_family if method else "",
                status="unavailable",
                reason=f"timeout after {timeout_s}s",
            )
        except Exception as e:  # noqa: BLE001 — never let one bad method break the batch
            logger.exception("MethodSwitcher.compare: method=%s crashed", method_id)
            return MethodResult(
                method_id=method.method_id if method else method_id,
                method_name=method.method_name if method else "(unknown)",
                method_family=method.method_family if method else "",
                status="error",
                reason=f"method crashed in compare: {e!r}",
            )

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
