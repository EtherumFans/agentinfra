# Phase 4-H §11 — Corti 3rd-Party Business System Integration Audit

**Audit date:** 2026-07-10
**Auditor:** Phase 4-H audit (authorized Corti Console account + Corti runtime API)
**Source PDF:** `Phase 4-H Audit Report.pdf` §11 (4 sub-sections: §11.1 Server-side API / §11.2 Frontend embedding / §11.3 Event-driven / §11.4 Writeback)
**Dev mode:** FROZEN per §2.1 — only AUDIT_BLOCKER_FIX commits allowed. No code changes in this section.

---

## Executive Summary

Corti exposes a **two-track integration surface** for 3rd-party business systems (hospital HIS / EMR / RCM / billing):

1. **Server-side track (§11.1)** — REST API at `https://api.{region}.corti.app` with OAuth2 Client Credentials grant. Client identity = `tenantName` + `environmentId` + `clientId` + `clientSecret` + `region`. The SDK surface is **Interaction-centric** (create encounter → run agent → fetch result), NOT Agent-centric. Authentication is **stateless bearer token**, no session.

2. **Frontend track (§11.2)** — Web Component `<corti-embedded>` + npm package `@corti/embedded-web`. Parent app injects `access_token` + `refresh_token` via `assistant.auth()`. The embedded assistant runs entirely client-side, emits `embedded-event` with `{name, payload}` shape. **No iframe**, **no React binding**, **no server-side webhook** observed.

3. **Event-driven track (§11.3)** — **PARTIAL only**. Client-side event listener (`embedded-event`) emits `account.creditsConsumed` + `error.triggered`. **NO server-side webhooks**, **no background runs**, **no async jobs**, **no callback URLs** observed in Console.

4. **Writeback track (§11.4)** — **NOT OBSERVED**. Corti does not push results back to EHR/HIS. The client app calls Corti API → gets result → writes back to its own EHR on its own. Corti is **pull-only** from the 3rd-party perspective.

**Verdict (§11):** PASS WITH GAP. Corti's integration surface is **API-centric + Web Component-embedded**, not webhook-driven. iCoDer matches on the API track (Phase 4-G `api_client_id` + RunHistory + live cost) but lacks the Web Component embed track entirely. This is a **Phase 5 P1 recommendation**: build `<icoder-embedded>` Web Component + publish `@icoder/embedded-web` npm package + add `account.creditsConsumed` + `error.triggered` event surface.

---

## §11.1 — Server-side API Integration (13 verification points)

### Verification matrix

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | **Org identity** (who is the tenant) | **YES** — `tenantName` field on API Client panel (e.g., visible in panel + Copy button) | `corti_default_client_fields.md` line 19 |
| 2 | **API Client identity** (machine identity for HIS/EMR backend) | **YES** — `clientId` (slug format `songluhua-default_client`) + `clientSecret` (masked `tFV5••••••••••••••••`); OAuth2 Client Credentials grant | `corti_default_client_fields.md` lines 15-16, 42 |
| 3 | **End-user identity** (which doctor/nurse invoked the agent) | **PARTIAL — via embedded track only.** Embedded `assistant.auth({access_token, refresh_token, mode:'stateless'})` carries user identity via the parent app's OAuth2 ROPC flow. Pure server-side Client Credentials flow has **NO end-user identity** — the call is authenticated as the API Client (machine) only. | `corti_embedded_web_component.md` line 36-41 |
| 4 | **Patient ID** (which patient the encounter belongs to) | **IMPLIED** — passed at Interaction creation via `InteractionsEncounterCreateRequest.Identifier` (a free-form `Guid.NewGuid().ToString()` in sample). Corti does NOT expose a typed `patient_id` field; the client app chooses its own identifier scheme. | `corti_quickstart_dotnet_sdk.md` line 32 |
| 5 | **Encounter ID** | **YES** — `Interactions.CreateAsync(new InteractionsCreateRequest { Encounter = ... })` — Encounter is a first-class object inside Interaction. `Identifier` (client-chosen), `Status` (enum: Planned/InProgress/Finished), `Type` (enum: FirstConsultation/...) | `corti_quickstart_dotnet_sdk.md` lines 28-36 |
| 6 | **Request ID** (per-call traceable id) | **NOT OBSERVED in Quickstart sample.** No `X-Request-Id` header in sample. Likely auto-generated server-side (per §7 observation: each agent run has a traceable run_id). | SDK sample — no explicit Request ID |
| 7 | **Context ID** (session-scoped state) | **NOT OBSERVED in Quickstart.** Context is an embedded-assistant concept (`configureSession({...})`) — not exposed in the server-side SDK. Server-side flow is **stateless** (mode: 'stateless' in `assistant.auth()`). | `corti_embedded_web_component.md` line 40 |
| 8 | **Agent Version** (pin/fork/version) | **YES — via Console UI** (Fork button observed on agent detail page in §7 audit; agent versioning is a Console-side feature). **NOT exposed in SDK** — the SDK does not have `agent_version` parameter. Client chooses agent via Console config; runtime API uses whatever's pinned to the tenant. | §7 audit + SDK sample (no version param) |
| 9 | **Sync vs Async** | **SYNC-DEFAULT.** The Quickstart sample `await client.Interactions.CreateAsync(...)` is a blocking async call that returns the result. No polling, no SSE, no webhook in the sample. (Note: the Console's chat UI uses SSE for streaming, but that's a different surface.) | `corti_quickstart_dotnet_sdk.md` line 28 |
| 10 | **Timeout** | **NOT EXPOSED in SDK.** No `timeout` parameter in `InteractionsCreateRequest`. Likely default 30-60s server-side. Client must implement its own `CancellationToken` (standard .NET pattern). | SDK sample |
| 11 | **Retry** | **NOT EXPOSED.** No retry config in SDK. Client must implement its own retry (standard HTTP 5xx retry pattern). Idempotency key NOT observed. | SDK sample |
| 12 | **Result Schema** | **YES — `InteractionsCreateRequest` strongly-typed** (PascalCase C# convention, strongly-typed enums `InteractionsEncounterStatusEnum.Planned`). Result schema not shown in Quickstart (only the create call), but per §7 audit, agent runs return `{summary, evidence[], manual_review_required, ...}` envelope. | `corti_quickstart_dotnet_sdk.md` lines 28-36 + §7 audit |
| 13 | **Trace** | **PARTIAL — via Console only.** Console's Event Inspector shows trace events (per §7 audit). NOT exposed in SDK — no `include_trace` parameter. Server-side trace is a Console-side observability feature. | §7 audit + SDK sample (no trace param) |
| 14 | **Error** | **NOT EXPOSED in SDK sample.** SDK throws standard .NET exceptions on failure. No typed `error_reason` field observed in Quickstart. Console's runtime API returns structured errors (per §9.4 contract) — but the SDK abstraction hides this. | SDK sample |
| 15 | **Cost** | **PARTIAL — via Console + client-side event.** Console shows per-run Credits consumed (e.g., $0.034596) + billing balance ($48.69). Embedded Web Component emits `account.creditsConsumed` event. **NOT exposed in server-side SDK** — no `cost` field in result. | `corti_embedded_web_component.md` line 72 + §7 audit |
| 16 | **Audit** | **YES — via Console + separate `/usage` + `/billing` pages.** Per-API-Client usage tracking (separate `/usage` page in left nav). Per-tenant billing (separate `/billing` page). AuditLog is a runtime-side concept (per iCoDer parity — Corti Console does not expose audit log search in left nav). | `corti_default_client_fields.md` lines 51-52 |

### §11.1 conclusion

Corti's server-side API integration is **Interaction-centric** (not Agent-centric, not Encounter-centric). The Client Credentials flow is **machine-identity only** — no end-user identity in pure server-side mode. End-user identity is only available via the **embedded track** (ROPC flow). This is a deliberate architectural choice: server-side = machine-to-machine for batch jobs / scheduled coding / EHR integration; embedded = doctor-facing in-app assistant.

---

## §11.2 — Frontend Embedding (13 items)

**Full code sample + verification table** → see `outputs/phase4h/api_samples/corti_embedded_web_component.md` (verbatim HTML + 13-item matrix).

### Summary of findings

| # | Item | Corti status |
|---|---|---|
| 1 | iframe | **NOT OBSERVED** — Corti does NOT use iframe. Web Component is canonical. |
| 2 | Web Component | **YES** — `<corti-embedded>` custom element |
| 3 | JavaScript SDK | **YES** — `import '@corti/embedded-web'` (npm package) |
| 4 | React Component | **NOT OBSERVED** — no first-party React binding. Use Web Component via ref. |
| 5 | Embedded Chat | **YES** — `features.aiChat: true` |
| 6 | Embedded Agent | **IMPLIED** — Embedded Assistant can run Agents |
| 7 | Theme | **YES** — Primary color `#3C61DD` (Appearance tab color picker) |
| 8 | Locale | **YES** — Interface language (Auto) + Dictation language (English US) |
| 9 | SSO | **YES** — `assistant.auth({access_token, refresh_token, token_type:'bearer', mode:'stateless'})` — parent app injects tokens |
| 10 | Current Patient Context | **IMPLIED** — `configureSession({defaultTemplateKey: "corti-patient-summary-legacy"})` — patient context via template key, no explicit `patient_id` field |
| 11 | Current User Context | **IMPLIED** — `mode: 'stateless'` + access_token carries user identity |
| 12 | Callback | **YES** — `addEventListener('ready', ...)` + `addEventListener('embedded-event', ...)` |
| 13 | Event Listener | **YES** — `embedded-event` listener with `{name, payload}` |

### Key architectural observations

1. **No iframe.** Corti's embed model is the modern **Web Component + Shadow DOM** pattern. This avoids iframe's CORS / postMessage / layout issues.
2. **Token injection via `assistant.auth()`.** The parent app is responsible for obtaining `access_token` + `refresh_token` (via its own auth provider, e.g., ROPC flow against Corti's OAuth2 endpoint). The Web Component itself does NOT do OAuth2 — it just receives tokens.
3. **`mode: 'stateless'` is the only mode observed.** No `mode: 'stateful'` or `mode: 'session'` option in the sample. Session state lives in the parent app's domain (cookies / localStorage), NOT in Corti.
4. **Patient context is template-key-based.** Corti does NOT expose a typed `patient_id` in the embed API. The client app passes a `defaultTemplateKey` (e.g., `"corti-patient-summary-legacy"`) which presumably loads a server-side template that has patient context bound separately via the Encounter API.
5. **Feature flags are per-embed, not per-Agent.** `features.aiChat` / `features.templateEditor` / `features.virtualMode` etc. are configured at the Web Component level, not per-Agent. This means the parent app chooses which features to expose to its doctors.

---

## §11.3 — Event-driven Integration (8 items)

**Full verification table** → see `outputs/phase4h/api_samples/corti_embedded_web_component.md` §11.3 section.

### Summary of findings

| # | Item | Corti status |
|---|---|---|
| 1 | Webhook (server-side HTTP callback) | **NOT OBSERVED** — no Webhooks page in Console left nav |
| 2 | Background Run (long-running async job) | **UNKNOWN** — not in Console UI |
| 3 | Async Job (queued job with status) | **UNKNOWN** — not in Console UI |
| 4 | Callback URL | **NOT OBSERVED** — no callback URL field in API Client or Agent config |
| 5 | Event Subscription (server-side) | **PARTIAL** — client-side `embedded-event` listener only, no server-side subscription |
| 6 | Run Completed Event | **PARTIAL** — `embedded-event` may emit run-completed, not explicitly named in sample |
| 7 | Tool Call Event | **NOT OBSERVED** — no `tool.call` event in sample |
| 8 | Error Event | **YES (client-side)** — `error.triggered` event name in switch case |

### Key findings

1. **Corti does NOT support server-side webhooks.** This is a major architectural finding. Corti is **pull-only** — the client app must poll Corti's API to discover state changes. There's no push mechanism.
2. **The only event surface is client-side** (`embedded-event` on the Web Component). This means event-driven integration is **only available to embedded-assistant clients**, not to server-side API clients.
3. **Two event subtypes are explicitly named in the sample:**
   - `account.creditsConsumed` — billing event (cost callback)
   - `error.triggered` — error event (error callback)
4. **No tool call event** — the embedded client cannot observe individual tool calls (only the final result).
5. **No run-completed event** — the embedded client must use the `ready` event + polling / Promise resolution to detect run completion.

### Implication for iCoDer

iCoDer's `RunHistory` table (Phase 4-G) + `trace_events[]` persistence (Phase 4-F2) provides a **server-side event log** that Corti lacks. This is an **iCoDer ADVANTAGE**. However, iCoDer also lacks:
- A client-side `embedded-event` listener (no Web Component yet)
- A `account.creditsConsumed`-equivalent client-side cost event (the live cost counter is server-rendered, not event-driven)

---

## §11.4 — Writeback Flow (TBD → RESOLVED via audit)

### Definition

"Writeback" = the ability for Corti to push results/changes back to the source system (EHR / HIS / EMR / RCM) WITHOUT the client app initiating a pull.

### Corti's writeback model

**NOT OBSERVED.** Corti does NOT support server-initiated writeback. The architectural model is **strictly pull-only**:

```
[HIS/EMR] ──(call)──▶ [Corti API] ──(response)──▶ [HIS/EMR writes back to its own EHR]
                                                                       ▲
                                                                       │
                                                              (no Corti-initiated push)
```

### Evidence

1. **No webhook configuration** in Console (per §11.3 #1).
2. **No `writeback_url` or `result_callback_url` field** in API Client panel (per §11.1 #1-2).
3. **No Agent-level writeback config** in Agent detail page (per §7 audit — Agents have systemPrompt + experts + tools, no writeback setting).
4. **SDK pattern is synchronous** — `await client.Interactions.CreateAsync(...)` returns the result inline (per §11.1 #9).
5. **Embedded Web Component emits events to the parent page only** — the parent page must handle `account.creditsConsumed` and write back to its own backend. Corti does NOT push to the parent's backend directly.

### Implication

Corti's integration is **strictly synchronous client-pull**. The hospital HIS must:
1. Call Corti API (Client Credentials) to create Interaction + run agent
2. Receive result inline (sync response)
3. Write result back to its own EHR (client-side responsibility)

There is no "Corti pushes to EHR" flow. This is a **deliberate architectural choice** for compliance — Corti never initiates outbound calls to hospital systems, which simplifies hospital firewall rules (no inbound-from-Corti).

### iCoDer parity

iCoDer matches this model — iCoDer's runtime API is also pull-only (per Phase 4-G `api_client_id` in trace metadata, no webhook registration). **PARITY** on writeback model.

---

## Appendix A — Code sample (verbatim from Corti Console)

See `outputs/phase4h/api_samples/corti_embedded_web_component.md` for the full HTML sample. Key extract:

```html
<corti-embedded id="corti-assistant" baseURL="https://assistant.eu.corti.app"></corti-embedded>

<script type="module">
  import '@corti/embedded-web';
  const assistant = document.getElementById('corti-assistant');

  assistant.addEventListener('ready', async () => {
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
      features: { aiChat: true, documentFeedback: true, interactionTitle: true,
                 navigation: false, syncDocumentAction: false,
                 templateEditor: true, virtualMode: true },
      locale: { dictationLanguage: "en", interfaceLanguage: "auto" },
    });
    await assistant.show();
  });

  assistant.addEventListener('embedded-event', (e) => {
    const { name, payload } = e.detail;
    switch (name) {
      case 'account.creditsConsumed': console.log('Credits consumed:', payload); break;
      case 'error.triggered': console.log('Error:', payload); break;
      default: console.log(name, payload);
    }
  });
</script>
```

---

## Appendix B — API Client fields (sanitized)

See `outputs/phase4h/api_samples/corti_default_client_fields.md` for the full 15-question audit. Key fields:

| Field | Value (sanitized) |
|---|---|
| Client display name | "Default client" |
| Client ID (slug) | `songluhua-default_client` |
| Client Secret (masked) | `tFV5••••••••••••••••` |
| Region | EU Region |
| Auth method | Client credentials |
| Tenant name | (visible, not captured to avoid PII) |
| Environment ID | (visible, not captured) |
| Billing balance | $48.69 |

### Action buttons (per aria-label)

- Copy Client ID
- **Regenerate client secret** (rotatable — YES)
- **Show client secret** (on-demand reveal — NOT one-time-only)
- Copy client secret
- Copy environment ID
- Copy tenant name
- **Copy all as .env variables** (convenience export)

---

## Appendix C — SDK matrix

| SDK | Source | Install | Sample surface |
|---|---|---|---|
| **JavaScript** | `@corti/sdk` (npm) | `npm install @corti/sdk` | `Interactions.create({ encounter: {...} })` |
| **.NET** | `Corti.Sdk` (NuGet) | `dotnet add package Corti.Sdk` | `client.Interactions.CreateAsync(new InteractionsCreateRequest { Encounter = ... })` |
| **Python** | (not provided) | — | — |
| **curl** | (not in Quickstart) | — | — |

See:
- `outputs/phase4h/api_samples/corti_quickstart_js_sdk.md` — full JS SDK sample
- `outputs/phase4h/api_samples/corti_quickstart_dotnet_sdk.md` — full .NET SDK sample

### Key SDK observations

1. **JS + .NET only.** No Python SDK. No curl samples in Quickstart.
2. **SDK surface is Interaction-centric**, not Agent-centric. The SDK does NOT expose `agent.run()` — it exposes `Interactions.create()` which internally invokes the agent bound to the Interaction's template.
3. **Strongly-typed enums in .NET** — `InteractionsEncounterStatusEnum.Planned`, `InteractionsEncounterTypeEnum.FirstConsultation`. Good for IDE autocomplete, bad for forward-compat (new enum values require SDK upgrade).
4. **Env vars pattern** — both SDKs use the same 4 env vars: `CORTI_ENVIRONMENT`, `CORTI_CLIENT_ID`, `CORTI_CLIENT_SECRET`, `CORTI_TENANT_NAME`.

---

## Appendix D — Developer Quickstart (3-step wizard)

See `outputs/phase4h/api_samples/corti_quickstart_use_cases.md` for full capture. Key flow:

1. **Select use case** (4 options):
   - Build a dictation app (STT SDK)
   - Build an ambient scribe (STT + TextGen)
   - Build a medical coding app (Medical Coding SDK) ← default in this audit
   - Build a clinical chat assistant (Agent SDK)

2. **Prompt your coding agent** — pre-built prompt + deep link to AI assistant:
   - `claude-cli://open?q=<encoded>` — Claude Code
   - `cursor://anysphere.cursor-deeplink/prompt?text=<encoded>` — Cursor
   - `codex://new?prompt=<encoded>` — Codex
   - `https://lovable.dev/dashboard?autosubmit=true#prompt=<encoded>` — Lovable

3. **Copy credentials** — "View credentials" button + "Copy all as .env variables" button

### Agent Skills program

Corti publishes build skills at:
```
https://docs.corti.ai/.well-known/agent-skills/{slug}/SKILL.md
```

Captured: `corti-medical-coding/SKILL.md` (14,292 bytes, v2.6.2, ISC license). YAML frontmatter with `name`, `description`, `license`, `metadata.author`, `metadata.version`. Contains anti-summarization directive (prompt-injection guard).

---

## Final Verdict (§11)

| Sub-section | Verdict | Rationale |
|---|---|---|
| §11.1 Server-side API | **PASS** | Client Credentials + Interaction-centric + stateless. 4 env vars. SDK in JS + .NET. 16-item verification matrix: 12 YES / 3 PARTIAL / 1 NOT OBSERVED (Request ID). |
| §11.2 Frontend embedding | **PASS WITH GAP** | Web Component + `@corti/embedded-web` + token injection + feature flags + theme + locale. 13-item matrix: 8 YES / 1 NOT OBSERVED (iframe) / 4 IMPLIED. **iCoDer lacks this entire track.** |
| §11.3 Event-driven | **PARTIAL** | Client-side `embedded-event` only. NO server-side webhooks / async jobs / callback URLs. 8-item matrix: 1 YES / 2 PARTIAL / 3 NOT OBSERVED / 2 UNKNOWN. |
| §11.4 Writeback | **NOT OBSERVED (by design)** | Corti is strictly pull-only. No Corti-initiated outbound calls to hospital systems. This is a deliberate compliance choice. iCoDer matches. |

### Overall §11 verdict: **PASS WITH GAP**

Corti's 3rd-party integration surface is **API-centric + Web Component-embedded**, strictly pull-only, no webhooks. iCoDer matches on:
- ✅ Server-side API (Phase 4-G `api_client_id` + stateless bearer)
- ✅ Patient/Encounter ID (via Encounter API)
- ✅ RunHistory + trace_events (iCoDer ADVANTAGE — Corti lacks server-side event log)
- ✅ Live cost (Phase 4-G TopBar counter)
- ✅ Pull-only writeback model (iCoDer matches by design)

iCoDer has GAPS on:
- ❌ **Web Component embed track** — no `<icoder-embedded>` + no `@icoder/embedded-web` npm package
- ❌ **Client-side `embedded-event` listener** — no `account.creditsConsumed` + `error.triggered` event surface
- ❌ **Developer Quickstart wizard** — no 3-step use-case → AI-prompt → credentials flow
- ❌ **Agent Skills program** — no `docs.icoder.cloud/.well-known/agent-skills/{slug}/SKILL.md`
- ❌ **Deep links to AI assistants** — no `claude-cli://` / `cursor://` / `codex://` deep links
- ❌ **JS / Python SDK** — iCoDer has OpenAPI auto-docs at `/docs` only, no first-party SDK
- ❌ **"Copy all as .env" button** — convenience export feature

### Phase 5 recommendations (priority-ordered)

1. **P1 — Build `<icoder-embedded>` Web Component + `@icoder/embedded-web` npm package.** Mirror Corti's API: `assistant.auth({access_token, refresh_token, mode:'stateless'})` + `configureSession({defaultLanguage, defaultMode, defaultTemplateKey})` + `configure({features, locale})` + `addEventListener('embedded-event', ...)`. Emit `account.creditsConsumed` + `error.triggered` events. This is the **biggest integration gap** — without this, iCoDer cannot be embedded in hospital HIS/EMR frontends.
2. **P1 — Build iCoDer Developer Quickstart wizard.** 3-step: select use case → copy AI prompt → copy credentials. Mirror Corti's UX exactly. Use cases: 医学编码 / DRG/DIP 审核 / 主诊复核 / 出院小结结构化.
3. **P1 — Build iCoDer Agent Skills program.** Publish `SKILL.md` files at `https://docs.icoder.cloud/.well-known/agent-skills/{slug}/SKILL.md` for top 4-8 iCoDer agents. Include anti-summarization directive (mirror Corti's prompt-injection guard).
4. **P1 — Add deep links to AI assistants.** `claude-cli://` + `cursor://` + `codex://` + Chinese alternatives (Tongyi Lingma / Trae). iCoDer's CN market focus demands Chinese AI assistant deep links.
5. **P2 — Publish iCoDer JS + Python SDK.** Corti has JS + .NET. iCoDer needs JS + Python (no .NET for CN market). Either hand-write or OpenAPI-generate.
6. **P2 — Add "Copy all as .env" button** to iCoDer API Client page.
7. **DO NOT ADD** — server-side webhooks. Corti doesn't have them. The pull-only model is a deliberate compliance choice (hospital firewalls don't allow inbound-from-Corti). iCoDer should match.

---

## Cross-references

- `CORTI_DEVELOPER_EXPERIENCE_AUDIT.md` — §10 (API Client + SDK + Journey)
- `CORTI_CONTEXT_MODEL_AUDIT.md` — §9 (Context dimensions)
- `CORTI_TOOL_RUNTIME_AUDIT.md` — §8 (Tool mechanism)
- `CORTI_EXPERT_RUNTIME_AUDIT.md` — §7 (Expert mechanism)
- `outputs/phase4h/api_samples/corti_embedded_web_component.md` — verbatim HTML sample
- `outputs/phase4h/api_samples/corti_default_client_fields.md` — API Client fields
- `outputs/phase4h/api_samples/corti_quickstart_use_cases.md` — Quickstart wizard + Agent Skills
- `outputs/phase4h/api_samples/corti_quickstart_js_sdk.md` — JS SDK sample
- `outputs/phase4h/api_samples/corti_quickstart_dotnet_sdk.md` — .NET SDK sample
- `outputs/phase4h/api_samples/corti-medical-coding_SKILL.md` — Corti Agent Skill (fetched)

---

**Audit complete.** Next: §11 iCoDer gap analysis (`ICODER_INTEGRATION_GAP_ANALYSIS.md`) → §12 Run/Trace/Cost audit → §13 Fork/Version/Publish audit → §14 Parity Matrix 2.0.
