"""Tests for HybridCodingAdapter medcoder mode dispatch (M1).

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 7.4, M1 expands the
``HybridCodingAdapter`` mode vocabulary from a single ``"medcoder"``
value to 5 values that map to the 4 ``MedCodERStrategy`` ablation
variants:

  - ``"medcoder"``               → ``variant="full"`` (canonical alias)
  - ``"medcoder_full"``          → ``variant="full"``
  - ``"medcoder_prompt"``        → ``variant="prompt"``
  - ``"medcoder_retrieve"``      → ``variant="retrieve"``
  - ``"medcoder_prompt+retrieve"`` → ``variant="prompt+retrieve"``

These tests verify the mode → variant dispatch and assert end-to-end
behaviour (schema shape, extracted_diagnoses population, mode
discriminator) without spinning up the real BGE-M3 / FAISS index.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from icoder_runtime.providers.medical_coding.hybrid_adapter import (  # noqa: E402
    HybridCodingAdapter,
    MEDCODER_MODES,
    _mode_to_variant,
)
from official_agents.medical_coding.schema import (  # noqa: E402
    CandidateCode,
    ExtractedDiagnosis,
    MedicalCodingOutputSchema,
)


# ── Stubs ───────────────────────────────────────────────────────────


class _StubGateway:
    """Stub LLM gateway that returns a pre-canned response per call."""

    def __init__(self, response: str | list[str] = ""):
        if isinstance(response, str):
            self._responses = [response]
        else:
            self._responses = list(response)
        self.calls: list[list[dict]] = []

    async def generate(self, messages, provider="default"):
        self.calls.append(list(messages))
        if not self._responses:
            return {"content": "{}"}
        if len(self._responses) == 1:
            return {"content": self._responses[0]}
        return {"content": self._responses.pop(0)}


class _StubRetriever:
    """Stub retriever returning a fixed list per disease (or empty)."""

    def __init__(self, results: dict | None = None):
        self.results = results or {}
        self.queries: list[str] = []

    async def retrieve_async(self, disease: str, top_k: int = 20, **kwargs):
        self.queries.append(disease)
        return list(self.results.get(disease, []))


def _stub_extraction_response() -> str:
    return '[{"disease_text": "心力衰竭", "supporting_evidence": "胸闷气短", "llm_initial_code": "I50.900"}]'


def _stub_rerank_response() -> str:
    return '{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", "final_confidence": 0.95, "rationale": "证据明确"}]}'


def _stub_candidates() -> list[CandidateCode]:
    return [
        CandidateCode(code="I50.100", name="左心衰竭", score=0.7, source="retrieve"),
        CandidateCode(code="I50.000", name="充血性心力衰竭", score=0.6, source="retrieve"),
    ]


# ── 1. Mode → variant dispatcher (pure function) ────────────────────


@pytest.mark.parametrize("mode,expected", [
    ("medcoder", "full"),
    ("medcoder_full", "full"),
    ("medcoder_prompt", "prompt"),
    ("medcoder_retrieve", "retrieve"),
    ("medcoder_prompt+retrieve", "prompt+retrieve"),
])
def test_mode_to_variant_dispatch(mode: str, expected: str) -> None:
    assert _mode_to_variant(mode) == expected


def test_mode_to_variant_unknown_mode_falls_back_to_full(caplog) -> None:
    """Defensive: any value that doesn't match a known branch falls
    through to ``'full'`` and logs a warning."""
    with caplog.at_level("WARNING"):
        # Use a value that doesn't start with ``medcoder_`` so it bypasses
        # both the explicit aliases and the prefix-strip branch.
        assert _mode_to_variant("totally_unknown") == "full"
    assert any(
        "unknown medcoder mode" in r.message
        for r in caplog.records
    )


def test_medcoder_modes_constant_lists_all_supported_values() -> None:
    """The constant is the single source of truth for supported medcoder
    modes. If you add a mode here, add a dispatch case to ``_mode_to_variant``."""
    assert set(MEDCODER_MODES) == {
        "medcoder",
        "medcoder_full",
        "medcoder_prompt",
        "medcoder_retrieve",
        "medcoder_prompt+retrieve",
        "code_like_humans",
    }


# ── 2. Constructor wiring ───────────────────────────────────────────


@pytest.mark.parametrize("mode", [
    "medcoder",
    "medcoder_full",
    "medcoder_prompt",
    "medcoder_retrieve",
    "medcoder_prompt+retrieve",
    "code_like_humans",
])
def test_medcoder_mode_constructs_strategy(mode: str) -> None:
    """Any medcoder mode causes the adapter to lazily own a
    :class:`MedCodERStrategy`."""
    adapter = HybridCodingAdapter(gateway=_StubGateway(), mode=mode)
    assert adapter._strategy is not None
    assert adapter.current_mode == mode


def test_legacy_mode_does_not_construct_strategy() -> None:
    """Legacy modes must not pay the MedCodERStrategy construction cost."""
    for mode in ("deepseek", "prompt_llm", "hybrid", "no_repair"):
        adapter = HybridCodingAdapter(mode=mode)
        assert adapter._strategy is None, f"{mode} unexpectedly built a strategy"


def test_medcoder_modes_have_repair_disabled() -> None:
    """Medcoder modes own their own retry strategy (in the strategy) so
    the legacy repair loop in HybridCodingAdapter must stay OFF for them."""
    for mode in MEDCODER_MODES:
        adapter = HybridCodingAdapter(gateway=_StubGateway(), mode=mode)
        assert adapter._repair_enabled is False, f"{mode} has repair loop on"


def test_legacy_modes_have_repair_enabled_by_default() -> None:
    for mode in ("deepseek", "hybrid"):
        adapter = HybridCodingAdapter(mode=mode)
        assert adapter._repair_enabled is True


def test_no_repair_mode_disables_repair() -> None:
    adapter = HybridCodingAdapter(mode="no_repair")
    assert adapter._repair_enabled is False


# ── 3. End-to-end mode dispatch (stubbed strategy) ──────────────────


def _make_adapter_with_spy(mode: str) -> tuple[HybridCodingAdapter, MagicMock]:
    """Construct an adapter and monkey-patch its strategy's ``run_variant``
    to a spy that returns a controlled schema."""
    adapter = HybridCodingAdapter(gateway=_StubGateway(), mode=mode)
    assert adapter._strategy is not None

    spy = MagicMock()

    async def _fake_run_variant(emr_or_messages, variant, ctx=None):
        spy(emr_or_messages, variant, ctx)
        out = MedicalCodingOutputSchema(
            mode="medcoder",
            provider="medcoder",
            confidence=0.9,
            notes=f"spy:{variant}",
            extracted_diagnoses=[
                ExtractedDiagnosis(
                    disease_text="spy",
                    llm_initial_code="X",
                    final_confidence=0.9,
                    final_top_k=[
                        CandidateCode(code="X", name="x", score=0.9, source="rerank"),
                    ],
                ),
            ],
        )
        return out

    adapter._strategy.run_variant = _fake_run_variant
    return adapter, spy


@pytest.mark.parametrize("mode,expected_variant", [
    ("medcoder", "full"),
    ("medcoder_full", "full"),
    ("medcoder_prompt", "prompt"),
    ("medcoder_retrieve", "retrieve"),
    ("medcoder_prompt+retrieve", "prompt+retrieve"),
])
def test_infer_async_dispatches_mode_to_correct_variant(
    mode: str, expected_variant: str,
) -> None:
    adapter, spy = _make_adapter_with_spy(mode)
    messages = [{"role": "user", "content": "病历文本"}]

    out = asyncio.run(adapter.infer_async(messages))

    assert spy.call_count == 1
    args = spy.call_args.args
    # Signature: (emr_or_messages, variant, ctx)
    assert args[0] == messages
    assert args[1] == expected_variant
    # Schema-level invariants
    assert isinstance(out, MedicalCodingOutputSchema)
    assert out.mode == "medcoder"
    assert out.provider == "medcoder"
    assert len(out.extracted_diagnoses) == 1
    assert out.notes == f"spy:{expected_variant}"


def test_legacy_mode_bypasses_strategy() -> None:
    """Non-medcoder modes must not route through the strategy — they
    use the legacy DeepSeek + RuleEngine pipeline."""
    adapter = HybridCodingAdapter(mode="hybrid")
    # No strategy was built → no dispatch should happen.
    assert adapter._strategy is None


# ── 4. Full end-to-end through real MedCodERStrategy ─────────────────


class TestFullVariantThroughStrategy:
    """Run the real ``MedCodERStrategy`` through ``HybridCodingAdapter`` to
    verify the full pipeline still produces the expected schema (mode +
    extracted_diagnoses + provider). Mirrors ``test_hybrid_medcoder`` but
    exercises the 4 explicit ``medcoder_*`` mode names."""

    def test_medcoder_full_happy_path(self):
        """End-to-end: 1 disease, 2 LLM calls (extraction + rerank)."""
        gw = _StubGateway([_stub_extraction_response(), _stub_rerank_response()])
        retriever = _StubRetriever({"心力衰竭": _stub_candidates()})
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder_full", retriever=retriever)

        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": "患者胸闷气短"}],
        ))

        assert isinstance(out, MedicalCodingOutputSchema)
        assert out.mode == "medcoder"
        assert out.provider == "medcoder"
        assert len(out.extracted_diagnoses) == 1
        edx = out.extracted_diagnoses[0]
        assert edx.disease_text == "心力衰竭"
        assert edx.llm_initial_code == "I50.900"
        # LLM calls: 1 extraction + 1 rerank = 2
        assert len(gw.calls) == 2

    def test_medcoder_prompt_skips_retrieval(self):
        """Prompt-only variant: no retriever calls."""
        gw = _StubGateway([_stub_extraction_response()])
        retriever = _StubRetriever({"心力衰竭": _stub_candidates()})
        adapter = HybridCodingAdapter(gateway=gw, mode="medcoder_prompt", retriever=retriever)

        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": "患者胸闷气短"}],
        ))

        assert out.mode == "medcoder"
        # No retrieval happened
        assert retriever.queries == []
        # LLM calls: 1 extraction (no rerank) = 1
        assert len(gw.calls) == 1

    def test_medcoder_retrieve_skips_extraction(self):
        """Retrieve-only variant: no extraction LLM call."""
        # Provide some retriever results so something comes back
        retriever = _StubRetriever({
            "患者": [_stub_candidates()[0]],  # sentence-split will surface "患者"
        })
        adapter = HybridCodingAdapter(
            gateway=_StubGateway(), mode="medcoder_retrieve", retriever=retriever,
        )

        out = asyncio.run(adapter.infer_async(
            [{"role": "user", "content": "患者胸闷气短"}],
        ))

        assert out.mode == "medcoder"
        # Retrieval was attempted at least once
        assert len(retriever.queries) >= 1

    def test_medcoder_canonical_alias_matches_explicit_full(self):
        """``mode="medcoder"`` and ``mode="medcoder_full"`` must produce
        identical run_variant dispatch."""
        spy_calls_full: list[str] = []

        async def _spy_full(emr_or_messages, variant, ctx=None):
            spy_calls_full.append(variant)
            return MedicalCodingOutputSchema(mode="medcoder", provider="medcoder")

        a1 = HybridCodingAdapter(gateway=_StubGateway(), mode="medcoder")
        a1._strategy.run_variant = _spy_full
        asyncio.run(a1.infer_async([{"role": "user", "content": "x"}]))

        spy_calls_explicit: list[str] = []

        async def _spy_explicit(emr_or_messages, variant, ctx=None):
            spy_calls_explicit.append(variant)
            return MedicalCodingOutputSchema(mode="medcoder", provider="medcoder")

        a2 = HybridCodingAdapter(gateway=_StubGateway(), mode="medcoder_full")
        a2._strategy.run_variant = _spy_explicit
        asyncio.run(a2.infer_async([{"role": "user", "content": "x"}]))

        assert spy_calls_full == spy_calls_explicit == ["full"]
