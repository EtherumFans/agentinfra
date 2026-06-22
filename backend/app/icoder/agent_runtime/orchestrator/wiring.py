"""Sync ↔ async bridge adapters (SPEC §10).

Phase 1 of the Orchestrator keeps the Planner and Delegator **sync**
(``LLMCall`` and ``ExpertInvoker`` are both ``Callable[..., dict]``). The
real backing services — :class:`LLMGateway` and the new
:class:`app.icoder.agent_runtime.experts.CodingExpert` — are async
because they wrap network and heavy model calls.

This module provides thin adapter classes that bridge the two shapes:

  - :class:`LMGatewaySyncAdapter` — wraps the async ``LLMGateway.generate``
    and exposes a sync ``(system, user) -> dict`` callable that the
    Planner accepts.

The MedCodER Expert path is now wired via
:func:`build_expert_invoker_from_hybrid`, which constructs a
:class:`CodingExpert` (the Runtime's first real Expert impl) and wraps
it in a thin dispatcher that returns a Phase-1 stub for non-coding
experts (``drg-expert`` / ``compliance-expert`` — Phase 5 work).

Both adapters use :func:`asyncio.run` to drive the coroutine. Phase 2
will migrate ``InboundHandler.handle`` to ``async def`` and drop the
adapters.

Why a separate module:
  - Keeps async boundaries out of the Planner/Delegator/InboundHandler
    code (which is unit-tested in isolation with simple fakes).
  - The lifespan wiring in ``app.main`` reads naturally:
    ``InboundHandler(..., llm_call=LMGatewaySyncAdapter(gw), invoker=build_expert_invoker_from_hybrid(hybrid), ...)``
  - Each adapter has a single, narrow contract that is easy to mock in
    ``test_wiring.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from .delegator import ExpertInvocation

if TYPE_CHECKING:
    from icoder_runtime.core.llm_gateway import LLMGateway
    from icoder_runtime.providers.medical_coding.hybrid_adapter import (
        HybridCodingAdapter,
    )
    from app.icoder.agent_runtime.experts.coding_expert import CodingExpert

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
# MedCodER expert invoker factory
# ---------------------------------------------------------------------------


# HybridCodingAdapter mode → MedCodERStrategy variant name. Mirrors
# ``HybridCodingAdapter._mode_to_variant``; duplicated here to avoid an
# import cycle (wiring.py is imported by app/main.py before the strategy
# is constructed, but we want a stable mapping without importing the
# adapter at module load).
_MODE_TO_VARIANT: dict[str, str] = {
    "medcoder": "full",
    "medcoder_full": "full",
    "medcoder_prompt": "prompt",
    "medcoder_retrieve": "retrieve",
    "medcoder_prompt+retrieve": "prompt+retrieve",
}


def _resolve_default_variant(mode: str | None) -> str:
    """Resolve the default ablation variant from a hybrid mode string.

    Falls back to ``"full"`` for unknown / legacy modes — those will be
    caught upstream by the ``hybrid._strategy is None`` guard, so this
    fallback is only hit in defensive paths.
    """
    if not mode:
        return "full"
    return _MODE_TO_VARIANT.get(mode, "full")


def _dispatch_expert_invocation(
    coding_expert: "CodingExpert | None",
    invocation: ExpertInvocation,
) -> dict:
    """Dispatch an ``ExpertInvocation`` to the right backend.

    Coding-expert invocations go through :class:`CodingExpert` (which
    itself wraps :class:`MedCodERStrategy`). All other expert IDs return
    a Phase-1 stub. This is the single place Phase 5 will add drg-expert
    / compliance-expert branches.
    """
    from app.icoder.agent_runtime.experts.coding_expert import CodingExpert

    if coding_expert is not None and invocation.expert_id == CodingExpert.EXPERT_ID:
        return coding_expert(invocation)
    return _stub_expert_invoker(invocation)


def build_expert_invoker_from_hybrid(
    hybrid: "HybridCodingAdapter | None",
) -> Callable[[ExpertInvocation], dict]:
    """Build the Delegator's ``invoker`` from a real
    :class:`HybridCodingAdapter`.

    M1: returns a dispatcher that routes ``coding-expert`` invocations
    to a :class:`CodingExpert` (the Runtime's first real Expert impl,
    wrapping :class:`MedCodERStrategy`). Other expert IDs get a Phase-1
    stub. Falls back to the stub entirely when ``hybrid is None`` or
    when ``hybrid._strategy`` was never built (i.e. ``mode`` is not in
    :data:`HybridCodingAdapter.MEDCODER_MODES`).

    The returned callable satisfies the public
    ``Callable[[ExpertInvocation], dict]`` contract — ``app/main.py``
    and the Delegator do not need to know about ``CodingExpert``.
    """
    if hybrid is None:
        logger.warning(
            "wiring.build_expert_invoker_from_hybrid: no hybrid adapter — "
            "returning echo stub",
        )
        return _stub_expert_invoker

    strategy = getattr(hybrid, "_strategy", None)
    if strategy is None:
        # Legacy / non-medcoder mode — the adapter doesn't own a strategy.
        # Real coding-expert calls would be misrouted, so fall back to the
        # stub entirely. (In practice this means the lifespan must pass a
        # medcoder-mode hybrid to get real coding inference.)
        logger.warning(
            "wiring.build_expert_invoker_from_hybrid: hybrid mode=%r has no "
            "strategy — returning echo stub for all experts",
            hybrid._mode,
        )
        return _stub_expert_invoker

    # Build the real Expert impl lazily so the wiring import doesn't pull
    # in the strategy module eagerly.
    from app.icoder.agent_runtime.experts.coding_expert import CodingExpert

    coding_expert = CodingExpert(
        strategy,
        default_variant=_resolve_default_variant(getattr(hybrid, "_mode", None)),
    )

    def _invoker(invocation: ExpertInvocation) -> dict:
        return _dispatch_expert_invocation(coding_expert, invocation)

    return _invoker


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


__all__ = [
    "LMGatewaySyncAdapter",
    "build_llm_call_from_gateway",
    "build_expert_invoker_from_hybrid",
]
