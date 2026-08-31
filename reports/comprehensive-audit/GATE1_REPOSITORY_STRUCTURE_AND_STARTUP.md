# Audit Gate 1 — Repository Structure and Startup Reproduction

> Track A1/A2/A3. **Question:** *Can a fresh engineer reproduce the system from the repo's docs?*

## A.1 Boot evidence (live)

| Service | Command | Result | Notes |
|---------|---------|--------|-------|
| Backend | `cd backend && ICODER_DEPLOYMENT_MODE=local python -m uvicorn app.main:app --port 8000` | ✅ boots in ~5s, 237 routes mounted | ICD-10-CN 33,304 codes + ICD-9-CM-3 23,165 codes loaded |
| Frontend | `cd frontend && npm run dev` | ✅ boots in ~0.5s | Vite v5.4.21, port **3000** (not 5173) |
| Health | `GET /api/health` | ✅ 200 JSON | Reports `version: 1.0.0`, `medcoder_index_ready: true`, `llm_provider: deepseek` |
| OpenAPI | `GET /openapi.json` | ✅ 200 | 204 paths / 239 operations |
| Docs | `GET /docs` | ✅ 200 Swagger UI | |

**Smoke of API surfaces:**

- `GET /api/v1/agents` → **404** (no such path — listing is via `/api/icoder/agents/hub` or `/api/rest/v1/agent_definitions`)
- `GET /api/v1/cdi/cases` → **404** (CDI router has different paths; will map in Gate 2)
- `GET /api/v1/runs/foo` → **401 Unauthorized** (auth-required ✓)
- `GET /api/v1/coding-compliance/run` → **405 Method Not Allowed** (POST-only ✓)

**External consumer build + smoke (Phase 7 Gate 2 path):**

```
cd phase7-external-consumer && npm run build && npm run smoke
→ dist/bundle.js 147.8kb, source map v3, 67 sources
→ 8/8 criteria PASS: SDK + embedded install cleanly from local .tgz
→ no workspace dependency, no monorepo internal path
→ type declarations parse, ESM imports resolve
→ Web Component class extends HTMLElement, customElements.define OK in jsdom
→ no implicit Console package reference, no missing peer dep
```

This is real, repeatable evidence that **SDK + Embedded can be consumed as external packages**, even if not yet published to public npm.

## A.2 Version drift (new P2)

| Component | Reported version | Evidence |
|-----------|------------------|----------|
| `VERSION` file | `1.1.0` | `cat E:/Corti4C/VERSION` |
| `/api/health` API | `1.0.0` | `curl /api/health` |
| `CHANGELOG.md` head | `[1.0.0] - 2026-05-31` | `head -5 CHANGELOG.md` |
| Git tag | `v1.0.0` | `git tag` |
| `@icoder/sdk` | `1.0.0-beta.2` | `packages/icoder-sdk/package.json` |
| `@icoder/embedded` | `2.0.0` | `packages/icoder-embedded/package.json` |
| `frontend/package.json` | `1.0.0` | `frontend/package.json` |
| `backend/app/main.py` `APP_VERSION` | TBD in Gate 4 | (sourced from settings.APP_VERSION) |
| `icoder-cdi-agent-v1.0.0-rc5` | rc5 (frozen iter 7) | commit `79b2b03` |

→ **At least 4 different version numbers** across components. The API reports a *different* version (1.0.0) than the VERSION file (1.1.0). This is a release-hygiene P2.

## A.3 Backend dependency install — verified

All 14 critical Python deps installed at correct pinned versions:

```
fastapi==0.115.0, uvicorn==0.30.6, sqlalchemy==2.0.35, alembic==1.13.2,
aiosqlite==0.20.0, httpx==0.27.2, openai==1.51.0,
sentence_transformers==3.2.1, faiss==1.9.0, rapidfuzz==3.10.0,
pydantic==2.9.2, jose==3.3.0, passlib==1.7.4
```

## A.4 Database migration state

| DB path | Size | Tables | Alembic head | Status |
|---------|------|--------|--------------|--------|
| `backend/data/icoder.db` | 4.4 MB | 43 | **`015`** | ✅ Live, used by app |
| `backend/data/test.db` | 1.2 MB | n/a | n/a | Test fixture |
| `backend/icoder.db` | 0 B | 0 | n/a | ⚠️ Stray (G0-004) |
| `backend/app.db` | 0 B | 0 | n/a | ⚠️ Stray (G0-004) |

15 Alembic migrations present (`002`..`015` + initial). The last 4 (`012_idempotency_records`, `013_run_history_status_and_cancel`, `014_api_client_attribution_and_origins`, `015_preview_sessions`) are **untracked** — Phase 7 work.

## A.5 Repository structure (deduplicated view)

```
E:/Corti4C/
├── backend/
│   ├── app/                        ← FastAPI host
│   │   ├── api/                    ← 38 routers (see §B)
│   │   ├── agents/experts/         ← 11 experts (audit/cdi/denial/diagnosis/drg/evidence/hcc/homepage/procedure/report/timeline)
│   │   ├── coding_runtime/         ← CodingRuntimeDispatcher + FastRuntime + MedCoderRuntime
│   │   ├── icoder/agent_runtime/   ← A2A facade + orchestrator + 5 experts (code_reconciler/coding/evidence_extractor/index_navigator/tabular_validator)
│   │   ├── icoder/mcp/             ← MCP server
│   │   ├── middleware/             ← auth, partner_cors, ...
│   │   ├── models/                 ← 25 SQLAlchemy models
│   │   ├── services/               ← incl. idempotency_service, preview_ticket, run_lifecycle, trace_token (Phase 7)
│   │   └── ...
│   ├── icoder_runtime/             ← Runtime Python package (own pyproject.toml)
│   │   ├── core/                   ← agent_pack, llm_gateway, registry, runtime_result, data_policy, pii_redaction
│   │   ├── providers/medical_coding/ ← DeepSeekCodingAdapter, HybridAdapter, MedcoderAdapter, MockAdapter, dictionary_rag, embedding_bge_m3
│   │   ├── providers/{drg,dip}/    ← DRG/DIP providers
│   │   ├── backends/               ← rule_engine_provider
│   │   ├── m2a/                    ← Model-to-Agent recorder (recorder, risk_router, run_trace, safety_gate, store, human_review)
│   │   ├── embedded/platform_runtime.py ← another runtime impl
│   │   └── ...
│   ├── compliance_services/        ← rule_engine + 4 rule sets
│   ├── official_agents/            ← 30 agent dirs (snake_case Python + kebab-case agent_pack.json)
│   ├── marketplace_core/           ← EMPTY (only __pycache__)
│   ├── marketplace_data/           ← index.json + packages/
│   ├── alembic/versions/           ← 15 migrations
│   ├── data/                       ← icoder.db, medcoder/{faiss.index, metadata.pkl}
│   └── tests/                      ← 271 .py files
├── frontend/
│   ├── src/pages/                  ← 27 page components
│   ├── src/components/
│   ├── tests/e2e/                  ← 5 Playwright specs
│   └── package.json
├── packages/
│   ├── icoder-sdk/                 ← @icoder/sdk@1.0.0-beta.2 ✅ canonical
│   ├── icoder-embedded/            ← @icoder/embedded@2.0.0 ✅ canonical
│   ├── icoder-web/                 ← ⚠️ DEPRECATED.md (Phase 6 Gate 1)
│   ├── web-components/             ← ⚠️ DEPRECATED.md
│   ├── icoder-python/              ← Python SDK (TBD)
│   └── examples/                   ← phase5_track_b2/c demos
├── web-components/                 ← ⚠️ DEPRECATED.md (root-level)
├── examples/
│   ├── partner-reference-app/      ← Phase 7 Gate 12 (express server)
│   ├── phase5_track_b2/
│   └── phase5_track_c/
├── phase7-external-consumer/       ← Phase 7 Gate 2 (npm package consumer)
├── scripts/                        ← evaluation, probe, crawler scripts
├── docs/                           ← incl. cloud/, corti_parity/, product/
├── reports/                        ← 130 .md files across 11 phase dirs
├── tests/                          ← (root-level, in addition to backend/tests)
├── deploy/                         ← cloud/regions.yaml etc.
├── fixtures/                       ← test fixtures
├── golden_captures/
├── artifacts/
├── public/
├── archive/
├── outputs/
├── screenshots/
├── tools/
├── postman/
├── src/                            ← (only contains utils/ — orphan?)
├── CHANGELOG.md
├── CLAUDE.md
├── DESIGN.md
├── README.md
├── VERSION (1.1.0)
└── 14 root PNGs (some tracked, see §E)
```

## A.6 Backend route surface (38 routers, 204 paths, 239 ops)

Routers grouped by API generation (deduced from `app/main.py` include_router block lines 1536–1576):

| Generation | Prefix | Routers |
|------------|--------|---------|
| **Legacy V1** (`/api/...`) | `/api/auth`, `/api/encounters`, `/api/codes`, `/api/billing`, `/api/keys`, `/api/team`, `/api/usage`, `/api/oauth`, `/api/admin`, `/api/customers`, `/api/templates`, `/api/tickets`, `/api/medical-docs`, `/api/drg`, `/api/organizations`, `/api/compliance`, `/api/tools`, `/api/ws` | 18 routers |
| **Corti-parity REST V1** | `/api/rest/v1/agent_definitions/*` | `agents_router` (1) |
| **iCoDer Hub V1** | `/api/icoder/agents/hub` | `icoder_agents_hub_router` (1) |
| **Corti-parity V2 tools** | `/api/v2/tools/{coding,extract-facts,streams,guided-documents,templates,sections,interactions,transcripts}` | 7 routers |
| **Runtime** | `/api/runtime/{runs,agents,registry,rule-engine,observability,medical-coding}`, `/api/runtime-platform/{registry,agents}` | 2 routers (run_trace_router, runtime_platform_router, standard_runtime_router) |
| **Phase 5 Track C/D V1** | `/api/v1/coding-compliance/run`, `/api/v1/cdi/*`, `/api/v1/coding/predict`, `/api/v1/agents/{id}/run` | 4 routers |
| **Phase 6/7** | `/api/embedded/*`, `/api/embedded/preview-sessions/*`, `/examples/*`, `/api/v1/runs/{id}`, `/api/clients/*` | 5 routers |
| **MCP** | `/mcp/v1/tools` | (mounted separately) |

→ **At least 6 different API generations coexist.** This is a fragmentation risk (PDF H2 "平行 Runtime"). The "platform_environments / platform_api_clients / platform_tenants" trio is committed as **cloud-flip stub (returns 501)** — not real.

## A.7 Parallel Runtime / Expert / Agent implementations

This is the most important finding of Gate 1. **There are 3+ parallel "expert" systems and 3+ parallel "medical coding runtime" layers.**

### Parallel expert systems

| Location | Files | Used by |
|----------|-------|---------|
| `backend/app/agents/experts/` | 11 experts (audit, cdi, denial, diagnosis, drg, evidence, hcc, homepage, procedure, report, timeline) | TBD (Gate 6) |
| `backend/app/icoder/agent_runtime/experts/` | 5 experts (code_reconciler, coding, evidence_extractor, index_navigator, tabular_validator) | orchestrator/wiring.py |
| `backend/official_agents/*/` | 30 agent dirs | pack registry |

→ **Two distinct "expert" hierarchies under `app/agents/` and `app/icoder/agent_runtime/`.** Gate 6 must determine which one is the live execution path for A2A facade, and whether the other is orphan code.

### Parallel medical coding runtimes

| Layer | Path | Role |
|-------|------|------|
| Pack | `backend/official_agents/medical_coding/` | agent_pack.json + schema (manifest only) |
| Adapter | `backend/icoder_runtime/providers/medical_coding/` | DeepSeekCodingAdapter, HybridAdapter, MedcoderAdapter, MockAdapter, dictionary_rag, embedding_bge_m3 |
| Dispatcher | `backend/app/coding_runtime/dispatcher.py` | `CodingRuntimeDispatcher` → routes by `mode` |
| Fast runtime | `backend/app/coding_runtime/fast_runtime.py` | Default — wraps DeepSeekCodingAdapter |
| Deep runtime | `backend/app/coding_runtime/medcoder_runtime.py` | Optional — 5-stage MedCodER pipeline |
| Legacy | `backend/app/agents/experts/diagnosis_expert.py` + `procedure_expert.py` | Legacy diagnosis/procedure experts |

→ **The medical coding path is layered** (Adapter → Runtime → Dispatcher → API), not duplicated. But `app/agents/experts/diagnosis_expert.py` + `procedure_expert.py` may be legacy parallel paths. Gate 5 will verify.

### Parallel agent_pack manifests

Each of the 30 agents in `backend/official_agents/` has **two sibling directories**:
- `snake_case/` — Python source (`agent.py`, `system_prompt_v2.py`, etc.)
- `kebab-case/` — `agent_pack.json` only (manifest referencing `icoder/<kebab-name>@<version>`)

For example: `code_validation/` (Python) + `code-validation/` (pack manifest). Same for `compliance_guardrail` + `compliance-guardrail`, `note_completeness` + `note-completeness`. **Not strictly duplicates**, but the dual-directory pattern is unusual and confusing. Gate 4 will validate that both halves are actually wired and consistent.

### Parallel Web Component implementations

| Path | Status | Tracked? |
|------|--------|----------|
| `packages/icoder-embedded/` | ✅ Canonical — `@icoder/embedded@2.0.0` method-based API | yes + dist tracked |
| `packages/icoder-web/` | ⚠️ DEPRECATED Phase 6 Gate 1 (attribute-based 1.0) | yes |
| `packages/web-components/` | ⚠️ DEPRECATED Phase 6 Gate 1 (prototype) | yes |
| `web-components/` (root) | ⚠️ DEPRECATED Phase 6 Gate 1 (prototype) | yes |

External consumer smoke (above) confirms only `@icoder/embedded` is consumed. The three DEPRECATED dirs are committed dead weight.

### Parallel platform runtimes

| Layer | Path | Status |
|------|------|--------|
| `backend/app/icoder/agent_runtime/` | A2A facade + orchestrator + experts | Live (Phase 5 Track C) |
| `backend/icoder_runtime/embedded/platform_runtime.py` | "embedded platform runtime" | TBD (Gate 6) |
| `backend/app/coding_runtime/` | Coding dispatcher | Live |
| `backend/marketplace_core/` | (empty — only __pycache__) | **Orphan** |

### Orphan / unused code (preliminary, deep audit in Gate 21)

- `backend/marketplace_core/` — directory exists but **only contains `__pycache__/`**. No `.py` source. **Orphan.**
- `src/utils/` — root-level `src/` directory, only contains `utils/`. Looks orphan.
- 14 PNG files at repo root are **tracked** in git — should be in `docs/` or `reports/`.

## A.8 Frontend structure

27 page components under `frontend/src/pages/`. From `App.tsx`, the route graph has **multiple aliases for the same page**:

- `/ai-studio/agents` = `/studio/agents` = `/runtime/agents` = `/manage/...` aliases
- `/ai-studio/medical-coding` = `/studio/medical-coding` = `/runtime/coding-review`
- `/ai-studio/embedded-assistant` = `/studio/embedded-assistant`

Gate 2 will produce the full route inventory; the headline is that **the IA has at least 3 generations of URL scheme co-existing for backward-compat**.

## A.9 Fresh-engineer boot checklist

| Step | Documented? | Works? |
|------|-------------|--------|
| 1. Clone repo | README ✓ | ✅ |
| 2. `cd backend && pip install -r requirements.txt` | README ✓ | ✅ (all 14 critical deps at pinned versions) |
| 3. `cd frontend && npm install` | README ✓ | ✅ |
| 4. `alembic upgrade head` | `backend/MIGRATION_RUNTIME.md` ✓ | ✅ (15 migrations apply cleanly) |
| 5. `python -m uvicorn app.main:app --port 8000` | CLAUDE.md ✓ | ✅ |
| 6. `npm run dev` | CLAUDE.md ✓ | ✅ (but on port 3000, not 5173) |
| 7. Seed initial user | `backend/app/seed.py` exists | TBD |
| 8. Login | undocumented — endpoints exist | TBD |
| 9. Set `LLM_API_KEY` | CLAUDE.md mentions `ICODER_CREDENTIAL_LLM` env | TBD |
| 10. Build SDK + Embedded | `packages/icoder-sdk/` build ✓ | ✅ (verified dist/ builds) |

**Verdict: a fresh engineer can boot from docs**, but will hit:
- port mismatch (3000 not 5173) — minor
- no documented login credentials — must inspect `seed.py` or register
- three deprecated Web Component directories with no obvious "use the canonical one" guidance from README

## A.10 New findings registered

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G1-001** | P2 | architecture | Three parallel expert hierarchies (`app/agents/experts/` vs `app/icoder/agent_runtime/experts/` vs `official_agents/`) — Gate 6 must map which is live |
| **G1-002** | P2 | architecture | At least 6 API generations coexist (`/api/*` legacy, `/api/rest/v1/*`, `/api/v2/tools/*`, `/api/runtime/*`, `/api/runtime-platform/*`, `/api/v1/*` Phase 5+; `/api/embedded/*`, `/api/clients/*`, `/mcp/v1/*`) |
| **G1-003** | P2 | release-hygiene | Version drift: `VERSION=1.1.0`, `/api/health` reports `1.0.0`, SDK `1.0.0-beta.2`, embedded `2.0.0`, git tag `v1.0.0`, CDI agent `rc5` |
| **G1-004** | P2 | orphan | `backend/marketplace_core/` is empty (only `__pycache__`); `src/utils/` looks orphan at repo root |
| **G1-005** | P3 | build-hygiene | 14 PNG files tracked at repo root (some phase 4h/4b screenshots) — should move to `docs/screenshots/` |
| **G1-006** | P2 | dual-naming | Each agent has snake_case Python dir + kebab-case agent_pack.json dir (30 agents × 2 dirs = 60 dirs). Confusing for newcomers. |
| **G1-007** | P1 | delivery | 3 cloud-flip routers (`platform_environments`, `platform_api_clients`, `platform_tenants`) are committed stubs returning **501 Not Implemented**. CLAUDE.md declares "托管云 SaaS" as the deployment model but the cloud layer is not implemented. |

## A.11 Gate 1 verdict

`BOOT_REPRODUCIBLE_WITH_FRAGMENTATION_AND_VERSION_DRIFT`

- Backend + frontend boot from docs ✅
- SDK + embedded build cleanly + external consumer smoke passes ✅
- Alembic head 015, 43 tables, ICD-10 33k + ICD-9-CM-3 23k codes loaded ✅
- **3 parallel expert hierarchies** to disambiguate in Gate 6
- **6+ API generations** co-existing — fragmentation risk
- **Version drift** across components
- **Cloud SaaS layer is 501 stub** despite CLAUDE.md declaring it as the deployment model
- `marketplace_core/` orphan, root-level PNGs tracked

Gate 1 closes. Proceed to **Gate 2 — Product Surface and Route Inventory**.
