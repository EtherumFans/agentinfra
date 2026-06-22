"""T5/T6 — wiring sync↔async adapters (SPEC §10).

Both adapters are exercised against :class:`unittest.mock.AsyncMock`
backends so we don't need a real LLM or MedCodER pipeline to run these
tests.
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
    MedCodERExpertAdapter,
    build_expert_invoker_from_hybrid,
    build_llm_call_from_gateway,
)


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
# MedCodERExpertAdapter
# ---------------------------------------------------------------------------


def _make_hybrid_mock(*, return_value) -> MagicMock:
    h = MagicMock(name="HybridCodingAdapter")
    h.infer_async = AsyncMock(return_value=return_value)
    return h


class _FakeMedCodERResult:
    """Stand-in for :class:`MedicalCodingOutputSchema` (a real dataclass).

    Production returns a dataclass with ``to_dict()``. MagicMock auto-creates
    a ``to_dict`` attribute (returns another MagicMock, truthy) which would
    win against ``model_dump`` — that's why we use a real stub here.
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data


def _make_invocation(expert_id="coding-expert", subtask="编码病历"):
    return ExpertInvocation(
        expert_id=expert_id,
        subtask_input=subtask,
        tool_constraints=["icd_search"],
        context={"trace_id": "t-1"},
    )


def test_medcoder_adapter_routes_coding_expert_to_infer_async():
    h = _make_hybrid_mock(
        return_value=_FakeMedCodERResult({"code": "I50.900"}),
    )
    adapter = MedCodERExpertAdapter(h)

    out = adapter(_make_invocation("coding-expert", "病历文本"))

    h.infer_async.assert_awaited_once()
    assert out == {"code": "I50.900"}


def test_medcoder_adapter_passes_user_message_with_subtask_input():
    h = _make_hybrid_mock(return_value=_FakeMedCodERResult({}))
    adapter = MedCodERExpertAdapter(h)

    adapter(_make_invocation("coding-expert", "胸痛 主诉"))

    messages = h.infer_async.call_args.kwargs["messages"]
    assert messages == [{"role": "user", "content": "胸痛 主诉"}]


def test_medcoder_adapter_passes_context_kwarg():
    h = _make_hybrid_mock(return_value=_FakeMedCodERResult({}))
    adapter = MedCodERExpertAdapter(h)

    inv = _make_invocation("coding-expert")
    adapter(inv)

    kwargs = h.infer_async.call_args.kwargs
    assert kwargs["context"] == {"trace_id": "t-1"}


def test_medcoder_adapter_non_coding_expert_returns_stub():
    """drg-expert / compliance-expert are Phase 1 stubs."""
    h = _make_hybrid_mock(return_value=_FakeMedCodERResult({"x": 1}))
    adapter = MedCodERExpertAdapter(h)

    out = adapter(_make_invocation("drg-expert", "分组"))

    assert out["expert_id"] == "drg-expert"
    assert out["echo"] == "分组"
    assert out["phase1_stub"] is True
    # Real MedCodER must NOT be called for non-coding experts
    h.infer_async.assert_not_called()


def test_medcoder_adapter_translates_generic_exception_to_expert_invocation_error():
    h = MagicMock(name="HybridCodingAdapter")
    h.infer_async = AsyncMock(side_effect=RuntimeError("pipeline boom"))
    adapter = MedCodERExpertAdapter(h)

    with pytest.raises(ExpertInvocationError, match="MedCodER infer failed"):
        adapter(_make_invocation("coding-expert", "x"))

    # Re-raise with __cause__
    try:
        adapter(_make_invocation("coding-expert", "x"))
    except ExpertInvocationError as exc:
        assert isinstance(exc.__cause__, RuntimeError)
        return
    pytest.fail("Expected ExpertInvocationError")


def test_medcoder_adapter_propagates_expert_invocation_error_unchanged():
    """If infer_async itself raises ExpertInvocationError, do not re-wrap."""
    h = MagicMock(name="HybridCodingAdapter")
    h.infer_async = AsyncMock(
        side_effect=ExpertInvocationError("already structured")
    )
    adapter = MedCodERExpertAdapter(h)

    with pytest.raises(ExpertInvocationError, match="already structured"):
        adapter(_make_invocation("coding-expert", "x"))


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


def test_build_expert_invoker_returns_real_adapter_when_hybrid_provided():
    h = _make_hybrid_mock(return_value=MagicMock(model_dump=lambda: {}))
    fn = build_expert_invoker_from_hybrid(h)
    assert isinstance(fn, MedCodERExpertAdapter)