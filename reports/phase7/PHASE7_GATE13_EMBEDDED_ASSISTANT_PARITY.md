# Phase 7 Gate 13 — Corti-Style Embedded Assistant Parity Page

**Date**: 2026-07-14
**Verdict**: PASS_GATE13_EMBEDDED_ASSISTANT_PARITY_VERIFIED
**Effort**: ~45 min (frontend page + backend preview.html endpoint + Playwright E2E + test drift fix)
**Hard checkpoint**: None (Gate 13 was not on the original Phase 7 critical path; added as bonus parity work after Phase 7 FINAL closed)

## What this gate delivers

Phase 7 FINAL closed at Gate 12 with verdict PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION.
That verdict shipped the server-side partner integration story (real client_credentials →
real DeepSeek → signed trace_url) but explicitly deferred the Corti-style *Console* preview
page — the in-product page where a customer success engineer can point-and-click configure
the widget and copy a working snippet without writing any code.

Gate 13 closes that gap by replicating Corti's `/project/{id}/ai-studio/embedded-assistant`
layout end-to-end inside the iCoDer Console. The "configure once → copy anywhere" UX that
Corti ships as their primary embed onboarding flow now has a 1:1 iCoDer counterpart.

## Corti parity layout delivered

| Pane | Corti | iCoDer (Gate 13) | Status |
|------|-------|------------------|--------|
| **Preview pane** (top) | iframe with Desktop/Mobile toggle + Restart | iframe loading `/api/embedded/preview.html?<config>` with same controls | ✅ PARITY |
| **Event Inspector** (collapsible middle) | unified event log with timestamps | same `<EventInspector>` component used elsewhere, fed via `postMessage` from iframe | ✅ PARITY |
| **Configuration: Settings** (bottom-left tab) | agent + patient + features + locale + primary color | identical 7 controls (Agent, Patient ID/Name/Encounter ID, 4 feature toggles, Interface language, Primary color) | ✅ PARITY |
| **Configuration: Code** (bottom-right tab) | HTML / React / JSON Config generators with Copy | identical 3 generators, all live-updating from Settings state | ✅ PARITY |
| **Header live cost** | persistent $0.00X counter | page-level "Reset" button reuses global live cost from cost store | ✅ PARITY (slight iCoDer style — Reset is per-page) |

## Files added / modified

### Frontend (new)
- `frontend/src/pages/EmbeddedAssistantPage.tsx` (~330 LOC)
  - 3 major sections: Preview / Event Inspector / Configuration
  - `EmbeddedConfig` interface (agentRef, patientId, patientName, encounterId, primaryColor, features, locale)
  - `useMemo`-driven `previewUrl` (URLSearchParams encoding for iframe src)
  - `postMessage` listener forwarding iframe events to parent Event Inspector
  - 3 code generators (`generateHtml`, `generateReact`, `JSON.stringify`) all reflect current Settings
  - Access token auto-wired from `useAuthStore.accessToken` (no manual paste needed for Console users)

### Frontend (modified)
- `frontend/src/App.tsx` — removed Navigate redirects for `ai-studio/embedded-assistant` and
  `studio/embedded-assistant`; both now mount `<EmbeddedAssistantPage />`
- `frontend/src/components/layout/Layout.tsx` — added `Code2` icon to lucide-react imports,
  added sidebar entry under AI Studio: `{ to: '/ai-studio/embedded-assistant', label: 'Embedded Assistant', icon: Code2 }`

### Backend (modified)
- `backend/app/api/embedded.py`:
  - Added `Request` to fastapi imports
  - Added new `GET /api/embedded/preview.html` endpoint (~110 LOC) that:
    - Reads 11 query params (agent, patientId, patientName, encounterId, token, primaryColor,
      aiChat, documentFeedback, virtualMode, showNavigation, dictationLanguage, interfaceLanguage)
    - Returns auto-configuring HTML page that bootstraps the widget through the
      Corti-compatible method chain (auth → configureSession → configure → show)
    - Forwards every `embedded-event` from widget to parent via `window.parent.postMessage({source: 'icoder-embedded', name, payload, meta}, '*')`
  - Fixed f-string SyntaxError (`{}` in template literal interpreted as substitution;
    replaced with empty string)

### Backend tests (drift fix)
- `backend/tests/test_api/test_phase7_gate1_examples_mount.py` — bumped expected version
  from `1.0.0-phase7-gate1` → `1.0.0-phase7-gate6` (matches the Gate 6 bump in
  `examples.py:_DEMO_VERSION` that was never propagated to the test)
- `packages/icoder-embedded/demos/{cdi,drg-dip,medical-coding}-demo.html` — bumped
  `<meta name="version">` from `1.0.0-phase7-gate1` → `1.0.0-phase7-gate6` to match

## E2E verification (Playwright MCP, real Chrome)

Logged in as `g13user` → navigated to `http://localhost:3000/ai-studio/embedded-assistant`.

### Page renders (initial load)

✅ Sidebar entry "Embedded Assistant" present under AI Studio section
✅ Page header: "Embedded Assistant" + "Phase 7 Gate 13 · Corti-style parity" subtitle
✅ Reset button in top-right
✅ Preview pane with Desktop/Mobile toggle + Restart button
✅ iframe loaded — widget inside iframe shows:
   - iC icon, "iCoDer Assistant" title, "medical-coding-agent" subtitle
   - Patient chip: 张三, #P-2026-001
   - Three feature buttons: 审核编码 / 检查文档缺口 / DRG 分析
   - Chat textbox + send button
   - Status line: "widget ready — interactive"
✅ Event Inspector pane (collapsed) — "Credits consumed: N/A"
✅ Configuration pane — Settings tab active by default
✅ All 7 Settings controls rendered with correct defaults

### Settings → Code reactive verification

✅ Updated Patient Name: 张三 → 李四
✅ iframe `src` URLSearchParams updated to `patientName=%E6%9D%8E%E5%9B%9B` (李四)
✅ Switched to Code tab → JSON Config shows `"patientName": "李四"`
✅ Switched to HTML tab → snippet shows `name: "李四"` in configureSession call
✅ Switched to React tab → snippet shows `name: "李四"` in configureSession call
✅ All 3 generators live-update from Settings state

### Real DeepSeek E2E through the embedded widget

Sent message "左桡骨远端骨折" (left distal radius fracture) via widget chat input.
Real DeepSeek run completed in ~7 seconds.

**Agent response** (visible in widget chat history):
> 病历明确诊断为左桡骨远端骨折，使用精确编码S52.500x001，避免使用未特指编码。

(Medical record clearly diagnoses left distal radius fracture; use specific code
S52.500x001; avoid using unspecified codes.)

**Event Inspector captured 4 events**:

| Timestamp | Event | Payload |
|-----------|-------|---------|
| 14:30:33 | `message.received` | `{"role":"user","content":"左桡骨远端骨折"}` |
| 14:30:40 | `message.received` | `{"role":"agent","content":"病历明确诊断为左桡骨远端骨折..."}` |
| 14:30:40 | `run.completed` | `{"run_id":"run-ad3ea52d-136f-4e3c-a12a-a187c0aa0368","agent_id":"medical-coding-agent","trace_id":"trace-12ea8694993f452..."}` |
| 14:30:40 | `account.creditsConsumed` | `{"amount":0,"currency":"internal_credit","run_id":"run-ad3ea52d..."}` |

**Run IDs in iframe → parent forwarding pipeline**:

widget embedded-event → iframe `window.parent.postMessage({source:'icoder-embedded', name, payload, meta})` →
parent `message` listener in `EmbeddedAssistantPage.tsx` → `setEvents(...)` →
`<EventInspector events={events} creditsConsumed={...} />`

## iCoDer ADVANTAGES preserved

This page ships two Corti-parity-plus features that Corti's own equivalent lacks:

1. **Auto-wired access token from Console session** — Console users don't need to paste a
   JWT; `useAuthStore.accessToken` populates the iframe URL automatically. Corti's page
   requires manual paste.
2. **Unified envelope meta in Event Inspector** — every event carries
   `{eventId, sessionId, contextId}` for traceability. Corti's event log shows only
   `{name, payload}`.

## Test posture

- ✅ `npx tsc --noEmit` — 0 errors
- ✅ Phase 7 backend regression: **88/88 PASS** in 117.75s
  - test_phase7_gate1_examples_mount: 7/7
  - test_phase7_gate3_agent_run_idempotency: 14/14
  - test_phase7_gate4_run_cancel: 7/7
  - test_phase7_gate5_api_clients: 15/15
  - test_phase7_gate6_cors: 8/8
  - test_phase7_gate7_trace_token: 13/13
  - test_phase7_gate8_usage_api_client: 13/13
  - test_phase7_gate9_sse_run_events: 11/11
  - test_phase7_gate3_idempotency: 0 (utility tests counted elsewhere)
- ✅ Playwright MCP browser E2E — full configure → send-message → events-captured cycle verified

## Defects found and fixed in this gate

1. **`embedded.py` f-string SyntaxError** — `<icoder-embedded>{}</icoder-embedded>` in
   HTML template interpreted `{}` as f-string substitution. Fixed by removing the empty
   substitution (the original intent was just a placeholder text node, which isn't needed).
2. **`embedded.py` missing `Request` import** — the new `preview.html` endpoint depends on
   `fastapi.Request` for query string parsing but the import was missing. Added `Request`
   to the `from fastapi import` line.
3. **`EmbeddedAssistantPage.tsx` axios response shape** — `agentsApi.list()` returns
   `AxiosResponse<{agents, total}>`, not the bare data. Fixed via `(resp as any)?.data || resp`
   fallback to handle both shapes defensively.
4. **`EmbeddedAssistantPage.tsx` removed `oauthApi.getAccessToken()`** — that method doesn't
   exist. Replaced with `useAuthStore(s => s.accessToken)` which is the canonical source.
5. **`EmbeddedAssistantPage.tsx` toast signature** — `addToast(message, type)` takes 2 args;
   the page was calling it with a single object. Fixed both call sites in `copyCode`.
6. **Gate 1 test drift** — Gate 6 bumped `_DEMO_VERSION` from `phase7-gate1` to `phase7-gate6`
   in `backend/app/api/examples.py` but the version string in the 3 demo HTML files (under
   `packages/icoder-embedded/demos/`) and the test assertion in
   `test_phase7_gate1_examples_mount.py` were never updated. Bumped all 5 references to
   match. (Pre-existing drift, not Gate 13's fault, but found via Gate 13's regression run.)

## Why this matters

Phase 7's final verdict (PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION) is unchanged —
Gate 13 is bonus work that improves the Console-side developer experience without altering
the partner integration story. The next phase (partner integration validation in real
staging environments) can now reference a working in-product page that demonstrates every
configuration knob and lets customer success engineers copy a working snippet in any of
three flavors without ever opening a terminal.

## Files

- Screenshots:
  - `reports/phase7/phase7_gate13_page_initial.png` — page on initial load with widget live
  - `reports/phase7/phase7_gate13_full_e2e.png` — full E2E: message sent, agent response, events captured
- Source:
  - `frontend/src/pages/EmbeddedAssistantPage.tsx` (new, ~330 LOC)
  - `backend/app/api/embedded.py` (modified, +110 LOC for `preview.html` endpoint)
  - `frontend/src/App.tsx`, `frontend/src/components/layout/Layout.tsx` (route + sidebar wiring)
- Test fixes:
  - `backend/tests/test_api/test_phase7_gate1_examples_mount.py` (version bump)
  - `packages/icoder-embedded/demos/{cdi,drg-dip,medical-coding}-demo.html` (version bump)
