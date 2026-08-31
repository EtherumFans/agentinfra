# Audit Gate 8 — Embedded / SDK / API Client / Partner App (Tracks J1-J5)

> Per PDF §三 Track J: audits the partner-facing surface — the SDK that partners call from their HIS/EMR, the embedded Web Component that mounts inside the clinical UI, the API Client registry that authenticates partners, and the reference app that demonstrates the canonical integration. Determines whether iCoDer is actually consumable from outside its own Console.

## J1. SDK package (`@icoder/sdk`) — REAL but NOT npm-published

### J1.1 Package shape

`packages/icoder-sdk/package.json`:

```json
{
  "name": "@icoder/sdk",
  "version": "1.0.0-beta.2",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": { ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js" } },
  "files": ["dist", "README.md"],
  "scripts": { "build": "tsc", "prepublishOnly": "npm run build" },
  "keywords": ["icoder", "medical", "coding", "icd-10", "ai", "healthcare"]
}
```

12 resource files (951 LOC under `src/`):

```
agents.ts        — POST /api/v1/agents/{id}/run unified facade
billing.ts       — GET /api/billing/* (balance, transactions, plans)
compliance.ts    — POST /api/v1/coding-compliance/run (7-stage)
facts.ts         — POST /api/v1/facts/extract
oauth.ts         — POST /api/oauth/token (4 grant types)
reviews.ts       — Coding review run lifecycle
runs.ts          — GET /api/v1/runs/{id} + /cancel + /events (SSE) + /trace (signed URL)
runtime.ts       — Runtime registry + agent install
speech-to-text.ts — Stub (STT not shipped)
textgen.ts       — POST /api/v2/tools/textgen (legacy Corti-style)
marketplace.ts   — Marketplace agent publish/install (REGISTRY_PUBLISH_DEFERRED per Phase 6)
```

### J1.2 External consumer smoke — 8/8 PASS

`phase7-external-consumer/smoke.mjs` was run against a clean external project (no workspace dep, no internal absolute paths). Result:

```
=== Phase 7 Gate 2 consumer smoke PASSED ===
  OK no workspace dependency
  OK no monorepo internal absolute path
  OK type declarations parse
  OK ESM imports resolve
  OK Web Component class exported + extends HTMLElement
  OK customElements.define succeeds in jsdom
  OK no missing peer dependency
  OK no implicit Console package reference
```

The SDK is structurally consumable from any Node 18+ ESM project.

### J1.3 NPM registry — NOT published

Live check:

```
$ curl -s -o /dev/null -w "%{http_code}" https://registry.npmjs.org/@icoder/sdk
404
$ curl -s -o /dev/null -w "%{http_code}" https://registry.npmjs.org/@icoder/embedded
404
```

Both packages return **404** from the public npm registry. Phase 5 Track A memory claims "npm publish prep" was closed, but "prep" never became "publish". A partner cannot `npm install @icoder/sdk` today — they must either (a) consume the embedded Web Component via `/api/embedded/assistant.js` dist-serve, or (b) clone the monorepo and import directly.

**Register as G8-001 (P1)**: SDK + Embedded packages are 1.0.0-beta.2 / 2.0.0 on disk and pass consumer smoke, but neither is published to the public npm registry. The "public npm published" verdict forbidden by the PDF cannot be claimed.

## J2. Embedded Web Component (`@icoder/embedded`) — REAL, Corti-compatible method-based API

### J2.1 Package shape

`packages/icoder-embedded/package.json`:

```json
{
  "name": "@icoder/embedded",
  "version": "2.0.0",
  "description": "iCoDer Embedded Assistant — embeddable AI coding assistant Web Component (Corti-compatible method-based API)",
  "main": "dist/icoder-assistant.js",
  "types": "dist/index.d.ts"
}
```

Source: `packages/icoder-embedded/src/icoder-assistant.ts` — Corti-compatible method chain:

```typescript
class iCoDerAssistant extends HTMLElement {
  configure({ accessToken, baseUrl, apiClientId, patientContext, ... }): Promise<void>
  setPatientContext({ patientId, name, encounterId }): void
  runAgent({ agentId, message }): Promise<RunResult>
  on(event: 'message.received' | 'run.completed' | ...): () => void
  clearPatientContext(): void
  clearSession(): void
}
customElements.define('icoder-embedded', iCoDerAssistant);
```

### J2.2 Distribution — backend dist-serve

Per `backend/app/api/embedded.py` (476 LOC), the widget is served from:

```
GET /api/embedded/assistant.js
GET /api/embedded/v2/assistant.js     ← v2 with method-based API
```

`Content-Type: application/javascript`, `Cache-Control: public, max-age=3600`, ETag-supported. The widget is intended to be loaded directly from the iCoDer backend, not from npm. This is the **canonical Corti-style distribution pattern** — partners never `npm install` the widget; they `<script src="https://icoder.cloud/api/embedded/assistant.js">` it.

### J2.3 Phase 7 Gate 13A — preview session HMAC Bootstrap Ticket

Verified in DB:

```
preview_sessions status distribution:
  PENDING    7
  EXCHANGED  5
  REVOKED    5
```

17 preview sessions issued; 5 were single-use exchanged for a real access token; 5 were revoked. The Phase 7 Gate 13A HMAC 60s single-use Bootstrap Ticket (alembic 015) is live and exercised.

### J2.4 Production usage — 0 tracked embedded runs

`run_history.api_client_id` distribution:

```
NULL/''  239   (Console runs)
partner-ref-07ef23d306cf  1   (Phase 7 Gate 12 reference-app run)
```

Only **1 production run** came from a partner OAuth client — the Phase 7 Gate 12 verification run itself. The widget has never been used by a real hospital partner.

## J3. Partner reference app — CANONICAL pattern, server-side token exchange

### J3.1 App shape

`examples/partner-reference-app/`:

```
package.json    — express ^4.21.2, node >=18
server/
  index.mjs     — Express server, 1 endpoint: GET /token (server-side OAuth exchange)
public/
  index.html    — HIS/EMR shell
  app.js        — widget bootstrap, fetch /token, configure <icoder-embedded>
README.md       — Phase 7 Gate 12 walkthrough
```

### J3.2 Token exchange flow (security audit)

`examples/partner-reference-app/server/index.mjs`:

```javascript
app.get('/token', async (req, res) => {
  const r = await fetch(`${ICODER_BASE_URL}/api/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: process.env.ICODER_CLIENT_ID,
      client_secret: process.env.ICODER_CLIENT_SECRET,
      scope: 'agents:run runs:read'
    })
  });
  const { access_token, expires_in } = await r.json();
  res.json({ accessToken: access_token, expiresIn: expires_in });
});
```

This is the **canonical Corti-style pattern**: partner's `client_secret` never reaches the browser. The browser receives only a short-lived `access_token`. iCoDer's reference app implements this correctly.

### J3.3 Widget bootstrap

`examples/partner-reference-app/public/app.js:29`:

```javascript
await import(`${cfg.baseUrl}/api/embedded/assistant.js`);
```

The widget is dynamically imported from the iCoDer backend after `/token` returns. This avoids npm dependency entirely and is the recommended pattern.

### J3.4 Live E2E verification

Per Phase 7 Gate 12 memory: real Playwright MCP E2E verified end-to-end:
- Server-side token exchange (HTTP 200, access_token returned)
- Widget CORS-allowlisted load
- Real DeepSeek run (5462ms, ICD D86.000 + S22.400)
- Signed trace URL surfaced
- Patient context events fired

The reference app is **demo-grade real**, not theater.

## J4. API Client registry — Phase 7 Gate 5, 9 endpoints live

### J4.1 Endpoints

`backend/app/api/platform_api_clients.py` — 9 CRUD endpoints under `/api/clients/*`:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/clients` | Create new OAuth client |
| GET | `/api/clients` | List clients (org-scoped) |
| GET | `/api/clients/{id}` | View client detail |
| POST | `/api/clients/{id}/disable` | Soft-disable |
| POST | `/api/clients/{id}/enable` | Re-enable |
| POST | `/api/clients/{id}/rotate-secret` | Rotate client_secret |
| PUT | `/api/clients/{id}/scopes` | Update scope list |
| PUT | `/api/clients/{id}/origins` | Update allowed_origins |
| POST | `/api/clients/{id}/test` | Smoke-test client credentials |

All endpoints org-scoped via `organization_id`. Wildcard origin (`*`) is explicitly forbidden. Secret is shown ONCE on create; subsequent reads return `is_active` only.

### J4.2 DB reality

```
oauth_clients table (1 row):
  client_id: partner-ref-07ef23d306cf
  name: Partner Reference App
  is_active: true
  scopes: agents:run runs:read
  allowed_origins: ["http://localhost:4400"]
  created_at: 2026-07-14 05:12:09
```

**Only 1 OAuth client has ever been registered.** Phase 7 Gate 12 reference app is the sole external integration. No hospital partner, no ISV, no third-party developer is in the system.

### J4.3 Console Sentinel for api_client_id

Per Phase 7 Gate 8 memory: Console-initiated runs use `api_client_id IS NULL` as the sentinel. The `/api/usage/by-client` endpoint maps this to a synthetic `"console"` bucket. This is correct design — Console sessions are not partner runs.

## J5. Phase 7 hard checkpoints — closed but single-tenant

### J5.1 Hard Checkpoint A (Gate 3 — Server-side idempotency)

`idempotency_records` distribution by `api_client_id`:

```
NULL/''  10  (Console-initiated Phase 7 testing)
partner-ref-07ef23d306cf  1  (Phase 7 Gate 12 verification)
```

Idempotency-Key dedup works for both Console and partner paths. Phase 7 Gate 3 is live.

### J5.2 Hard Checkpoint B (Gate 7 — Signed trace URL)

Per Phase 7 Gate 7 memory: HMAC-SHA256 signed 24h token, secrets.compare_digest constant-time, org-scoped 403-not-404. 13/13 tests pass.

### J5.3 Hard Checkpoint C (Gate 10 — Three demos)

Per Phase 7 Gate 10 memory: medical-coding / CDI / DRG-DIP demos all run against real DeepSeek in Playwright MCP, all surface signed trace_url. 4 defects fixed in that gate.

### J5.4 Hard Checkpoint D (Gate 12 — Partner reference app)

CLOSED. See §J3.

## J6. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G8-001** | P1 | npm-publish | `@icoder/sdk@1.0.0-beta.2` and `@icoder/embedded@2.0.0` both return 404 from `registry.npmjs.org`. The SDK + Web Component are real on disk and pass consumer smoke, but neither is published to the public npm registry. Partners cannot `npm install` them; they must clone the monorepo or use the dist-serve widget. |
| **G8-002** | P1 | single-tenant | Only **1 OAuth client** (`partner-ref-07ef23d306cf` = Phase 7 Gate 12 reference app) has ever been registered. No hospital partner, no ISV, no third-party developer exists in the system. The "partner integration" surface is theoretical. |
| G8-003 | P2 | demo-only | The 1 partner run visible in `run_history.api_client_id` is the Phase 7 Gate 12 verification run itself. There are **zero production embedded runs** from any real consumer of the widget. |
| G8-004 | P2 | stale-deprecated | Per Gate 0 finding G0-002: 3 deprecated Web Component directories (`packages/embedded/`, `packages/embedded-vite/`, `icoder-web-component/`) still on disk alongside the live `packages/icoder-embedded/`. Confirmed in Gate 0 evidence; not cleaned up. |
| G8-005 | P3 | package-naming | Package naming splits across two scopes — `@icoder/sdk` (programmatic API) + `@icoder/embedded` (Web Component). Corti uses `@corti/sdk` + `@corti/embedded` consistently. iCoDer parity is correct, but the **publish scope `@icoder` has never been registered on npm** (no org profile). |
| G8-006 | P3 | docs-fragmentation | `examples/partner-reference-app/README.md` references Phase 7 Gate 12. There is no single canonical "Partner Integration Guide" — instructions are scattered across the reference-app README, the Console Developer Quickstart page, the SDK README, and the embedded MIGRATION-2.0.md. |

## J7. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **J1 SDK** | `REAL_BETA2_CONSUMABLE_NOT_NPM_PUBLISHED` — 12 resources, 951 LOC, 8/8 external smoke PASS; package not on registry |
| **J2 Embedded** | `REAL_V2_DIST_SERVE_HMAC_PREVIEW` — Corti-compatible method-based API, dist-served from `/api/embedded/assistant.js`, Phase 7 Gate 13A HMAC Bootstrap Ticket live |
| **J3 Reference App** | `CANONICAL_PATTERN_LIVE_DEMO_ONLY` — Server-side token exchange is correct Corti pattern; 0 real hospital partners; 1 demo run only |
| **J4 API Clients** | `9_ENDPOINTS_LIVE_SINGLE_TENANT` — Full CRUD, rotation, scope/origin management; only 1 client ever registered |
| **J5 Hard Checkpoints** | `A_B_C_D_CLOSED_BUT_THEORETICAL` — All 4 Phase 7 hard checkpoints closed in code/tests, never exercised at partner scale |

## J8. Gate 8 verdict

`EMBEDDED_AND_SDK_ARE_REAL_BUT_UNPUBLISHED_AND_SINGLE_TENANT`

Specifically:

- ✅ SDK is structurally complete (12 resources, 951 LOC, external smoke 8/8 PASS)
- ✅ Embedded Web Component implements Corti-compatible method-based API (configure / setPatientContext / runAgent / on / clearPatientContext / clearSession)
- ✅ Partner reference app implements canonical server-side token exchange — `client_secret` never reaches browser
- ✅ Phase 7 hard checkpoints A (idempotency), B (signed trace URL), C (3 demos), D (reference app) all closed in code
- ✅ API Client registry has 9 real CRUD endpoints with secret rotation, scope/origin management
- ✅ Phase 7 Gate 13A HMAC Bootstrap Ticket verified live (17 preview sessions, 5 EXCHANGED, 5 REVOKED)
- ❌ **G8-001 P1**: Neither `@icoder/sdk` nor `@icoder/embedded` is on the public npm registry — 404 from `registry.npmjs.org`
- ❌ **G8-002 P1**: Only 1 OAuth client ever registered (Phase 7 Gate 12 self-verification); no real hospital partner in the system
- ⚠️ The "partner integration" story is real in code but theoretical in production — zero external consumers
- ⚠️ 3 deprecated Web Component directories still on disk (G0-002 not cleaned)

Gate 8 closes. Proceed to **Gate 9 — Auth, Security, PHI, Multi-tenant**.
