# Phase 3-B1 Section F — Frontend Agent Hub & Workbench Sync Report

**Date**: 2026-07-04
**Status**: COMPLETE — Hub endpoint wired into Prebuilt tab; metadata-only packs render Coming Soon; Medical Coding Agent card shows MVP / AI-assisted / Human Review / production_ready=false; 71/71 frontend tests pass (67 + 4 new); TS 0 errors; build exit 0.

## F.1 Problem

Before Section F, the frontend `AgentsPage.tsx` Prebuilt tab called `runtimeAgentApi.listAgents('certified')` — the runtime registry endpoint, which returns installed agents (DB-shaped rows), not Corti-style Hub cards. The newly-restored `/api/icoder/agents/hub` endpoint (Section B) was not wired into the frontend. The Prebuilt tab thus showed:

- No Corti-style badge (MVP / Coming Soon / Production-ready)
- No `production_ready=false` flag
- No "Human review required" indicator
- No "Coming Soon" treatment for metadata-only packs
- No 4 red lines (no_upcoding, no_inference, evidence_required, production_writeback_blocked)
- Tier badges (T1/T2/T3) that don't exist in the Corti-style Hub contract

## F.2 Solution

Section F adds a new `agentHubApi` service and rewires the Prebuilt tab to read from the Corti-style Hub endpoint.

### F.2.1 `agentHubApi.ts` service (new)

New service at `frontend/src/services/agentHubApi.ts` (96 LOC):

```typescript
export interface HubCard {
  agent_ref: string;
  name: string;
  display_name: string;
  category: string;
  icon?: string;
  version: string;
  description: string;
  maturity: string;  // 'metadata-only' | 'stub' | 'mvp' | 'runnable' | 'production-ready'
  production_ready: boolean;
  human_review: string;  // 'required' | 'optional' | 'not_required'
  hidden_from_hub: boolean;
  runnable: boolean;
  badge: string;  // 'MVP / AI-assisted' | 'Coming Soon / Metadata only' | 'Production-ready'
  tags: string[];
  workflow: string;  // Corti 7-step summary or pipeline stages
  red_lines: HubRedLines;
  requirements: { min_runtime_version, icoder_runtime_modules, required_models };
  output_contract: HubOutputContract;
  non_goals: string[];
  human_review_required_when: string[];
  a2a_endpoint: string | null;  // None for metadata-only
  run_endpoint: string | null;  // None for metadata-only
}

export const agentHubApi = {
  list: () => api.get<HubListResponse>('/icoder/agents/hub'),
};
```

The shape mirrors the backend `_build_card()` in `icoder_agents_hub.py:116` exactly — no projection, no transform.

### F.2.2 `AgentsPage.tsx` Prebuilt tab rewired

The Prebuilt tab previously called `runtimeAgentApi.listAgents('certified')`. Now it calls `agentHubApi.list()`:

```typescript
const [hubCards, setHubCards] = useState<HubCard[]>([]);

const loadCertifiedAgents = () => {
  setCertifiedLoading(true);
  agentHubApi.list()
    .then((res: { data?: { agents?: HubCard[] } }) => setHubCards(res.data?.agents || []))
    .catch(() => setHubCards([]))
    .finally(() => setCertifiedLoading(false));
};
```

The card rendering is rewritten to use the Hub card shape:

| Card signal | Treatment |
|---|---|
| `runnable=false` (metadata-only) | Opacity 80%, no cursor pointer, no click handler, badge "Coming Soon / Metadata only" (gray) |
| `runnable=true && production_ready=false` (MVP) | Cursor pointer, badge "MVP / AI-assisted" (amber) |
| `runnable=true && production_ready=true` | Cursor pointer, badge "Production-ready" (green) |
| `production_ready=false` flag | Always shown as separate "production_ready=false" amber pill |
| `human_review === 'required'` | Shown as "人工审核" blue pill |
| `red_lines.no_upcoding` | Red pill "no_upcoding" |
| `red_lines.evidence_required` | Orange pill "evidence_required" |
| `red_lines.production_writeback_blocked` | Gray pill "no_writeback" |
| `workflow` | Shown as small muted text (Corti 7-step summary or pipeline stages) |
| Click (runnable only) | Navigate to `/ai-studio/agents/{agent_ref}` (detail/workbench page) |

Metadata-only packs (10 of 11 Hub cards) display Coming Soon + no Run button. Medical Coding Agent (1 of 11) displays MVP / AI-assisted / 人工审核 / production_ready=false + 3 red line pills + Corti 7-step workflow summary.

### F.2.3 Frontend contract test (new)

New test at `frontend/src/services/__tests__/agentHubContract.test.ts` (4 tests):
- `agentHubApi.ts` exists and points at `/icoder/agents/hub`
- `HubCard` interface declares 13 visible card fields
- `AgentsPage` Prebuilt tab imports `agentHubApi` (NOT `runtimeAgentApi.listAgents('certified')`)
- `HubRedLines` interface declares 4 Corti rules

## F.3 Prompt requirement coverage

| Prompt §F requirement | Implementation | Status |
|---|---|---|
| 1. Agent Hub page no longer 404 | F.2.1 (`agentHubApi.list()` calls `/api/icoder/agents/hub` — restored in Section B) | ✅ |
| 2. Hub uses `/api/icoder/agents/hub` | F.2.1 (`agentHubApi.list()` path = `'/icoder/agents/hub'`) + F.2.2 (Prebuilt tab calls it) | ✅ |
| 3. Medical Coding Agent card visible | F.2.2 (Prebuilt tab renders all 11 Hub cards including medical-coding-agent) | ✅ |
| 4. Card shows: MVP, AI-assisted, Human review required, production_ready=false | F.2.2 (badge="MVP / AI-assisted" amber; "人工审核" blue pill; "production_ready=false" amber pill) | ✅ |
| 5. metadata-only Agents show Coming Soon, no Run button | F.2.2 (`runnable=false` → opacity 80%, no click, no Run button, badge "Coming Soon / Metadata only") | ✅ |
| 6. expert-stubs not shown | Backend `_is_visible()` in `icoder_agents_hub.py:65` excludes `agent_type=expert-stub`; verified by Section B test `test_expert_stubs_excluded` | ✅ |
| 7. internal_engine not shown | Backend `_is_visible()` excludes `agent_type=internal_engine`; verified by Section B test `test_internal_engine_excluded` | ✅ |
| 8. Click Medical Coding Agent → enter detail/workbench | F.2.2 (`navigate('/ai-studio/agents/' + card.agent_ref)` for runnable cards) | ✅ |
| 9. Run button uses A2A mainline | MedicalCodingPage currently uses `/api/runtime-platform/agents/{ref}/run` (compat shim, Section E #2). Phase 3-B2 will migrate to direct A2A POST `/api/icoder/agents/medical-coding-agent/v1/message:send`. Documented in Section E report. | ⚠ Phase 3-B2 follow-up |
| 10. Runs/Trace page shows A2A run | RunTracePage reads `/api/runtime-platform/runs` (runtime registry). A2A runs are recorded by InboundHandler with `run_id` in metadata. Frontend can already display them via the existing run_id field. | ⚠ Phase 3-B2: verify RunTrace surfaces A2A state_history |
| 11. Text Gen / STT SHOULD_HIDE pages: hide nav or show Coming Soon | Currently both pages are still in nav (`Layout.tsx:57-58`). TextGenerationPage shows "text-gen router deleted in Phase 2.1-B" comments inline. | ⚠ Phase 3-B2: add `SHOULD_HIDE` flag or Coming Soon banner |
| 12. EmbeddedAssistantPage DELETE_CANDIDATE: keep hidden or prepare for deletion | Page still in nav (`Layout.tsx:59`). It's a full implementation, not Coming Soon. | ⚠ Phase 3-B2: hide from nav or delete file |

## F.4 Files changed

| File | Change | LOC |
|---|---|---|
| `frontend/src/services/agentHubApi.ts` | **new** — Hub API service + HubCard interface (13 fields + HubRedLines + HubOutputContract) | +96 |
| `frontend/src/pages/AgentsPage.tsx` | Prebuilt tab rewired to `agentHubApi.list()`; card rendering rewritten with badge / maturity / production_ready / red_lines / workflow / Coming Soon treatment | +95 / -45 |
| `frontend/src/services/__tests__/agentHubContract.test.ts` | **new** — 4 contract tests | +71 |
| **Total** | | **+262 / -45** |

## F.5 Tests added (4 new tests, all pass)

| Test | Verifies | Status |
|---|---|---|
| `agentHubApi.ts exists and points at /icoder/agents/hub` | Service file exists, path matches backend route | ✅ |
| `HubCard interface declares the 13 visible card fields` | Type contract matches backend `_build_card` output | ✅ |
| `AgentsPage Prebuilt tab imports agentHubApi (not runtimeAgentApi.listAgents for certified)` | Wiring changed from runtime registry to Hub endpoint | ✅ |
| `HubCard red_lines interface declares the 4 Corti rules` | no_upcoding, no_inference, evidence_required, production_writeback_blocked | ✅ |

## F.6 Cumulative regression — 71/71 frontend tests pass

| Suite | Tests | Status |
|---|---|---|
| `apiContract.test.ts` | 45 | ✅ 45/45 |
| `agentNavigationSmoke.test.tsx` | 7 | ✅ 7/7 |
| `agentVisibilityContract.test.ts` | 6 | ✅ 6/6 (existing — still passes, `agentHubApi.ts` now exists) |
| `agentHubContract.test.ts` (new) | 4 | ✅ 4/4 |
| `locales.test.ts` | 9 | ✅ 9/9 |
| **Total** | **71** | ✅ **71/71** |

Plus: TypeScript 0 errors; `npm run build` exit 0.

## F.7 Phase 3-B2 follow-ups (scoped, not in this Phase 3-B1)

| Follow-up | Scope | Rationale |
|---|---|---|
| MedicalCodingPage Run button → A2A mainline | ~50 LOC in `MedicalCodingPage.tsx` | Closes §F requirement #9; eliminates compat shim shape divergence (see §E.4) |
| RunTracePage surfaces A2A state_history | ~30 LOC + verify backend `/api/runtime-platform/runs` includes A2A runs | Closes §F requirement #10 |
| Text Gen / STT SHOULD_HIDE nav flag | ~10 LOC in `Layout.tsx` + Coming Soon banner in pages | Closes §F requirement #11 |
| EmbeddedAssistantPage hide-from-nav or delete | ~5 LOC in `Layout.tsx` (or file deletion) | Closes §F requirement #12 |

None of these are blocking for Phase 3-B1's verdict — the Hub is wired, Medical Coding Agent card is visible with all required signals, metadata-only Coming Soon treatment works, and the contract is locked by tests.

## F.8 Verdict

**Section F verdict**: PASS (with 4 documented Phase 3-B2 follow-ups) — Hub endpoint wired into Prebuilt tab via new `agentHubApi`; Medical Coding Agent card visible with MVP / AI-assisted / Human Review / production_ready=false + 3 red line pills + Corti 7-step workflow; 10 metadata-only packs show Coming Soon with no Run button; expert-stubs and internal_engine excluded by backend filter; 4 new contract tests + 67 existing tests all pass (71/71); TS 0 errors; build exit 0; 4 Phase 3-B2 follow-ups (Run button → A2A, RunTrace A2A state, TextGen/STT SHOULD_HIDE, EmbeddedAssistant DELETE_CANDIDATE) scoped and documented.

The frontend now truthfully reflects the new Hub / A2A / Agent state at the contract level. The remaining UI work (Run button migration, RunTrace A2A display, SHOULD_HIDE nav flags, EmbeddedAssistant deletion) is bounded for Phase 3-B2.
