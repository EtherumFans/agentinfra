# UI contract diff - medical-coding - 2026-07-01 12:07 UTC

**Result: 6/7 checks pass**

- OK `real_time_char_counter` — Input area header shows a live char + cost estimate that updates on every keystroke (not just after Predict).
- OK `no_plain_textarea_in_page` — Plain <textarea> in MedicalCodingPage is replaced by HighlightedTextarea component (proves the input panel was migrated to the overlay pattern).
- OK `highlighted_textarea_overlay_pattern` — HighlightedTextarea component renders BOTH a textarea (input) AND a <pre> overlay (highlight display), shares INPUT_TEXT_CLASS for font-metric sync, and uses EvidenceHighlighter as JSX (not just imported).
- OK `evidence_highlighter_focused_state` — EvidenceHighlighter accepts a focusedSpanIndex prop and renders a distinct class (bg-green) for the focused span vs default (bg-yellow) for others — matches Corti screenshot where clicked code's evidence shows in green.
- OK `i18n_keys_added` — Two new i18n keys (charCount, costEstimate) added to BOTH zh-CN and en-US locale objects in locales.ts. Parity test enforces this automatically.
- OK `char_counter_live` — Runtime (Playwright): typing in the input updates [data-testid=char-counter] text per keystroke (not gated on Predict).
- FAIL `click_code_highlights_evidence` — Code table row carries data-testid='code-row-{i}' AND the row's onClick calls setFocusedSpanIndex so the focused state flows down to EvidenceHighlighter (bg-green). End-to-end: dataEvidences(result) reads result.evidences which is now populated by RuntimeRunResult.from_runner_output via the cycle-22 markdown evidence parser (parse_evidences_from_markdown).
  - Error: [2mexpect([22m[31mreceived[39m[2m).[22mtoBeTruthy[2m()[22m
  - 
  - Received: [31mfalse[39m
