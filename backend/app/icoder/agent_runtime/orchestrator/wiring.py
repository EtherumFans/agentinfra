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
it in a thin dispatcher that fails closed for unsupported expert IDs.

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

from .delegator import ExpertInvocation, ExpertInvocationError
from .planner import PlannerError

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
    itself wraps :class:`MedCodERStrategy`). Unsupported expert IDs fail
    closed until a production implementation is registered.
    """
    from app.icoder.agent_runtime.experts.coding_expert import CodingExpert

    if coding_expert is not None and invocation.expert_id == CodingExpert.EXPERT_ID:
        return coding_expert(invocation)
    return unavailable_expert_invoker(invocation)


def build_expert_invoker_from_hybrid(
    hybrid: "HybridCodingAdapter | None",
) -> Callable[[ExpertInvocation], dict]:
    """Build the Delegator's ``invoker`` from a real
    :class:`HybridCodingAdapter`.

    M1: returns a dispatcher that routes ``coding-expert`` invocations
    to a :class:`CodingExpert` (the Runtime's first real Expert impl,
    wrapping :class:`MedCodERStrategy`). Other expert IDs fail closed.
    Missing Hybrid/strategy dependencies also fail closed when ``hybrid is None`` or
    when ``hybrid._strategy`` was never built (i.e. ``mode`` is not in
    :data:`HybridCodingAdapter.MEDCODER_MODES`).

    The returned callable satisfies the public
    ``Callable[[ExpertInvocation], dict]`` contract — ``app/main.py``
    and the Delegator do not need to know about ``CodingExpert``.

    E1 (2026-06-26): the canonical path is now
    :func:`build_expert_invoker_for_medcoder` which routes to 4 D2
    expert packs (evidence_extractor / index_navigator / code_reconciler
    / tabular_validator). This factory is kept as the back-compat
    fallback for any non-medcoder Agent or M1 callers that still expect
    a single ``coding-expert`` wrapper.
    """
    if hybrid is None:
        logger.warning(
            "wiring.build_expert_invoker_from_hybrid: no hybrid adapter — "
            "Expert calls will fail closed",
        )
        return unavailable_expert_invoker

    strategy = getattr(hybrid, "_strategy", None)
    if strategy is None:
        # Legacy / non-medcoder mode — the adapter doesn't own a strategy.
        # Real coding-expert calls would be misrouted, so fall back to the
        # unavailable callable. (In practice this means the lifespan must pass a
        # medcoder-mode hybrid to get real coding inference.)
        logger.warning(
            "wiring.build_expert_invoker_from_hybrid: hybrid mode=%r has no "
            "strategy — Expert calls will fail closed",
            hybrid._mode,
        )
        return unavailable_expert_invoker

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
# E1 (2026-06-26) — 4 D2 expert packs as the canonical MedCodER path
# ---------------------------------------------------------------------------
# Per ORCHESTRATOR §3.2 + AGENT_CARD §3.2: the Orchestrator's ``invoker`` is
# the single point where AgentDefinition.expert_ids are dispatched to real
# Python Expert impls. E1 replaces the single ``coding-expert`` glue
# (MedCodERStrategy) with 4 atomic D2 expert packs, each owning one stage
# of the MedCodER 5-stage pipeline:
#
#   - evidence-extractor  (Stage 1 — LLM fact extraction)
#   - index-navigator     (Stage 2 — BGE-M3 + FAISS retrieval)
#   - code-reconciler     (Stage 3 + 4 — merge + RankGPT-style rerank)
#   - tabular-validator   (Stage 5 — MedicalCodingRuleSet calibration)
#
# ``coding-expert`` is kept as a back-compat dispatch (M1 hybrid path) for
# any caller that hasn't migrated to the 4-expert AgentDefinition yet. The
# Plaquard downstream aggregation just merges whatever experts[].result
# came back, so the back-compat dispatch is transparent to the Aggregator.


def build_expert_invoker_for_medcoder(
    llm_gateway: "LLMGateway | None" = None,
    *,
    medcoder_retriever: Any = None,
    rule_engine: Any = None,
    hybrid_fallback: "HybridCodingAdapter | None" = None,
) -> Callable[[ExpertInvocation], dict]:
    """Build the canonical E1 invoker dispatching 4 D2 expert packs.

    Per E1 (2026-06-26) — this is the canonical MedCodER Agent path. Each
    of the 4 atomic experts is a real Python impl (D2) with both
    ``__call__(invocation) -> dict`` (sync) and ``invoke_async(arg, ctx)
    -> dict`` (async) entry points. The Orchestrator's Delegator
    (sync, per Phase 1 SPEC §3.1) drives them sequentially.

    Args:
        llm_gateway: :class:`LLMGateway` for the LLM-backed experts
            (evidence_extractor / code_reconciler). When ``None``, those
            experts fall back to deterministic offline mode and mark
            their result with ``is_mock=True``.
        medcoder_retriever: :class:`MedCodERRetriever` for
            index_navigator. When ``None`` or un-loaded, the expert
            returns ``retriever_status="missing"`` with empty candidate
            lists (graceful degradation per D2 design).
        rule_engine: :class:`RuleEngine` for tabular_validator. When
            ``None``, the expert lazy-imports ``RuleEngine()`` (the
            singleton that lives in ``app.services.rule_engine_registry``).
        hybrid_fallback: optional M1 ``HybridCodingAdapter`` that owns
            the ``coding-expert`` strategy. When supplied,
            ``coding-expert`` invocations still route to the M1
            ``CodingExpert(strategy)`` for back-compat. When ``None``,
            ``coding-expert`` fails closed.

    Returns:
        A ``Callable[[ExpertInvocation], dict]`` dispatcher. Each call
        routes to the matching expert instance (one of the 4 D2 packs,
        or the M1 back-compat ``CodingExpert``; every other ID fails closed).
    """
    # Lazy imports — keep the wiring module cheap to import.
    from app.icoder.agent_runtime.experts.code_reconciler_expert import (
        CodeReconcilerExpert,
    )
    from app.icoder.agent_runtime.experts.evidence_extractor_expert import (
        EvidenceExtractorExpert,
    )
    from app.icoder.agent_runtime.experts.index_navigator_expert import (
        IndexNavigatorExpert,
    )
    from app.icoder.agent_runtime.experts.tabular_validator_expert import (
        TabularValidatorExpert,
    )

    evidence_expert = EvidenceExtractorExpert(llm_gateway=llm_gateway)
    index_expert = IndexNavigatorExpert(retriever=medcoder_retriever)
    reconcile_expert = CodeReconcilerExpert(llm_gateway=llm_gateway)
    validate_expert = TabularValidatorExpert(rule_engine=rule_engine)

    # Back-compat: only build the M1 CodingExpert wrapper if a hybrid
    # adapter with a real strategy is provided. Otherwise the M1 path
    # fails closed.
    coding_expert = None
    if hybrid_fallback is not None:
        strategy = getattr(hybrid_fallback, "_strategy", None)
        if strategy is not None:
            from app.icoder.agent_runtime.experts.coding_expert import (
                CodingExpert,
            )
            coding_expert = CodingExpert(
                strategy,
                default_variant=_resolve_default_variant(
                    getattr(hybrid_fallback, "_mode", None),
                ),
            )

    def _invoker(invocation: ExpertInvocation) -> dict:
        eid = invocation.expert_id
        if eid == EvidenceExtractorExpert.EXPERT_ID:
            return evidence_expert(invocation)
        if eid == IndexNavigatorExpert.EXPERT_ID:
            return index_expert(invocation)
        if eid == CodeReconcilerExpert.EXPERT_ID:
            return reconcile_expert(invocation)
        if eid == TabularValidatorExpert.EXPERT_ID:
            return validate_expert(invocation)
        # Back-compat: M1 ``coding-expert`` glue.
        if eid == "coding-expert" and coding_expert is not None:
            return coding_expert(invocation)
        logger.warning(
            "wiring.build_expert_invoker_for_medcoder: unknown expert_id=%r — "
            "failing closed",
            eid,
        )
        return unavailable_expert_invoker(invocation)

    return _invoker


# ---------------------------------------------------------------------------
# Fail-closed runtime callables
# ---------------------------------------------------------------------------


def _unavailable_llm_call(system: str, user: str) -> dict:
    """Fail closed when no production LLM provider is configured.

    Returning an empty or synthetic model response here used to make an
    unavailable backend look like a successful LLM invocation before the
    Planner rejected the fabricated plan. Raise the classified runtime error
    directly so callers receive a retryable 503 and traces never claim that a
    model ran.
    """
    del system, user
    raise PlannerError(
        "LLM backend unavailable: no configured provider",
        code="planning_failed",
        http_status=503,
        retryable=True,
    )


def unavailable_expert_invoker(invocation: ExpertInvocation) -> dict:
    """Fail closed when an Expert has no production implementation."""
    raise ExpertInvocationError(
        "expert backend unavailable",
        retryable=False,
        code="expert_failed",
        http_status=503,
    )


# ---------------------------------------------------------------------------
# Factory helpers (lifespan wiring in app/main.py)
# ---------------------------------------------------------------------------


def build_llm_call_from_gateway(
    gateway: "LLMGateway | None",
    *,
    default_provider: str | None = None,
) -> Callable[[str, str], dict]:
    """Build the Planner's ``llm_call`` from a real :class:`LLMGateway`.

    Fails closed with a retryable 503 when the gateway is missing or has no
    configured providers. Tests that need a deterministic LLM must inject one
    explicitly; the production factory never fabricates a model response.
    """
    if gateway is None:
        logger.warning(
            "wiring.build_llm_call_from_gateway: no gateway — "
            "returning fail-closed unavailable callable",
        )
        return _unavailable_llm_call

    if not gateway.is_configured:
        logger.warning(
            "wiring.build_llm_call_from_gateway: gateway has no providers — "
            "returning fail-closed unavailable callable",
        )
        return _unavailable_llm_call

    return LMGatewaySyncAdapter(
        gateway,
        default_provider=default_provider,
    )


__all__ = [
    "LMGatewaySyncAdapter",
    "build_expert_invoker_for_medcoder",
    "build_expert_invoker_from_hybrid",
    "build_llm_call_from_gateway",
    "unavailable_expert_invoker",
]
