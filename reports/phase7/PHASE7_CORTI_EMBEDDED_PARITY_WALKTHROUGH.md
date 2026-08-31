# Phase 7 — Corti Embedded Assistant Walkthrough × iCoDer Parity Gap Report

**Date**: 2026-07-14
**Walker**: Claude (Playwright MCP, headed Chrome at 127.0.0.1:9222)
**Corti account**: songluhua@gmail.com, project `b8f8129a-c31d-407f-b723-6ecc592d31e4`
**Pages walked**: `/project/{id}/ai-studio/embedded-assistant` (full settings + 3 code sub-tabs + event inspector)

**Trigger**: User directive "iCoDer 的嵌入式集成要复刻 Corti，所以需要走查" — iCoDer's embedded integration must replicate Corti.

---

## 1. Corti page anatomy

URL: `https://console.corti.app/project/{project_id}/ai-studio/embedded-assistant`

Top bar (page-level, replaces default Home bar):
- Live cost counter `$0.000000` (6 decimals, button → opens detail)
- `Reset live cost` button
- Project credits `$48.09` → links to billing
- `Docs` link → `https://docs.corti.ai/assistant/welcome`

Body is a vertical stack of 3 panes:

### 1.1 Preview pane (top)

```
┌─────────────────────────────────────────────┐
│ Preview        [● Desktop ○ Mobile] [⏸]    │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │                                         │ │
│ │   <iframe src="https://                │ │
│ │     assistant.eu.corti.app">            │ │
│ │   (renders <corti-embedded>)            │ │
│ │   State: "Initializing..."              │ │
│ │                                         │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

- View toggle: 2 radio buttons (Desktop / Mobile)
- iframe loads the **region-prefixed** widget URL `https://assistant.eu.corti.app`
- Without auth: shows "Initializing..." indefinitely
- The `⏸` button (next to View toggle) is disabled in current state — likely "restart session" or "pause"

### 1.2 Event Inspector pane (middle, collapsible)

```
┌─────────────────────────────────────────────┐
│ ▼ Event Inspector       Credits consumed: $0│
│ ┌─────────────────────────────────────────┐ │
│ │ [All] [Config] [Events] [Errors]        │ │
│ │                          [Clear][Copy]  │ │
│ │                          [Download]     │ │
│ │ No messages yet                         │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

- 4 sub-tabs filter the message stream
- 3 toolbar buttons: Clear (wipe log), Copy (to clipboard), Download (as file)
- Empty state: "No messages yet"
- Header counter: live `$X` consumed since page load

### 1.3 Configuration pane (bottom, two radio tabs)

#### 1.3.1 Settings tab

```
Session defaults
  Primary spoken language [English (US) ▾]
  Default mode  ● In-person  ○ Virtual

Features
  Allow virtual mode          [ON ●]
  Show interaction title      [ON ●]
  Enable AI chat              [ON ●]
  Show document feedback      [ON ●]
  Enable template editor      [ON ●]
  Show navigation             [OFF ○]
  Show sync-document action   [OFF ○]

Appearance
  Primary color [#3C61DD ____] [↺ Reset]

Locale
  Interface language [Auto (browser default) ▾]
  Dictation language [English (US) ▾]

New to Embedded Assistant?  [Take a tour]  [Dismiss]
```

Each control has an info tooltip next to its label (e.g. `defaultLanguage` `defaultMode` `aiChat` etc.) — these match the JS API field name. Changing a control **immediately** propagates to the live Preview iframe (via `assistant.configure(...)`).

#### 1.3.2 Code tab (3 sub-tabs)

**HTML (web component)** — Copy-able snippet:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    corti-embedded { width: 100%; height: 100vh; }
  </style>
</head>
<body>
  <corti-embedded id="corti-assistant"
    baseURL="https://assistant.eu.corti.app"></corti-embedded>
  <script type="module">
    import '@corti/embedded-web';
    const TENANT = "base";
    const ENVIRONMENT = "eu";
    const assistant = document.getElementById('corti-assistant');
    assistant.addEventListener('ready', async () => {
      try {
        await assistant.auth({
          access_token: 'YOUR_ACCESS_TOKEN',
          refresh_token: 'YOUR_REFRESH_TOKEN',
          token_type: 'bearer',
          mode: 'stateless',
        });
        await assistant.configureSession({
          defaultLanguage: "en",
          defaultMode: "in-person",
          defaultOutputLanguage: "en",
          defaultTemplateKey: "corti-patient-summary-legacy",
        });
        await assistant.configure({
          features: { aiChat: true, documentFeedback: true, ... },
          locale: { dictationLanguage: "en", interfaceLanguage: "auto" },
        });
        await assistant.show();
      } catch (error) { console.log('Initialization error:', error); }
    });
    assistant.addEventListener('embedded-event', (e) => {
      const { name, payload } = e.detail;
      switch (name) {
        case 'account.creditsConsumed': console.log('Credits consumed:', payload); break;
        case 'error.triggered':         console.log('Error:', payload); break;
        default:                        console.log(name, payload);
      }
    });
  </script>
</body>
</html>
```

**React** — Copy-able snippet:

```tsx
import { useRef, useCallback } from "react";
import { CortiEmbeddedReact, type CortiEmbeddedReactRef } from "@corti/embedded-web/react";

const TENANT = "base";
const ENVIRONMENT = "eu";

async function fetchCredentials() {
  const response = await fetch("/api/auth/token");
  return response.json();
}

function App() {
  const cortiRef = useRef<CortiEmbeddedReactRef>(null);

  const handleReady = useCallback(async () => {
    const ref = cortiRef.current;
    if (!ref) return;
    const credentials = await fetchCredentials();
    ref.auth(credentials);
    ref.configureSession({
      defaultLanguage: "en", defaultMode: "in-person",
      defaultOutputLanguage: "en",
      defaultTemplateKey: "corti-patient-summary-legacy",
    });
    ref.configure({
      features: { aiChat: true, documentFeedback: true, ... },
      locale: { dictationLanguage: "en", interfaceLanguage: "auto" },
    });
    ref.show();
  }, []);

  const handleEvent = useCallback(
    (event: CustomEvent<{ name: string; payload: unknown }>) => {
      const { name, payload } = event.detail;
      switch (name) {
        case "account.creditsConsumed": console.log("Credits consumed:", payload); break;
        case "error.triggered":         console.log("Error:", payload); break;
        default:                        console.log(name, payload);
      }
    }, []
  );

  return (
    <CortiEmbeddedReact
      ref={cortiRef}
      baseURL="https://assistant.eu.corti.app"
      onReady={handleReady}
      onEvent={handleEvent}
      style={{ width: "100%", height: "600px" }}
    />
  );
}
```

**JSON Config** — Copy-able snippet, mirrors the Settings tab:

```json
{
  "interface": {
    "appearance": { "primaryColor": null },
    "features": {
      "aiChat": true,
      "documentFeedback": true,
      "interactionTitle": true,
      "navigation": false,
      "syncDocumentAction": false,
      "templateEditor": true,
      "virtualMode": true
    },
    "locale": { "dictationLanguage": "en", "interfaceLanguage": "auto" }
  },
  "session": {
    "defaultLanguage": "en",
    "defaultMode": "in-person",
    "defaultOutputLanguage": "en",
    "defaultTemplateKey": "corti-patient-summary-legacy"
  }
}
```

All 3 code snippets are **generated dynamically from the Settings tab state** — toggling a feature immediately re-renders all 3 code blocks. The Copy button copies the currently-visible snippet.

---

## 2. API surface observed (Corti widget)

| Method | Signature | Notes |
|---|---|---|
| `auth` | `{access_token, refresh_token, token_type, mode}` | `refresh_token` included |
| `configureSession` | `{defaultLanguage, defaultMode, defaultOutputLanguage, defaultTemplateKey}` | No patient fields |
| `configure` | `{features, locale}` | See Features toggle list above |
| `show` | `()` | Triggers actual UI render |
| Event `embedded-event` | `{name, payload}` | 2-field detail only |

Event names visible in sample code: `account.creditsConsumed`, `error.triggered`, plus default fallback.

---

## 3. iCoDer current state

### 3.1 What we DO have

| Component | Path | Status |
|---|---|---|
| Web Component (widget) | `packages/icoder-embedded/src/icoder-assistant.ts` | Corti-compatible since Phase 4-D |
| Compiled dist | `packages/icoder-embedded/dist/icoder-assistant.js` | Built today (Gate 6) |
| Backend serve | `/api/embedded/assistant.js` | Dist-serve, set up Phase 6 Gate 1 |
| SDK package | `packages/icoder-sdk/` (@icoder/sdk@1.0.0-beta.2) | Phase 6 Gate 4 |
| 3 partner demos | `/examples/medical-coding/`, `/examples/cdi/`, `/examples/drg-dip/` | Phase 6 Gate 7 + Phase 7 Gate 1 |
| EventInspector component | `frontend/src/components/common/EventInspector.tsx` | Existed since Phase 3-F |
| WorkbenchLayout | `frontend/src/components/layout/WorkbenchLayout.tsx` | 2-pane shell |
| 9-red-line PHI safety | widget JSDoc + `clearPatientContext()` | Phase 6 Gate 2 |

### 3.2 What we DON'T have (parity gaps)

**Critical** (page itself missing):

| Item | Corti | iCoDer | Fix |
|---|---|---|---|
| `/ai-studio/embedded-assistant` page | Full page | **REDIRECT to `/ai-studio/agents`** (`App.tsx:86, 108`) | Build new page |

The redirect currently sends partners to the Agents list, which is the wrong mental model. Partners expect a single configuration page where they can:
1. Preview the widget live
2. Toggle features and see the code update
3. Copy a ready-to-paste snippet (HTML / React / JSON)
4. Watch events stream in from their test interactions

**Major** (page contents, ranked by partner value):

| Item | Priority | Effort |
|---|---|---|
| Live Preview iframe pointing to widget | P0 | S — iframe `/examples/medical-coding/` or build a dedicated `/preview` route that loads `/api/embedded/assistant.js` with the current settings |
| Settings tab with 11 controls (Session defaults / Features / Appearance / Locale) | P0 | M — straightforward React form, mirror Corti's structure |
| Code tab with 3 sub-tabs (HTML / React / JSON) generated from Settings | P0 | M — code generators that read the form state |
| Copy button on each code sub-tab | P0 | S — `navigator.clipboard.writeText` |
| Event Inspector pane wired into page | P1 | S — component exists; just mount it with the right event source |
| Live cost counter + Reset button in page header | P1 | S — Home page already has this pattern (TopBar live cost) |
| Desktop / Mobile preview toggle | P2 | S — width breakpoint switch on iframe |
| Tour banner ("New to Embedded Assistant?") | P3 | XS — optional polish |
| Per-field info tooltip with JS API name | P2 | S — pattern from Corti: `<label> Friendly name <tooltip>i</tooltip> <code>fieldName</code>` |

**Minor** (API surface differences that are iCoDer advantages, not gaps):

| Item | Corti | iCoDer |
|---|---|---|
| `configureSession` patient fields | Not in sample | We accept `patientId`, `name`, `encounterId` — surface these in our Settings tab |
| Event envelope | `{name, payload}` | We emit `{name, payload, meta}` with `meta.contextId / eventId / sessionId / timestamp / version` — document this |
| `trace_url` | No event for it | We emit `run.completed` carrying `trace_url` — Corti has nothing equivalent |
| `patient.context.cleared` / `session.cleared` | No events | We emit them on `clearPatientContext()` / `clearSession()` |
| Regions supported | 3 (EU/US/CN) | 3 via `ICODER_ENVIRONMENT` |

---

## 4. Recommended build sequence

**Goal**: replace the redirect at `/ai-studio/embedded-assistant` with a Corti-parity page that lets partners self-serve integrate the widget without reading docs.

### Step 1 — Page skeleton + Settings tab (P0, ~3-4h)

- New file: `frontend/src/pages/EmbeddedAssistantPage.tsx`
- Remove `<Route path="ai-studio/embedded-assistant" element={<Navigate to="/ai-studio/agents" replace />} />` from `App.tsx:86` and `App.tsx:108`
- Add `<Route path="ai-studio/embedded-assistant" element={<EmbeddedAssistantPage />} />`
- 4 sections in a single scrollable column: Session defaults / Features / Appearance / Locale
- Each control has: friendly label + info tooltip showing JS API field name + the actual input
- React state lifts all values into a single `config` object

### Step 2 — Live Preview iframe (P0, ~1-2h)

- New backend route: `GET /api/embedded/preview.html` returning a self-contained HTML that:
  - Imports `/api/embedded/assistant.js`
  - Reads query params `?primaryColor=...&aiChat=...&defaultMode=...` etc.
  - Calls `assistant.configure(...)` with those values
  - Auto-auths using the current Console JWT (so the iframe "just works" for the logged-in admin)
- Frontend: iframe with `src={/api/embedded/preview.html?...}` rebuilt whenever Settings change (debounced 250ms)
- Desktop/Mobile toggle: just swap iframe width between 100% and 390px

### Step 3 — Code tab with 3 generators + Copy (P0, ~2-3h)

- Sub-tabs: HTML / React / JSON Config (radix tabs)
- Each sub-tab is a `<pre><code>{generated}</code></pre>` block
- Generators are pure functions taking `config` state → string
- Copy button uses `navigator.clipboard.writeText(generated)`
- The HTML generator should include the JS API call sequence: `auth → configureSession → configure → show` plus the `embedded-event` listener

### Step 4 — Event Inspector wiring (P1, ~1h)

- Mount existing `EventInspector.tsx` in a collapsible pane between Preview and Configuration
- Listen to the iframe's `window.postMessage` events forwarded from the widget
- Or — easier — have the iframe post messages up to the parent via `window.parent.postMessage`

### Step 5 — Page header live cost (P1, ~30min)

- Reuse the TopBar live cost pattern from HomePage
- Add "Reset live cost" button

### Step 6 — Mobile preview toggle + tour banner + tooltips (P2-P3, ~1h)

- Mobile/Desktop radio toggle
- "Take a tour" → links to a docs page
- Each setting label has an `i` tooltip with the JS API field name

**Total estimate**: ~10h for full Corti parity on this single page.

---

## 5. Screenshots captured

| File | What |
|---|---|
| `corti_embedded_assistant_code_html.png` | Code tab, HTML sub-tab |
| `corti_embedded_assistant_react_tab.png` | Code tab, React sub-tab |
| `corti_embedded_assistant_event_inspector.png` | Event Inspector expanded, JSON Config sub-tab visible |
| `corti_embedded_assistant_settings_tab.png` | Settings tab full view |

All screenshots at repo root (working dir = `E:\Corti4C\backend`).

---

## 6. Action requested

This is a **gap-report**, not an implementation. The next decision point:

| Option | What |
|---|---|
| A | Implement Steps 1+2+3 (P0) now as Phase 7 Gate 13 "Embedded Assistant Parity Page" — adds ~6-8h to Phase 7 |
| B | Defer to Phase 8 (post-Phase-7) — Phase 7 stays focused on Gates 0-12 acceptance, parity page ships after |
| C | Build only the minimum (Step 1 + Step 3 HTML-only) — ~3h, covers the most common partner question "where do I copy the snippet from?" |

User to pick. The current Phase 7 brief doesn't require this page — Gates 0-12 don't reference it. But "复刻 Corti" directive suggests it should be on the roadmap somewhere.
