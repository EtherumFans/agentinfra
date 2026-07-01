"""Phase 2 cycle 22 — markdown evidence parser regression tests.

The ``RuntimeRunResult.from_runner_output`` helper now populates
``metadata.evidences`` (and hoists it to the top-level API
response) by parsing Stage-1 MedCodER markdown blocks. The
``MedicalCodingPage.dataEvidences`` frontend hook then renders
each span with ``<EvidenceHighlighter>`` so a clicked code row
highlights its evidence in the input panel.

Before this parser existed, the runtime check
``click_code_highlights_evidence`` was ``_deferred`` (see
``corti_ui_contracts/medical-coding.json`` cycle 21 closeout).
Cycle 22 closes that gap and these tests pin the parser's
correct behaviour against the four LLM output variations seen
in production:

* Chinese curly quotes ``"..."`` (U+201C/U+201D) — the dominant
  flavour; DeepSeek V4 emits this in Stage 1 markdown.
* Straight ASCII quotes ``"..."`` — produced by some prompts
  and on shorter examples.
* Chinese book brackets ``「...」`` — observed in older runs.
* (line, col_start, col_end) tuples that the LLM gets wrong
  (off-by-one col_end is the most common drift).

For each flavour we verify (a) the parser returns the expected
text span, (b) the global char_start/char_end match the slice
in the original source, and (c) the LLM's (line, col) drift is
corrected via the source.find() fallback.
"""

from __future__ import annotations

import pytest

from icoder_runtime.core.evidence_parser import (
    _extract_quoted,
    _line_col_to_offset,
    parse_evidences_from_markdown,
)


# ── Quote-flavour extraction ─────────────────────────────────────────

@pytest.mark.parametrize(
    "line, expected",
    [
        # Chinese curly quotes (U+201C/U+201D) — the dominant LLM flavour
        (
            '    *   **支持证据 (原文片段):** "诊断：冠状动脉粥样硬化性心脏病"',
            "诊断：冠状动脉粥样硬化性心脏病",
        ),
        # Chinese book brackets 「...」
        (
            '    *   **支持证据 (原文片段):** 「手术：PCI术」',
            "手术：PCI术",
        ),
        # Straight ASCII double quotes
        (
            '    *   **支持证据 (原文片段):** "chronic heart failure"',
            "chronic heart failure",
        ),
    ],
)
def test_extract_quoted_supports_three_quote_flavours(line, expected):
    assert _extract_quoted(line) == expected


def test_extract_quoted_returns_none_when_no_quote():
    assert _extract_quoted("**支持证据**: no quoted text") is None


# ── (line, col) → global offset conversion ──────────────────────────

def test_line_col_to_offset_basic():
    # 3 lines, no trailing newline.
    # line 1 = "abc\n" (4 bytes incl. \n), line 2 = "de\n" (3 bytes), line 3 = "fghij".
    # Line 2 starts at global offset 4; col 1-2 (1-indexed inclusive) → global [4, 6).
    lines = ["abc", "de", "fghij"]
    cs, ce = _line_col_to_offset(lines, 2, 1, 2)
    assert (cs, ce) == (4, 6)
    # Verify the slice is "de"
    assert "abc\nde\nfghij"[cs:ce] == "de"


def test_line_col_to_offset_clamps_oversized_col():
    lines = ["abc"]  # length 3
    # col 1-99 should clamp to 1-3
    cs, ce = _line_col_to_offset(lines, 1, 1, 99)
    assert (cs, ce) == (0, 3)


def test_line_col_to_offset_handles_oversized_line():
    lines = ["abc"]
    # line 99 should clamp to last line
    cs, ce = _line_col_to_offset(lines, 99, 1, 3)
    assert (cs, ce) == (0, 3)


# ── End-to-end parsing on real LLM output ────────────────────────────

# Source: a typical 5-line admission record (matches the cycle-22
# curl test fixture so the asserted offsets are bit-exact reproducible).
SOURCE_5LINE = (
    "入院记录\n"
    "患者：张三，男，65岁\n"
    "主诉：反复胸闷3年\n"
    "诊断：冠状动脉粥样硬化性心脏病\n"
    "手术：PCI术"
)


def test_parse_curly_quotes_diagnosis_and_procedure():
    """The dominant LLM flavour: Chinese curly quotes around text."""
    output = (
        "#### **阶段 1: 抽取阶段**\n"
        "\n"
        "*   **诊断 1: 冠状动脉粥样硬化性心脏病**\n"
        '    *   **支持证据 (原文片段):** "诊断：冠状动脉粥样硬化性心脏病"\n'
        "    *   **字符跨度 (Char Span):** 第 4 行，第 1-14 字符 "
        "(假设从第1行第1字符开始计数)\n"
        "    *   **证据类型:** 明确诊断陈述\n"
        "\n"
        "*   **手术 1: PCI术**\n"
        '    *   **支持证据 (原文片段):** "手术：PCI术"\n'
        "    *   **字符跨度 (Char Span):** 第 5 行，第 1-8 字符\n"
        "    *   **证据类型:** 明确手术名称\n"
    )
    evs = parse_evidences_from_markdown(output, SOURCE_5LINE)
    assert len(evs) == 2

    # Diagnosis at global offset 27..42
    d, p = evs
    assert d["text"] == "诊断：冠状动脉粥样硬化性心脏病"
    assert d["char_start"] == 27
    assert d["char_end"] == 42
    # LLM said 1-14 but the text is 15 chars; the fallback must
    # correct the off-by-one drift and find the real slice.
    assert SOURCE_5LINE[d["char_start"]:d["char_end"]] == d["text"]

    # Procedure at global offset 43..50
    assert p["text"] == "手术：PCI术"
    assert (p["char_start"], p["char_end"]) == (43, 50)
    assert SOURCE_5LINE[p["char_start"]:p["char_end"]] == p["text"]


def test_parse_ascii_quotes_works():
    output = (
        '*   **诊断 1: Heart failure**\n'
        '    *   **支持证据 (原文片段):** "chronic heart failure"\n'
        "    *   **字符跨度 (Char Span):** 第 1 行，第 1-21 字符\n"  # 21 chars
    )
    src = "chronic heart failure in this patient"
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "chronic heart failure"
    assert evs[0]["char_start"] == 0
    assert evs[0]["char_end"] == 21
    assert src[evs[0]["char_start"]:evs[0]["char_end"]] == evs[0]["text"]


def test_parse_book_bracket_quotes_works():
    output = (
        '*   **诊断 1: 冠心病**\n'
        "    *   **支持证据 (原文片段):** 「诊断：冠心病」\n"
        "    *   **字符跨度 (Char Span):** 第 1 行，第 1-6 字符\n"
    )
    src = "诊断：冠心病"
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "诊断：冠心病"
    assert (evs[0]["char_start"], evs[0]["char_end"]) == (0, 6)


def test_parse_no_evidence_blocks_returns_empty_list():
    output = "Some unrelated markdown\n\nNo Stage 1 here.\n"
    assert parse_evidences_from_markdown(output, "any source") == []


def test_parse_evidence_block_without_char_span_falls_back_to_source_find():
    """If the LLM omits 字符跨度 entirely, fall back to source.find()
    so the frontend's EvidenceHighlighter still gets a valid (start,
    end) pair it can render. Previously this case emitted 0/0, which
    the frontend's buildSegments filter then dropped (end > start).
    """
    output = (
        '*   **诊断 1: Heart failure**\n'
        '    *   **支持证据 (原文片段):** "heart failure"\n'
        "    *   **证据类型:** 明确诊断\n"
    )
    src = "Patient has heart failure today."
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "heart failure"
    found = src.find("heart failure")
    assert evs[0]["char_start"] == found
    assert evs[0]["char_end"] == found + len("heart failure")
    assert src[evs[0]["char_start"]:evs[0]["char_end"]] == evs[0]["text"]


def test_parse_plain_global_range_format():
    """LLM sometimes emits a plain "M-K" global char range instead of
    the verbose "第N行，第M-K字符" flavour. The parser must accept this
    and snap to the actual quoted text if the range includes padding.
    """
    output = (
        '*   **支持证据 (Supporting Evidence):** "chronic heart failure, NYHA class III"\n'
        "    *   **字符跨度 (Char Span):** 0-38 (假设原文为 `Patient has chronic heart failure, NYHA class III.`)\n"
    )
    src = "Patient has chronic heart failure, NYHA class III."
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "chronic heart failure, NYHA class III"
    # The plain range "0-38" actually points at "Patient has " — the
    # parser must snap to the quoted text via source.find().
    found = src.find("chronic heart failure, NYHA class III")
    assert evs[0]["char_start"] == found
    assert evs[0]["char_end"] == found + len("chronic heart failure, NYHA class III")
    assert src[evs[0]["char_start"]:evs[0]["char_end"]] == evs[0]["text"]


def test_parse_bracket_list_global_range_format():
    """DeepSeek V4 sometimes emits a Python-list global range like
    "[0, 40]" instead of "0-40" or "第N行...". The parser must accept
    this flavour and snap to the quoted text on mismatch.
    """
    output = (
        "*   **支持证据:**\n"
        '    *   **原文片段:** "chronic heart failure, NYHA class III"\n'
        "    *   **字符跨度 (char span):** [0, 40] (假设原文起始位置为0)\n"
    )
    src = "Patient has chronic heart failure, NYHA class III."
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "chronic heart failure, NYHA class III"
    found = src.find("chronic heart failure, NYHA class III")
    assert evs[0]["char_start"] == found
    assert evs[0]["char_end"] == found + len("chronic heart failure, NYHA class III")


def test_parse_ascii_double_quote_matches():
    """The Stage 1 block has been observed with straight ASCII quotes
    (U+0022) — confirm `_extract_quoted` captures it."""
    line = '    *   **支持证据 (Supporting Evidence):** "chronic heart failure"'
    assert _extract_quoted(line) == "chronic heart failure"


def test_parse_empty_inputs_return_empty():
    assert parse_evidences_from_markdown("", "any source") == []
    assert parse_evidences_from_markdown("not a string", "any source") == []
    # source=empty is allowed; offsets fall back to 0/0
    evs = parse_evidences_from_markdown(
        '*   **支持证据 (原文片段):** "X"\n    *   **字符跨度:** 第 1 行，第 1-1 字符\n',
        "",
    )
    assert evs == [{"text": "X", "char_start": 0, "char_end": 0}]


def test_parse_llm_off_by_one_falls_back_to_source_find():
    """LLM sometimes reports col_end = last_char_idx (exclusive) when
    the frontend expects inclusive, or vice-versa. The fallback must
    locate the real slice via source.find().
    """
    output = (
        '*   **支持证据 (原文片段):** "heart failure"\n'
        "    *   **字符跨度 (Char Span):** 第 1 行，第 1-13 字符\n"  # 13 ≠ 22
    )
    src = "Patient has heart failure today."
    evs = parse_evidences_from_markdown(output, src)
    assert len(evs) == 1
    assert evs[0]["text"] == "heart failure"
    # Fallback found it at offset 12
    assert evs[0]["char_start"] == 12
    assert evs[0]["char_end"] == 12 + len("heart failure")
    assert src[evs[0]["char_start"]:evs[0]["char_end"]] == evs[0]["text"]


# ── RuntimeResult integration ────────────────────────────────────────


def test_runtime_result_metadata_evidences_is_hoisted_to_top_level():
    """The full integration: from_runner_output() must populate
    metadata.evidences and to_api_response() must hoist it to the
    top-level ``evidences`` field the frontend reads.
    """
    from icoder_runtime.core.runtime_result import RuntimeRunResult

    runner_result = {
        "review_id": "test-run-001",
        "output": (
            '*   **支持证据 (原文片段):** "诊断：冠状动脉粥样硬化性心脏病"\n'
            "    *   **字符跨度 (Char Span):** 第 4 行，第 1-14 字符\n"
        ),
        "agent_name": "medical-coding-agent",
        "agent_version": "2.0.0",
        "processing_time_ms": 1234,
        "state_log": {"entries": [], "chain_valid": True},
    }
    source = "诊断：冠状动脉粥样硬化性心脏病"
    r = RuntimeRunResult.from_runner_output(runner_result, agent_ref="x@1.0.0", source=source)
    # evidence must be parsed and stored in metadata
    assert "evidences" in r.metadata
    assert len(r.metadata["evidences"]) == 1
    assert r.metadata["evidences"][0]["text"] == "诊断：冠状动脉粥样硬化性心脏病"
    # to_api_response hoists it to top-level
    api = r.to_api_response()
    assert "evidences" in api
    assert api["evidences"][0]["text"] == "诊断：冠状动脉粥样硬化性心脏病"
    # metadata is stripped from API response
    assert "metadata" not in api
