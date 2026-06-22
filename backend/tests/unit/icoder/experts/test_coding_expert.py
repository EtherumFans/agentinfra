"""Tests for ``CodingExpert`` — iCoDer Runtime's first real Expert impl.

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 7.4 (M1), the runtime had
``MedCodERExpertAdapter`` — a sync-async bridge wrapping
``HybridCodingAdapter.infer_async``. M1 replaces it with
:class:`CodingExpert`, which delegates to the new
:class:`MedCodERStrategy` and exposes the
``Callable[[ExpertInvocation], dict]`` contract the Delegator expects.

This file exercises:

  - ``invoke_async`` happy path with a stub strategy
  - ``invoke_sync`` (sync bridge via ``asyncio.run``)
  - ``__call__`` alias used by Phase 1 Delegator wiring
  - Generic exceptions translated to ``ExpertInvocationError``
  - ``ExpertInvocationError`` propagates unchanged
  - ``_schema_to_dict`` handles dataclass (``to_dict``),
    pydantic (``model_dump``), and ``__dict__`` fallback
  - ``_resolve_variant_from_context`` reads ``ctx["variant"]``
  - ``is_mock=True`` annotates result with ``is_mock`` flag
  - ``expert_id`` is attached to the result dict
  - Invalid ``default_variant`` falls back to ``"full"``
  - ``subtask_input=None``/empty handled gracefully
  - Empty/None ``context`` handled gracefully
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.icoder.agent_runtime.experts.coding_expert import CodingExpert
from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)


# ── Stubs ───────────────────────────────────────────────────────────


@dataclass
class _StubStrategy:
    """Stand-in for :class:`MedCodERStrategy`.

    Records every ``run_variant`` call so tests can assert wiring, and
    returns whatever schema/exception the test wants.
    """

    VARIANTS = ("full", "prompt", "retrieve", "prompt+retrieve")

    schema: Any = None
    side_effect: BaseException | None = None
    calls: list[tuple[str, str, dict]] = field(default_factory=list)

    async def run_variant(self, emr_text, variant, ctx):
        self.calls.append((emr_text, variant, ctx))
        if self.side_effect is not None:
            raise self.side_effect
        return self.schema


@dataclass
class _DataclassSchema:
    """Has ``to_dict()`` — mirrors the real ``MedicalCodingOutputSchema``."""

    primary: str
    secondary: list

    def to_dict(self) -> dict:
        return {"primary_code": self.primary, "secondary_codes": self.secondary}


@dataclass
class _PydanticSchema:
    """Has ``model_dump()`` (Pydantic v2) — future-proofing path."""

    primary: str

    def model_dump(self) -> dict:
        return {"primary_code": self.primary}


@dataclass
class _PlainSchema:
    """No ``to_dict``/``model_dump`` — exercises the ``__dict__`` fallback."""

    primary: str
    secondary: list = field(default_factory=list)


def _invocation(
    expert_id: str = "coding-expert",
    subtask_input: str = "胸痛 主诉",
    context: dict | None = None,
) -> ExpertInvocation:
    return ExpertInvocation(
        expert_id=expert_id,
        subtask_input=subtask_input,
        tool_constraints=["icd_search"],
        context=context if context is not None else {"trace_id": "t-1"},
        attempt=1,
    )


# ── 1. invoke_async ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_async_happy_path_delegates_to_strategy():
    """The async path forwards emr_text + ctx + variant to ``run_variant``."""
    schema = _DataclassSchema(primary="I50.900", secondary=["I10.x05"])
    strategy = _StubStrategy(schema=schema)
    expert = CodingExpert(strategy)

    result = await expert.invoke_async("emr-xyz", {"k": "v"}, variant="full")

    assert strategy.calls == [("emr-xyz", "full", {"k": "v"})]
    assert result["primary_code"] == "I50.900"
    assert result["secondary_codes"] == ["I10.x05"]
    assert result["expert_id"] == "coding-expert"


@pytest.mark.asyncio
async def test_invoke_async_uses_default_variant_when_not_pinned():
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy, default_variant="prompt")

    await expert.invoke_async("emr")

    assert strategy.calls == [("emr", "prompt", {})]


@pytest.mark.asyncio
async def test_invoke_async_explicit_variant_overrides_default():
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy, default_variant="full")

    await expert.invoke_async("emr", variant="retrieve")

    assert strategy.calls[0][1] == "retrieve"


@pytest.mark.asyncio
async def test_invoke_async_none_ctx_defaults_to_empty_dict():
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy)

    await expert.invoke_async("emr", ctx=None)

    assert strategy.calls[0][2] == {}


@pytest.mark.asyncio
async def test_invoke_async_is_mock_annotates_result():
    """``is_mock=True`` stamps ``result["is_mock"] = True`` for the
    recorder / observability layer."""
    schema = _DataclassSchema(primary="I50.900", secondary=[])
    strategy = _StubStrategy(schema=schema)
    expert = CodingExpert(strategy, is_mock=True)

    result = await expert.invoke_async("emr")

    assert result.get("is_mock") is True
    assert result.get("expert_id") == "coding-expert"


@pytest.mark.asyncio
async def test_invoke_async_translates_runtime_error_to_expert_invocation_error():
    """Generic exceptions raised by the strategy are translated to
    :class:`ExpertInvocationError` so the Delegator's retry/backoff
    layer can handle them uniformly."""
    strategy = _StubStrategy(
        schema=None,
        side_effect=RuntimeError("deepseek 502"),
    )
    expert = CodingExpert(strategy)

    with pytest.raises(ExpertInvocationError, match="RuntimeError"):
        await expert.invoke_async("emr")

    try:
        await expert.invoke_async("emr")
    except ExpertInvocationError as exc:
        # Underlying cause preserved for diagnostics.
        assert isinstance(exc.__cause__, RuntimeError)
        # Delegator uses these fields to drive retry behaviour.
        assert exc.stage == "delegating"
        assert exc.retryable is True
        return
    pytest.fail("Expected ExpertInvocationError")


@pytest.mark.asyncio
async def test_invoke_async_propagates_expert_invocation_error_unchanged():
    """If the strategy already raises :class:`ExpertInvocationError`,
    CodingExpert must NOT re-wrap it (Delegator would re-classify)."""
    original = ExpertInvocationError("structured failure", retryable=False)
    strategy = _StubStrategy(side_effect=original)
    expert = CodingExpert(strategy)

    with pytest.raises(ExpertInvocationError, match="structured failure") as info:
        await expert.invoke_async("emr")
    # Same exception instance — not wrapped.
    assert info.value is original


# ── 2. invoke_sync / __call__ ───────────────────────────────────────


def test_invoke_sync_drives_async_path_via_asyncio_run():
    """Phase 1 Delegator is sync — ``invoke_sync`` wraps ``invoke_async``
    in ``asyncio.run``. Behaviour must match the async path."""
    schema = _DataclassSchema(primary="I50.900", secondary=["E11.900"])
    strategy = _StubStrategy(schema=schema)
    expert = CodingExpert(strategy)

    result = expert.invoke_sync(_invocation())

    assert strategy.calls == [("胸痛 主诉", "full", {"trace_id": "t-1"})]
    assert result["primary_code"] == "I50.900"
    assert result["secondary_codes"] == ["E11.900"]
    assert result["expert_id"] == "coding-expert"


def test_invoke_sync_falls_back_to_empty_string_when_subtask_input_is_none():
    """``subtask_input=None`` (rare but legal) must not crash."""
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy)
    inv = ExpertInvocation(
        expert_id="coding-expert",
        subtask_input=None,  # type: ignore[arg-type]
        context={"trace_id": "t-1"},
    )

    expert.invoke_sync(inv)

    assert strategy.calls[0][0] == ""


def test_invoke_sync_falls_back_to_empty_context():
    """``context=None`` (default in dataclass) must be normalised to ``{}``."""
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy)
    inv = ExpertInvocation(
        expert_id="coding-expert",
        subtask_input="病历文本",
        context=None,  # type: ignore[arg-type]
    )

    expert.invoke_sync(inv)

    assert strategy.calls[0][2] == {}


def test_invoke_sync_resolves_variant_from_invocation_context():
    """If the Planner pins ``context["variant"] = "prompt"``, the Expert
    must propagate it to the strategy."""
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy, default_variant="full")

    expert.invoke_sync(_invocation(context={"variant": "prompt", "trace_id": "t"}))

    assert strategy.calls[0][1] == "prompt"


def test_call_alias_matches_invoke_sync_contract():
    """``CodingExpert(invocation) == expert.invoke_sync(invocation)``.

    The ``__call__`` alias is what keeps the
    ``Callable[[ExpertInvocation], dict]`` type contract working for the
    Phase 1 Delegator, which just calls the invoker as a function.
    """
    schema = _DataclassSchema(primary="I50.900", secondary=[])
    strategy = _StubStrategy(schema=schema)
    expert = CodingExpert(strategy)

    via_call = expert(_invocation())
    via_method = expert.invoke_sync(_invocation())

    assert via_call == via_method


def test_invoke_sync_translates_error_to_expert_invocation_error():
    strategy = _StubStrategy(side_effect=ValueError("parse failed"))
    expert = CodingExpert(strategy)

    with pytest.raises(ExpertInvocationError, match="ValueError"):
        expert.invoke_sync(_invocation())


def test_invoke_sync_cannot_run_inside_event_loop():
    """``asyncio.run`` raises ``RuntimeError`` if called from a running
    loop — that's intentional (Phase 2 will use ``invoke_async`` directly)."""
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    expert = CodingExpert(strategy)

    async def _inner():
        # We're inside an event loop → invoke_sync must NOT be used.
        with pytest.raises(RuntimeError, match="asyncio.run"):
            expert.invoke_sync(_invocation())

    asyncio.run(_inner())


# ── 3. _schema_to_dict (static helper) ──────────────────────────────


def test_schema_to_dict_prefers_to_dict_for_dataclass():
    schema = _DataclassSchema(primary="I50.900", secondary=[])
    assert CodingExpert._schema_to_dict(schema) == {
        "primary_code": "I50.900",
        "secondary_codes": [],
    }


def test_schema_to_dict_falls_back_to_model_dump_for_pydantic():
    schema = _PydanticSchema(primary="I50.900")
    assert CodingExpert._schema_to_dict(schema) == {"primary_code": "I50.900"}


def test_schema_to_dict_falls_back_to_dict_for_plain_object():
    schema = _PlainSchema(primary="I50.900", secondary=["E11.900"])
    assert CodingExpert._schema_to_dict(schema) == {
        "primary": "I50.900",
        "secondary": ["E11.900"],
    }


# ── 4. _resolve_variant_from_context ───────────────────────────────


def test_resolve_variant_returns_string_when_present():
    assert (
        CodingExpert._resolve_variant_from_context({"variant": "retrieve"})
        == "retrieve"
    )


def test_resolve_variant_returns_none_when_absent():
    assert CodingExpert._resolve_variant_from_context({"other": 1}) is None


def test_resolve_variant_handles_none_and_empty():
    assert CodingExpert._resolve_variant_from_context(None) is None
    assert CodingExpert._resolve_variant_from_context({}) is None


def test_resolve_variant_ignores_non_string_values():
    assert CodingExpert._resolve_variant_from_context({"variant": 42}) is None
    assert CodingExpert._resolve_variant_from_context({"variant": None}) is None


# ── 5. Construction / default_variant validation ────────────────────


def test_invalid_default_variant_falls_back_to_full(caplog):
    """If the strategy exposes a different ``VARIANTS`` tuple, the
    expert logs a warning and falls back to ``'full'``."""
    strategy = _StubStrategy(schema=_DataclassSchema(primary="X", secondary=[]))
    # Override VARIANTS so "weird" is not in it.
    strategy.VARIANTS = ("full", "prompt")  # type: ignore[misc]

    with caplog.at_level("WARNING"):
        expert = CodingExpert(strategy, default_variant="weird")

    assert expert._default_variant == "full"
    assert any(
        "default_variant 'weird' not in strategy.VARIANTS" in r.message
        for r in caplog.records
    )


def test_expert_id_and_name_constants_are_stable():
    """The Delegator / Agent Card use these as a routing key — do not
    rename without a coordinated migration."""
    assert CodingExpert.EXPERT_ID == "coding-expert"
    assert "Coding Expert" in CodingExpert.EXPERT_NAME
