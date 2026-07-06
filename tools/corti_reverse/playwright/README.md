# Phase 3-B1.5 Section C — Corti Agentic Framework Probe

**Status**: IMPLEMENTED (spec + config + tsconfig). Not yet run against live Corti — operator must supply credentials.

## Files

| File | Purpose |
|---|---|
| `playwright.config.ts` | Playwright config: baseURL, viewport 1500×873, storageState from env, list+json+html reporters |
| `corti_agentic_framework_probe.spec.ts` | 31 tests: 15 paths + 15 stability runs (3× first 5 paths) + 1 full-session |
| `tsconfig.json` | TypeScript config with typeRoots pointing to `frontend/node_modules/@types` |
| `node_modules` (junction) | Junction to `frontend/node_modules` — reuses `@playwright/test` + `@types/node` without duplicate install |

## Test inventory

| # | Test ID | Description |
|---|---|---|
| 1-15 | `C-01-login` … `C-15-a2a-mcp-docs` | 15 paths from Section B observation log |
| 16-30 | `C-01-login-run1` … `C-05-medical-coding-card-run3` | 3× stability on first 5 paths |
| 31 | `C-full-session` | Single test navigating all 15 paths in sequence |

Total: **31 tests in 1 file** (verified via `npx playwright test --list`).

## Per-path capture

Each path captures:
- `artifacts/corti_reverse/screenshots/C-<id>.png` — full-page screenshot
- `artifacts/corti_reverse/hars/C-<id>.har` — HAR with embedded response bodies (`mode: full`, `content: embed`)
- `artifacts/corti_reverse/traces/C-<id>.zip` — Playwright trace (screenshots + snapshots + sources)
- `artifacts/corti_reverse/screenshots/C-<id>.console.json` — console messages with timestamps
- `artifacts/corti_reverse/screenshots/C-<id>.network.json` — network metadata (url, method, status, resourceType, time)

## Run instructions

### Prerequisites

1. Authorized Corti account (Google OAuth or email/password).
2. VPN/proxy from China network to reach `console.corti.app`.
3. Project ID + cloned agent ID in Corti (or willingness to clone during the run).
4. `cd frontend && npm install` (Playwright + browsers already installed in repo).

### Option A: Storage state (recommended)

Reuses a logged-in profile without re-authenticating per run.

```bash
# One-time: extract storage state from a logged-in Chrome session.
# (Run any browser-based Corti session once, then save the cookies/localStorage.)
# Or use Playwright's auth.setup.ts pattern:
cd frontend
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://console.corti.app/');
  // Manually log in via Google OAuth in the launched browser.
  // Then press Enter in this terminal to save state.
  await new Promise(r => process.stdin.once('data', r));
  await context.storageState({ path: '../artifacts/corti_reverse/.auth/state.json' });
  await browser.close();
})();
"

# Run the probe with saved state
cd ../frontend
CORTI_STORAGE_STATE=../artifacts/corti_reverse/.auth/state.json \
CORTI_PROJECT_ID=<your-project-uuid> \
CORTI_AGENT_ID=<your-cloned-agent-uuid> \
npx playwright test --config=../tools/corti_reverse/playwright/playwright.config.ts
```

### Option B: Email + password

Will trigger Google OAuth or email login per run (slower; may hit captchas).

```bash
cd frontend
CORTI_EMAIL=your.email@gmail.com \
CORTI_PASSWORD=... \
CORTI_PROJECT_ID=<your-project-uuid> \
CORTI_AGENT_ID=<your-cloned-agent-uuid> \
npx playwright test --config=../tools/corti_reverse/playwright/playwright.config.ts
```

### Run a subset

```bash
# Only the stability suite
npx playwright test --config=../tools/corti_reverse/playwright/playwright.config.ts --grep "stability"

# Only one path
npx playwright test --config=../tools/corti_reverse/playwright/playwright.config.ts --grep "01-login"

# Only the full-session capture
npx playwright test --config=../tools/corti_reverse/playwright/playwright.config.ts --grep "full-session"
```

## Post-capture redaction (REQUIRED before commit)

All HARs and screenshots MUST pass through `redact_har.py` before commit. Run:

```bash
# Redact all HARs
for har in ../artifacts/corti_reverse/hars/C-*.har; do
  python ../tools/corti_reverse/har_analyzer/redact_har.py \
    --input "$har" \
    --output "${har%.har}.redacted.har"
done

# Redact all screenshots (OCR-based; requires pytesseract + Pillow)
for png in ../artifacts/corti_reverse/screenshots/C-*.png; do
  python ../tools/corti_reverse/har_analyzer/redact_har.py \
    --input "$png" \
    --output "$png" \
    --image-mode
done
```

Or use the batch script:

```bash
python ../tools/corti_reverse/playwright/redact_all.py
```

After redaction:
- Commit only `*.redacted.har` and the OCR-masked PNGs.
- Never commit raw (un-redacted) HARs or screenshots.
- The `B-07-...-full.png` screenshot from Section B contains the full Medical Coding Agent system prompt — handle with extra care (do not commit to public repo).

## Validation status (as of 2026-07-05)

| Check | Status |
|---|---|
| Spec parses via `npx playwright test --list` | ✅ 31 tests in 1 file |
| TypeScript compiles via `tsc --noEmit` | ✅ No errors |
| Skip-when-no-auth logic | ✅ 31/31 skipped when CORTI_EMAIL/CORTI_STORAGE_STATE unset |
| Per-path HAR recording (contextOptions.recordHar) | ✅ Configured |
| Per-path trace recording | ✅ Configured |
| Per-path screenshot (full page) | ✅ Configured |
| Per-path console + network metadata capture | ✅ Configured |
| 3× stability on first 5 paths | ✅ Implemented |
| Full-session capture test | ✅ Implemented |
| Post-capture redaction (HAR + image modes) | ✅ Tool exists at `tools/corti_reverse/har_analyzer/redact_har.py` |
| Actual run against live Corti | ⏸ Pending operator credentials + VPN |

## Authorization boundaries (per Phase 3-B1.5 prompt)

- ✅ Authorized Corti account (user's own).
- ✅ No bypassing access control — login via Google OAuth as normal user.
- ✅ No decompilation, no copying private code/prompts/models/data.
- ✅ All screenshots and HAR files MUST pass `redact_har.py` before commit.
- ✅ User IDs / project IDs / agent IDs logged are the user's own; allowed to record for traceability.

## Limitations

1. **No live run in this session**: requires operator credentials + VPN. Spec is fully runnable; expected output described above.
2. **HAR for full-session test**: needs a separate context with `recordHar` set. Run with `CORTI_FULL_SESSION_HAR=1` and the operator launches a fresh context (documented in spec).
3. **WebSocket frame bodies**: Chrome HAR truncates WS payloads. Use mitmproxy (Tool #3, `tools/corti_reverse/mitmproxy_capture_plan.md`) if WS inspection is needed for the run streaming path.
4. **SSE chunks**: HAR records SSE responses but may truncate long streams. Verify via `analyze_corti_har.py --check-sse`.
5. **System prompt of Medical Coding Agent**: visible in `B-07-...-full.png` from Section B. Section C tests do not specifically capture system prompt text (only Settings panel structure); but if a screenshot of the Settings panel is taken, it may include prompt text — must run `redact_har.py --image-mode` before commit.
