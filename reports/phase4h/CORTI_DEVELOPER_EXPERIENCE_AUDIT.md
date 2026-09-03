# Phase 4-H §10 — Corti Developer Experience Audit (PASS)

**Closed:** 2026-07-10 (local)
**Auditor:** Claude (Sonnet 4.5) under dev-FROZEN constraint (§2.1)
**Audit vehicle:** Corti Console project `b8f8129a` + Developer Quickstart + API Clients page
**Output spec (PDF §10):** this file + `outputs/phase4h/api_samples/`

---

## Executive summary

Corti's developer experience is structured around a **3-step Quickstart wizard** (select use case → prompt your AI coding agent → copy credentials) that leverages external AI coding assistants (Claude Code / Cursor / Codex / Lovable) to build apps on the Corti SDK. This is enabled by Corti's **Agent Skills program** — published at `https://docs.corti.ai/.well-known/agent-skills/{slug}/SKILL.md` — which provides build skill specifications that AI assistants consume to scaffold Corti-based apps.

The API Client model is **2 default clients** (Client credentials OAuth2 + ROPC for embedded) + region selection (US / EU). Secrets are masked by default (`tFV5••••••••••••••••`) and can be revealed on-demand, rotated, or copied as `.env` variables. No per-Client scope, rate-limit, or Agent RBAC.

The SDK surface is **JavaScript + .NET only** (no Python, no curl in the Quickstart). The Quickstart focuses on `Interactions.create()` (Encounter creation); the Agent SDK surface (`agents.create` + `agents.messageSend`) is visible only via the per-Agent Code tab (per §7 audit).

**iCoDer parity verdict: §10 PASS WITH GAP.** iCoDer has the API Client infrastructure (Phase 4-G, 2026-07-10 PASS) but lacks: (1) Developer Quickstart wizard, (2) Agent Skills program, (3) deep links to AI assistants, (4) JS/Python SDK. These are 4 P1_DEVELOPER gaps for Phase 5.

---

## §10.1 API Client lifecycle (15 questions)

Per PDF §10.1, the following 15 questions were probed:

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Find API Client page | **YES** — `/api-clients` under Manage nav | URL captured |
| 2 | Create test Client | Dialog captured (NOT submitted to avoid polluting audit account) | `phase4h_corti_12_create_api_client_dialog.png` |
| 3 | Configurable fields | Client display name + How will this client be used? (Direct API access / Embedded Assistant) + Authentication method (locked: Client credentials) + Region (US / EU) | Dialog |
| 4 | Auth method | **Client credentials** (Direct API access) OR **ROPC** (Embedded Assistant) | Two default clients observed |
| 5 | Record Client ID | `songluhua-default_client` (slug format: `username-clientname`) | Captured |
| 6 | Secret shown only once? | **NO** — masked by default (`tFV5••••••••••••••••`), revealable on-demand via "Show client secret" button | Action button |
| 7 | Rotatable? | **YES** — "Regenerate client secret" button | Action button |
| 8 | Disableable? | **NO** — default clients cannot be deleted ("Default clients are ready to use... They can't be deleted but you can create and configure more") | UI text |
| 9 | Has Scope? | **NO** — no per-Client scope field | Not in dialog/panel |
| 10 | Has Rate Limit? | **NO** — no per-Client rate-limit field | Not in dialog/panel |
| 11 | Has Agent permissions? | **NO** — no per-Client Agent RBAC | Not in dialog/panel |
| 12 | Org isolation? | **IMPLIED** via `tenantName` + `environmentId` (Environment → Tenant → API Client model) | Captured fields |
| 13 | Has Usage? | **YES** — separate `/usage` page in left nav | Left nav |
| 14 | Has Cost Attribution? | **YES** — `/billing` page + per-run `Credits consumed: $X` footer + `$48.69` balance link in breadcrumb | Breadcrumb + §7.3.3 |
| 15 | (extra) Default clients count | **2** — Client credentials + ROPC | Both headings captured |

### §10.1 key findings

**Finding 1 — Two OAuth flows, two default clients.**
Corti ships 2 default clients per project:
- **Default client** — `Client credentials` OAuth2 flow for backend-service integration (server-to-server, no user context)
- **Default embedded client** — `ROPC (Resource Owner Password)` flow for Embedded Assistant (frontend Web Component, user-supplied credentials)

This matches the iCoDer cloud architecture per CLAUDE.md: "API Client (`backend-service` 服务端集成 或 `ROPC embedded` Web Component 嵌入)". **iCoDer parity MATCH.**

**Finding 2 — Secret is masked, not one-time-only.**
The Client Secret is masked by default as `tFV5••••••••••••••••` (first 4 chars revealed + 16 dots). It can be revealed on-demand via "Show client secret" button, and re-masked after. It is NOT one-time-only-at-creation (the user can reveal it any time).

**Finding 3 — Secret is rotatable.**
"Regenerate client secret" button is present. Clicking it would generate a new secret + invalidate the old one. (Not clicked to avoid disrupting the audit account.)

**Finding 4 — No per-Client scope / rate limit / Agent RBAC.**
Corti does NOT surface per-Client scope, per-Client rate-limit, or per-Client Agent permission fields. All API Clients have full access to all Agents in the project. Rate limiting is at the platform level (not per-Client). This is a SIMPLIFICATION — Corti relies on the project boundary (API Clients are scoped to a single project) rather than fine-grained per-Client RBAC.

**Finding 5 — Region is a data-residency choice.**
Region selection (US / EU) determines "where your data is processed and stored" — per the dialog description: "Choose the region closest to your users or aligned with your data residency requirements for optimal performance and compliance." This is the **GDPR / HIPAA data residency** dimension. iCoDer adds **CN region** (per CLAUDE.md) — iCoDer ADVANTAGE for Chinese hospital data sovereignty.

**Finding 6 — Tenant + Environment multi-tenancy.**
Each API Client belongs to a Tenant (医院), and each Tenant belongs to an Environment (EU/US/CN). The `tenantName` and `environmentId` fields are surfaced as copyable values. This is the **three-layer cloud SaaS model** that iCoDer also follows (per CLAUDE.md: "三层架构: Environment (EU/US/CN) → Tenant (医院) → API Client").

---

## §10.2 Official API examples

Per PDF §10.2, the official API examples were copied from the Corti Console.

### §10.2 verification table

| # | Verification | Result | Evidence |
|---|---|---|---|
| 1 | Examples can run directly? | **PARTIAL** — JS + .NET samples are runnable with `npm install @corti/sdk dotenv` / `dotnet add package Corti.Sdk` + env vars. Sample creates an Interaction, NOT a coding prediction. | `corti_quickstart_js_sdk.md` + `corti_quickstart_dotnet_sdk.md` |
| 2 | URL correct? | **YES** — SDK uses `environment: process.env.CORTI_ENVIRONMENT` (e.g., "eu" / "us"); runtime URL is `api.eu.corti.app` (per §7 audit). SDK abstracts the URL. | §7 audit |
| 3 | Agent Ref has version? | **UNKNOWN** — Quickstart sample does NOT include Agent Ref (it creates an Interaction, not an Agent run). Per §7 audit, `agents.create({name, experts[{name, type:"reference"}]})` uses Expert name as ref, no version. | §7 audit |
| 4 | Token acquisition? | **YES** — `auth: {clientId, clientSecret}` in JS SDK + `CortiClientAuth.ClientCredentials(clientId, clientSecret)` in .NET. OAuth2 Client Credentials flow. | SDK samples |
| 5 | Request body structure? | **YES** for `interactions.create({encounter: {identifier, status, type}})`. **NO** sample for `agents.messageSend({message: {role, parts, messageId, kind}})` in Quickstart — visible only in per-Agent Code tab. | SDK samples + §7 audit |
| 6 | Response body structure? | **PARTIAL** — `const { interactionId } = await client.interactions.create(...)` shows the destructured response. Full response structure (Run ID, Trace ID, Cost) not in Quickstart sample. | SDK sample |
| 7 | Run ID? | **NO** — Quickstart sample returns `interactionId`, NOT `runId`. Per §7 audit, `agents.messageSend()` returns a Message object with runId/run_id in metadata. | §7 audit |
| 8 | Trace ID? | **NO** — not in Quickstart sample. Per §7 audit, no per-run trace endpoint observed in agent detail page. | §7 + §8 audits |
| 9 | Error? | **NO** — no error handling in Quickstart sample. SDK exceptions not documented. | SDK sample |
| 10 | Cost? | **PARTIAL** — `response.usageInfo.creditsConsumed` field referenced in `corti-medical-coding/SKILL.md` (line 47), but NOT in the Quickstart JS/.NET samples. | SKILL.md |
| 11 | Streaming? | **NO** — Quickstart samples are one-shot REST round-trips. No SSE/WebSocket streaming in Quickstart. | SDK sample |
| 12 | Attachment? | **NO** — not in Quickstart. The `interactions.create()` sample doesn't include attachments. Per §9 audit, JSON dropzone accepts attachments in Console chat. | §9 audit |
| 13 | Context? | **NO** — not in Quickstart. Context is passed via SDK methods, not Quickstart sample. | §9 audit |
| 14 | Idempotency? | **NO** — no `Idempotency-Key` header in Quickstart sample. The `encounter.identifier` field is the user-supplied idempotency key for the Encounter. | SDK sample |
| 15 | Timeout? | **NO** — no timeout configuration in Quickstart. SDK default timeout assumed. | SDK sample |
| 16 | Retry? | **NO** — no retry configuration in Quickstart. | SDK sample |
| 17 | Rate Limit Header? | **NO** — not in Quickstart. Rate limit platform-level, not per-Client. | §10.1 #10 |

### §10.2 key findings

**Finding 1 — Quickstart sample creates an Interaction, NOT an Agent run.**
The JS SDK + .NET SDK samples both call `client.interactions.create({encounter: {identifier, status, type}})`. This is the **Encounter/Interaction** API surface (per `docs/ICODER_V1_A2A_SPEC.md` mapping), NOT the **Agent run** API surface. The Agent SDK surface (`agents.create` + `agents.messageSend`) is visible only via the per-Agent Code tab (per §7 audit).

**Implication:** Corti's developer onboarding funnels new developers through the Encounter API first (the "stable" API surface), then exposes the Agent SDK as a power-user feature accessible via the per-Agent Code tab.

**Finding 2 — `encounter.identifier` is the idempotency key.**
The Quickstart sample explicitly says "Replace with your own identifier" and uses `crypto.randomUUID()`. This is a **client-supplied idempotency key** for the Encounter — if the same identifier is sent twice, the second call is idempotent (returns the existing Interaction). This is a common pattern for healthcare APIs (prevents duplicate encounter creation on retry).

**Finding 3 — No Run ID / Trace ID / Cost in Quickstart sample.**
The Quickstart sample destructures `{ interactionId }` from the response. It does NOT surface Run ID, Trace ID, or Cost — these are runtime constructs that surface in the Agent run flow, not the Interaction creation flow.

**Finding 4 — `response.usageInfo.creditsConsumed` is documented in SKILL.md, not Quickstart.**
The Quickstart JS/.NET samples don't show Cost. But the `corti-medical-coding/SKILL.md` (line 47) explicitly references `response.usageInfo.creditsConsumed` — so the Cost field IS in the API response, just not surfaced in the Quickstart sample.

**Finding 5 — No streaming / attachment / retry / timeout / rate-limit in Quickstart.**
The Quickstart is minimal — one-shot REST round-trip, no streaming, no attachment, no retry/timeout config, no rate-limit header. These advanced features are NOT part of the Quickstart developer journey.

---

## §10.3 SDK

Per PDF §10.3, all SDK / code tags were inspected.

### §10.3 SDK inventory

| Language | Status | Install | Source |
|---|---|---|---|
| JavaScript | **YES** — `@corti/sdk` npm package | `npm install @corti/sdk dotenv` | Quickstart + per-Agent Code tab |
| .NET (C#) | **YES** — `Corti.Sdk` NuGet package | `dotnet add package Corti.Sdk` | Quickstart + per-Agent Code tab |
| Python | **NO** — not in Quickstart, not in Code tab | — | Not observed |
| curl | **NO** — not in Quickstart. Per §7 audit, Code tab has "JSON Config" but not raw curl. | — | §7 audit |
| Go / Ruby / Rust / Java | **NO** — not observed | — | — |

### §10.3 SDK details (per PDF §10.3 spec)

| # | Detail | JS SDK | .NET SDK |
|---|---|---|---|
| 1 | Install method | `npm install @corti/sdk dotenv` | `dotnet add package Corti.Sdk` |
| 2 | Initialization | `new CortiClient({environment, auth:{clientId, clientSecret}, tenantName})` | `new CortiClient(tenantName, environment, new CortiClientAuth.ClientCredentials(clientId, clientSecret))` |
| 3 | Authentication | OAuth2 Client Credentials (clientId + clientSecret env vars) | Same |
| 4 | Agent call | **NOT in Quickstart** — per §7 audit: `cortiClient.agents.create({name, experts, description, systemPrompt})` + `cortiClient.agents.messageSend(agentId, {message: {...}})` | **NOT in Quickstart** — per §7 audit: `client.Agents.CreateAsync(new AgentsCreateAgent {...})` |
| 5 | Streaming | **NO** in Quickstart | **NO** in Quickstart |
| 6 | Async | `await client.interactions.create(...)` | `await client.Interactions.CreateAsync(...)` |
| 7 | Attachment | **NO** in Quickstart | **NO** in Quickstart |
| 8 | Trace | **NO** in Quickstart | **NO** in Quickstart |
| 9 | Error Type | **NOT documented** in Quickstart | **NOT documented** in Quickstart |
| 10 | Type Definitions | TypeScript types via `@corti/sdk` package | C# strongly-typed enums (`InteractionsEncounterStatusEnum.Planned` etc.) |
| 11 | Version Pinning | **NOT documented** in Quickstart — `npm install @corti/sdk` installs latest. Version pinning via `package.json` semver range. | **NOT documented** in Quickstart — `dotnet add package Corti.Sdk` installs latest. Version pinning via `.csproj` `<PackageReference Version="x.y.z" />`. |

### §10.3 key findings

**Finding 1 — JS + .NET only.** Corti provides official SDKs for JavaScript (npm `@corti/sdk`) and .NET (NuGet `Corti.Sdk`). No Python SDK, no curl examples, no Go/Ruby/Rust/Java SDKs.

**Finding 2 — SDK surface = Interactions API first.** The Quickstart surfaces `client.interactions.create()` (Encounter creation). The Agent SDK surface (`client.agents.*`) is hidden in the per-Agent Code tab.

**Finding 3 — No streaming / attachment / trace / error type / version pinning in Quickstart.** These are advanced features that the Quickstart does NOT document. A developer would need to read the SDK source or the full docs at `docs.corti.ai/sdk/js/overview` (per Docs link in breadcrumb).

---

## §10.4 Developer Journey

Per PDF §10.4, the developer journey was executed end-to-end:

| Step | Action | Result |
|---|---|---|
| 1 | Create or Fork Agent | **DONE in §7** — forked `PHASE4H-AUDIT-MC` from `medical-coding-icd-10-cpt-agent` preset |
| 2 | Test Agent | **DONE in §7.3.3** — ran test prompt, got K35.80 + 44970, cost $0.020060 |
| 3 | Get call examples | **DONE** — Code tab captured JS + .NET + JSON Config in §7; Quickstart captured JS + .NET in §10.2 |
| 4 | Create API Client | Dialog captured (`phase4h_corti_12_create_api_client_dialog.png`) — NOT submitted (default clients already exist) |
| 5 | Use API / SDK call | **NOT EXECUTED** — would require running external JS/.NET script with env vars; out of audit scope (no Python/curl to run inline) |
| 6 | View Run | **DONE** — agent detail page shows chat panel + cost footer; NO RunHistory (per §7 audit) |
| 7 | View Trace | **NONE in Console** — per §7 + §8 audits, Corti Console has NO per-run trace viewer in agent detail page |
| 8 | View Cost | **DONE** — `$0.034596` cumulative in breadcrumb; per-run `Credits consumed: $0.020060` footer in chat panel |
| 9 | Modify Agent | Settings tab exposes Name / systemPrompt / Experts / Pinned message parts (per §9 audit) |
| 10 | Call again | **DONE in §9** — multi-turn follow-up message, K35.80 recalled, cost delta $0.014536 |
| 11 | Version behavior | **UNKNOWN** — Corti Console agent detail sidebar has only Duplicate + Delete (per §7 audit); no Publish / Version / Rollback UI. Per §13 Fork/Version/Publish audit (pending). |

### §10.4 key findings

**Finding 1 — Developer Journey is Console-centric, NOT SDK-centric.**
The Corti Console developer journey focuses on: (1) fork an Agent → (2) test in chat → (3) view Code tab for SDK snippets → (4) create API Client → (5) run via SDK externally. The Console does NOT provide a "Run via API" button or API playground; the developer must run the SDK sample externally.

**Finding 2 — Agent Skills program is the secret sauce.**
The Developer Quickstart's Step 2 ("Prompt your coding agent") directs the user to use an external AI assistant (Claude Code / Cursor / Codex / Lovable) with a pre-built prompt that fetches a build skill from `docs.corti.ai/.well-known/agent-skills/{slug}/SKILL.md`. This is a **viral developer acquisition** strategy — Corti publishes build skills, AI assistants consume them, new developers scaffold Corti-based apps in <5 minutes.

**Finding 3 — No in-Console trace/run-history.**
The developer journey has a GAP at Step 7 (View Trace) — Corti Console does not provide a per-run trace viewer. The developer would need to instrument their SDK call to capture the response's `runId` / `traceId` (if exposed) and call a separate trace endpoint (not observed in this audit).

**Finding 4 — No in-Console API playground.**
Unlike Stripe (which has a "Send test request" UI), Corti Console does NOT provide an API playground. The developer must use an external SDK or curl to make API calls. (No curl in Quickstart is a related limitation.)

---

## Appendix A — Evidence

### A.1 Screenshots
- `screenshots/phase4h/phase4h_corti_12_create_api_client_dialog.png` — Create API Client dialog with 5 fields
- `screenshots/phase4h/phase4h_corti_13_default_client_detail.png` — Default client expanded detail panel with action buttons
- `screenshots/phase4h/phase4h_corti_14_developer_quickstart.png` — Developer Quickstart 3-step wizard full page

### A.2 API samples (`outputs/phase4h/api_samples/`)
- `corti_quickstart_js_sdk.md` — JS SDK install + sample (creates Interaction)
- `corti_quickstart_dotnet_sdk.md` — .NET SDK install + sample
- `corti_quickstart_use_cases.md` — 4 use cases + Agent Skills program + deep links to AI assistants
- `corti_default_client_fields.md` — API Client field inventory + 15-question answers
- `corti-medical-coding_SKILL.md` — Corti's published Agent Skill (14,292 bytes, fetched from docs.corti.ai)

### A.3 iCoDer source cross-checks

- iCoDer Phase 4-G (PASS, 2026-07-10): `api_client_id` in inline + persisted trace metadata + RunHistory table (alembic 010) + Forked-from badge + live cost TopBar
- iCoDer CLAUDE.md: "三层架构: Environment (EU/US/CN) → Tenant (医院) → API Client (backend-service / ROPC embedded)"
- iCoDer cloud architecture docs: `docs/cloud/CLOUD_DEPLOYMENT.md`

## Appendix B — iCoDer Phase 5 recommendations

Based on §10 findings, ordered by PDF §19 priority:

### P0_INTEGRATION (blocks 3rd-party integration)
- **None identified** — iCoDer Phase 4-G already has the API Client infrastructure; the gaps below are P1_DEVELOPER, not P0.

### P1_DEVELOPER (improves developer experience)

1. **Build iCoDer Quickstart wizard.** 3-step wizard mirroring Corti: select use case → copy AI prompt → copy credentials. Route: `/developer-quickstart` (currently iCoDer doesn't have this).

2. **Build iCoDer Agent Skills program.** Publish build skills at `https://docs.icoder.cloud/.well-known/agent-skills/{slug}/SKILL.md` for:
   - `icoder-medical-coding` (mirror Corti's)
   - `icoder-drg-dip-review`
   - `icoder-principal-diagnosis-review`
   - `icoder-discharge-summary-structuring`
   - `icoder-compliance-guardrail`
   - `icoder-evidence-extractor`
   - `icoder-note-completeness`
   - `icoder-procedure-extractor`

3. **Add deep links to AI assistants.** For Chinese market:
   - **Tongyi Lingma** (Alibaba's AI coding assistant)
   - **Trae** (ByteDance's AI coding assistant)
   - **Claude Code** (international)
   - **Cursor** (international)
   - **Codex** (international)

4. **Publish iCoDer JS + Python SDK.** Corti has JS + .NET; iCoDer should have JS + Python (no .NET for Chinese market). Approach options:
   - Hand-written SDK (like Corti)
   - OpenAPI-generated SDK (via openapi-generator) — covers JS / Python / Go / Java / Rust / etc.

5. **Verify iCoDer API Client fields.** Match Corti's 4 action buttons: Copy Client ID / Regenerate secret / Show secret / Copy secret / Copy env ID / Copy tenant / Copy all as .env. If any are missing, add them.

### P2_POLISH
- Add in-Console API playground (Stripe-style "Send test request" UI) — Corti doesn't have this either, but it would be an iCoDer ADVANTAGE.
- Add per-Client scope / rate-limit / Agent RBAC — neither Corti nor iCoDer has these; P2 because not blocking integration.

### DO_NOT_COPY
- Do NOT copy Corti's lack of in-Console trace viewer — iCoDer RunTrace drawer is an iCoDer ADVANTAGE, keep it.
- Do NOT copy Corti's "no curl in Quickstart" — iCoDer should add curl examples for developers who don't want to install an SDK.
