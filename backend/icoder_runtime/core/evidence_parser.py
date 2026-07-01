"""Evidence parser — extract evidence spans from MedCodER markdown output.

The LLM (DeepSeek V4) emits Stage 1 evidence in a markdown block like:

    **诊断 1: 冠状动脉粥样硬化性心脏病**
    - **支持证据 (原文片段):** "诊断：冠状动脉粥样硬化性心脏病"
    - **字符跨度 (char span):** 第 4 行，第 1-15 字符 (假设从"诊"字开始计数)

    **手术 1: PCI术**
    - **支持证据 (原文片段):** "手术：PCI术"
    - **字符跨度 (char span):** 第 5 行，第 1-8 字符

The char span is a (line, col_start, col_end) tuple in the original
**input** text (the user typed 1-indexed; we normalise to 0-indexed global
char offsets). Frontend ``EvidenceHighlighter`` consumes global offsets.

LLM char spans are best-effort — the (text, line, col) tuple is what
matters. We compute the global offset from (line, col) and verify the
resulting slice matches the quoted text. If not, fall back to
``source.find(text)`` at that line.

Used by:
* ``RuntimeRunResult.from_runner_output`` (fills ``metadata.evidences``)
* ``MedicalCodingPage.dataEvidences`` (frontend fallback parser)
"""

from __future__ import annotations

import re
from typing import Any


# LLM markdown patterns. Both 诊断 and 手术 produce the same block shape,
# distinguished only by the section header (诊断 N: ... vs 手术 N: ...).
# We accept either header because the parser is header-agnostic — we only
# look for the two bullet points under any **<something> N: <name>** header.
#
# Quote flavours seen in production:
#   * ASCII straight quotes  "..."    (English / some Chinese runs)
#   * Curly Chinese quotes   "..."    (U+201C/U+201D)
#   * Chinese book brackets  「...」  (older runs)
#
# Char-span flavours seen in production:
#   * "第 N 行，第 M-K 字符"  (1-indexed line/col, the format the parser
#     was originally written for)
#   * "M-K (假设原文为 ...)"   (plain 0-indexed global char range, no
#     line/col split — the most common DeepSeek V4 output for short
#     single-line inputs)
#
# We accept both with separate regexes and prefer the line/col flavour
# when present (it's more precise for multi-line EMRs); the plain range
# flavour is the fallback.

_QUOTED_TEXT_RE = re.compile(
    r'"([^"]+)"|'        # ASCII straight quotes
    r'“([^”]+)”|'        # Chinese curly quotes U+201C/U+201D
    r'「([^」]+)」'       # Chinese book brackets
)
_LINE_COL_RE = re.compile(r"第\s*(\d+)\s*行[，,]\s*第\s*(\d+)\s*[-~]\s*(\d+)\s*字符")
# Plain global char range, e.g. "0-38" or "12-45". Anchored with \b on
# the right so "38" in "0-38 (假设原文为 ...)" matches cleanly without
# eating the following space.
_PLAIN_RANGE_RE = re.compile(r"\b(\d+)\s*[-~]\s*(\d+)\b")
# Python-list global char range, e.g. "[0, 40]" or "[12, 45]". DeepSeek
# V4 also emits this flavour with parenthetical hints like
# "(假设原文起始位置为0)".
_BRACKET_RANGE_RE = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]")


def _extract_quoted(text_line: str) -> str | None:
    """Pull the quoted evidence text out of the 支持证据 line.

    Accepts ASCII / Chinese full-width / 「」 quote flavours because the LLM
    has produced all three in different runs.
    """
    m = _QUOTED_TEXT_RE.search(text_line)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def _line_col_to_offset(
    source_lines: list[str], line: int, col_start: int, col_end: int
) -> tuple[int, int]:
    """Convert 1-indexed (line, col_start, col_end) to 0-indexed global
    (char_start, char_end) offsets.

    The resulting slice is ``source[char_start:char_end]``.
    """
    # Clamp line into [1, len(source_lines)]; LLM is best-effort.
    line_idx = max(1, min(line, len(source_lines)))
    # Sum lengths of preceding lines + 1 (for each \n) → start of this line.
    line_start = sum(len(source_lines[i]) + 1 for i in range(line_idx - 1))
    # Clamp col_start, col_end to the actual line length.
    line_len = len(source_lines[line_idx - 1])
    cs = max(1, min(col_start, line_len))
    ce = max(cs, min(col_end, line_len))
    return line_start + cs - 1, line_start + ce


def parse_evidences_from_markdown(
    output: str, source: str
) -> list[dict[str, Any]]:
    """Extract evidence spans from a MedCodER 5-stage markdown output.

    Parameters
    ----------
    output : str
        The LLM-generated markdown (typically ``result.output``).
    source : str
        The original user input text. Used to compute global char offsets
        from the LLM's (line, col) coordinates. If empty, every span's
        char_start/char_end fall back to 0 (frontend will fuzzy-match
        the text via ``EvidenceHighlighter``'s built-in substring search).

    Returns
    -------
    list of dicts ``{"text": str, "char_start": int, "char_end": int}``.
    Empty list if no evidence blocks are found.
    """
    if not output or not isinstance(output, str):
        return []

    source_lines = source.split("\n") if source else []
    out: list[dict[str, Any]] = []

    # Walk line-by-line looking for the 支持证据 / 字符跨度 pair. The
    # pair can be separated by intervening markdown noise (whitespace,
    # bold markers) but in practice is adjacent — we scan a small window
    # (next 5 lines) after each 支持证据 line for 字符跨度.
    #
    # The supporting-evidence bullet can be marked with either Chinese
    # (支持证据 / 原文片段) or English (Supporting Evidence) headers —
    # DeepSeek V4 emits the mixed-form "支持证据 (Supporting Evidence):"
    # most often. The actual quoted text may sit on the same bullet or
    # on a nested child bullet (one indent level deeper), so we drive
    # the scan off the quoted-text line and look *back* up to 3 lines
    # for the "支持证据" header.
    lines = output.splitlines()
    for i, line in enumerate(lines):
        quoted = _extract_quoted(line)
        if not quoted:
            continue
        # Confirm a "支持证据" header sits within the prior 3 lines
        # (typical Stage-1 layout: header → nested quoted-text bullet).
        header_found = "支持证据" in line
        if not header_found:
            for k in range(max(0, i - 3), i):
                if "支持证据" in lines[k]:
                    header_found = True
                    break
        if not header_found:
            continue
        # Look ahead up to 5 lines for 字符跨度. Prefer the line/col
        # flavour (precise for multi-line EMRs); fall back to a plain
        # global range ("M-K") or Python-list range ("[M, K]") if the
        # LLM emitted that instead.
        span = None
        is_global_range = False
        for j in range(i + 1, min(i + 6, len(lines))):
            m = _LINE_COL_RE.search(lines[j])
            if m:
                span = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                break
            m = _BRACKET_RANGE_RE.search(lines[j])
            if m:
                span = (int(m.group(1)), int(m.group(2)))
                is_global_range = True
                break
            m = _PLAIN_RANGE_RE.search(lines[j])
            if m:
                span = (int(m.group(1)), int(m.group(2)))
                is_global_range = True
                break
        if span is None:
            # No char span reported by LLM — fall back to source.find()
            # so the frontend's EvidenceHighlighter still gets a valid
            # (start, end) pair it can render. Only emit 0/0 when the
            # source itself doesn't contain the quoted text at all.
            if source:
                found = source.find(quoted)
                if found >= 0:
                    out.append({
                        "text": quoted,
                        "char_start": found,
                        "char_end": found + len(quoted),
                    })
                else:
                    out.append({"text": quoted, "char_start": 0, "char_end": 0})
            else:
                out.append({"text": quoted, "char_start": 0, "char_end": 0})
            continue
        if is_global_range:
            cs, ce = span
        else:
            line_n, col_s, col_e = span
            if source_lines:
                cs, ce = _line_col_to_offset(source_lines, line_n, col_s, col_e)
            else:
                cs, ce = 0, 0
            # Verify the LLM-computed slice matches the quoted text.
            # If not, fall back to source.find(quoted) at the same line.
            if source and source[cs:ce] != quoted:
                # Clamp line_n to a valid index; LLM can report a line
                # number that exceeds the source (off-by-one or
                # whitespace drift). The line_text must come from the
                # *clamped* index so source_lines[k] doesn't IndexError.
                clamped_line = max(1, min(line_n, len(source_lines)))
                line_offset = sum(
                    len(source_lines[k]) + 1 for k in range(clamped_line - 1)
                )
                line_text = source_lines[clamped_line - 1]
                found = line_text.find(quoted)
                if found >= 0:
                    cs = line_offset + found
                    ce = cs + len(quoted)
                else:
                    # Last resort: global find.
                    found = source.find(quoted)
                    if found >= 0:
                        cs = found
                        ce = found + len(quoted)
                    else:
                        cs, ce = 0, 0
        # For the plain-range flavour, also verify against the source —
        # the LLM's M-K range may include surrounding whitespace, so
        # snap to the actual quoted text position when possible.
        if is_global_range and source and source[cs:ce] != quoted:
            found = source.find(quoted)
            if found >= 0:
                cs, ce = found, found + len(quoted)
            else:
                cs, ce = 0, 0
        out.append({"text": quoted, "char_start": cs, "char_end": ce})

    return out