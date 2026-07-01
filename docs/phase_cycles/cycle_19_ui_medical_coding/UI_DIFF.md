# UI contract diff - medical-coding - 2026-07-01 04:02 UTC

**Result: 3/5 checks pass**

- OK `real_time_char_counter` — Input area header shows a live char + cost estimate that updates on every keystroke (not just after Predict).
- FAIL `no_plain_textarea_in_page` — Plain <textarea> in MedicalCodingPage is replaced by HighlightedTextarea component (proves the input panel was migrated to the overlay pattern).
  - jsx_used NOT FOUND: '<HighlightedTextarea'
- FAIL `highlighted_textarea_overlay_pattern` — HighlightedTextarea component renders BOTH a textarea (input) AND a <pre> overlay (highlight display), shares INPUT_TEXT_CLASS for font-metric sync, and uses EvidenceHighlighter as JSX (not just imported).
  - jsx_used NOT FOUND: '<EvidenceHighlighter'
- OK `evidence_highlighter_focused_state` — EvidenceHighlighter accepts a focusedSpanIndex prop and renders a distinct class (bg-green) for the focused span vs default (bg-yellow) for others — matches Corti screenshot where clicked code's evidence shows in green.
- OK `i18n_keys_added` — Two new i18n keys (charCount, costEstimate) added to BOTH zh-CN and en-US locale objects in locales.ts. Parity test enforces this automatically.
