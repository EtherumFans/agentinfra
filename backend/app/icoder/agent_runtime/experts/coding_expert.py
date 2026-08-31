"""CodingExpert — iCoDer Runtime's first real Expert implementation.

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 5 + Part 7.4, the audit flags
"Coding Expert 没有 Python impl — Phase 1 仅做 routing, 实质逻辑是
HybridCodingAdapter 黑盒" (50/100 score for that layer). M1 fixes that:

  - New ``app.icoder.agent_runtime.experts.CodingExpert`` (this file)
  - Wraps :class:`MedCodERStrategy` (5 stages + 4 variants)
  - Replaces the sync-async bridge ``MedCodERExpertAdapter`` in
    ``orchestrator/wiring.py`` (next commit deletes that bridge)
  - First real Expert impl in the Runtime — Phase 5 will add
    drg-expert, compliance-expert, dip-expert alongside.

Public contract
---------------
Phase 1 Delegator is sync; the Expert invoker signature is
``Callable[[ExpertInvocation], dict]``. ``CodingExpert.__call__``
satisfies that — internally it uses ``asyncio.run`` to drive the
async ``invoke_async`` path. Phase 2 will move Delegator to
``async def`` and use ``invoke_async`` directly (no ``asyncio.run``).

Error handling
--------------
``invoke_async`` re-raises generic exceptions as
:class:`ExpertInvocationError` so the Delegator's retry / backoff
layer handles them uniformly. The Delegator depends on this error
type — do not change it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)

if TYPE_CHECKING:
    from icoder_runtime.providers.medical_coding.medcoder_strategy import (
        MedCodERStrategy,
    )

logger = logging.getLogger(__name__)


# ── CodingExpert ────────────────────────────────────────────────────


class CodingExpert:
    """Real Python Expert impl for ``coding-expert``.

    Wraps a :class:`MedCodERStrategy` and exposes the
    ``Callable[[ExpertInvocation], dict]`` contract the Orchestrator's
    Delegator expects (Phase 1 sync path). The async ``invoke_async``
    is also exposed for Phase 2 native Delegator wiring.

    Args:
        strategy: a :class:`MedCodERStrategy` (or any object with a
            ``run_variant(emr_text, variant, ctx) -> Awaitable[MedicalCodingOutputSchema]``
            method).
        default_variant: ablation variant to run when
            ``ExpertInvocation`` doesn't pin one (defaults to
            ``"full"`` — full 5-stage pipeline).
        is_mock: when ``True``, marks every result with
            ``is_mock=True`` for the recorder / observability layer.
            Not used in production paths.
    """

    EXPERT_ID: str = "coding-expert"
    EXPERT_NAME: str = "Coding Expert (MedCodER 5-stage)"

    def __init__(
        self,
        strategy: "MedCodERStrategy",
        *,
        default_variant: str = "full",
        is_mock: bool = False,
    ) -> None:
        if default_variant not in getattr(strategy, "VARIANTS", ("full",)):
            # Be tolerant — accept the strategy's variants tuple OR
            # the legacy set; we'll dispatch the closest match.
            logger.warning(
                "CodingExpert: default_variant %r not in strategy.VARIANTS=%r; "
                "falling back to 'full'",
                default_variant,
                getattr(strategy, "VARIANTS", ()),
            )
            default_variant = "full"
        self._strategy = strategy
        self._default_variant = default_variant
        self._is_mock = is_mock

    # ── Phase 1 sync interface (Delegator still sync) ─────────────

    def invoke_sync(self, invocation: ExpertInvocation) -> dict:
        """Phase 1 entry — Delegator calls this with ``ExpertInvocation``.

        Internally drives ``invoke_async`` via ``asyncio.run`` (which
        fails if called from a running event loop — Phase 2 removes
        this restriction by going fully async).
        """
        return self._run_sync(
            invocation.subtask_input or "",
            invocation.context or {},
            variant=self._resolve_variant_from_context(invocation.context),
        )

    # Alias so the ``Callable[[ExpertInvocation], dict]`` contract
    # works without callers explicitly naming the method.
    __call__ = invoke_sync

    # ── Phase 2 async interface ───────────────────────────────────

    async def invoke_async(
        self,
        emr_text: str,
        ctx: dict | None = None,
        *,
        variant: str | None = None,
    ) -> dict:
        """Native async entry. M1 exposes this; Phase 2 will wire it
        to the Delegator's ``async_expert_invoke`` path.

        Returns a plain ``dict`` representation of the
        :class:`MedicalCodingOutputSchema` (dataclass → ``.to_dict()``
        with a ``.model_dump()`` / ``__dict__`` fallback chain).

        Raises:
            ExpertInvocationError: if ``strategy.run_variant`` raises
                any non-fatal error. The underlying exception is
                re-raised as ``ExpertInvocationError`` so the
                Delegator's retry / backoff layer handles it
                uniformly.
        """
        v = variant or self._default_variant
        ctx = ctx or {}
        try:
            schema = await self._strategy.run_variant(emr_text, v, ctx)
        except ExpertInvocationError:
            # Already structured — propagate unchanged so the Delegator
            # sees the original code/stage/retryable fields rather than
            # a generic wrapper.
            raise
        except Exception as exc:  # translate to ExpertInvocationError
            logger.exception("CodingExpert: run_variant(%r) failed", v)
            raise ExpertInvocationError(
                f"CodingExpert: run_variant({v!r}) failed "
                f"[{type(exc).__name__}]: {exc}",
                stage="delegating",
            ) from exc

        # Annotate is_mock on the dict representation (for recorder /
        # observability downstream).
        result = self._schema_to_dict(schema)
        if self._is_mock and isinstance(result, dict):
            result["is_mock"] = True
        # Carry the expert_id so the Aggregator can attribute output
        # even if multiple Experts run in one Orchestrator cycle.
        if isinstance(result, dict):
            result.setdefault("expert_id", self.EXPERT_ID)
        return result

    # ── helpers ───────────────────────────────────────────────────

    def _run_sync(
        self,
        emr_text: str,
        ctx: dict,
        *,
        variant: str | None = None,
    ) -> dict:
        """Drive ``invoke_async`` synchronously via ``asyncio.run``.

        Will fail with ``RuntimeError: asyncio.run() cannot be called
        from a running event loop`` if invoked from within an async
        context — that's intentional; the async path should use
        ``invoke_async`` directly.
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            # Check before constructing ``_invoke()``. Passing an already
            # created coroutine to asyncio.run while a loop is active raises
            # and then emits a second, misleading "was never awaited" warning.
            raise RuntimeError(
                "asyncio.run() cannot be called from a running event loop; "
                "use CodingExpert.invoke_async()"
            )

        async def _invoke() -> dict:
            return await self.invoke_async(emr_text, ctx, variant=variant)

        return asyncio.run(_invoke())

    @staticmethod
    def _schema_to_dict(schema: Any) -> dict:
        """Convert a :class:`MedicalCodingOutputSchema` (dataclass) to dict.

        The schema is a plain ``@dataclass`` — it exposes
        ``.to_dict()`` (preferred) but no ``.model_dump()``. We accept
        either for future-proofing if the schema migrates to pydantic.
        """
        to_dict = getattr(schema, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        model_dump = getattr(schema, "model_dump", None)
        if callable(model_dump):
            return model_dump()
        # Fall back to a shallow copy of ``__dict__`` (works for plain
        # dataclasses / pydantic v1 ``.dict()``-less objects). We do not
        # use ``dict(schema)`` because dataclasses are not iterable.
        if hasattr(schema, "__dict__"):
            return dict(schema.__dict__)
        return {}

    @staticmethod
    def _resolve_variant_from_context(ctx: dict | None) -> str | None:
        """Pull an explicit ``variant`` from the invocation's context.

        Context keys consumed:
          - ``variant`` (str) — pass through to ``run_variant``

        Returns ``None`` if not set; ``CodingExpert`` falls back to
        ``default_variant`` in that case.
        """
        if not ctx:
            return None
        v = ctx.get("variant")
        return v if isinstance(v, str) else None


__all__ = [
    "CodingExpert",
]
