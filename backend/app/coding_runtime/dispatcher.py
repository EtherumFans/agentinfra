"""CodingRuntimeDispatcher — mode → runtime routing.

Single entry point for the API layer. Given a :class:`CodingRequest`,
routes to the appropriate runtime based on ``request.mode``.

Design notes:
  - Lazily instantiates runtimes (FastRuntime needs the platform_gateway
    which isn't available at module-load time).
  - Returns a friendly error :class:`CodingResult` on unknown mode (rather
    than raising) so the API layer can return a clean 400 with a hint.
"""
from __future__ import annotations

import logging
from typing import Any

from app.coding_runtime.base import (
    CodingRequest,
    CodingResult,
    CodingRuntime,
    RuntimeMode,
)
from app.coding_runtime.fast_runtime import FastCodingRuntime
from app.coding_runtime.medcoder_runtime import MedCoderRuntime

logger = logging.getLogger(__name__)


class CodingRuntimeDispatcher:
    """Routes a CodingRequest to the appropriate CodingRuntime.

    Single shared instance lives at ``app.state.coding_dispatcher`` (set
    by ``get_dispatcher()`` on first call). Stateless except for the
    cached runtime instances.
    """

    def __init__(self):
        self._fast: FastCodingRuntime | None = None
        self._deep: MedCoderRuntime | None = None

    def _get_fast(self) -> FastCodingRuntime:
        if self._fast is None:
            self._fast = FastCodingRuntime()
        return self._fast

    def _get_deep(self) -> MedCoderRuntime:
        if self._deep is None:
            self._deep = MedCoderRuntime()
        return self._deep

    def select_runtime(self, mode: RuntimeMode) -> CodingRuntime:
        """Return the runtime for ``mode``. Falls back to Fast on unknown."""
        if mode == RuntimeMode.MEDCODER_DEEP:
            return self._get_deep()
        # Default + unknown → Fast (never raise)
        return self._get_fast()

    async def dispatch(self, request: CodingRequest) -> CodingResult:
        """Route ``request`` to the appropriate runtime and invoke predict."""
        runtime = self.select_runtime(request.mode)
        try:
            return await runtime.predict(request)
        except Exception as exc:
            # Defensive — should never happen since runtimes catch their own
            # errors, but if one slips through we return a clean error result
            # instead of letting the API 500.
            logger.error(
                f"CodingRuntimeDispatcher: runtime {runtime.name} crashed: {exc!r}",
                exc_info=True,
            )
            return CodingResult(
                codes=[],
                summary=f"内部错误: {str(exc)[:200]}。请重试或切换至 Fast Coding 模式。",
                runtime_mode=request.mode.value,
                latency_ms=0,
                llm_provider="deepseek",
                trace_id="",
                run_id=request.run_id,
                error=True,
                error_reason="runtime_crashed",
            )


_dispatcher: CodingRuntimeDispatcher | None = None


def get_dispatcher() -> CodingRuntimeDispatcher:
    """Return the shared dispatcher (singleton)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = CodingRuntimeDispatcher()
    return _dispatcher


def reset_dispatcher() -> None:
    """Reset the singleton (for tests)."""
    global _dispatcher
    _dispatcher = None
