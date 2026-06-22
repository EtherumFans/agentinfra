"""T5/T6 — wiring sync↔async adapters (SPEC §10).

Both adapters are exercised against :class:`unittest.mock.AsyncMock`
backends so we don't need a real LLM or MedCodER pipeline to run these
tests.

M1 update: ``MedCodERExpertAdapter`` was deleted and replaced by
:func:`build_expert_invoker_from_hybrid`, which constructs a real
:class:`CodingExpert` (wrapping :class:`MedCodERStrategy`) and wraps it
in a thin dispatcher. The public contract
``Callable[[ExpertInvocation], dict]`` is unchanged — these tests now
exercise that contract end-to-end.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)
from app.icoder.agent_runtime.orchestrator.wiring import (
    LMGatewaySyncAdapter,
    _dispatch_expert_invocation,
    _stub_expert_invoker,
    build_expert_invoker_from_hybrid,
    build_llm_call_from_gateway,
)
from app.icoder.agent_runtime.experts.coding_expert import CodingExpert


# ---------------------------------------------------------------------------
# LMGatewaySyncAdapter
# ---------------------------------------------------------------------------


def _make_gateway_mock(*, is_configured=True) -> MagicMock:
    gw = MagicMock(name="LLMGateway")
    gw.is_configured = is_configured
    gw.generate = AsyncMock(return_value={"content": "{}", "model": "fake"})
    return gw


def test_lm_adapter_builds_two_message_list():
    """Adapter must produce [system, user] messages for every call."""
    gw = _make_gateway_mock()
    adapter = LMGatewaySyncAdapter(gw)

    adapter("you are a planner", "encode this")

    args, kwargs = gw.generate.call_args
    messages = args[0]
    assert messages == [
        {"role": "system", "content": "you are a planner"},
        {"role": "user", "content": "encode this"},
    ]


def test_lm_adapter_passes_provider_kwarg():
    gw = _make_gateway_mock()
    adapter = LMGatewaySyncAdapter(gw, default_provider="deepseek")

    adapter("sys", "user")

    kwargs = gw.generate.call_args.kwargs
    assert kwargs["provider"] == "deepseek"


def test_lm_adapter_default_provider_empty_string():
    """When no default_provider is configured, pass provider=""."""
    gw = _make_gateway_mock()
    adapter = LMGatewaySyncAdapter(gw)

    adapter("sys", "user")

    kwargs = gw.generate.call_args.kwargs
    assert kwargs["provider"] == ""


def test_lm_adapter_returns_gateway_payload_unchanged():
    gw = _make_gateway_mock()
    gw.generate = AsyncMock(
        return_value={"content": "plan-json", "model": "deepseek-v4", "latency_ms": 123}
    )
    adapter = LMGatewaySyncAdapter(gw)

    out = adapter("sys", "user")

    assert out == {"content": "plan-json", "model": "deepseek-v4", "latency_ms": 123}


def test_lm_adapter_empty_system_and_user_allowed():
    """Empty inputs are passed through (Planner's tests do this)."""
    gw = _make_gateway_mock()
    adapter = LMGatewaySyncAdapter(gw)

    adapter("", "")

    messages = gw.generate.call_args.args[0]
    assert messages[0] == {"role": "system", "content": ""}
    assert messages[1] == {"role": "user", "content": ""}


def test_lm_adapter_propagates_gateway_exception():
    """Real gateway errors must bubble — Planner's retry layer handles them."""
    gw = _make_gateway_mock()
    gw.generate = AsyncMock(side_effect=RuntimeError("deepseek timeout"))
    adapter = LMGatewaySyncAdapter(gw)

    with pytest.raises(RuntimeError, match="deepseek timeout"):
        adapter("sys", "user")


def test_lm_adapter_propagates_provider_missing_error():
    """If the underlying generate() raises because the provider is missing,
    the adapter must let it bubble (the Planner handles provider fallback)."""
    gw = _make_gateway_mock()
    gw.generate = AsyncMock(side_effect=KeyError("provider 'ghost' not registered"))
    adapter = LMGatewaySyncAdapter(gw, default_provider="ghost")

    with pytest.raises(KeyError, match="ghost"):
        adapter("sys", "user")


# ---------------------------------------------------------------------------
# Expert invoker dispatcher (M1: CodingExpert via build_expert_invoker_from_hybrid)
# ---------------------------------------------------------------------------


class _StubStrategyResult:
    """Stand-in for the object a MedCodERStrategy returns.

    Production: a ``MedicalCodingOutputSchema`` dataclass with
    ``to_dict()``. Tests can use any object exposing ``to_dict``.
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data


def _make_hybrid_mock(*, return_value=None, mode: str = "medcoder") -> MagicMock:
    """Build a MagicMock that quacks like ``HybridCodingAdapter``.

    M1: HybridCodingAdapter lazily owns a ``_strategy`` only when
    ``mode in MEDCODER_MODES``. We attach a stub strategy directly so
    the wiring factory can wrap it in ``CodingExpert``.
    """
    h = MagicMock(name="HybridCodingAdapter")
    h._mode = mode
    h.infer_async = AsyncMock(return_value=return_value)
    # The factory calls ``getattr(hybrid, "_strategy", None)``; an
    # explicit attribute is cleaner than ``getattr`` default behavior.
    strategy = MagicMock(name="MedCodERStrategy")
    # CodingExpert validates default_variant against strategy.VARIANTS;
    # expose the real tuple so mode-aware variants (e.g. "prompt") work.
    strategy.VARIANTS = ("full", "prompt", "retrieve", "prompt+retrieve")
    strategy.run_variant = AsyncMock(return_value=return_value)
    h._strategy = strategy
    return h


def _make_invocation(expert_id="coding-expert", subtask="编码病历"):
    return ExpertInvocation(
        expert_id=expert_id,
        subtask_input=subtask,
        tool_constraints=["icd_search"],
        context={"trace_id": "t-1"},
    )


def test_invoker_dispatch_coding_expert_routes_to_coding_expert():
    """``build_expert_invoker_from_hybrid`` returns a dispatcher that
    forwards ``coding-expert`` invocations to a real ``CodingExpert``."""
    h = _make_hybrid_mock(
        return_value=_StubStrategyResult({"code": "I50.900"}),
    )
    invoker = build_expert_invoker_from_hybrid(h)
    out = invoker(_make_invocation("coding-expert", "病历文本"))

    h._strategy.run_variant.assert_awaited_once()
    assert out["code"] == "I50.900"
    assert out["expert_id"] == "coding-expert"


def test_invoker_dispatch_coding_expert_passes_emr_to_strategy():
    """The factory feeds ``invocation.subtask_input`` to the strategy
    via CodingExpert.invoke_sync."""
    h = _make_hybrid_mock(return_value=_StubStrategyResult({}))
    invoker = build_expert_invoker_from_hybrid(h)

    invoker(_make_invocation("coding-expert", "胸痛 主诉"))

    # _strategy.run_variant is called by CodingExpert.invoke_async
    args, kwargs = h._strategy.run_variant.call_args
    # Signature: (emr_text, variant, ctx)
    assert args[0] == "胸痛 主诉"
    assert args[2] == {"trace_id": "t-1"}


def test_invoker_dispatch_coding_expert_passes_context_kwarg():
    h = _make_hybrid_mock(return_value=_StubStrategyResult({}))
    invoker = build_expert_invoker_from_hybrid(h)

    inv = _make_invocation("coding-expert")
    invoker(inv)

    # The third positional arg is the ctx dict passed to strategy.
    assert h._strategy.run_variant.call_args.args[2] == {"trace_id": "t-1"}


def test_invoker_dispatch_non_coding_expert_returns_stub():
    """drg-expert / compliance-expert are Phase 1 stubs — the dispatcher
    must NOT route them to CodingExpert."""
    h = _make_hybrid_mock(
        return_value=_StubStrategyResult({"code": "I50.900"}),
    )
    invoker = build_expert_invoker_from_hybrid(h)

    out = invoker(_make_invocation("drg-expert", "分组"))

    assert out["expert_id"] == "drg-expert"
    assert out["echo"] == "分组"
    assert out["phase1_stub"] is True
    # Real MedCodER must NOT be called for non-coding experts
    h._strategy.run_variant.assert_not_called()


def test_invoker_dispatch_translates_generic_exception_to_expert_invocation_error():
    """Generic exceptions raised by the strategy are translated to
    ExpertInvocationError (delegator retry layer depends on this)."""
    h = _make_hybrid_mock()
    h._strategy.run_variant = AsyncMock(side_effect=RuntimeError("pipeline boom"))
    invoker = build_expert_invoker_from_hybrid(h)

    with pytest.raises(ExpertInvocationError, match="RuntimeError"):
        invoker(_make_invocation("coding-expert", "x"))

    # Re-raise preserves __cause__
    try:
        invoker(_make_invocation("coding-expert", "x"))
    except ExpertInvocationError as exc:
        assert isinstance(exc.__cause__, RuntimeError)
        return
    pytest.fail("Expected ExpertInvocationError")


def test_invoker_dispatch_propagates_expert_invocation_error_unchanged():
    """If CodingExpert already raises ExpertInvocationError, the
    dispatcher must NOT re-wrap it."""
    original = ExpertInvocationError("already structured", retryable=False)
    h = _make_hybrid_mock()
    h._strategy.run_variant = AsyncMock(side_effect=original)
    invoker = build_expert_invoker_from_hybrid(h)

    with pytest.raises(ExpertInvocationError, match="already structured") as info:
        invoker(_make_invocation("coding-expert", "x"))
    assert info.value is original


def test_invoker_dispatch_resolves_default_variant_from_hybrid_mode():
    """The factory picks the right default variant based on the hybrid's
    mode string (``medcoder`` → ``full``, ``medcoder_prompt`` → ``prompt``)."""
    h = _make_hybrid_mock(
        return_value=_StubStrategyResult({}), mode="medcoder_prompt",
    )
    invoker = build_expert_invoker_from_hybrid(h)

    invoker(_make_invocation("coding-expert", "x"))

    args = h._strategy.run_variant.call_args.args
    assert args[1] == "prompt"


def test_invoker_dispatch_canonical_alias_uses_full():
    """``mode="medcoder"`` (the canonical alias) maps to ``variant="full"``."""
    h = _make_hybrid_mock(return_value=_StubStrategyResult({}), mode="medcoder")
    invoker = build_expert_invoker_from_hybrid(h)

    invoker(_make_invocation("coding-expert", "x"))

    assert h._strategy.run_variant.call_args.args[1] == "full"


def test_invoker_dispatch_helper_handles_coding_expert_directly():
    """Unit test for the small dispatcher helper used by the factory."""
    strategy = MagicMock(name="Strategy")
    strategy.run_variant = AsyncMock(
        return_value=_StubStrategyResult({"code": "I50.900"}),
    )
    expert = CodingExpert(strategy)

    out = _dispatch_expert_invocation(expert, _make_invocation("coding-expert"))

    assert out["code"] == "I50.900"


def test_invoker_dispatch_helper_returns_stub_when_expert_none():
    """When no CodingExpert is available (e.g. hybrid without strategy),
    the helper falls back to the stub for every expert id."""
    out = _dispatch_expert_invocation(
        None, _make_invocation("coding-expert", "x"),
    )
    assert out["phase1_stub"] is True
    assert out["expert_id"] == "coding-expert"


def test_invoker_dispatch_helper_non_coding_expert_returns_stub():
    """The dispatcher always returns the stub for non-coding experts,
    regardless of whether a CodingExpert is wired up."""
    strategy = MagicMock(name="Strategy")
    strategy.run_variant = AsyncMock(
        return_value=_StubStrategyResult({"code": "I50.900"}),
    )
    expert = CodingExpert(strategy)
    out = _dispatch_expert_invocation(expert, _make_invocation("drg-expert", "x"))

    assert out["phase1_stub"] is True
    strategy.run_variant.assert_not_called()


# ---------------------------------------------------------------------------
# Factory helpers (lifespan wiring)
# ---------------------------------------------------------------------------


def test_build_llm_call_returns_stub_when_gateway_is_none():
    fn = build_llm_call_from_gateway(None)
    out = fn("sys", "user")
    assert out["content"] == "{}"
    assert out["model"] == "stub"


def test_build_llm_call_returns_stub_when_gateway_not_configured():
    gw = _make_gateway_mock(is_configured=False)
    fn = build_llm_call_from_gateway(gw)
    out = fn("sys", "user")
    assert out["model"] == "stub"


def test_build_llm_call_returns_real_adapter_when_configured():
    gw = _make_gateway_mock(is_configured=True)
    fn = build_llm_call_from_gateway(gw, default_provider="deepseek")
    assert isinstance(fn, LMGatewaySyncAdapter)


def test_build_expert_invoker_returns_stub_when_hybrid_is_none():
    fn = build_expert_invoker_from_hybrid(None)
    out = fn(_make_invocation("coding-expert"))
    assert out["phase1_stub"] is True


def test_build_expert_invoker_returns_stub_when_hybrid_has_no_strategy():
    """Legacy / non-medcoder hybrid modes don't build a strategy; the
    factory must still return a callable (the stub)."""
    h = MagicMock(name="HybridCodingAdapter")
    h._mode = "hybrid"
    h._strategy = None
    fn = build_expert_invoker_from_hybrid(h)
    out = fn(_make_invocation("coding-expert"))
    assert out["phase1_stub"] is True


def test_build_expert_invoker_returns_dispatcher_when_hybrid_has_strategy():
    h = _make_hybrid_mock(
        return_value=_StubStrategyResult({"code": "I50.900"}),
    )
    fn = build_expert_invoker_from_hybrid(h)
    out = fn(_make_invocation("coding-expert"))
    # Functional check: the dispatcher routed to the strategy and the
    # returned dict includes the expert_id (set by CodingExpert).
    assert out["code"] == "I50.900"
    assert out["expert_id"] == "coding-expert"


def test_stub_expert_invoker_contract():
    """Smoke test: the stub's return shape is stable (used by many
    downstream tests + the Phase 5 expert stub wiring)."""
    out = _stub_expert_invoker(_make_invocation("any-expert", "any"))
    assert out == {
        "expert_id": "any-expert",
        "echo": "any",
        "phase1_stub": True,
    }
