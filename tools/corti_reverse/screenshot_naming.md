# Screenshot Naming Convention

**Tool**: #5 — Standardized naming for Corti screenshots
**Phase**: 3-B1.5 Section A

## Pattern

```
<section>-<step>-<page>-<state>.png
```

- `<section>`: Phase 3-B1.5 section letter (`B` for Manual Exploration,
  `C` for Playwright Capture, etc.)
- `<step>`: Step number within section (e.g., `03`, `13`)
- `<page>`: Short page identifier (`agent-library`, `medical-coding-card`)
- `<state>`: Optional state qualifier (`empty`, `error`, `loaded`,
  `with-input`)

## Examples

| Section | Step | Page | State | Filename |
|---|---|---|---|---|
| B | 01 | login | loaded | `B-01-login-loaded.png` |
| B | 03 | agent-library | empty | `B-03-agent-library-empty.png` |
| B | 03 | agent-library | with-filters | `B-03-agent-library-with-filters.png` |
| B | 05 | medical-coding-card | default | `B-05-medical-coding-card-default.png` |
| B | 06 | medical-coding-detail | experts-tab | `B-06-medical-coding-detail-experts-tab.png` |
| B | 13 | error | empty-input | `B-13-error-empty-input.png` |
| C | 04 | medical-coding-detail | default | `C-04-medical-coding-detail-default.png` |
| C | 04 | medical-coding-detail | run-1 | `C-04-medical-coding-detail-run-1.png` |

## Full vs Viewport

- **Default**: viewport-only (1280×720 or 1500×873) — smaller file,
  captures the visible UI.
- **Full page**: append `-full` to state, e.g., `B-03-agent-library-empty-full.png`.
  Use when the page has important content below the fold (e.g., long
  agent list, run trace history).

## Stability Runs

For Section C stability runs (3x), append `-run<N>`:

```
C-04-medical-coding-detail-default-run1.png
C-04-medical-coding-detail-default-run2.png
C-04-medical-coding-detail-default-run3.png
```

## Redaction

All screenshots MUST pass through `redact_har.py --image-mode` before
commit. The image mode:

1. Strips page title (visible in browser tab).
2. Strips URL bar contents.
3. OCR-scans visible DOM text for emails / names / PHI and masks
   them with black rectangles.

If `pytesseract` is not installed, image-mode is skipped with a
warning — but the screenshot MUST then be manually reviewed before
commit.

## Storage

All screenshots live in `artifacts/corti_reverse/screenshots/`.
Never commit screenshots outside this directory.

## Reference Index

After capture, update
`docs/reverse_engineering/corti/CORTI_MANUAL_OBSERVATION_LOG.md` with
a screenshot reference table:

| Step | Screenshot | Page URL | Notes |
|---|---|---|---|
| B-01 | `B-01-login-loaded.png` | https://app.corti.ai/login | Standard Corti login page |
| B-03 | `B-03-agent-library-empty.png` | https://app.corti.ai/agents | Initial load, no filters applied |
| ... | ... | ... | ... |
