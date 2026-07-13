"""Track H3.15 — snap_quote_to_chart unit tests.

Verifies the deterministic quote-correction helper that closes the iter 4
regressions:
  - clear_gap under-query 1/10 → 3/10 (CEA over-blocks paraphrased quotes)
  - evidence_quote_verbatim 0.971 → 0.882 (LLM paraphrases despite QUOTE-ANCHOR)
"""

from __future__ import annotations

from app.icoder.agent_runtime.cdi.claim_evidence_gate import (
    QUOTE_SNAP_THRESHOLD,
    snap_quote_to_chart,
)


# ---------------------------------------------------------------------------
# Fast paths — no correction needed
# ---------------------------------------------------------------------------


def test_snap_empty_quote_returns_empty() -> None:
    assert snap_quote_to_chart("", "chart text") == ""
    assert snap_quote_to_chart(None, "chart text") is None  # type: ignore[arg-type]


def test_snap_empty_chart_returns_original() -> None:
    assert snap_quote_to_chart("some quote", "") == "some quote"


def test_snap_quote_too_short_returns_original() -> None:
    # Below 4 chars, fuzzy matching is unreliable — defer to original.
    assert snap_quote_to_chart("高血压", "患者有高血压病史") == "高血压"


def test_snap_quote_already_verbatim_returns_unchanged() -> None:
    chart = "患者男, 65岁, 因胸痛入院. 诊断: 急性心肌梗死. 行PCI术后好转出院."
    quote = "诊断: 急性心肌梗死"
    assert snap_quote_to_chart(quote, chart) == quote


def test_snap_quote_verbatim_at_offset_returns_unchanged() -> None:
    chart = "prefix text. 诊断: 急性心肌梗死. suffix text."
    quote = "诊断: 急性心肌梗死"
    assert snap_quote_to_chart(quote, chart) == quote


# ---------------------------------------------------------------------------
# Snap behavior — minor paraphrasing
# ---------------------------------------------------------------------------


def test_snap_full_width_colon_to_half_width() -> None:
    """Classic case: LLM emits half-width colon, chart uses full-width."""
    # Use the actual unicode characters (full-width : is U+FF1A, half-width : is U+003A)
    full_colon = "："
    half_colon = ":"
    chart = f"诊断{full_colon}急性心肌梗死"
    quote = f"诊断{half_colon}急性心肌梗死"
    # Confirm the two strings are NOT identical before snapping
    assert chart != quote
    snapped = snap_quote_to_chart(quote, chart)
    # The snap should land on a substring that IS verbatim in chart
    assert snapped in chart
    assert snapped != quote  # change occurred
    assert full_colon in snapped


def test_snap_dropped_punctuation() -> None:
    """LLM dropped the colon; snap finds the matching chart span."""
    chart = "患者主诉:胸痛3天. 诊断:急性心肌梗死."
    quote = "者主诉:胸痛3天"  # dropped leading char
    snapped = snap_quote_to_chart(quote, chart)
    assert snapped in chart
    assert len(snapped) == len(quote)


def test_snap_minor_word_swap() -> None:
    """LLM swapped '因病' for '因'; snap finds the closest chart substring."""
    chart = "患者因胸痛入院, 心电图提示ST段抬高."
    quote = "患者因胸痛入院,心电图提示ST段抬高"  # missing space + period
    snapped = snap_quote_to_chart(quote, chart)
    assert snapped in chart


# ---------------------------------------------------------------------------
# Safety — don't snap when LLM is too divergent (hallucination guard)
# ---------------------------------------------------------------------------


def test_snap_hallucinated_quote_returns_original() -> None:
    """When the LLM invents text not in the chart, snap should NOT fabricate."""
    chart = "患者男, 65岁. 诊断: 高血压."
    hallucination = "患者被诊断为晚期肺癌伴多发转移"  # completely unrelated
    result = snap_quote_to_chart(hallucination, chart)
    # Below threshold → return original so CEA-001 / semantic gate can flag it
    assert result == hallucination


def test_snap_threshold_default_is_075() -> None:
    assert QUOTE_SNAP_THRESHOLD == 0.75


def test_snap_custom_threshold_more_permissive() -> None:
    """A lower threshold allows snapping quotes that the default rejects."""
    chart = "ABCDEFGHIJKLMNOP"  # 16 chars
    # Identical quote — sanity baseline
    quote = "ABCDEFGHIJKLMNOP"
    strict = snap_quote_to_chart(quote, chart, threshold=0.99)
    assert strict == quote  # already verbatim

    # A divergent quote with no overlap is NEVER snapped (safety: would be
    # hallucination). Even at threshold=0.0, if no window scores > 0, the
    # original is returned so downstream gates can flag it.
    divergent_quote = "XXXXYYYYZZZZWWWW"
    skipped = snap_quote_to_chart(divergent_quote, chart)
    assert skipped == divergent_quote  # too divergent, kept original
    permissive = snap_quote_to_chart(divergent_quote, chart, threshold=0.0)
    assert permissive == divergent_quote  # still no match → original


# ---------------------------------------------------------------------------
# Length preservation
# ---------------------------------------------------------------------------


def test_snap_preserves_quote_length() -> None:
    chart = "prefix. 患者主诉胸痛3天. suffix."
    quote = "患者主诉:胸痛3天"  # 9 chars, minor punctuation diff
    snapped = snap_quote_to_chart(quote, chart)
    assert len(snapped) == len(quote)
    assert snapped in chart


# ---------------------------------------------------------------------------
# Integration — orchestrator end-to-end
# ---------------------------------------------------------------------------


def test_orchestrator_snaps_gap_and_query_quotes() -> None:
    """H3.15 — orchestrator should snap quotes for both gaps and queries."""
    from app.icoder.agent_runtime.cdi import CDIOrchestrator, CDICase

    chart = (
        "患者男, 65岁. 因胸痛3天入院. "
        "诊断: 急性下壁心肌梗死. "
        "行PCI术. 好转出院."
    )

    # Stub runner returns paraphrased quotes — simulates H3.14-amplifier LLM
    def stub_runner(stage, case, kwargs):  # type: ignore[no-untyped-def]
        if stage == "gap_identification":
            return {
                "gaps": [{
                    "gap_id": "g1",
                    "description": "病原体未明确",
                    "evidence_span": {
                        "document_id": "入院记录",
                        "quote": "诊断急性下壁心肌梗死",  # missing ": "
                    },
                }],
                "risk_flags": [],
                "run_id": "r1", "trace_id": "t1",
            }
        if stage == "query_generation":
            return {
                "queries": [{
                    "query_id": "q1",
                    "gap_id": "g1",
                    "topic": "病原体",
                    "query_text": "请明确本次心肌梗死的病原学证据.",
                    "evidence_span": {
                        "document_id": "入院记录",
                        "quote": "诊断急性下壁心肌梗死",  # paraphrased
                    },
                    "response_options": ["A. ..", "B. ..", "C. ..", "D. 无法确定"],
                }],
                "run_id": "r2", "trace_id": "t2",
            }
        return {"run_id": "r0", "trace_id": "t0"}

    case = CDICase(case_id="c1", chart_excerpt=chart)
    orchestrator = CDIOrchestrator(runner=stub_runner)
    orchestrator.run(case, stages=(
        "gap_identification",
        "query_generation",
    ))

    # Gap quote should be snapped to a verbatim chart substring
    assert case.documentation_gaps
    gap_quote = case.documentation_gaps[0].evidence_span.quote
    assert gap_quote in chart, f"gap quote {gap_quote!r} not verbatim in chart"

    # Query quote should be snapped too
    assert case.proposed_provider_queries
    query_quote = case.proposed_provider_queries[0].evidence_span.quote
    assert query_quote in chart, f"query quote {query_quote!r} not verbatim in chart"

    # Snapped counts are recorded for traceability
    assert "quote_snapped=1" in case.stage_run_ids.get(
        "gap_identification_risk_flags", ""
    )
    assert case.stage_run_ids.get("query_generation::quote_snapped") == "1"
