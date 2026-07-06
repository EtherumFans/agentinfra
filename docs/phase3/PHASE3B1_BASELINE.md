# Phase 3-B1 Section A — Baseline (Read-Only Audit)

**Date**: 2026-07-04
**Status**: COMPLETE — 15 items audited; 4 relationship diagrams + 3 endpoint classification lists + modification scope produced
**Author**: Phase 3-B1 prompt execution

## A.1 Purpose

This baseline locks the *current state* before any Phase 3-B1 code change. It is read-only: no code, no agent_pack.json, no test, no frontend file is modified in this section. All modifications are catalogued here as scope; Sections B-F execute them.

The 6 Phase 3-B follow-ups from Phase 3-B0 (see `project_phase3_b0_full_agent_audit_2026_07_04.md`) become the input queue for this round:

1. Migrate Medical Coding Agent from legacy `/run` to A2A mainline (closes dim 17 platform-alignment cap)
2. Restore `/api/icoder/agents/hub` endpoint (closes dim 9 for all agents)
3. Consolidate 3 duplicate execution endpoints (`/run`, `/medical-coding/test`, `/v2/tools/coding/icoder`)
4. Implement 10 metadata-only packs as proper runnable Agents — **out of scope this round** (Phase 3-B2)
5. Wire SpeechToTextPage + TextGenerationPage to existing Phase 1.2/1.3 backends — **out of scope this round** (Phase 3-B2)
6. Delete EmbeddedAssistantPage — **out of scope this round** (Phase 3-B2)

Items 4-6 are explicitly deferred to Phase 3-B2 per the prompt ("本轮不实施新的 Pre-built Agent"). Items 1-3 are the scope of Phase 3-B1.

## A.2 Inputs Read

The following 10 docs were read in this section (or carried from Phase 3-B0):

| # | Doc | Source | Key takeaway |
|---|---|---|---|
| 1 | `docs/architecture/CURRENT_ARCHITECTURE.md` (342 LOC) | repo | §3.6 confirms legacy bypass: medical-coding calls `app/api/v2_tools_coding.py` → `icoder_runtime/core/` → `HybridCodingAdapter`; `app/icoder/agent_runtime/orchestrator/` not actually running |
| 2 | `docs/architecture/MAINLINE_VS_LEGACY.md` (477 LOC) | repo | §3.3 lists `icoder_agents_hub.py` (1029 LOC) as Legacy "migrate (Phase 2 迁到 /rest/v1/agent_definitions)" — confirms Hub endpoint was deleted in Phase 2.1-B, not yet restored |
| 3 | `docs/product/PRODUCT_DIRECTION.md` | repo | MedCodER 降级声明; Corti 20 Pre-built Agents mapping (iCoDer 3/20 aligned) |
| 4 | `project_phase3_b0_full_agent_audit_2026_07_04.md` | memory | PASS verdict; 6 Phase 3-B follow-ups; 39 A.5 violations fixed; 99 tests pass |
| 5 | `docs/phase3/PHASE3B0_FULL_AGENT_AUDIT_FINAL_REPORT.md` | repo (read in prior session) | Verdict PASS; 21 surfaces scored on 17 Corti dimensions; 14 STUB_ONLY → honest relabel |
| 6 | `docs/phase3/PHASE3B0_FULL_AGENT_INVENTORY.md` | repo (read in prior session) | 16 packs + 5 page-as-agent features + 63 endpoints + 24 frontend pages + 5 MCP tools + 8 A2A routes |
| 7 | `docs/phase3/PHASE3B0_AGENT_CORTI_PARITY_AUDIT.md` | repo (read in prior session) | 21 surfaces scored; 1 ALIGNED + 3 PARTIALLY_ALIGNED + 2 MISALIGNED + 14 STUB_ONLY + 1 DELETE_CANDIDATE |
| 8 | `docs/phase3/PHASE3B0_MANUAL_QA_SIMULATION_MATRIX.md` | repo (read in prior session) | 14/14 spec areas; 7 PASS / 3 PARTIAL / 1 STUB_ACCEPTED / 3 SHOULD_HIDE |
| 9 | `docs/phase3/PHASE3B0_QUICK_FIX_REPORT.md` | repo (carried in system-reminder) | 4 quick fix types applied to 15 packs; 39 A.5 violations → 0 |
| 10 | `docs/phase3/PHASE3B0_TESTING_VERIFICATION_REPORT.md` | repo (carried in system-reminder) | 5 verification rounds; 99 cumulative tests pass; 18/18 frontend pages 200; 9/9 backend endpoints honest |

Plus code reads in this section:

| File | LOC | Purpose |
|---|---|---|
| `backend/app/icoder/agent_runtime/a2a/agent_card.py` | 310 | Only `medcoder_coding_review_card()` factory exists — no factory for `medical-coding-agent@2.0.0` |
| `backend/app/icoder/agent_runtime/a2a/routes_discovery.py` | 212 | `_list_all_cards()` hardcodes Phase 1 fallback to `medcoder_coding_review_card()`; provider contract is `Callable[[str], AgentCard | None]` |
| `backend/app/icoder/agent_runtime/a2a/routes_inbound.py` | 213 | `POST /v1/message:send` → `InboundHandler.handle()`; sync handler run in `asyncio.to_thread` |
| `backend/app/api/runtime_platform.py:224-294` | 70 | Legacy `/agents/{ref:path}/run` endpoint — restored for medical-coding-agent only; runs HybridCodingAdapter directly, bypasses PlatformRuntime.run_agent |
| `backend/app/main.py:385-593` | 208 | A2A wiring: `_build_phase1_agent_provider()` only registers `medcoder-coding-review`; `mount_a2a(handler, agent_provider, expert_caller)` |
| `backend/official_agents/medical_coding/agent_pack.json` | 286 | v1.2 pack; declares `a2a.endpoint=/api/icoder/agents/medical-coding-agent/v1/message:send` but no factory exists |
| `backend/official_agents/medcoder-coding-review/agent_pack.json` | 237 | v1.2 pack; `agent_type=internal_engine`, `hidden_from_hub=true`, 4 real experts (evidence-extractor/index-navigator/code-reconciler/tabular-validator) |
| `backend/app/icoder/agent_runtime/orchestrator/inbound_handler.py:170-244` | 75 | `InboundHandler.handle()` — calls `agent_provider(agent_id)`, returns AGENT_NOT_FOUND (404) when None |

## A.3 Audit — 15 Items

### A.3.1 Agent Hub frontend page (`/ai-studio/agents`)

**State**: Page exists, returns 200, renders `AgentsPage.tsx`. Frontend has no `agentHubApi.ts` (deleted in Phase 2.1-B). `AgentsPage.tsx` calls `/api/agents` (legacy `app/api/agents.py` router, line 654 — also deleted in Phase 2.1-B per MAINLINE_VS_LEGACY.md §3.3) OR `runtimeApi.ts` (current).

**Verdict**: Frontend page exists but has no Hub backend to call. Frontend currently calls `runtimeApi.ts` for `/api/runtime-platform/agents` list (line 361). This is a Corti parity gap — Corti's Agent Hub is the canonical entry; iCoDer has no equivalent.

**Phase 3-B1 action**: Section F will rewire `AgentsPage.tsx` to call the restored `/api/icoder/agents/hub` endpoint.

### A.3.2 `/api/icoder/agents/hub` missing reason

**State**: Endpoint returns 404. `app/api/icoder_agents_hub.py` (1029 LOC) was deleted in Phase 2.1-B (commit `5c4e0e3` per P1.2 corti-parity-deletion memory). No replacement was created.

**Root cause**: P1.2 deleted 5 self-invented iCoDer concepts (Doctor/MethodCompare/RunTrace/Marketplace/methods/) including the Hub. The expectation was that `/rest/v1/agent_definitions` would replace it, but that endpoint is auth-gated (401) and DB-mastered, not pack-mastered — so it doesn't show the 16 official agents as a Corti-style Hub.

**Verdict**: Hub endpoint must be restored. It must be pack-mastered (read `official_agents/**/agent_pack.json`) so the 16 packs appear regardless of DB state. Section B implements.

### A.3.3 A2A discovery returns 1 agent

**State**: `GET /api/icoder/agents` returns `{"agents": [{"id": "medcoder-coding-review", ...}]}` — only 1 of 16 packs.

**Root cause**: `routes_discovery.py:122` calls `_resolve_card(provider, "medcoder-coding-review")` and falls back to `medcoder_coding_review_card()` fixture. There is no factory for `medical-coding-agent@2.0.0`, no factory for the 10 metadata-only certified packs, no factory for the 4 expert-stubs. The `_phase1_agent_provider` callback in `main.py:572-575` only returns a card for `medcoder-coding-review` and None for everything else.

**Verdict**: A2A discovery must enumerate all 16 packs (visible ones — 11 certified + 1 internal_engine + 4 expert-stubs; the 4 expert-stubs are `hidden_from_hub=true` so should be filtered). Section C implements.

### A.3.4 `/api/rest/v1/agent_definitions` data source

**State**: Endpoint exists, auth-gated (returns 401 without token, 200 with). Backed by `AgentDefinition` DB model + `agent_registry_sync_service.repair_from_registry()` which syncs runtime registry → DB. seed.py collision documented in B0.

**Verdict**: This is the DB-mastered CRUD endpoint (Corti `/v1/agents` equivalent). It's NOT the Hub (pack-mastered) and NOT A2A discovery (card-mastered). All 3 must coexist with clear responsibilities. Section C defines the 4-entry-point contract.

### A.3.5 16 agent packs state

**State**: 16 packs in `backend/official_agents/**/agent_pack.json`. Breakdown (post-B0 quick fixes):

| Category | Count | Status |
|---|---|---|
| `agent_type=certified` (user-facing) | 11 | 10 metadata-only (maturity=metadata-only, production_ready=false, hidden_from_hub=false) + 1 runnable (medical-coding-agent@2.0.0, maturity=mvp, production_ready=false) |
| `agent_type=internal_engine` | 1 | medcoder-coding-review@1.0.0 (maturity=internal, hidden_from_hub=true, 4 real experts) — only fully ALIGNED agent |
| `agent_type=expert-stub` | 4 | evidence-extractor / index-navigator / code-reconciler / tabular-validator (maturity=stub, hidden_from_hub=true, 4 MedCodER pipeline stages) |
| **Total** | **16** | |

**Verdict**: 15 packs need A2A card factories (10 metadata-only + 4 expert-stub-hidden + 1 medical-coding-agent). 1 pack (medcoder-coding-review) already has a factory. Section B/C/D implements.

### A.3.6 10 metadata-only packs

**State**: All 10 declare `maturity=metadata-only, production_ready=false, hidden_from_hub=false`. Their `experts[]` array is empty. They have no run path — by design (B0 honest labeling).

**Verdict**: Phase 3-B2 implements them as proper runnable Agents (the "17 Pre-built Agents roadmap"). Phase 3-B1 only needs them to *appear* in the Hub with "Metadata only / Coming soon" badges, no Run button. Section B implements.

### A.3.7 4 expert-stub packs

**State**: All 4 declare `maturity=stub, hidden_from_hub=true`. They're MedCodER pipeline stages (Stage 1/2/4/5), invoked internally by `medcoder-coding-review-agent@1.0.0` via the E1 wiring (`build_expert_invoker_for_medcoder`).

**Verdict**: They should NOT appear in Hub or A2A discovery. Section B's Hub builder must respect `hidden_from_hub=true`. No code change to the packs themselves.

### A.3.8 Medical Coding Agent run path (CURRENT — legacy bypass)

**State**: The agent_pack.json declares `a2a.endpoint=/api/icoder/agents/medical-coding-agent/v1/message:send` but no card factory exists for `medical-coding-agent`. So calling that URL returns 404 (AGENT_NOT_FOUND from `InboundHandler.handle()`).

The actual run path is:

```
POST /api/runtime-platform/agents/icoder/medical-coding-agent@2.0.0/run
  → runtime_platform.py:224 run_agent_by_ref()
  → check agent_ref == "icoder/medical-coding-agent@2.0.0" (line 246)
  → HybridCodingAdapter(gateway, mode="hybrid").infer_async(messages)  (line 291-293)
  → MedicalCodingOutputSchema (v1) → project to MedicalCodingAgentOutputV2 (v2, 8 fields)
  → return RuntimeRunResult-shaped JSON with v2 fields hoisted
```

This bypasses:
- `PlatformRuntime.run_agent()` (raises NotImplementedError per Phase 2.1-A)
- `InboundHandler` orchestrator (the A2A mainline)
- The 4 D2 expert packs (evidence-extractor / index-navigator / code-reconciler / tabular-validator)
- The medcoder-coding-review-agent@1.0.0 internal_engine

**Verdict**: This is the central gap. Phase 3-B1 Section D migrates the run path to A2A mainline. The legacy `/run` endpoint becomes a compatibility shim (returns 410 for non-medical-coding agents, keeps working for medical-coding-agent during the migration window, then deleted in Phase 3-B2).

### A.3.9 4 duplicate execution endpoints

**State**:

| # | Endpoint | File:Line | Status |
|---|---|---|---|
| 1 | `POST /api/runtime-platform/agents/{ref:path}/run` | runtime_platform.py:224 | Restored for medical-coding-agent only; 410 for others |
| 2 | `POST /api/runtime-platform/medical-coding/test` | runtime_platform.py:666 | Test endpoint, runs HybridCodingAdapter(mode="hybrid") |
| 3 | `POST /api/v2/tools/coding/icoder` | v2_tools_coding.py | Phase 1.1 Corti-style 15-system spec predictor (no LLM) — DIFFERENT semantic |
| 4 | `POST /api/icoder/agents/{agent_id}/v1/message:send` | routes_inbound.py:71 | A2A mainline — currently only handles `medcoder-coding-review` |

Plus (per MAINLINE_VS_LEGACY.md, deleted in 2.1-B):
- ~~`POST /api/icoder/coding-review/run`~~ (deleted)
- ~~`POST /api/agents/{id}/run`~~ (deleted)
- ~~`POST /api/agents/{id}/stream`~~ (deleted)

**Verdict**: Section E classifies these 4 live endpoints: keep_mainline / keep_compatibility / test_only / deprecated / return_410 / delete_later.

### A.3.10 Runs/Trace path

**State**: `/api/icoder/runs` exists (P1.0-E). `RunTracePage` renders. RunHistory DB table + AuditLog. Medical Coding Agent runs through `/run` do create RunHistory rows (via `runtime_platform.py` RunRecorder), so traces exist. After A2A migration, the InboundHandler must also write to RunHistory (recorder_adapter.py exists).

**Verdict**: No new work in Phase 3-B1 except ensuring A2A mainline path writes to RunHistory (the recorder_adapter exists; verify in Section G).

### A.3.11 8-field output contract state

**State**: `MedicalCodingAgentOutputV2` schema (8 fields: encounter_summary, documentation_analysis, code_assignment, documentation_gaps, uncodable_items, validation_summary, human_review, trace_refs) is defined in `backend/official_agents/medical_coding/schema.py`. The legacy `/run` endpoint projects v1 → v2 (runtime_platform.py:296-298). After A2A migration, the InboundHandler + CodingExpert path must produce v2 directly.

**Verdict**: 9 red lines enforced in agent_pack.json permissions (no_upcoding, no_inference, evidence_required, production_writeback_blocked, phi_redaction=required, human_review=required, no F1 to user, no EMR writeback, no fully-automated claim). Phase 3-A 8-field contract test exists (`test_medical_coding_v2_fields_always_present`). Section D must preserve this contract.

### A.3.12 40 Phase 3-B0 tests state

**State**: 27 backend + 13 frontend = 40 Phase 3-B0 tests, all pass. Cumulative 99 (40 new + 5 Phase 3-A + 45 apiContract + 9 i18n). 0 skips, 0 xfails, 0 lowered assertions.

**Verdict**: Phase 3-B1 must not regress these. Section G verifies.

### A.3.13 Frontend Agent Hub state

**State**: `AgentsPage.tsx` exists, calls `runtimeApi.ts` for list. No `agentHubApi.ts` (deleted in 2.1-B). `AgentsPage` renders 11 certified packs from the runtime platform list (the 4 expert-stubs are filtered out by `hidden_from_hub`; the 1 internal_engine is also filtered).

**Verdict**: Section F creates a new `agentHubApi.ts` that calls `/api/icoder/agents/hub`, and rewires `AgentsPage.tsx` to use it. The new Hub list shows 11 certified + 1 medical-coding-agent (= 12 visible packs) with Corti-style cards.

### A.3.14 Frontend Medical Coding Page state

**State**: `MedicalCodingPage.tsx` calls `/api/runtime-platform/agents/icoder/medical-coding-agent@2.0.0/run` via `runtimeApi.ts`. After A2A migration, the page should call `/api/icoder/agents/medical-coding-agent/v1/message:send` (the A2A mainline) OR keep calling `/run` as a compatibility shim that internally routes to A2A.

**Verdict**: Section F decides: keep `/run` as compatibility shim (zero frontend change) OR switch frontend to A2A URL (cleaner but more frontend churn). Prompt says "前端 services sync" — leaning toward switching, but Section F will pick the lower-risk path.

### A.3.15 Live API state probe (carried from B0)

| Probe | Result |
|---|---|
| `GET /api/runtime/status` | 200, execution_mode=legacy (honest) |
| `GET /api/icoder/agents` | 200, returns 1 agent (medcoder-coding-review) |
| `GET /.well-known/agent.json` | 200 |
| `GET /api/rest/v1/agent_definitions` | 401 (auth-gated) |
| `GET /api/rest/v1/agent_definitions/templates` | 200 |
| `POST /mcp/v1/tools/list` | 200, returns 5 tools |
| `POST /api/runtime/agents/medical-coding-agent@2.0.0/run` | 400 (input validation or auth) |
| `POST /api/runtime/agents/diagnosis-extractor@1.0.0/run` | 401 (auth blocks before 410) |
| `GET /api/icoder/agents/hub` | **404** (the gap) |

**Verdict**: All probes honest. The 404 on `/hub` is the central evidence for Section B.

## A.4 Relationship Diagrams

### A.4.1 Agent Hub missing link diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ Frontend: AgentsPage.tsx                                         │
│   ↓ calls runtimeApi.ts → GET /api/runtime-platform/agents      │
│   ↓ (no Hub call — agentHubApi.ts was deleted in 2.1-B)         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ Backend: GET /api/runtime-platform/agents                        │
│   ← runtime_platform.py:361 @router.get("/agents")              │
│   ← lists DB-backed agents (AgentModel)                          │
│   ← does NOT read official_agents/**/agent_pack.json             │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ Backend: GET /api/icoder/agents/hub   ← ** 404 GAP **            │
│   ← icoder_agents_hub.py was deleted in Phase 2.1-B              │
│   ← NO replacement exists                                        │
│   ← should read official_agents/**/agent_pack.json               │
│   ← should return Corti-style Hub cards (12 visible packs)       │
└──────────────────────────────────────────────────────────────────┘
```

**Gap**: The missing vertical arrow between "official_agents/**/agent_pack.json" (16 packs on disk) and "GET /api/icoder/agents/hub" (404). Section B restores it.

### A.4.2 Agent Hub / A2A / agent_definitions / agent_pack four-way relationship

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  official_agents/       │         │  AgentDefinition DB     │
│  **/agent_pack.json     │         │  (AgentModel, CRUD)     │
│  (16 packs on disk)     │         │  (DB is master for CRUD)│
└──────────┬──────────────┘         └──────────┬──────────────┘
           │                                    │
           │ read                               │ CRUD
           │                                    │
           ▼                                    ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│  GET /api/icoder/       │         │  /api/rest/v1/          │
│  agents/hub             │         │  agent_definitions      │
│  (Hub — pack-mastered,  │         │  (CRUD — DB-mastered,   │
│  Corti-style cards,     │         │  auth-gated, user-      │
│  no auth, read-only)    │         │  created agents)        │
└──────────┬──────────────┘         └─────────────────────────┘
           │                                    │
           │ read                               │
           │                                    │
           ▼                                    ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│  GET /api/icoder/       │         │  (separate concerns —    │
│  agents                 │         │   Hub shows official     │
│  + /.well-known/        │         │   packs + user-created;  │
│    agent.json           │         │   agent_definitions      │
│  + /agents/{id}/card    │         │   is the editing CRUD)   │
│  (A2A discovery —       │         └─────────────────────────┘
│  AgentCard v0.3,        │
│  capability filter,     │
│  Phase 4 DB-backed)     │
└─────────────────────────┘
```

**Responsibilities (Section C defines)**:
- **Hub** (`/api/icoder/agents/hub`): pack-mastered, no auth, read-only, Corti-style card list for browsing
- **A2A discovery** (`/api/icoder/agents` + `/.well-known/agent.json` + `/agents/{id}/card`): AgentCard v0.3, capability filter, Phase 4 plugs in DB
- **agent_definitions** (`/api/rest/v1/agent_definitions*`): DB-mastered, auth-gated, CRUD for user-created agents
- **agent_pack.json** (`official_agents/**/agent_pack.json`): canonical source-of-truth for the 16 official packs

### A.4.3 Medical Coding Agent current legacy bypass running link

```
┌────────────────────────────────────────────────────────────────┐
│ Frontend: MedicalCodingPage.tsx                                │
│   ↓ runtimeApi.ts.runMedicalCodingAgent()                      │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ POST /api/runtime-platform/agents/                             │
│   icoder/medical-coding-agent@2.0.0/run                        │
│   (runtime_platform.py:224 run_agent_by_ref)                   │
│   ↓ agent_ref check (line 246) — only this 1 ref is allowed   │
│   ↓ PIIRedactor (line 285)                                     │
│   ↓ HybridCodingAdapter(gateway, mode="hybrid").infer_async()  │
│   ↓   (line 291-293) — BYPASSES A2A InboundHandler             │
│   ↓   BYPASSES PlatformRuntime.run_agent (raises NotImpl)      │
│   ↓   BYPASSES 4 D2 expert packs                               │
│   ↓   BYPASSES medcoder-coding-review-agent@1.0.0              │
│   ↓ MedicalCodingOutputSchema v1 → project to v2 8 fields      │
│   ↓   (line 296-298)                                           │
│   ↓ RunRecorder → RunHistory DB                                │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Response: RuntimeRunResult JSON with v2 fields hoisted         │
│   (encounter_summary, documentation_analysis, code_assignment, │
│    documentation_gaps, uncodable_items, validation_summary,    │
│    human_review, trace_refs)                                   │
└────────────────────────────────────────────────────────────────┘
```

**Gaps**:
1. Bypasses A2A mainline (InboundHandler orchestrator)
2. Bypasses the 4 D2 expert packs (evidence-extractor / index-navigator / code-reconciler / tabular-validator) — runs HybridCodingAdapter directly
3. `PlatformRuntime.run_agent` still raises NotImplementedError (Phase 2.1-A) — not used
4. The agent_pack.json-declared `a2a.endpoint=/api/icoder/agents/medical-coding-agent/v1/message:send` is a dead pointer (no card factory → 404)
5. Dim 17 (platform alignment) capped at 1/5 because of bypass (per B0 audit)

### A.4.4 Modules needing A2A mainline migration

```
Migrate to A2A mainline (Section D):
├── backend/app/icoder/agent_runtime/a2a/agent_card.py
│   └── ADD: medical_coding_agent_card() factory  (parallel to medcoder_coding_review_card)
├── backend/app/main.py:494-556  _build_phase1_agent_provider()
│   └── EXTEND: register both medcoder-coding-review AND medical-coding-agent
├── backend/app/main.py:572-575  _phase1_agent_provider()
│   └── EXTEND: return card for both agent_ids
├── backend/app/icoder/agent_runtime/a2a/routes_discovery.py:112-126  _list_all_cards()
│   └── REWRITE: enumerate visible packs from official_agents/ + provider (no hardcoded fallback)
├── backend/app/icoder/agent_runtime/orchestrator/wiring.py
│   └── VERIFY: build_expert_invoker_for_medcoder handles medical-coding-agent (already does — 4 D2 experts)
└── backend/app/api/runtime_platform.py:224-294  run_agent_by_ref()
    └── CONVERT: keep for medical-coding-agent as compatibility shim OR return 410 + migrate frontend to A2A URL
```

## A.5 Endpoint Classification Lists

### A.5.1 Endpoints to migrate to A2A mainline (this round)

| Endpoint | File:Line | Action |
|---|---|---|
| `POST /api/runtime-platform/agents/icoder/medical-coding-agent@2.0.0/run` | runtime_platform.py:224 | Demote to compatibility shim (Section D.3) OR delete (decision in Section D) |
| (implicit) `POST /api/icoder/agents/medical-coding-agent/v1/message:send` | routes_inbound.py:71 | Enable by adding card factory (Section D.2) |

### A.5.2 Endpoints to keep as compatibility shim

| Endpoint | File:Line | Reason |
|---|---|---|
| `POST /api/runtime-platform/agents/{ref:path}/run` | runtime_platform.py:224 | Keep returning 410 for non-medical-coding agents (already does). For medical-coding-agent: keep during migration window, internally route to A2A InboundHandler, return same v2-shaped response. Frontend can switch gradually. |
| `POST /api/runtime-platform/medical-coding/test` | runtime_platform.py:666 | Test endpoint (no auth, dev-only). Keep as test_only (Section E). |
| `POST /api/v2/tools/coding/icoder` | v2_tools_coding.py | Different semantic (15-system spec predictor, no LLM) — keep as separate Phase 1.1 endpoint (Section E). |

### A.5.3 Endpoints to 410 / deprecate

| Endpoint | File:Line | Action |
|---|---|---|
| (none new this round) | — | The 16 legacy routers deleted in 2.1-B are already gone. No new 410s in 3-B1. The `/run` endpoint stays as compat shim. |

Plus (deferred to Phase 3-B2 or later):
- `POST /api/runtime-platform/medical-coding/test` — candidate for deletion once A2A mainline + test framework is stable (not this round)
- `POST /api/runtime-platform/agents/{ref:path}/run` — candidate for full deletion once frontend fully switches to A2A URL (not this round)

## A.6 Modification Scope (this round = Phase 3-B1)

### In scope

1. **Section B**: Restore `GET /api/icoder/agents/hub` endpoint (new router `app/api/icoder_agents_hub.py` rebuilt, pack-mastered, no auth, read-only). Returns Corti-style Hub cards for 12 visible packs (11 certified + 1 medical-coding-agent; 4 expert-stubs and 1 internal_engine filtered by `hidden_from_hub=true`).
2. **Section C**: Unify 4 entry points (Hub / A2A discovery / agent_definitions / agent_pack) — define responsibilities, write contract test, ensure no overlap.
3. **Section D**: Migrate Medical Coding Agent run path from legacy `/run` bypass to A2A mainline. Add `medical_coding_agent_card()` factory. Extend `_phase1_agent_provider` to return both `medcoder-coding-review` AND `medical-coding-agent` cards. Rewrite `_list_all_cards()` to enumerate visible packs. Verify `InboundHandler` + 4 D2 expert packs produce v2 8-field output.
4. **Section E**: Classify 4 live execution endpoints. Keep `/run` as compatibility shim (internally routes to A2A). Keep `/medical-coding/test` as test_only. Keep `/v2/tools/coding/icoder` as separate Phase 1.1 endpoint. Document the 4-endpoint taxonomy.
5. **Section F**: Rebuild `frontend/src/services/agentHubApi.ts` calling `/api/icoder/agents/hub`. Rewire `AgentsPage.tsx` to use it. Decide MedicalCodingPage path (keep `/run` shim OR switch to A2A URL — Section F picks lower-risk).
6. **Section G**: 5 verification rounds (inventory / backend / frontend / HTTP smoke / cumulative tests).
7. **Section H**: Final report with PASS/FAIL verdict.

### Out of scope (Phase 3-B2 or later)

- Implementing 10 metadata-only packs as runnable Agents (Phase 3-B2)
- Wiring SpeechToTextPage / TextGenerationPage to Phase 1.2/1.3 backends (Phase 3-B2)
- Deleting EmbeddedAssistantPage (Phase 3-B2)
- Deleting `/run` and `/medical-coding/test` endpoints (Phase 3-B2 or later, after frontend fully switches)
- F1 optimization, model training, prompt tuning (never — out of Phase 3 scope)
- New Pre-built Agents beyond the 16 existing packs (Phase 3-B2+)
- Marketplace implementation (Phase 4)

### Hard constraints (preserved from Phase 3-A + B0)

- Phase 3-A 8-field output contract (`MedicalCodingAgentOutputV2`) — must still be produced after A2A migration
- 9 red lines (no_upcoding, no_inference, evidence_required, production_writeback_blocked, phi_redaction=required, human_review=required, no F1 to user, no EMR writeback, no fully-automated claim)
- 5 honesty rules (A.5.1-A.5.5) — no stubs wrapped as runnable, no metadata-only implied as MVP, production_ready must be declared
- No new tests skipped, no xfails, no lowered assertions
- No fake data, no fake output to make tests pass
- 99 cumulative tests must not regress

## A.7 Baseline Verdict

**Section A verdict**: PASS — 15 items audited; 4 relationship diagrams produced; 3 endpoint classification lists produced; modification scope locked; no code changes made in this section.

The baseline confirms the 3 Phase 3-B1 scope items (Hub restoration, A2A mainline migration, endpoint consolidation) are well-defined, the 3 deferred items (10 metadata-only packs, orphan pages, EmbeddedAssistant delete) are explicitly Phase 3-B2, and the 99-test baseline + 8-field contract + 9 red lines are the regression gates.

Sections B-H execute the scope in order.
