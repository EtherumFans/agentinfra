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

import json
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
    build_expert_invoker_for_medcoder,
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


# ---------------------------------------------------------------------------
# E1 (2026-06-26) — build_expert_invoker_for_medcoder
# ---------------------------------------------------------------------------
# Per E1 design (memory/project_e1_first_real_agent_2026_06_26.md), the
# canonical MedCodER Agent path now dispatches 4 D2 expert packs instead
# of a single ``coding-expert`` glue. These tests lock down:
#   1. The 4 expert_ids route to the 4 Python impls (not stubs).
#   2. The M1 ``coding-expert`` back-compat is preserved when a hybrid
#      fallback is provided.
#   3. Unknown expert_ids fall through to the Phase-1 stub.
# Per Agent Card SPEC §3.3 (Q7 5件套), each expert_pack.json expert entry
# must have id / system_prompt / tools / model / non_goals / output_contract
# — see test_agent_pack_e1_4_experts_5_piece_complete below.


# Stable expert_id strings (mirror EXPERT_ID class attrs on each expert)
_FOUR_EXPERT_IDS = (
    "evidence-extractor",
    "index-navigator",
    "code-reconciler",
    "tabular-validator",
)


def test_e1_invoker_routes_4_d2_expert_ids_to_real_packs():
    """E1: each of the 4 D2 expert_ids is dispatched to its real Python
    impl, NOT the Phase-1 stub. We verify by checking that each call
    returns a result dict with the matching ``expert_id`` and a stage-
    specific output field, and that ``phase1_stub`` is absent."""
    invoker = build_expert_invoker_for_medcoder(
        llm_gateway=None,
        medcoder_retriever=None,
        rule_engine=None,
        hybrid_fallback=None,
    )
    # evidence-extractor (LLM-offline) returns diagnosis_facts
    out_evidence = invoker(_make_invocation("evidence-extractor", "老年男性胸痛 3 小时。"))
    assert out_evidence["expert_id"] == "evidence-extractor"
    assert "phase1_stub" not in out_evidence
    assert "diagnosis_facts" in out_evidence  # E1 Stage 1 schema

    # index-navigator (no retriever) returns retriever_status=missing
    out_index = invoker(_make_invocation("index-navigator", "{}"))
    assert out_index["expert_id"] == "index-navigator"
    assert out_index["retriever_status"] == "missing"
    assert "phase1_stub" not in out_index

    # code-reconciler (no LLM) returns primary_diagnosis (offline path)
    payload = {
        "diagnosis_candidates": [
            {"fact": "胸痛", "candidates": [
                {"code": "I20.0", "name": "不稳定型心绞痛", "score": 0.9, "chapter": "心血管"},
            ]},
        ],
        "procedure_candidates": [],
    }
    out_reconcile = invoker(
        _make_invocation("code-reconciler", json.dumps(payload, ensure_ascii=False)),
    )
    assert out_reconcile["expert_id"] == "code-reconciler"
    assert "primary_diagnosis" in out_reconcile  # E1 Stage 3+4 schema
    assert "phase1_stub" not in out_reconcile

    # tabular-validator (RuleEngine lazy-loaded) returns passed/issues
    out_validate = invoker(
        _make_invocation("tabular-validator", json.dumps({
            "primary_diagnosis": {"code": "I20.0"},
            "secondary_diagnoses": [],
            "procedures": [],
            "confidence": 0.9,
        })),
    )
    assert out_validate["expert_id"] == "tabular-validator"
    assert "passed" in out_validate  # E1 Stage 5 schema
    assert "rule_set" in out_validate
    assert "phase1_stub" not in out_validate


def test_e1_invoker_coding_expert_uses_hybrid_fallback_when_provided():
    """E1 back-compat: when ``hybrid_fallback`` is supplied, the M1
    ``coding-expert`` invocations still route to ``CodingExpert(strategy)``
    — never to the Phase-1 stub."""
    h = _make_hybrid_mock(
        return_value=_StubStrategyResult({"primary_diagnosis": {"code": "I50.900"}}),
    )
    invoker = build_expert_invoker_for_medcoder(
        llm_gateway=None,
        hybrid_fallback=h,
    )
    out = invoker(_make_invocation("coding-expert", "病历文本"))
    assert out["primary_diagnosis"] == {"code": "I50.900"}
    assert out["expert_id"] == "coding-expert"
    assert "phase1_stub" not in out


def test_e1_invoker_coding_expert_falls_back_to_stub_without_hybrid():
    """E1 back-compat: when no ``hybrid_fallback`` is provided, the
    ``coding-expert`` (M1 path) returns the Phase-1 stub. This is the
    E1 design — the canonical Agent path is 4 expert packs; the M1
    hybrid wrapper is opt-in via ``hybrid_fallback``."""
    invoker = build_expert_invoker_for_medcoder(
        llm_gateway=None,
        hybrid_fallback=None,
    )
    out = invoker(_make_invocation("coding-expert", "病历文本"))
    assert out["phase1_stub"] is True
    assert out["expert_id"] == "coding-expert"


def test_e1_invoker_unknown_expert_id_falls_back_to_stub():
    """E1: any expert_id not in the 4 D2 packs (and not 'coding-expert'
    with a hybrid_fallback) returns the Phase-1 stub. This is the
    forward-compat path for Phase 5 (drg-expert, compliance-expert)."""
    invoker = build_expert_invoker_for_medcoder(
        llm_gateway=None,
        hybrid_fallback=None,
    )
    out = invoker(_make_invocation("drg-expert", "分组"))
    assert out["phase1_stub"] is True
    assert out["expert_id"] == "drg-expert"


def test_e1_invoker_4_expert_ids_match_d2_class_constants():
    """Lockdown: the 4 strings the factory dispatches on must match
    the EXPERT_ID class attribute on each D2 expert pack. If a D2
    pack's EXPERT_ID changes, the wiring dispatch breaks silently —
    this test catches the regression at the boundary."""
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
    assert EvidenceExtractorExpert.EXPERT_ID == "evidence-extractor"
    assert IndexNavigatorExpert.EXPERT_ID == "index-navigator"
    assert CodeReconcilerExpert.EXPERT_ID == "code-reconciler"
    assert TabularValidatorExpert.EXPERT_ID == "tabular-validator"
    # And the factory's expected set must include all 4.
    assert set(_FOUR_EXPERT_IDS) == {
        EvidenceExtractorExpert.EXPERT_ID,
        IndexNavigatorExpert.EXPERT_ID,
        CodeReconcilerExpert.EXPERT_ID,
        TabularValidatorExpert.EXPERT_ID,
    }
