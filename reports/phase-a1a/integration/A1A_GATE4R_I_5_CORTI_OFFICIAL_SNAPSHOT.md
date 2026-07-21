# Phase A1A Gate 4R-I.5 — Corti Official Snapshot (Clean-Room)

**Date**: 2026-07-21
**Charter**: Phase A1A Gate 4R-I
**Predecessor**: Gate 4R-I.2 (`532552e` directory index layer)
**Successor**: Gate 4R-I.6 (iCoDer capability inventory)

Charter §8 requires capturing the current Corti public docs as the
canonical clean-room target. Only public, legally obtained official
sources are used. Every undocumented behavior is marked `UNKNOWN`.

## §1. Snapshot procedure

1. `curl -sSL https://docs.corti.ai/llms.txt` — primary canonical dump
2. `curl -sSL https://docs.corti.ai/` — docs landing
3. `curl -sSL https://www.corti.ai/` — marketing landing (context only)
4. `curl -sSL https://trust.corti.ai/` — trust/compliance
5. 4 key sub-pages fetched for contract detail
6. SHA-256 each capture
7. Build capability catalog from `llms.txt` link index

## §2. Captured artefacts (8 files)

| File | Size | SHA-256 | Source | HTTP |
|---|---:|---|---|---|
| `docs.corti.ai__llms.txt` | 68974 | `752a9302...` | https://docs.corti.ai/llms.txt | 200 |
| `docs.corti.ai__index.html` | 449543 | `6c75fd5a...` | https://docs.corti.ai/ | 200 |
| `www.corti.ai__index.html` | 186209 | `d29423a9...` | https://www.corti.ai/ | 200 |
| `trust.corti.ai__index.html` | 5682 | `43932f70...` | https://trust.corti.ai/ | 403 |
| `docs.corti.ai__about_admin-api.md` | 4097 | `8961362c...` | https://docs.corti.ai/about/admin-api.md | 200 |
| `docs.corti.ai__about_compliance.md` | 5426 | `1553e0ae...` | https://docs.corti.ai/about/compliance.md | 403 |
| `docs.corti.ai__agentic_architecture.md` | 2500 | `abe58e3d...` | https://docs.corti.ai/agentic/architecture.md | 200 |
| `docs.corti.ai__assistant_introduction.md` | 5558 | `f0325112...` | https://docs.corti.ai/assistant/introduction.md | 200 |

Manifest at `docs/corti-parity/official-snapshot/CORTI_OFFICIAL_SNAPSHOT_MANIFEST.json`.

## §3. Access-blocked sources

| URL | HTTP | Reason |
|---|---|---|
| `https://trust.corti.ai/` | 403 | Cloudflare bot protection blocks scripted access; content not captured |
| `https://docs.corti.ai/about/compliance.md` | 403 | Same |

These are recorded as `UNKNOWN` in the parity matrix. Charter §1.5 rule 5
requires UNKNOWN rather than guess.

## §4. Corti capability catalog (from `llms.txt` 395 entries)

13 top-level categories with page counts:

| Category | Pages | Purpose |
|---|---:|---|
| `about` | 4 | Admin API, compliance, help, public roadmap |
| `agentic` | 33 | A2A protocol, agents CRUD, context, memory, experts |
| `api-reference` | 86 | Admin auth, customers, quotas, projects, users, etc. |
| `assistant` | 117 | Embedded API surface (addFacts, auth, configure, etc.) |
| `authentication` | 5 | Client credentials, environments, tenants, security |
| `coding` | 36 | ACHI, CCAM, CCI, CDI, CHOP, ICD-10, etc. medical coding standards |
| `get_started` | 6 | Ambient scribe, CDI outpatient, dictation, encounter coding |
| `models` | 4 | Corti-hosted EU AI models |
| `quickstart` | 3 | AI coding tools, real-time dictation, transcription |
| `release-notes` | (counted in llms.txt) | Per-product release notes |
| `sdk` | (counted in llms.txt) | Official SDKs |
| `stt` | (counted in llms.txt) | Speech-to-text API |
| `textgen` | (counted in llms.txt) | Text generation API |
| **Total** | **395** | |

Full extraction at `docs/corti-parity/official-snapshot/CORTI_CAPABILITY_EXTRACTION.txt`.

## §5. Corti capability dimensions (charter §8.1 — 30 dimensions)

| # | Dimension | Corti evidence source |
|---|---|---|
| 1 | Authentication | `authentication/overview.md`, `authentication/quickstart.md` |
| 2 | Environments (EU/US/...) | `authentication/environments_tenants.md` |
| 3 | Tenants | `authentication/environments_tenants.md` |
| 4 | Customers (sub-tenant) | `api-reference/admin/customers/*` |
| 5 | Projects | `api-reference/admin/*` |
| 6 | API clients | `authentication/creating_clients.md` |
| 7 | Rate limiting | TBD — search api-reference |
| 8 | Quotas and credits | `api-reference/admin/customers/get-quotas-for-a-customer.md` |
| 9 | Audit logging | TBD |
| 10 | Webhooks | TBD |
| 11 | A2A protocol | `agentic/a2a-protocol.md` |
| 12 | Agent CRUD | `agentic/agents/{create,get,update,delete}-agent-by-id.md` |
| 13 | Agent card | `agentic/agents/get-agent-card.md` |
| 14 | Agent registry experts | `agentic/agents/list-registry-experts.md` |
| 15 | Context and memory | `agentic/context-memory.md`, `agentic/agents/{get,delete}-context-by-id.md` |
| 16 | Tasks | `agentic/agents/get-task-by-id.md`, `agentic/agents/send-message-to-agent.md` |
| 17 | Embedded assistant API | `assistant/api-reference.md`, 117 assistant/* pages |
| 18 | Speech-to-text | `stt/*` (transcribe, recordings, transcripts) |
| 19 | Text generation | `textgen/*` (documents, facts, guided document) |
| 20 | Medical coding | `coding/*` (ICD-10, ACHI, CCAM, CCI, CHOP, CDI) |
| 21 | Corti-hosted models | `models/*` (EU-hosted frontier models) |
| 22 | SDKs | `sdk/*` |
| 23 | Compliance | `about/compliance.md` (403 — UNKNOWN); trust.corti.ai (403 — UNKNOWN) |
| 24 | Regional deployment | `authentication/environments_tenants.md` (data residency) |
| 25 | Sample apps | `get_started/*`, `quickstart/*` |
| 26 | Documentation | `docs.corti.ai` (395 pages) |
| 27 | Support / help | `about/help.md` |
| 28 | Console (admin UI) | inferred from `api-reference/admin/*` |
| 29 | Sandbox | TBD |
| 30 | Credits/billing | `api-reference/admin/customers/get-quotas-for-a-customer.md` |

Dimensions marked TBD will be extracted from the 395-page dump in
sub-gate 4R-I.7 (parity matrix).

## §6. Key Corti concepts (for parity comparison)

- **Environment** (EU/US): top-level residency boundary
- **Tenant**: customer organization within an environment
- **Project**: sub-tenant unit (Corti-specific)
- **API client**: programmatic credential with client_id + client_secret
- **Customer**: end-customer of a project (sub-sub-tenant)
- **Agent**: AI agent in the Agentic Framework; identified by ID; has card
- **Expert**: callable knowledge source (DrugBank, ClinicalTrials, calculator, ICD, etc.)
- **Context (thread)**: conversation/session state with memory chunks
- **Task**: agent execution instance
- **Embedded Assistant**: widget that runs Corti Assistant inside a customer's app

## §7. Corti Agentic Framework experts (sample from llms.txt)

- DrugBank (drug lookups, DDI)
- ClinicalTrials.gov (study search)
- Medical Calculator (BMI, HbA1c, etc.)
- ICD-10 (diagnosis coding)
- (33 agentic/* pages include more)

Corti claims EU-hosted frontier AI models as a separate product line
(`models/*`).

## §8. Clean-room compatibility scope (initial)

For each Corti capability dimension, the parity matrix in 4R-I.7 will
assess iCoDer against this snapshot. The matrix uses only these
statuses (charter §9):

```
IMPLEMENTED_AND_RUNTIME_VERIFIED
IMPLEMENTED_BUT_PARTIALLY_TESTED
IMPLEMENTED_BUT_BROKEN
CONTRACT_ONLY
STUB_OR_MOCK_ONLY
TEST_ONLY
DOCUMENTED_ONLY
NOT_IMPLEMENTED
BLOCKED_BY_MISSING_SPEC
BLOCKED_BY_EXTERNAL_DEPENDENCY
BLOCKED_BY_UNKNOWN_REQUIREMENT
```

Corti capabilities with no public spec → iCoDer status will be
`BLOCKED_BY_MISSING_SPEC` or `BLOCKED_BY_UNKNOWN_REQUIREMENT`.

## §9. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Use third-party blogs as canonical | NOT DONE ✓ |
| Use search summaries as canonical | NOT DONE ✓ |
| Use non-official screenshots | NOT DONE ✓ |
| Use repo's historical `docs/corti-reverse-engineered/` | NOT DONE ✓ |
| Copy Corti proprietary prompts/code/UI | NOT DONE ✓ |
| Guess undocumented behavior (vs. marking UNKNOWN) | NOT DONE ✓ |
| Push / PR / master | NOT DONE ✓ |

## §10. Provisional verdict

```
PASS_A1A_GATE4R_I_5_CORTI_OFFICIAL_SNAPSHOT_CAPTURED
```

Tier: CAPTURED (not VERIFIED). The snapshot is a capture, not a
certification. It does NOT assert that iCoDer matches Corti.

## §11. Next

Gate 4R-I.6 — iCoDer capability inventory:
- Read OpenAPI schema from backend FastAPI
- Read route registrations in `backend/app/api/*`
- For each route, assess status against the 18 verification dimensions
- Cross-reference against this Corti catalog (gap analysis)
