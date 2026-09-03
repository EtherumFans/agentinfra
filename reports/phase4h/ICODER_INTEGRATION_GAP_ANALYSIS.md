# Phase 4-H §11 — iCoDer Integration Gap Analysis

**Audit date:** 2026-07-10
**Companion file:** `CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` (Corti side)
**Source PDF:** `Phase 4-H Audit Report.pdf` §11
**Dev mode:** FROZEN per §2.1 — this is a READ-ONLY gap analysis. No code changes.

---

## Executive Summary

iCoDer has **more parity than initially apparent** — the gap is **API surface conformance + polish**, not feature absence. The core building blocks already exist:

| Corti feature | iCoDer status | File / Evidence |
|---|---|---|
| Developer Quickstart wizard (3-step) | ✅ **EXISTS** | `frontend/src/pages/DeveloperQuickstartPage.tsx` (330 LOC, 4 tabs) |
| 4 use cases (dictation/scribe/coding/chat) | ✅ **EXISTS** | Same file lines 53-58 |
| 4 AI tool deep links (Claude/Cursor/Codex/Lovable) | ✅ **EXISTS** | Same file lines 12-14 |
| "Copy all as .env" button | ✅ **EXISTS in Quickstart** | Same file line 158, 176, 207 |
| Agent Skills program (4 SKILL.md) | ✅ **EXISTS** | `public/.well-known/agent-skills/{icoder-chat,icoder-coding,icoder-dictation,icoder-scribe}/SKILL.md` |
| Web Component source | ✅ **EXISTS** | `packages/icoder-embedded/src/icoder-assistant.ts` (300 LOC) |
| `@icoder/embedded` npm package config | ✅ **EXISTS** | `packages/icoder-embedded/package.json` (Apache-2.0, v1.0.0) |
| Backend Web Component JS endpoint | ✅ **EXISTS** | `backend/app/api/embedded.py` (`/api/embedded/assistant.js` + `/api/embedded/preview`) |
| API Client page (OAuth2) | ✅ **EXISTS** | `frontend/src/pages/APIClientsPage.tsx` (207 LOC) |
| api_client_id in trace metadata | ✅ **EXISTS (Phase 4-G)** | memory `project_phase4_g_live_cost_api_client_runhistory_fork_2026_07_10.md` |
| RunHistory table | ✅ **EXISTS (Phase 4-G)** | Same memory |
| Live cost counter (TopBar) | ✅ **EXISTS (Phase 4-G)** | Same memory |
| trace_events[] persistence | ✅ **EXISTS (Phase 4-F2)** | memory `project_phase4_f2_a2a_unified_run_2026_07_10.md` |

**iCoDer ADVANTAGES vs Corti:**

| iCoDer feature | Corti status |
|---|---|
| API Playground tab (live request/response tester) | Corti Quickstart lacks — only AI prompt + SDK |
| 4 SKILL.md files published (icoder-chat/coding/dictation/scribe) | Corti has 2+ skills (corti-medical-coding confirmed; corti-dictation inferred) — both at ~equal |
| Explicit `setPatientContext({patientId, name, encounterId})` method | Corti only has `defaultTemplateKey` — no explicit patient ID |
| RunHistory server-side event log | Corti lacks server-side event log (only client-side `embedded-event`) |
| OpenAPI auto-docs at `/docs` | Corti relies on SDK + Skills |
| `agent-ref` attribute on Web Component (select agent at embed time) | Corti selects agent via Console config, not at embed time |

**iCoDer GAPS vs Corti:**

| Gap | Severity | Files to modify |
|---|---|---|
| 1. Web Component API does NOT match Corti's surface | **P1** | `packages/icoder-embedded/src/icoder-assistant.ts` |
| 2. `@icoder/embedded` not published to npm | **P1** | CI/CD pipeline |
| 3. No "Regenerate client secret" button | **P2** | `frontend/src/pages/APIClientsPage.tsx` |
| 4. No "Show client secret" on-demand reveal | **P2** | Same |
| 5. No "Copy all as .env" button on API Client page (only in Quickstart) | **P3** | Same |
| 6. No Theme (Primary color picker) on Web Component | **P2** | `packages/icoder-embedded/src/icoder-assistant.ts` |
| 7. No Locale (Interface language + Dictation language) config | **P2** | Same |
| 8. No `features.aiChat` / `features.templateEditor` / `features.virtualMode` feature flags | **P2** | Same |
| 9. No `configureSession({defaultTemplateKey})` method | **P3** | Same |
| 10. No `account.creditsConsumed` event subtype (only `coding.completed`) | **P2** | Same |
| 11. No `error.triggered` event subtype (only `error`) | **P3** | Same |
| 12. No `.NET SDK` actual package (only sample code in Quickstart) | **P3** | New repo `icoder-dotnet-sdk` |
| 13. No `curl` code tab in Quickstart (only JS + .NET + AI Tools + Playground) | **P3** | `frontend/src/pages/DeveloperQuickstartPage.tsx` |
| 14. No Python SDK | **P3** | New repo `icoder-python-sdk` |

---

## §11.1 — Server-side API Integration: iCoDer parity check

| # | Corti item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Org identity (tenantName) | ✅ **MATCH** — iCoDer has Environment (EU/US/CN) → Tenant (医院) → API Client per CLAUDE.md | CLAUDE.md cloud architecture |
| 2 | API Client identity (clientId + clientSecret + OAuth2 Client Credentials) | ✅ **MATCH** — `oauthApi.create(name, desc, scopes)` returns `client_id` + `client_secret` per `APIClientsPage.tsx` line 40-43 | `frontend/src/pages/APIClientsPage.tsx` |
| 3 | End-user identity (embedded ROPC) | ✅ **MATCH** — iCoDer Web Component accepts `access-token` attribute; iCoDer has 2 default client types (backend-service + ROPC embedded) per CLAUDE.md | CLAUDE.md + `embedded.py` line 50 |
| 4 | Patient ID | ✅ **ADVANTAGE** — iCoDer has explicit `setPatientContext({patientId, name, encounterId})` method; Corti only has `defaultTemplateKey` | `packages/icoder-embedded/src/icoder-assistant.ts` line 217 |
| 5 | Encounter ID | ✅ **MATCH** — iCoDer `setPatientContext({encounterId})` carries encounter ID | Same |
| 6 | Request ID (per-call traceable) | ✅ **ADVANTAGE** — iCoDer has `trace_id` in unified envelope (Phase 4-F2); Corti has no `X-Request-Id` in sample | memory `project_phase4_f2_a2a_unified_run_2026_07_10.md` |
| 7 | Context ID (session-scoped) | ⚠️ **PARTIAL** — iCoDer has `contextId` in A2A spec (memory `E--Corti4C-docs-ICODER_V1_CONTEXT_SPEC.md`) but not exposed in Web Component API | Context spec doc |
| 8 | Agent Version (pin/fork/version) | ✅ **MATCH** — iCoDer `agent_ref` attribute accepts `medical-coding-agent-1.0.0` format with version suffix; Forked-from badge exists per Phase 4-G | `embedded.py` line 55-58 + Phase 4-G memory |
| 9 | Sync vs Async | ✅ **MATCH** — iCoDer unified endpoint `POST /api/v1/agents/{id}/run` is sync (Phase 4-F2); A2A `message/send` is sync | memory `project_phase4_f2_a2a_unified_run_2026_07_10.md` |
| 10 | Timeout | ❌ **GAP** — iCoDer does not expose `timeout` parameter in API Client page or SDK | `APIClientsPage.tsx` |
| 11 | Retry | ❌ **GAP** — iCoDer does not expose retry config or idempotency key | Same |
| 12 | Result Schema | ✅ **MATCH** — iCoDer unified envelope has 13 fields (Phase 4-F2) vs Corti's 16 fields; covers `summary`, `evidence[]`, `manual_review_required`, `trace_events[]`, `error`, `error_reason` | memory `project_phase4_f2_a2a_unified_run_2026_07_10.md` |
| 13 | Trace | ✅ **ADVANTAGE** — iCoDer `include_trace` parameter in unified endpoint + trace_events persisted to RunTraceStore; Corti trace is Console-only | Same |
| 14 | Error | ✅ **MATCH** — iCoDer structured error contract `{error: true, error_reason: "llm_call_failed"/"unknown_agent"/"runtime_crash"}` per Phase 4-F plan §9.4 | Plan file `jolly-bubbling-swing.md` |
| 15 | Cost | ✅ **MATCH** — iCoDer live cost counter in TopBar (Phase 4-G); per-run cost in trace metadata; `account.creditsConsumed`-equivalent server-side | memory `project_phase4_g_live_cost_api_client_runhistory_fork_2026_07_10.md` |
| 16 | Audit | ✅ **ADVANTAGE** — iCoDer has AuditLog + RunHistory (Phase 4-G) + trace_events persisted server-side; Corti has `/usage` + `/billing` but no audit log search | Same |

### §11.1 verdict

iCoDer **matches or exceeds** Corti on §11.1 server-side API integration. Notable:
- ✅ **iCoDer ADVANTAGE** on Patient ID (#4), Request ID (#6), Trace (#13), Audit (#16)
- ❌ **iCoDer GAP** on Timeout (#10) + Retry (#11) — but Corti doesn't expose these either, so this is a **shared gap, not a regression**

---

## §11.2 — Frontend Embedding: iCoDer parity check

### Existing iCoDer Web Component API (from `packages/icoder-embedded/src/icoder-assistant.ts`)

```html
<icoder-assistant
  id="assistant"
  base-url="http://localhost:8000"
  agent-ref="medical-coding-agent-1.0.0"
  theme="light"
  access-token="..."
></icoder-assistant>

<script type="module">
import { iCoDerAssistant } from '/api/embedded/assistant.js';
const el = document.getElementById('assistant');
el.setPatientContext({ patientId: 'P001', name: '张三', encounterId: 'E001' });
el.addEventListener('ready', () => console.log('ready'));
el.addEventListener('coding.completed', e => console.log('coding', e.detail));
el.addEventListener('error', e => console.error('error', e.detail));
</script>
```

### Corti Web Component API (from `outputs/phase4h/api_samples/corti_embedded_web_component.md`)

```html
<corti-embedded
  id="corti-assistant"
  baseURL="https://assistant.eu.corti.app"
></corti-embedded>

<script type="module">
import '@corti/embedded-web';
const assistant = document.getElementById('corti-assistant');
assistant.addEventListener('ready', async () => {
  await assistant.auth({ access_token, refresh_token, token_type: 'bearer', mode: 'stateless' });
  await assistant.configureSession({ defaultLanguage, defaultMode, defaultOutputLanguage, defaultTemplateKey });
  await assistant.configure({ features: { aiChat, documentFeedback, ... }, locale: { ... } });
  await assistant.show();
});
assistant.addEventListener('embedded-event', (e) => {
  const { name, payload } = e.detail;
  switch (name) {
    case 'account.creditsConsumed': ...
    case 'error.triggered': ...
  }
});
</script>
```

### API surface comparison (13 items)

| # | Corti feature | iCoDer status | Gap severity |
|---|---|---|---|
| 1 | iframe | NOT OBSERVED (Corti doesn't use) | ✅ MATCH — iCoDer also uses Web Component, no iframe |
| 2 | Web Component `<corti-embedded>` | iCoDer has `<icoder-assistant>` (different tag name, but same concept) | ⚠️ **P3** — tag name differs; if matching Corti exactly, should rename to `<icoder-embedded>` |
| 3 | JS SDK `@corti/embedded-web` (npm) | iCoDer has `@icoder/embedded` package config but NOT published to npm; served via `/api/embedded/assistant.js` endpoint | ⚠️ **P1** — must publish to npm for true 3rd-party embeddability |
| 4 | React Component | Corti doesn't have either | ✅ MATCH (both lack) |
| 5 | Embedded Chat (`features.aiChat: true`) | iCoDer Web Component has built-in chat UI (input + send button per source line 180-181) but NO toggle to disable; always on | ⚠️ **P2** — need `features.aiChat` flag |
| 6 | Embedded Agent | iCoDer `agent-ref` attribute selects agent at embed time — iCoDer ADVANTAGE | ✅ iCoDer ADVANTAGE |
| 7 | Theme (Primary color #3C61DD via Appearance tab) | iCoDer has `theme="light"` / `theme="dark"` select only — no custom Primary color picker | ⚠️ **P2** — need custom color picker |
| 8 | Locale (Interface language Auto + Dictation language) | iCoDer has NO locale config in Web Component | ⚠️ **P2** — need `locale: {interfaceLanguage, dictationLanguage}` |
| 9 | SSO (`assistant.auth({access_token, refresh_token, mode:'stateless'})`) | iCoDer uses `access-token` attribute (string) — no `refresh_token`, no `mode`, no `token_type` | ⚠️ **P2** — should add `assistant.auth()` method matching Corti signature |
| 10 | Current Patient Context (`defaultTemplateKey`) | iCoDer has `setPatientContext({patientId, name, encounterId})` — iCoDer ADVANTAGE (more explicit) | ✅ iCoDer ADVANTAGE |
| 11 | Current User Context (`mode: 'stateless'` + access_token) | iCoDer uses `access-token` attribute (assumes stateless) — implicit | ⚠️ **P3** — should expose `mode` field |
| 12 | Callback (`addEventListener('ready', ...)`) | iCoDer has `addEventListener('ready', ...)` — ✅ MATCH | ✅ MATCH |
| 13 | Event Listener (`embedded-event` with `{name, payload}`) | iCoDer emits `coding.completed` + `error` directly (no `embedded-event` envelope); no `account.creditsConsumed` equivalent | ⚠️ **P2** — should emit unified `embedded-event` with `{name, payload}` and add `account.creditsConsumed` |

### §11.2 verdict

iCoDer Web Component **works but does NOT match Corti's API surface**. The iCoDer Web Component uses a **attribute-based config** pattern, while Corti uses a **method-call config** pattern (`assistant.auth()` / `assistant.configureSession()` / `assistant.configure()` / `assistant.show()`).

**Decision required:** Should iCoDer:
- (A) **Mirror Corti's API surface exactly** — rename `<icoder-assistant>` → `<icoder-embedded>`, add `assistant.auth()` / `configureSession()` / `configure()` / `show()` methods, emit unified `embedded-event` with `account.creditsConsumed` + `error.triggered` subtypes. **Recommended** per memory `feedback_agent_pages_replicate_corti.md` ("智能体页面必须 1:1 复刻 Corti UI/IA/流程").
- (B) **Keep current iCoDer API** — simpler attribute-based config, but breaks Corti parity.

Per CLAUDE.md "iCoDer 复刻方向" + memory `feedback_corti_alignment.md`, recommendation is **(A) mirror Corti**. This is a **P1 Phase 5 task**.

---

## §11.3 — Event-driven Integration: iCoDer parity check

| # | Corti feature | iCoDer status | Gap severity |
|---|---|---|---|
| 1 | Webhook (server-side HTTP callback) | ❌ NOT OBSERVED in iCoDer either — iCoDer is also pull-only by design (matches Corti) | ✅ MATCH (both lack, by design) |
| 2 | Background Run | ❌ NOT OBSERVED | ✅ MATCH (both lack) |
| 3 | Async Job | ❌ NOT OBSERVED | ✅ MATCH (both lack) |
| 4 | Callback URL | ❌ NOT OBSERVED | ✅ MATCH (both lack) |
| 5 | Event Subscription (server-side) | ✅ **ADVANTAGE** — iCoDer has RunHistory table (Phase 4-G) + trace_events persisted server-side; Corti has only client-side `embedded-event` | ✅ iCoDer ADVANTAGE |
| 6 | Run Completed Event | ✅ **ADVANTAGE** — iCoDer `coding.completed` event (Web Component) + RunHistory status field (server-side) | ✅ iCoDer ADVANTAGE |
| 7 | Tool Call Event | ❌ NOT OBSERVED in iCoDer Web Component (tool calls visible in RunTrace page server-side) | ⚠️ **P3** — could add `tool.call` event to Web Component |
| 8 | Error Event (`error.triggered`) | ⚠️ PARTIAL — iCoDer has `error` event (different name); should rename to `error.triggered` for Corti parity | ⚠️ **P3** |

### §11.3 verdict

iCoDer **matches Corti on event-driven integration** — both are pull-only by design (no server-side webhooks). iCoDer has an **ADVANTAGE** on server-side event log (RunHistory + trace_events).

---

## §11.4 — Writeback Flow: iCoDer parity check

| # | Corti feature | iCoDer status | Gap severity |
|---|---|---|---|
| 1 | Server-initiated writeback (Corti pushes to EHR) | NOT OBSERVED in Corti (pull-only by design) | ✅ MATCH — iCoDer also pull-only |
| 2 | Client-initiated writeback (client calls API, writes back to own EHR) | ✅ MATCH — iCoDer `POST /api/v1/agents/{id}/run` returns result; client writes back to own HIS | ✅ MATCH |

### §11.4 verdict

iCoDer **matches Corti exactly** on writeback model — both are **strictly pull-only**. No gap.

---

## Per-item gap inventory (priority-ordered for Phase 5)

### P1 — Critical for Corti parity

#### GAP-11-01: Web Component API surface does NOT match Corti

**Current state:** iCoDer `<icoder-assistant>` uses attribute-based config:
- `base-url` + `access-token` + `agent-ref` + `theme` attributes
- `setPatientContext()` method
- Emits `ready` / `coding.completed` / `error` events

**Corti state:** `<corti-embedded>` uses method-call config:
- `baseURL` attribute (URL only)
- `assistant.auth({access_token, refresh_token, token_type, mode})` method
- `assistant.configureSession({defaultLanguage, defaultMode, defaultOutputLanguage, defaultTemplateKey})` method
- `assistant.configure({features, locale})` method
- `assistant.show()` method
- Emits `ready` + `embedded-event` (with `{name, payload}` envelope, subtypes `account.creditsConsumed` + `error.triggered`)

**Files to modify:**
- `packages/icoder-embedded/src/icoder-assistant.ts` — rewrite to match Corti API:
  - Rename tag to `<icoder-embedded>` (per Corti convention)
  - Add `assistant.auth({access_token, refresh_token, token_type, mode})` method
  - Add `assistant.configureSession({defaultLanguage, defaultMode, defaultOutputLanguage, defaultTemplateKey})` method (iCoDer: add `patientId` + `encounterId` as explicit fields per iCoDer ADVANTAGE)
  - Add `assistant.configure({features: {aiChat, documentFeedback, interactionTitle, navigation, syncDocumentAction, templateEditor, virtualMode}, locale: {dictationLanguage, interfaceLanguage}})` method
  - Add `assistant.show()` / `assistant.hide()` methods
  - Replace `coding.completed` + `error` events with unified `embedded-event` with `{name, payload}` envelope
  - Add event subtypes: `account.creditsConsumed` + `error.triggered` + `run.completed` + `tool.call` (bonus)
- `backend/app/api/embedded.py` — update preview page to use new API
- `frontend/src/pages/AgentChatPage.tsx` — if it references old Web Component API, update

**Estimated effort:** 4-6 hours

**Test:** `packages/icoder-embedded/__tests__/` — write unit tests for new API surface; browser walkthrough with embedded preview page.

---

#### GAP-11-02: `@icoder/embedded` not published to npm

**Current state:** `packages/icoder-embedded/package.json` exists with name `@icoder/embedded` v1.0.0, but package is NOT published to npm registry. Consumers can't `npm install @icoder/embedded`.

**Files to modify:**
- Set up CI/CD pipeline to publish on release (GitHub Actions workflow)
- Add `README.md` to package
- Build `dist/` artifacts (run `tsc`)
- Publish to npm (requires npm account + scope ownership)

**Estimated effort:** 2-4 hours (once CI/CD set up)

---

### P2 — Polish for Corti parity

#### GAP-11-03: No "Regenerate client secret" button

**Current state:** iCoDer `APIClientsPage.tsx` has Copy + Delete actions, but NO Regenerate button.

**Corti state:** Corti has 4 action buttons per client: Copy Client ID / Regenerate client secret / Show client secret / Copy client secret / Copy environment ID / Copy tenant name / Copy all as .env.

**Files to modify:**
- `frontend/src/pages/APIClientsPage.tsx` — add Regenerate button per client row
- `backend/app/api/oauth.py` (or equivalent) — add `POST /api/oauth/clients/{id}/regenerate-secret` endpoint

**Estimated effort:** 2 hours

---

#### GAP-11-04: No "Show client secret" on-demand reveal for existing clients

**Current state:** iCoDer shows client secret ONCE at creation time (line 66-82 of `APIClientsPage.tsx`), then it's never retrievable again.

**Corti state:** Corti shows masked secret `tFV5••••••••••••••••` by default, with "Show client secret" button to reveal on-demand (re-masked after).

**Files to modify:**
- `frontend/src/pages/APIClientsPage.tsx` — store masked secret per client; add Show/Hide toggle
- `backend/app/api/oauth.py` — return masked secret in list response; add `GET /api/oauth/clients/{id}/secret` endpoint for reveal (with audit log)

**Note:** This is a security trade-off. Corti's "show on-demand" is more convenient but increases risk of secret leakage. iCoDer's "show once only" is more secure. **Decision required:** match Corti (convenience) or keep current (security).

**Estimated effort:** 3 hours

---

#### GAP-11-05: No Theme (Primary color picker) on Web Component

**Current state:** iCoDer Web Component has `theme="light"` / `theme="dark"` select only.

**Corti state:** Corti Appearance tab has Primary color picker (`#3C61DD` default) — full HSL color wheel.

**Files to modify:**
- `packages/icoder-embedded/src/icoder-assistant.ts` — accept `--icoder-primary` CSS variable; add Primary color picker to preview page
- `backend/app/api/embedded.py` — add color picker to preview page

**Estimated effort:** 2 hours

---

#### GAP-11-06: No Locale config on Web Component

**Current state:** iCoDer Web Component has no locale config.

**Corti state:** Corti has Interface language (Auto / browser default) + Dictation language (English US).

**Files to modify:**
- `packages/icoder-embedded/src/icoder-assistant.ts` — add `locale: {interfaceLanguage, dictationLanguage}` to `configure()` method
- `backend/app/api/embedded.py` — add locale selectors to preview page

**Note:** iCoDer being CN-market-focused, default should be 简体中文 / 中文 (普通话). English/US as secondary.

**Estimated effort:** 2 hours

---

#### GAP-11-07: No `features.*` feature flags on Web Component

**Current state:** iCoDer Web Component is always-on (chat UI always visible).

**Corti state:** Corti has 7 feature flags: `aiChat` / `documentFeedback` / `interactionTitle` / `navigation` / `syncDocumentAction` / `templateEditor` / `virtualMode`.

**Files to modify:**
- `packages/icoder-embedded/src/icoder-assistant.ts` — add `features` object to `configure()` method; conditionally render chat / document feedback / template editor / etc.

**Estimated effort:** 3 hours

---

#### GAP-11-08: No `account.creditsConsumed` event subtype

**Current state:** iCoDer emits `coding.completed` event (run-completed).

**Corti state:** Corti emits unified `embedded-event` with `{name, payload}` envelope, subtypes include `account.creditsConsumed` (cost callback).

**Files to modify:**
- `packages/icoder-embedded/src/icoder-assistant.ts` — replace direct `coding.completed` event with unified `embedded-event`; add `account.creditsConsumed` subtype (pull cost from API response)

**Estimated effort:** 1 hour (subsumed by GAP-11-01)

---

### P3 — Minor polish

#### GAP-11-09: No "Copy all as .env" button on API Client page

**Current state:** iCoDer has "Copy all as .env" in DeveloperQuickstartPage (line 158, 176, 207), but NOT on APIClientsPage.

**Corti state:** Corti has it on the API Client detail panel.

**Files to modify:**
- `frontend/src/pages/APIClientsPage.tsx` — add "Copy all as .env" button per client row

**Estimated effort:** 30 minutes

---

#### GAP-11-10: No `error.triggered` event subtype name match

**Current state:** iCoDer emits `error` event.

**Corti state:** Corti emits `error.triggered` (dot-namespaced).

**Files to modify:** Same as GAP-11-01 — rename `error` → `error.triggered` in unified `embedded-event` envelope.

**Estimated effort:** subsumed by GAP-11-01

---

#### GAP-11-11: No `curl` code tab in Quickstart

**Current state:** iCoDer Quickstart has 4 tabs: AI Tools / JS SDK / .NET SDK / API Playground.

**Corti state:** Corti Quickstart has 2 SDK tabs (JS + .NET). iCoDer has 4 tabs (more) but no `curl` tab.

**Decision:** iCoDer's API Playground tab is **better than curl** — it's interactive. **No change needed** — iCoDer ADVANTAGE.

**Estimated effort:** 0 (no change)

---

#### GAP-11-12: No Python SDK

**Current state:** iCoDer has JS + .NET SDK samples in Quickstart, but no Python SDK.

**Corti state:** Corti has JS + .NET only — also no Python.

**Decision:** Match Corti (don't add Python). iCoDer has `/docs` OpenAPI auto-docs which can generate Python client via `openapi-generator`. **No change needed**.

**Estimated effort:** 0 (no change)

---

#### GAP-11-13: No actual `.NET SDK` package (only sample code)

**Current state:** iCoDer Quickstart shows `dotnet add package iCoDer.Sdk` (line 216), but no actual NuGet package exists.

**Corti state:** Corti has actual `Corti.Sdk` NuGet package.

**Files to modify:**
- New repo `icoder-dotnet-sdk` with generated client + publish to NuGet
- OR: remove `.NET SDK` tab from Quickstart if not planning to publish

**Estimated effort:** 8-16 hours (if building from scratch) OR 30 minutes (if removing tab)

---

## iCoDer ADVANTAGES (Corti lacks these)

| # | iCoDer feature | Corti equivalent |
|---|---|---|
| 1 | API Playground tab in Quickstart (live request/response tester) | Corti Quickstart lacks — only AI prompt + SDK samples |
| 2 | Explicit `setPatientContext({patientId, name, encounterId})` method on Web Component | Corti only has `defaultTemplateKey` (no explicit patient ID) |
| 3 | `agent-ref` attribute on Web Component (select agent at embed time) | Corti selects agent via Console config, not at embed time |
| 4 | RunHistory server-side event log (Phase 4-G) | Corti has only client-side `embedded-event` — no server-side event log |
| 5 | trace_events[] persisted to RunTraceStore (Phase 4-F2) | Corti trace is Console-only — not persisted via API |
| 6 | OpenAPI auto-docs at `/docs` | Corti relies on SDK + Skills — no public OpenAPI |
| 7 | `include_trace` parameter in unified endpoint | Corti SDK has no trace parameter |
| 8 | CN Region support (EU/US/CN per CLAUDE.md) | Corti has only EU/US — no CN region |
| 9 | 4 iCoDer SKILL.md files (icoder-chat/coding/dictation/scribe) — CN-focused | Corti has corti-medical-coding + (inferred corti-dictation) — EN-focused |
| 10 | AuditLog + trace_events server-side event log search | Corti has `/usage` + `/billing` but no audit log search |

---

## Phase 5 Recommendations (priority-ordered)

### P1 — Critical

1. **GAP-11-01** — Rewrite Web Component to match Corti API surface (`<icoder-embedded>` + `assistant.auth()` + `configureSession()` + `configure()` + `show()` + unified `embedded-event`). 4-6 hours.
2. **GAP-11-02** — Publish `@icoder/embedded` to npm. 2-4 hours.

### P2 — Polish

3. **GAP-11-03** — Add "Regenerate client secret" button. 2 hours.
4. **GAP-11-04** — Add "Show client secret" on-demand reveal (with security review). 3 hours.
5. **GAP-11-05** — Add Theme (Primary color picker) to Web Component. 2 hours.
6. **GAP-11-06** — Add Locale config to Web Component. 2 hours.
7. **GAP-11-07** — Add `features.*` feature flags to Web Component. 3 hours.
8. **GAP-11-08** — Add `account.creditsConsumed` event subtype. 1 hour (subsumed by #1).

### P3 — Minor

9. **GAP-11-09** — Add "Copy all as .env" button to API Client page. 30 minutes.
10. **GAP-11-10** — Rename `error` → `error.triggered`. Subsumed by #1.
11. **GAP-11-13** — Build actual .NET SDK package OR remove .NET tab. Decision required.

### DO NOT IMPLEMENT

- ❌ Server-side webhooks — Corti doesn't have them. The pull-only model is a deliberate compliance choice (hospital firewalls don't allow inbound-from-Corti). iCoDer should match.
- ❌ Python SDK — Corti doesn't have one. iCoDer's `/docs` OpenAPI is sufficient.
- ❌ iframe embedding — Corti doesn't use iframe. Web Component is the modern pattern.

---

## Cross-references

- `CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` — Corti side of §11 audit
- `outputs/phase4h/api_samples/corti_embedded_web_component.md` — Corti Web Component verbatim code
- `outputs/phase4h/api_samples/corti_default_client_fields.md` — Corti API Client fields
- `outputs/phase4h/api_samples/corti_quickstart_use_cases.md` — Corti Quickstart wizard
- `outputs/phase4h/api_samples/corti_quickstart_js_sdk.md` — Corti JS SDK
- `outputs/phase4h/api_samples/corti_quickstart_dotnet_sdk.md` — Corti .NET SDK
- `frontend/src/pages/DeveloperQuickstartPage.tsx` — iCoDer Quickstart (330 LOC, parity confirmed)
- `frontend/src/pages/APIClientsPage.tsx` — iCoDer API Client page (207 LOC, 3 gaps)
- `packages/icoder-embedded/src/icoder-assistant.ts` — iCoDer Web Component (300 LOC, API surface gap)
- `packages/icoder-embedded/package.json` — iCoDer npm package config (not published)
- `backend/app/api/embedded.py` — iCoDer backend Web Component endpoints
- `public/.well-known/agent-skills/` — 4 iCoDer SKILL.md files (parity with Corti)

---

**Gap analysis complete.** Next: §12 Run/Trace/Cost/observability parity audit → §13 Fork/Version/Publish audit → §14 Parity Matrix 2.0.
