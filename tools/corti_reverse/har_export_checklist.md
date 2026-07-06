# Chrome DevTools HAR Export Checklist

**Tool**: #1 — Manual HAR export procedure
**Phase**: 3-B1.5 Section A
**Use when**: Playwright automation is unavailable, or when verifying
a specific failure mode interactively.

## Prerequisites

- Chrome ≥ 100 with logged-in Corti profile.
- Corti account with authorized workspace.
- Output directory `artifacts/corti_reverse/hars/` exists.

## Procedure

1. Open Chrome.
2. Navigate to Corti URL with logged-in profile.
3. Open DevTools (F12 or Ctrl+Shift+I).
4. Switch to **Network** tab.
5. Tick checkboxes:
   - ☑ Preserve log (across navigation)
   - ☑ Disable cache
   - ☑ Hide background requests (optional — reduces noise)
6. Filter by `Fetch/XHR` if only API calls are needed; otherwise
   leave on `All`.
7. Reload the page (Ctrl+R) OR perform the action under test
   (click button, submit form).
8. Wait for the action to complete — verify by the network
   activity stopping OR the UI showing the result.
9. Right-click any network request → **Save all as HAR with content**.
   - Chrome: choose "Save all as HAR with content" (NOT "Save all as
     HAR" — the latter strips response bodies).
10. Save to `artifacts/corti_reverse/hars/<descriptive-name>.har`.
11. Run redaction before commit:
    ```bash
    python tools/corti_reverse/har_analyzer/redact_har.py \
      --input artifacts/corti_reverse/hars/<name>.har \
      --output artifacts/corti_reverse/hars/<name>.redacted.har
    ```
12. Verify redaction by opening the redacted HAR in a text editor
    and searching for `Bearer`, `cookie`, `@`, `<email-pattern>` —
    none should appear.

## Naming Convention

`<section>-<step>-<page>-<state>.har`

Examples:
- `B-03-agent-library-initial-load.har`
- `B-05-medical-coding-agent-card-click.har`
- `B-13-error-empty-input.har`
- `C-04-medical-coding-agent-detail.har`

## What to Capture per Session

For each Corti page under test:
1. HAR for the **page load** (all initial XHRs).
2. HAR for the **primary action** (button click, form submit).
3. HAR for any **secondary action** (filter, scroll-loaded XHRs).
4. HAR for any **error state** (empty input, permission denied).

## Pitfalls

- **WebSocket frames**: Chrome HAR truncates WS frame payloads. Use
  mitmproxy (Tool #3) if WS frame bodies are needed.
- **SSE streams**: Chrome HAR records SSE responses but may not
  capture all chunks if the stream is long. Verify by parsing the
  HAR with `analyze_corti_har.py --check-sse`.
- **Service Worker**: if Corti uses a SW, some requests may not
  appear in the Network tab. Disable SW in Application tab if needed.
- **Cross-origin**: HAR records cross-origin requests but response
  bodies may be hidden if CORS blocks. Use mitmproxy for full
  cross-origin visibility.

## After Capture

1. Save HAR to `artifacts/corti_reverse/hars/`.
2. Run `redact_har.py` to produce `<name>.redacted.har`.
3. Run `analyze_corti_har.py` to produce `<name>.report.md`.
4. Run `extract_route_graph.py --har <name>.redacted.har` to update
   the cumulative route graph in
   `docs/reverse_engineering/corti/CORTI_ROUTE_GRAPH.md`.
5. Commit only the redacted HAR + report + route graph. Never
   commit the raw (un-redacted) HAR.
