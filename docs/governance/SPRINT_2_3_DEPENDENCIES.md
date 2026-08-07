# Sprint 2 / Sprint 3 Dependencies

**Date**: 2026-08-07
**Sprint 1 status**: engineering-doable subset shipped (M1-M4 minus publish/DNS/deploy)
**This document**: enumerates every Sprint 2 / Sprint 3 task and tags its
dependency type so the next sprint can plan around concrete blockers
rather than re-discovering them.

## Legend

- 🔴 **EXTERNAL**: requires a credential, secret, or account that is NOT
  in the engineering team's possession. Engineering cannot unblock alone.
- 🟡 **CROSS-FUNCTIONAL**: requires design, product, or charter-board
  input. Engineering can scaffold but not finalize.
- 🟢 **ENGINEERING**: pure code, no external dependency. Can ship in any
  sprint that has capacity.
- ⚪ **CHARTER-GATED**: requires charter board approval (5-tuple
  interaction). Must NOT be shipped under PARTIAL_*_FILED verdict.

---

## Sprint 2 — P0: design partner developer experience

### P1 — `npm publish @icoder/sdk@1.0.0`

- **Dependency type**: 🔴 EXTERNAL (npm org + 2FA + DNS)
- **Blocks**: every external developer who wants to `npm install`
- **Pre-conditions** (from `packages/icoder-sdk/PUBLISH.md`):
  1. `https://api.cn.icoder.cloud` resolves and serves 200 on `/api/rest/v1/health`
  2. npm organization `@icoder` registered; publishing identity has 2FA
  3. `npm run build` clean; `dist/` reproducible from clean checkout
  4. CHANGELOG.md updated to real `1.0.0` version header
- **Engineering readiness**: ✅ all pre-publish engineering items complete
  in Sprint 1 (CHANGELOG, PUBLISH, README baseURL).

### P2 — Docusaurus site deploy to `docs.icoder.cloud`

- **Dependency type**: 🔴 EXTERNAL (DNS + TLS + hosting account)
- **Blocks**: every external developer who needs docs
- **Pre-conditions**:
  1. DNS record `docs.icoder.cloud` → Vercel / Netlify / Cloudflare Pages
  2. TLS certificate provisioned
  3. `docs-site/` `npm install` + `npm run build` clean
  4. 5-10 core docs migrated from `docs/` (Sprint 2 task P3)
- **Engineering readiness**: ✅ scaffold complete in Sprint 1; migration
  list in `docs-site/README.md`.

### P3 — Migrate 5-10 core docs from `docs/` to `docs-site/docs/`

- **Dependency type**: 🟢 ENGINEERING
- **Pre-conditions**: none — content rewrite, can start immediately in Sprint 2
- **Migration list** (priority order, see `docs-site/README.md` for full table):
  1. `docs/QUICKSTART.md` → `docs-site/docs/quickstart.md` (P0)
  2. `docs/SDK-TUTORIAL.md` → `docs-site/docs/sdk/tutorial.md` (P0)
  3. `docs/sdk/*` → `docs-site/docs/sdk/*` (P0)
  4. `docs/cloud/CLOUD_DEPLOYMENT.md` → `docs-site/docs/deploy/cloud.md` (P1)
  5. `docs/agent-pack.md` → `docs-site/docs/agent-pack/format.md` (P1)
  6. `docs/ICODER_V1_{A2A,MCP,AGENT_CARD}_SPEC.md` → `docs-site/docs/protocol/*` (P2)

### P4 — Console API Clients: rotate-secret endpoint + UI

- **Dependency type**: 🟢 ENGINEERING
- **Pre-conditions**: none — see `docs/governance/CONSOLE_API_CLIENTS_AUDIT.md`
- **Scope**:
  - Backend: `POST /api/oauth/clients/{id}/rotate-secret`
  - Backend: revoke all outstanding refresh tokens on rotate
  - Frontend: "Rotate Secret" button + reveal-once modal (reuse create flow)
- **Engineering readiness**: ✅ audit complete; remediation scope clear.

### P5 — Console API Clients: surface `last_used_at`

- **Dependency type**: 🟢 ENGINEERING
- **Pre-conditions**: none — frontend already wired, fix backend `_handle_client_credentials`
- **Scope**:
  - Backend: in `_handle_client_credentials`, write `OAuthClient.last_used_at = utcnow()`
  - Backend: alembic migration if column missing (check current schema)
  - Frontend: NO CHANGES (already reads `c.last_used_at`)

### P6 — Real LLM provider credentials in cloud environments

- **Dependency type**: 🔴 EXTERNAL (DeepSeek / Azure / Qwen / Moonshot API keys)
- **Blocks**: every cloud-mode runtime call
- **Pre-conditions**:
  1. `LLM_API_KEY` provisioned in cloud KMS (not on disk)
  2. `ICODER_CREDENTIAL_LLM` vault path configured per region
  3. KMS rotation hook fired at least once (Phase A1D.4 deliverable)
- **Engineering readiness**: ✅ fallback factories + auto-failover shipped
  in Phase A1D.4; just need real keys.

### P7 — KMS rotation hook execution (per-region)

- **Dependency type**: 🔴 EXTERNAL (KMS service access)
- **Blocks**: `PRODUCTION_READINESS` charter field improvement
- **Pre-conditions**:
  1. KMS service IAM role assigned to iCoDer runtime
  2. Rotation lambda / cloud function deployed
  3. `KMSVersionToken` cache validated against real KMS

### P8 — Per-route `policy_decision` + `purpose_of_use` wiring

- **Dependency type**: 🟢 ENGINEERING
- **Pre-conditions**: none — Phase A1D.3 primitives shipped, just need
  per-route wiring in agent_run.py / oauth.py / etc.
- **Engineering readiness**: ✅ primitive layer complete; wiring is
  mechanical pass.

### P9 — 20 baseline test failures follow-up (Phase A1D.5 deferred)

- **Dependency type**: 🟢 ENGINEERING (mostly) + 🔴 (Windows-only MCP unicode)
- **Pre-conditions**: none for 18/20; Linux CI for the remaining 2
- **Scope**: see `audit/phase-a1d/` detailed list

### P10 — Compliance guardrail PASS-vs-WARNING decision

- **Dependency type**: 🟡 CROSS-FUNCTIONAL (product owner decision)
- **Blocks**: A1D.5 full closure
- **Open question**: should `manual_review_required=true` but no `severity=critical`
  issue be PASS or WARNING? Product owner to decide.

---

## Sprint 3 — Pilot readiness

### G1 — Pilot environment hardening

- **Dependency type**: 🔴 EXTERNAL (real hospital data + IT ops)
- **Blocks**: first paying design partner
- **Pre-conditions**:
  1. All Sprint 2 P0 items closed
  2. 等保 (MLPS 2.0) level 3 certification in progress
  3. Design partner signed pilot agreement
  4. Real PHI test corpus (anonymized) provisioned

### P7-pilot — Per-tenant encryption keys (Phase A1D finding)

- **Dependency type**: 🟢 ENGINEERING
- **Pre-conditions**: per-tenant KMS namespace provisioned
- **Scope**: replace single Fernet master key with per-tenant derived keys

### P8-pilot — DRG-DIP rule engine GA

- **Dependency type**: 🟡 CROSS-FUNCTIONAL (clinical rules)
- **Pre-conditions**: coding rule set R001-R010 stable; DRG-DIP rule
  structure must be signed off by clinical coding consultant

### P9-pilot — Bidirectional CDI ↔ Medical Coding loop

- **Dependency type**: 🟡 CROSS-FUNCTIONAL (clinical workflow)
- **Pre-conditions**: CDI Agent shipped to Stage 4 (production_ready=true)

---

## Charter-gated items (NOT in any sprint until 5-tuple improves)

The following items MUST NOT ship under current `PARTIAL_*_FILED` verdict.
Any sprint that wants to ship these needs charter board approval + fresh
re-gate per Charter §Gate 7.

- ⚪ **Corti parity re-attempt**: needs fresh re-gate A2+ per Charter
- ⚪ **`PRODUCTION_READY` verdict emission**: requires all 5-tuple fields
  to advance from current state (GATE4_8=CONTRADICTED / GATE4_9=SUPERSEDED /
  GATE4_ACCEPTANCE=REOPENED / CORTI_PARITY=NOT_DEMONSTRATED /
  PRODUCTION_READINESS=NOT_VERIFIED)
- ⚪ **On-prem / hospital-internal Docker deployment**: rejected by R6
  cloud-only ADR (`docs/governance/DEPLOYMENT_PATH_ADR.md`)

---

## Dependency graph (simplified)

```
Sprint 1 (DONE)        Sprint 2 (P0)              Sprint 3 (Pilot)
─────────────          ─────────────────          ─────────────────
M1 SDK scaffold  ────► P1 npm publish  ─────────► G1 Pilot env
                                              │
M2 Docusaurus    ────► P2 DNS + deploy  ──────► │
                       P3 Doc migration         │
M3 Quickstart    ────► (consumes P3)            │
                                              │
M4 API Clients   ────► P4 Rotate secret         │
audit                P5 last_used_at            │
                                                │
A1D.4 LLM fallback ─► P6 Real LLM keys  ──────► │
A1D.4 KMS rotation ► P7 KMS hook exec  ────────► │
A1D.3 policy/purpose► P8 Per-route wiring ────► │
A1D.5 baseline    ► P9 20 test follow-up ─────► │
                       P10 PASS-vs-WARNING (PO) │
                                                ▼
                                          G1 Pilot readiness
                                          P7-pilot per-tenant KMS
                                          P8-pilot DRG-DIP GA
                                          P9-pilot CDI ↔ MC loop
```

## What Sprint 1 actually shipped (this session)

| Deliverable | Path | Status |
|------------|------|--------|
| M1.1 CHANGELOG | `packages/icoder-sdk/CHANGELOG.md` | ✅ |
| M1.2 PUBLISH checklist | `packages/icoder-sdk/PUBLISH.md` | ✅ |
| M1.3 README cloud-only baseURL | `packages/icoder-sdk/README.md` | ✅ |
| M2.1 Docusaurus scaffold | `docs-site/` (10 files) | ✅ |
| M3 5-min Quickstart | `docs-site/docs/quickstart.md` | ✅ |
| M4 API Clients audit | `docs/governance/CONSOLE_API_CLIENTS_AUDIT.md` | ✅ |
| This deps doc | `docs/governance/SPRINT_2_3_DEPENDENCIES.md` | ✅ |

**Charter compliance** (this session):
- 5-tuple (GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE / CORTI_PARITY /
  PRODUCTION_READINESS): NOT MUTATED.
- 8 forbidden verdicts: NOT EMITTED (no PRODUCTION_READY / etc.).
- 12 forbidden git ops: NOT PERFORMED (no push, no master, no amend, no
  `-A`, no force).
- Currency: CNY (¥) convention honoured; no USD references in new docs.

## Open questions for charter board (no answer needed to ship Sprint 1)

1. Should Sprint 2 P1 `npm publish` be a charter-gated event? Default
   assumption: no (publish is orthogonal to 5-tuple, per PUBLISH.md).
2. Can Sprint 2 start before Sprint 1 final commit lands on master?
   Default assumption: yes (Sprint 2 work touches different files).
3. Is Docusaurus DNS `docs.icoder.cloud` the canonical URL, or should
   it be `developer.icoder.cloud`? Open for product/marketing input.
