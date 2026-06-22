"""Sync ↔ async bridge adapters (SPEC §10).

Phase 1 of the Orchestrator keeps the Planner and Delegator **sync**
(``LLMCall`` and ``ExpertInvoker`` are both ``Callable[..., dict]``). The
real backing services — :class:`LLMGateway` and
:class:`HybridCodingAdapter` — are async because they wrap network and
heavy model calls.

This module provides thin adapter classes that bridge the two shapes:

  - :class:`LMGatewaySyncAdapter` — wraps the async ``LLMGateway.generate``
    and exposes a sync ``(system, user) -> dict`` callable that the
    Planner accepts.

  - :class:`MedCodERExpertAdapter` — wraps the async
    ``HybridCodingAdapter.infer_async`` and exposes a sync
    ``(ExpertInvocation) -> dict`` callable that the Delegator accepts.
    Non-``coding-expert`` invocations return a Phase-1 stub
    (``{"echo": ..., "phase1_stub": True}``) — full wiring for drg /
    compliance experts is Phase 5.

Both adapters use :func:`asyncio.run` to drive the coroutine. Phase 2
will migrate ``InboundHandler.handle`` to ``async def`` and drop the
adapters.

Why a separate module:
  - Keeps async boundaries out of the Planner/Delegator/InboundHandler
    code (which is unit-tested in isolation with simple fakes).
  - The lifespan wiring in ``app.main`` reads naturally:
    ``InboundHandler(..., llm_call=LMGatewaySyncAdapter(gw), invoker=MedCodERExpertAdapter(hybrid), ...)``
  - Each adapter has a single, narrow contract that is easy to mock in
    ``test_wiring.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from .delegator import ExpertInvocation, ExpertInvocationError

if TYPE_CHECKING:
    from icoder_runtime.core.llm_gateway import LLMGateway
    from icoder_runtime.providers.medical_coding.hybrid_adapter import (
        HybridCodingAdapter,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM sync adapter
# ---------------------------------------------------------------------------


class LMGatewaySyncAdapter:
    """Sync wrapper around :meth:`LLMGateway.generate`.

    The :class:`Planner` takes a sync ``(system, user) -> dict`` callable.
    The :class:`LLMGateway` exposes an async ``generate(messages, ...)``.
    This adapter closes the gap by running the coroutine via
    :func:`asyncio.run` on each call.

    Phase 2 will replace this with a native async Planner path.
    """

    def __init__(
        self,
        gateway: "LLMGateway",
        *,
        default_provider: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._provider = default_provider or ""

    def __call__(self, system_prompt: str, user_message: str) -> dict:
        messages = self._build_messages(system_prompt, user_message)
        return self._run(self._gateway.generate, messages)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _build_messages(system_prompt: str, user_message: str) -> list[dict[str, str]]:
        """Build the messages list.

        Both empty inputs are allowed — the Planner calls us with concrete
        prompts in production but tests pass short / empty values to verify
        we don't reject them.
        """
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    def _run(self, coro_factory: Callable[..., Any], messages: list[dict[str, str]]) -> dict:
        """Drive ``coro_factory(messages, provider=...)`` synchronously.

        Any exception from the gateway propagates unchanged so the
        Planner's retry layer (3x with exponential backoff) sees the
        real error.
        """

        async def _invoke() -> dict:
            return await coro_factory(
                messages,
                provider=self._provider or "",
            )

        return asyncio.run(_invoke())


# ---------------------------------------------------------------------------
# MedCodER expert sync adapter
# ---------------------------------------------------------------------------


class MedCodERExpertAdapter:
    """Sync wrapper around :meth:`HybridCodingAdapter.infer_async`.

    The :class:`Delegator` takes a sync ``(ExpertInvocation) -> dict``
    callable. The :class:`HybridCodingAdapter` exposes an async
    ``infer_async(messages, ...) -> MedicalCodingOutputSchema``.

    Routing:
      - ``expert_id == "coding-expert"`` → real MedCodER 5-stage pipeline.
      - any other ``expert_id`` → Phase-1 stub
        (``{"echo": subtask_input, "phase1_stub": True}``). Phase 5 wires
        drg-expert / compliance-expert to their real adapters.

    The :class:`HybridCodingAdapter` instance must be constructed with
    ``mode="medcoder"`` so the NAACL 2025 5-stage pipeline runs.
    """

    CODING_EXPERT_ID = "coding-expert"

    def __init__(self, hybrid: "HybridCodingAdapter") -> None:
        self._hybrid = hybrid

    def __call__(self, invocation: ExpertInvocation) -> dict:
        if invocation.expert_id != self.CODING_EXPERT_ID:
            return {
                "expert_id": invocation.expert_id,
                "echo": invocation.subtask_input,
                "phase1_stub": True,
            }
        return self._invoke_medcoder(invocation)

    # -- helpers ----------------------------------------------------------

    def _invoke_medcoder(self, invocation: ExpertInvocation) -> dict:
        messages = [
            {
                "role": "user",
                "content": invocation.subtask_input,
            }
        ]
        try:
            result = self._run_infer(messages, invocation.context)
        except ExpertInvocationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            # Translate generic failures into ExpertInvocationError so the
            # Delegator's retry/backoff layer can handle them uniformly.
            # Include the underlying exception type + message verbatim so
            # the A2A error envelope shows the real cause (otherwise it's
            # just "MedCodER infer failed: ..." with no detail).
            logger.exception("MedCodERExpertAdapter: infer failed")
            raise ExpertInvocationError(
                f"MedCodER infer failed [{type(exc).__name__}]: {exc}",
                stage="delegating",
            ) from exc
        # ``MedicalCodingOutputSchema`` is a dataclass (NOT pydantic), so
        # ``.model_dump()`` is unavailable — use ``.to_dict()`` instead.
        # Pydantic v2 schemas would expose ``.model_dump()``; we accept
        # either so future migrations don't regress.
        to_dict = getattr(result, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        model_dump = getattr(result, "model_dump", None)
        if callable(model_dump):
            return model_dump()
        # Last resort: fall back to __dict__-style coercion.
        return dict(result) if hasattr(result, "__dict__") else {}

    def _run_infer(
        self,
        messages: list[dict[str, str]],
        context: dict | None,
    ) -> Any:
        async def _invoke() -> Any:
            return await self._hybrid.infer_async(
                messages=messages,
                context=context or None,
            )

        return asyncio.run(_invoke())


# ---------------------------------------------------------------------------
# Factory helpers (lifespan wiring in app/main.py)
# ---------------------------------------------------------------------------


def build_llm_call_from_gateway(
    gateway: "LLMGateway | None",
    *,
    default_provider: str | None = None,
) -> Callable[[str, str], dict]:
    """Build the Planner's ``llm_call`` from a real :class:`LLMGateway`.

    Falls back to a deterministic stub when the gateway is missing (e.g.
    during unit tests, or when ``ICODER_PHASE1_STUB_LLM=1`` is set in
    production to short-circuit real LLM calls).
    """
    if gateway is None:
        logger.warning(
            "wiring.build_llm_call_from_gateway: no gateway — "
            "returning deterministic stub",
        )
        return _stub_llm_call

    if not gateway.is_configured:
        logger.warning(
            "wiring.build_llm_call_from_gateway: gateway has no providers — "
            "falling back to deterministic stub",
        )
        return _stub_llm_call

    return LMGatewaySyncAdapter(
        gateway,
        default_provider=default_provider,
    )


def build_expert_invoker_from_hybrid(
    hybrid: "HybridCodingAdapter | None",
) -> Callable[[ExpertInvocation], dict]:
    """Build the Delegator's ``invoker`` from a real
    :class:`HybridCodingAdapter`.

    Falls back to a no-op stub when the adapter is missing.
    """
    if hybrid is None:
        logger.warning(
            "wiring.build_expert_invoker_from_hybrid: no hybrid adapter — "
            "returning echo stub",
        )
        return _stub_expert_invoker

    return MedCodERExpertAdapter(hybrid)


# ---------------------------------------------------------------------------
# Stubs (used when ICODER_PHASE1_STUB_LLM=1 or no real backends wired)
# ---------------------------------------------------------------------------


def _stub_llm_call(system: str, user: str) -> dict:
    """Deterministic stub LLM — returns an empty plan that the Planner
    will reject as ``planning_failed``. Tests that want a happy-path
    plan should inject their own LLM."""
    return {"content": "{}", "model": "stub", "latency_ms": 0}


def _stub_expert_invoker(invocation: ExpertInvocation) -> dict:
    return {
        "expert_id": invocation.expert_id,
        "echo": invocation.subtask_input,
        "phase1_stub": True,
    }


__all__ = [
    "LMGatewaySyncAdapter",
    "MedCodERExpertAdapter",
    "build_llm_call_from_gateway",
    "build_expert_invoker_from_hybrid",
]