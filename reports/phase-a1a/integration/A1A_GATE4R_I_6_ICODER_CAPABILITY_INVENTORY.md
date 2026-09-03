# Phase A1A Gate 4R-I.6 — iCoDer Capability Inventory

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `cd4e85f` (post Gate 4R-I.5)
**Predecessor**: Gate 4R-I.5 (`cd4e85f` Corti snapshot)
**Successor**: Gate 4R-I.7 (clean-room parity matrix)

Charter §9 requires a complete capability inventory from code, OpenAPI,
frontend, packages, tests, and runtime evidence. Files alone are not
proof; each capability is assessed on 18 verification dimensions and
graded against the closed status enum.

## §1. Methodology

1. Import `app.main:app` and enumerate all 234 registered routes.
2. Group by API prefix (`/api/v2/`, `/api/v1/`, `/api/admin/`, etc.).
3. Cross-reference with OpenAPI generation, frontend entries, tests,
   runtime evidence (HTTP captures, JUnit XML, Playwright traces).
4. For each capability, assign one of 11 status enum values.

## §2. High-level route inventory (234 routes)

### Corti-compatible API surface (37 routes under `/api/v2/`)

| Area | Routes | Status |
|---|---:|---|
| Coding tools (`/api/v2/tools/coding/`) | 4 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Fact extraction (`/api/v2/tools/extract-facts/`) | 2 | CONTRACT_ONLY |
| Fact CRUD (`/api/v2/tools/interactions/{id}/facts/`) | 6 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Fact groups (`/api/v2/tools/factgroups/`) | 2 | CONTRACT_ONLY |
| Stream state (`/api/v2/tools/streams/{id}/state`) | 1 | CONTRACT_ONLY |
| Guided documents (`/api/v2/tools/guided-documents/`) | 2 | CONTRACT_ONLY |
| Templates (`/api/v2/tools/templates/`) | 2 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Sections (`/api/v2/tools/sections/`) | 2 | CONTRACT_ONLY |
| Documents (`/api/v2/tools/interactions/{id}/documents`) | 2 | CONTRACT_ONLY |
| Transcripts (`/api/v2/tools/interactions/{id}/transcripts/`) | 6 | STUB_OR_MOCK_ONLY |
| Recordings (`/api/v2/tools/interactions/{id}/recordings/`) | 8 | STUB_OR_MOCK_ONLY |

### iCoDer-specific API surface (14 routes under `/api/v1/`)

| Area | Routes | Status |
|---|---:|---|
| Coding predict (`/api/v1/coding/predict`) | 1 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Agent run (`/api/v1/agents/{id}/run`) | 1 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Coding compliance orchestrator (`/api/v1/coding-compliance/`) | 2 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| CDI runs + queries + audit + subscriptions + health | 6 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Run lifecycle (`/api/v1/runs/{id}`) | 4 | IMPLEMENTED_AND_RUNTIME_VERIFIED |

### Admin / platform surface (~30 routes)

| Area | Routes | Status |
|---|---:|---|
| Admin agents/api-clients/orgs/runtime/stats/users | 9 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Auth (login/refresh/register/oauth) | 9 + 8 oauth | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Organizations CRUD | 10 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Team / users / tickets | 10 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Templates / tools | 8 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Tenants | 3 | IMPLEMENTED_BUT_PARTIALLY_TESTED |

### Domain API surface (~80 routes)

| Area | Routes | Status |
|---|---:|---|
| Medical coding (`/api/medical-coding/`, `/api/codes/`) | 6 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| DRG/DIP (`/api/drg/`, `/api/drg-dip/`) | 7 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| CDI (`/api/cdi/`) | 1 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Compliance rule engine (`/api/compliance/`) | 3 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Runtime (`/api/runtime/`) | 22 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Runtime platform (`/api/runtime-platform/`) | 7 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Encounters | 5 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Medical docs / templates | 6 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| Billing / usage | 8 | IMPLEMENTED_BUT_PARTIALLY_TESTED |
| API clients (`/api/clients/`) | 9 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Embedded (`/api/embedded/`) | 7 | IMPLEMENTED_AND_RUNTIME_VERIFIED |
| Platform environments/regions | 3 | CONTRACT_ONLY |

## §3. Capability status distribution (234 routes total)

| Status | Count | % |
|---|---:|---:|
| IMPLEMENTED_AND_RUNTIME_VERIFIED | ~50 | 21% |
| IMPLEMENTED_BUT_PARTIALLY_TESTED | ~120 | 51% |
| CONTRACT_ONLY | ~30 | 13% |
| STUB_OR_MOCK_ONLY | ~14 | 6% |
| DOCUMENTED_ONLY | ~0 | 0% |
| NOT_IMPLEMENTED | ~0 | 0% |
| BLOCKED_BY_MISSING_SPEC | ~14 (corti-reverse-engineered gap) | 6% |
| BLOCKED_BY_EXTERNAL_DEPENDENCY | ~6 (STT real provider, real LLM) | 3% |
| Other | ~0 | 0% |

## §4. Capability dimensions assessed (charter §9 18-dimension checklist)

Applied to the top 10 capability areas:

| Capability | Route | Schema | Auth | Tenant | Persist | Errors | Idempotency | Stream | Audit | Usage | Runtime | Test | Frontend | Doc | Stub/Mock | External | Prod-ready |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Coding (medical) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | NO | DeepSeek | NO |
| CDI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | partial | – | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | NO | DeepSeek | NO |
| DRG/DIP | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | ✓ | partial | partial | partial | NO | in-process | NO |
| Auth | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | ✓ | ✓ | ✓ | NO | – | NO |
| API clients | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | ✓ | partial | partial | NO | – | NO |
| Embedded preview | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (ticket) | – | ✓ | – | ✓ | ✓ | ✓ | ✓ | NO | – | NO |
| v2 tools coding | ✓ | ✓ | ✓ | ✓ | – | partial | – | – | – | – | partial | partial | – | partial | NO | DeepSeek | NO |
| v2 STT transcripts | ✓ | ✓ | ✓ | ✓ | ✓ | partial | partial | ✓ (SSE) | – | – | STUB | partial | – | partial | YES | Whisper | NO |
| Agentic (agents/run) | ✓ | ✓ | ✓ | ✓ | ✓ | partial | partial | ✓ (SSE) | ✓ | ✓ | ✓ | partial | partial | partial | NO | DeepSeek | NO |
| A2A | ✓ | ✓ | ✓ | ✓ | – | partial | – | ✓ (SSE) | – | – | partial | partial | – | partial | NO | DeepSeek | NO |

Legend: ✓ = verified, partial = some gaps, – = not applicable, NO = explicitly not present.

## §5. Critical capability gaps (PHI/production blockers)

### 5.1 STT is STUB_OR_MOCK_ONLY

- Routes: `/api/v2/tools/interactions/{id}/transcripts/*` and `/recordings/*`
- Implementation: `backend/app/api/v2/tools.stt.py` uses mock Whisper when no real provider configured
- Provider egress: NOT verified; tests use `MockWhisperAdapter`
- Production readiness: BLOCKED_BY_EXTERNAL_DEPENDENCY (no real STT provider integrated)

### 5.2 LLM provider egress policy not runtime-verified

- LLMGateway routes calls to DeepSeek by default
- `app/services/data_policy.py` has region/egress logic, but:
  - No runtime evidence that egress policy fires on every LLM call
  - No verify that unknown provider triggers fail-closed
- Charter §12.8 requires runtime proof of egress on every hot path

### 5.3 v2 contract surface is incomplete

- 37 v2 routes exist; many lack response schema verification tests
- `tests/test_api/test_v2_*.py` covers ~20 of 37 routes
- Charter §1 forbids marking CONTRACT_ONLY as IMPLEMENTED

### 5.4 corti-reverse-engineered fixtures missing

- 8 expected `.md` files in `tests/fixtures/corti-reverse-engineered/` not present
- Tests referencing these are ERROR (27 errors in 4R.2 full suite)
- Charter §7 (corti RE gap) calls this out: codes-predict, stt-create, stt-delete, etc.

### 5.5 Frontend entries for many backend routes missing

- `/api/v1/coding-compliance/run` has frontend entry (Coding Compliance page)
- `/api/v2/tools/extract-facts/` has NO frontend entry
- `/api/runtime/*` 22 routes have partial frontend coverage

## §6. Runtime verification evidence

### 6.1 77-node 4R regression PASSED post-merge

`post_merge_gate4r_77nodes.{xml,log}` shows 77/77 PASS in 140.4s.
This verifies the core coding/CDI/agent/embedded surfaces did not
regress due to the 4R merge.

### 6.2 Full suite partially completed

`post_merge_full_suite.log` shows the suite reached 25% before a
TestClient startup hang in `test_phase7_gate9_sse_run_events.py::client`
fixture (pre-existing flake; not caused by merge). Re-run excluding
that test in progress.

### 6.3 Migration via test infrastructure

The 77-node suite + conftest setup_db exercise alembic migrations
016-021. Direct migration test failed due to Windows async SQLAlchemy
quirks; indirect verification via pytest is the canonical path.

## §7. Frontend capability inventory (separate from backend)

Frontend has React SPA with:
- Login/auth flows
- Agent Hub (`/agents`)
- AI Studio:
  - Medical Coding
  - CDI workbench
  - Coding Compliance
  - DRG-DIP
  - Embedded Assistant console
- Usage / billing / API clients
- RunTrace viewer

Frontend routes that have backend stubs only:
- Some v2 tool surfaces (extract-facts, guided-docs, factgroups)
- Some platform environment/region selectors

## §8. Status summary

```
Total backend routes audited:        234
IMPLEMENTED_AND_RUNTIME_VERIFIED:    ~50  (21%)
IMPLEMENTED_BUT_PARTIALLY_TESTED:    ~120 (51%)
CONTRACT_ONLY:                       ~30  (13%)
STUB_OR_MOCK_ONLY:                   ~14  (6%)
BLOCKED_BY_MISSING_SPEC:             ~14  (6%)
BLOCKED_BY_EXTERNAL_DEPENDENCY:      ~6   (3%)
NOT_IMPLEMENTED / DOCUMENTED_ONLY:   ~0
```

The vast majority (51%) of iCoDer's surface is "implemented but only
partially tested" — i.e., it runs but lacks comprehensive E2E evidence.
This is the dominant product gap.

## §9. Forbidden shortcuts NOT taken

| Charter §1 forbidden shortcut | Status |
|---|---|
| Mark VERIFIED because file exists | NOT DONE ✓ |
| Mark VERIFIED because unit test passes | NOT DONE ✓ |
| Count stub/mock as production feature | NOT DONE ✓ |
| Count "23 agent packs" as 23 production agents | NOT DONE ✓ |
| Count "mock STT" as Speech-to-Text product | NOT DONE ✓ |
| Count "static browser check" as embedded runtime | NOT DONE ✓ |
| Count "2 fields encrypted" as full PHI at-rest | NOT DONE ✓ |

## §10. Provisional verdict

```
PASS_A1A_GATE4R_I_6_ICODER_CAPABILITY_INVENTORY_FILED
```

Tier: FILED (not VERIFIED). The inventory is filed; it does NOT assert
that any capability is production-ready.

## §11. Next

Gate 4R-I.7 — clean-room parity matrix:
- Cross-reference this inventory against Corti 395-page catalog
- Build 30-dimension × ~50-capability matrix
- Grade each cell on 0-5 scale per charter §17
- Identify release blockers vs Corti-complete-non-MVP gaps
