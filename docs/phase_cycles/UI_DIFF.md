# UI contract diff — medical-coding — 2026-07-03 (post cycle-22)

**Result: 7/7 checks pass** (cycle 22 修复 `char_counter_live` + `click_code_highlights_evidence` 两个 runtime deferred)

- OK `real_time_char_counter` — Input area header shows a live char + cost estimate that updates on every keystroke (not just after Predict).
- OK `no_plain_textarea_in_page` — Plain `<textarea>` in MedicalCodingPage is replaced by HighlightedTextarea component (proves the input panel was migrated to the overlay pattern).
- OK `highlighted_textarea_overlay_pattern` — HighlightedTextarea component renders BOTH a textarea (input) AND a `<pre>` overlay (highlight display), shares INPUT_TEXT_CLASS for font-metric sync, and uses EvidenceHighlighter as JSX (not just imported).
- OK `evidence_highlighter_focused_state` — EvidenceHighlighter accepts a `focusedSpanIndex` prop and renders a distinct class (bg-green) for the focused span vs default (bg-yellow) for others — matches Corti screenshot where clicked code's evidence shows in green.
- OK `i18n_keys_added` — Two new i18n keys (charCount, costEstimate) added to BOTH zh-CN and en-US locale objects in locales.ts. Parity test enforces this automatically.
- OK `char_counter_live` — Runtime (Playwright): typing in the input updates `[data-testid=char-counter]` text per keystroke. Fixed in cycle 22 via markdown evidence parser wiring (RuntimeRunResult.from_runner_output now populates `metadata.evidences`, runtime_platform passes `body.input` so the parser can extract char spans).
- OK `click_code_highlights_evidence` — Code table row carries `data-testid='code-row-{i}'` AND the row's onClick calls `setFocusedSpanIndex` so the focused state flows down to EvidenceHighlighter (bg-green). End-to-end: `dataEvidences(result)` reads `result.evidences` populated by the cycle-22 markdown evidence parser (`parse_evidences_from_markdown`).

See `cycle_20_ui_runtime/REPORT.md` for the canonical 7/7 pass snapshot (2026-07-01 12:23 UTC).
