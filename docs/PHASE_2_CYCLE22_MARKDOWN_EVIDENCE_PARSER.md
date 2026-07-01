# Phase 2 Cycle 22 — Markdown Evidence Parser

## 1. Context

Cycle 21 unblocked 3 runtime gates (agent ref 1.0.0→2.0.0, v1.2 install path,
default allow-experts permission policy) but explicitly deferred the
`click_code_highlights_evidence` runtime check to cycle 22+ because
`RuntimeRunResult.from_runner_output` did not populate `result.evidences`.
The frontend's `dataEvidences(result)` hook reads that field to render
`<EvidenceHighlighter>` spans, but the underlying evidence lived only as
markdown tables inside `result.output` (e.g.
`**字符跨度 (Char Span):** 第 4 行，第 1-14 字符`).

This cycle closes that gap by parsing Stage-1 MedCodER markdown into
structured `{text, char_start, char_end}` spans server-side.

## 2. Audit (cycle 21 closeout → cycle 22 start)

- `corti_ui_contracts/medical-coding.json` schema v2, 7 checks (5 static +
  2 runtime). `click_code_highlights_evidence` runtime was `_deferred` per
  cycle 21 §3.4
- `backend/icoder_runtime/core/runtime_result.py:from_runner_output` —
  signature had no `source` parameter; `metadata` was a flat dict with
  agent_name/agent_version/chain_valid only, no `evidences` key
- `backend/app/api/runtime_platform.py:run_agent_by_ref` —
  `RuntimeRunResult.from_runner_output(result, agent_ref=rec.agent_id)`
  didn't forward `body.input`, so even if the parser existed it would
  have no source text to compute char offsets against
- DeepSeek V4 Stage-1 markdown output (observed across 10+ runs) emits
  evidence in 3 quote flavours × 3 span formats:
  - quotes: ASCII `"..."`, Chinese curly `"..."` (U+201C/U+201D),
    book brackets `「...」`
  - spans: `第 N 行，第 M-K 字符` (1-indexed line/col),
    `[M, K]` (Python-list global range),
    `M-K` (plain global range)
- LLM char spans are best-effort: off-by-one on `col_end` is the most
  common drift (e.g. text is 15 chars, LLM says "1-14"); the parser
  must verify `source[cs:ce] == quoted` and fall back to
  `source.find(quoted)` on mismatch

## 3. Spec — what cycle 22 ships

### 3.1 Backend: `evidence_parser.py` (NEW, 236 LOC)

`backend/icoder_runtime/core/evidence_parser.py` exposes one public entry
point:

```python
def parse_evidences_from_markdown(output: str, source: str) -> list[dict[str, Any]]
```

Returns `[{"text": str, "char_start": int, "char_end": int}, ...]` —
empty list if no evidence blocks are found.

Pipeline:
1. Walk `output.splitlines()` looking for a quoted-text line
   (`_extract_quoted` accepts all 3 quote flavours via a single regex
   with 3 alternations)
2. Confirm a `支持证据` header sits within the prior 3 lines (typical
   Stage-1 layout: header → nested quoted-text bullet)
3. Look ahead up to 5 lines for a char-span line. Prefer the line/col
   flavour (`_LINE_COL_RE`) — most precise for multi-line EMRs; fall
   back to `_BRACKET_RANGE_RE` (`[M, K]`) then `_PLAIN_RANGE_RE` (`M-K`)
4. Convert (line, col_start, col_end) → global (cs, ce) via
   `_line_col_to_offset` (1-indexed → 0-indexed, with clamping for
   oversized line/col values from LLM drift)
5. **Verify** `source[cs:ce] == quoted`; on mismatch, snap to
   `source.find(quoted)` at the reported line, then globally. Only
   emit `0/0` when the quoted text isn't in source at all.

### 3.2 Backend: `runtime_result.py` wiring

`RuntimeRunResult.from_runner_output` gains a `source: str = ""` parameter.
The parser runs eagerly (under try/except — never fails the run if the
parser bugs out). Results land in `metadata.evidences` plus a new
`metadata.source_len` for debugging.

`to_api_response()` hoists `metadata.evidences` to the top-level
`evidences` field (the typed `RuntimeRunResult.evidences?: any[]`
interface the frontend already declares). `metadata` itself is still
stripped from the API response.

### 3.3 Backend: `runtime_platform.py` wiring

`run_agent_by_ref` now passes `source=body.input` to
`from_runner_output`. One-line change; no API contract change.

### 3.4 Contract: `_deferred` → active runtime

`corti_ui_contracts/medical-coding.json`:
- Removed the `_deferred` marker on `click_code_highlights_evidence.runtime`
- Updated the description to reference the cycle-22 parser by name

### 3.5 Tests: `test_evidence_parser.py` (NEW, 310 LOC, 18 tests)

| Group | Test | Asserts |
|---|---|---|
| quote extraction | `test_extract_quoted_supports_three_quote_flavours` (parametrised ×3) | ASCII / curly / book brackets all match |
| quote extraction | `test_extract_quoted_returns_none_when_no_quote` | non-quoted line returns None |
| offset conversion | `test_line_col_to_offset_basic` | (line=2, col=1-2) → (4, 6) on 3-line source |
| offset conversion | `test_line_col_to_offset_clamps_oversized_col` | col 1-99 clamps to 1-3 |
| offset conversion | `test_line_col_to_offset_handles_oversized_line` | line 99 clamps to last line |
| end-to-end | `test_parse_curly_quotes_diagnosis_and_procedure` | dominant flavour, 2 evidence blocks |
| end-to-end | `test_parse_ascii_quotes_works` | ASCII flavour |
| end-to-end | `test_parse_book_bracket_quotes_works` | book bracket flavour |
| end-to-end | `test_parse_no_evidence_blocks_returns_empty_list` | unrelated markdown → `[]` |
| end-to-end | `test_parse_evidence_block_without_char_span_falls_back_to_source_find` | missing 字符跨度 line → source.find fallback |
| end-to-end | `test_parse_plain_global_range_format` | `0-38` plain range + snap on mismatch |
| end-to-end | `test_parse_bracket_list_global_range_format` | `[0, 40]` Python-list range |
| end-to-end | `test_parse_ascii_double_quote_matches` | straight ASCII double quote |
| end-to-end | `test_parse_empty_inputs_return_empty` | empty output / non-string / empty source |
| end-to-end | `test_parse_llm_off_by_one_falls_back_to_source_find` | col_end drift corrected via source.find |
| integration | `test_runtime_result_metadata_evidences_is_hoisted_to_top_level` | from_runner_output populates metadata; to_api_response hoists to top-level |

## 4. Verification

### 4.1 Unit tests

```
$ python -m pytest tests/unit/icoder_runtime/test_evidence_parser.py -v
======================== 18 passed, 1 warning in 1.25s ========================
```

### 4.2 Toolchain (`scripts/icoder_ui_diff.py`)

```
[ui-diff] feature=medical-coding  checks=7  schema_version=2
  [OK]  real_time_char_counter
  [OK]  no_plain_textarea_in_page
  [OK]  highlighted_textarea_overlay_pattern
  [OK]  evidence_highlighter_focused_state
  [OK]  i18n_keys_added
  [OK]  char_counter_live
  [OK]  click_code_highlights_evidence

[summary] 7/7 checks pass for medical-coding
[OK] wrote corti_ui_contracts\medical-coding.VERIFIED_OK
```

The Playwright runtime path now reaches the agent endpoint (cycle 21),
gets a real DeepSeek V4 response back, the parser extracts evidence
spans, `dataEvidences(result)` renders them, the user clicks
`[data-testid=code-row-0]`, `setFocusedSpanIndex` flows down to
`<EvidenceHighlighter>`, and `mark[class*='bg-green-200']` count ≥ 1.

### 4.3 End-to-end flow

```
browser → POST /api/runtime/agents/medical-coding-agent-2.0.0/run
        → PlatformRuntime.run_agent
        → AgentRunner → DeepSeek V4 → Stage-1 markdown output
        → RuntimeRunResult.from_runner_output(result, source=body.input)
        → parse_evidences_from_markdown(output, source)
        → metadata.evidences = [{text, char_start, char_end}, ...]
        → to_api_response() hoists evidences to top-level
        → frontend dataEvidences(result) → EvidenceHighlighter
        → click code-row-0 → setFocusedSpanIndex(0) → bg-green-200
```

## 5. Cycle 23+ follow-up

1. **DB recovery runbook**: cycle 21 §5.2 mentioned this as a cycle 22
   follow-up, but the markdown parser ate the cycle. The recovery
   runbook (stale `alembic_version=005` + empty schema → `mv
   data/icoder.db data/icoder.db.bakYYYYMMDD` + restart so `init_db()`
   rebuilds) belongs in `docs/dev/BACKEND_RECOVERY.md` as cycle 23.
2. **Parser robustness**: the 3 quote flavours + 3 span formats cover
   every Stage-1 output variation seen in 10+ DeepSeek V4 runs, but
   a new flavour (e.g. smart quotes from a different prompt template)
   would silently produce `[]`. Add a fallback regex that accepts any
   `**...**`-wrapped quoted text if cycle 24+ sees new shapes.
3. **Frontend Markdown fallback**: if backend parsing ever fails on a
   real LLM output, add a client-side regex parser in `dataEvidences`
   as graceful degradation (separate cycle).

## 6. Files touched

```
backend/icoder_runtime/core/evidence_parser.py                    (NEW, 236 LOC)
backend/icoder_runtime/core/runtime_result.py                    (+source param, +evidences metadata, +to_api_response hoist)
backend/app/api/runtime_platform.py                               (forward body.input as source)
backend/tests/unit/icoder_runtime/test_evidence_parser.py         (NEW, 310 LOC, 18 tests)
corti_ui_contracts/medical-coding.json                            (_deferred → active runtime)
corti_ui_contracts/medical-coding.VERIFIED_OK                     (timestamp refresh)
```
