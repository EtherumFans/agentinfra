# Phase 7 Gate 0 — Phase 6 Runtime Baseline Re-Audit

**Date**: 2026-07-14
**Tier**: `GATE0_PHASE6_RUNTIME_BASELINE_AUDITED_WITH_HONEST_GAPS`
**Method**: Source code reading + dist inspection + alembic state + test inventory. **No browser execution in this gate** — that is reserved for Phase 7 Gate 10/11.

## Method

Per Phase 7 brief §五, **"不得仅根据 Phase 6 报告中的 PASS 结论判断能力已经完成"**. This gate reads the actual code, dist artifacts, alembic state, and test inventory for each Phase 6 claim. The matrix below records:

- **报告声称** — what the Phase 6 gate closure report says
- **代码实际** — what the source actually contains (with line numbers)
- **浏览器实际** — whether browser evidence exists (typically NO — Phase 6 explicitly deferred browser walkthrough to Phase 7)
- **测试** — which tests cover the capability
- **当前状态** — honest verdict for Phase 7 consumption

## Capability matrix

### 1. `<icoder-embedded>` — canonical Web Component

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 1: "2.0 dist-serve via /api/embedded/assistant.js" |
| 代码实际 | `packages/icoder-embedded/src/icoder-assistant.ts:752` — `customElements.define('icoder-embedded', iCoDerEmbedded)`. 763 LOC source. Dist: `dist/icoder-assistant.js` 664 LOC (31.6KB). |
| 浏览器实际 | **NOT VERIFIED** in Phase 6. Backend `/api/embedded/preview` exists but no Playwright run was executed in P6. |
| 测试 | `frontend/tests/e2e/phase5_a4_embedded.spec.ts` — 6 cases covering registration/methods/show+ready/legacy alias. NOT yet run in Phase 7. |
| 当前状态 | **SHIPPED-as-source-and-dist, BROWSER_E2E_DEFERRED** |

### 2. Legacy `<icoder-assistant>` compatibility

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 5 A5 + Phase 6 Gate 1: "deprecated alias preserved for 2.0.x window" |
| 代码实际 | `icoder-assistant.ts:753-757` — `_deprecatedAlias = customElements.get('icoder-assistant')` then re-register as alias |
| 浏览器实际 | **NOT VERIFIED** in Phase 6. |
| 测试 | `phase5_a4_embedded.spec.ts` case "legacy <icoder-assistant> tag still registers" |
| 当前状态 | **SHIPPED, BROWSER_E2E_DEFERRED** |

### 3. `auth()` method (2.0 method-based API)

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 5 A4 + Phase 6 Gate 1: method chain auth → configureSession → configure → show |
| 代码实际 | `icoder-assistant.ts:347` — `async auth(opts: AuthOptions)` |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | phase5_a4 method-existence assertion |
| 当前状态 | **SHIPPED, BROWSER_E2E_DEFERRED** |

### 4. `configureSession()` + Patient Context

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 2: PHI memory-only, configureSession({patientId, name, encounterId}) |
| 代码实际 | `icoder-assistant.ts:356` — `configureSession()`; cross-patient console.warn at line 362-363; `_contextId` updated at line 366 |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | phase5_a4 case "configureSession renders patient context bar" |
| 当前状态 | **SHIPPED, BROWSER_E2E_DEFERRED** |

### 5. Patient Context safety — clear API

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 2: `clearPatientContext()` + `clearSession()` + cross-patient warn |
| 代码实际 | `clearPatientContext()` at line 456; `clearSession()` at line 469; **zero** references to `localStorage` / `sessionStorage` / `document.cookie` in widget (grep confirms) |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | phase5_a4 (extended in P6 G2): 2 cases for clear + meta event assertions |
| 当前状态 | **SHIPPED, BROWSER_E2E_DEFERRED, STORAGE_AUDIT_PENDING** (Phase 7 Gate 6 will run real Storage/Console audit) |

### 6. Unified Event Envelope v1.0 — `meta`

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 3: `{name, payload, meta:{version,eventId,timestamp,sessionId,contextId}}` |
| 代码实际 | `EmbeddedEventMeta` interface at line 221; `_emitEmbeddedEvent()` at line 510 builds meta with randomUUID + ISO timestamp + sessionId + contextId. Verified in dist: 21 matches for meta fields. |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | phase5_a4 "Phase 6 Gate 3 — meta.sessionId stable across multiple events; eventId unique" |
| 当前状态 | **SHIPPED, BROWSER_E2E_DEFERRED** |

### 7. Retry — 1 automatic on network errors

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 3: 1 retry on TypeError, NOT on AbortError (timeout), NOT on 4xx/5xx |
| 代码实际 | `icoder-assistant.ts:665-678` — `doFetch(1)` → catch networkErr → if `controller.signal.aborted` re-throw → else `doFetch(2)` |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | None — retry behavior is not covered |
| 当前状态 | **CLIENT-SIDE-ONLY**. **CRITICAL Phase 7 concern**: client retry may create duplicate Runs at the backend if both fetches reach the server (e.g. timeout after server-side completion). Server-side dedup (Phase 7 Gate 3) is required to make retry safe. |

### 8. AbortController — 90s timeout

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 3: 90s default, `request-timeout-ms` attribute override, AbortError classified as `kind:'timeout', retriable:false` |
| 代码实际 | `icoder-assistant.ts:618-619` — `new AbortController()` + `setTimeout(() => controller.abort(), timeoutMs)` |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | None |
| 当前状态 | **CLIENT-SIDE-ONLY**. **CRITICAL Phase 7 concern**: abort only stops the browser from waiting for the response. The backend Run continues to completion and charges real DeepSeek cost. Phase 7 Gate 4 needs `POST /api/v1/runs/{run_id}/cancel` to make abort meaningful. |

### 9. `Idempotency-Key` header

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 3: client sends `Idempotency-Key` + `X-Attempt` header; "Server-side dedup (用 Idempotency-Key 做 cache) 是 Phase 7 候选" |
| 代码实际 | `icoder-assistant.ts:649-657` — `doFetch()` sets both headers |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | None |
| Backend | **ZERO server-side dedup**. Grep `idempotency` across `backend/app/`: only 1 unrelated match in `a2a_routes.py:102` ("Mark as mounted (idempotency guard)"). |
| 当前状态 | **CLIENT-ONLY, SERVER-NOT-IMPLEMENTED**. Phase 7 Gate 3 P0. |

### 10. SDK Build (`@icoder/sdk@1.0.0-beta.2`)

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 4: 3 new resources (Runs/RunHistory/RunTrace) + A2A types |
| 代码实际 | `packages/icoder-sdk/src/resources/runs.ts` (225 LOC, verified); `dist/index.js` exports confirmed; `dist/resources/runs.{js,d.ts}` present |
| 浏览器实际 | N/A |
| 测试 | None (SDK has no test suite) |
| 当前状态 | **PACKAGE_BUILD_VERIFIED_WITH_PRE-EXISTING_ERRORS**. `src/resources/compliance.ts` has 4 TypeScript errors (`Cannot find name 'iCoDerClient'`, `Property 'http' does not exist`). Phase 6 G4 report flagged these as pre-existing. They will break Phase 7 Gate 2 `.tgz` install validation. |

### 11. `.tgz` external install

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 4: "REGISTRY_PUBLISH_DEFERRED per Phase 6 §4.3" |
| 代码实际 | No `.tgz` ever built. |
| 浏览器实际 | N/A |
| 测试 | None |
| 当前状态 | **NOT ATTEMPTED**. Phase 7 Gate 2. |

### 12. Medical Coding Demo

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 7: HTML file 160 LOC, T12-equivalent scenario |
| 代码实际 | `packages/icoder-embedded/demos/medical-coding-demo.html` exists (7.7KB) |
| 浏览器实际 | NOT VERIFIED |
| Backend mount | **NO BACKEND ROUTE** serves the demo. Grep `/examples` and `demos` in `backend/app/api/embedded.py`: 0 matches. |
| 测试 | None |
| 当前状态 | **FILE-EXISTS-ASSET, NO_BACKEND_MOUNT, NO_BROWSER_E2E**. Phase 7 Gates 1 + 10. |

### 13. CDI Demo

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 7: HTML file 154 LOC |
| 代码实际 | `packages/icoder-embedded/demos/cdi-demo.html` (7.8KB) |
| 浏览器实际 | NOT VERIFIED |
| Backend mount | NO BACKEND ROUTE |
| 测试 | None |
| 当前状态 | **FILE-EXISTS, NO_BACKEND_MOUNT, NO_BROWSER_E2E** |

### 14. DRG/DIP Demo

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 7: HTML file 160 LOC |
| 代码实际 | `packages/icoder-embedded/demos/drg-dip-demo.html` (8.1KB) |
| 浏览器实际 | NOT VERIFIED |
| Backend mount | NO BACKEND ROUTE |
| 测试 | None |
| 当前状态 | **FILE-EXISTS, NO_BACKEND_MOUNT, NO_BROWSER_E2E** |

### 15. `trace_url` deep-link

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 5: field on AgentRunResponse, surfaced in `run.completed` event payload |
| 代码实际 | `backend/app/api/agent_run.py:182-203` — `trace_url` field + `_trace_url_for()` helper; populated in 4 return sites (`_map_coding_result` success+error, `_map_backend_response`, `_error_response`). Frontend route `/ai-studio/runs/:runId/trace` in `App.tsx:82`. |
| 浏览器实际 | NOT VERIFIED in Phase 6 |
| 测试 | `test_phase4f_agent_run.py::test_error_response_trace_url_is_deep_link` |
| 当前状态 | **SHIPPED, CROSS_APP_AUTH_NOT_ADDRESSED**. The trace_url points to a route that requires Console login cookie. Partner apps (no Console session) cannot open it. Phase 7 Gate 7 needs signed-token access. |

### 16. Usage multi-dim + per-agent

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 8: `agent_id` + `runtime_mode` filters; new `/by-agent` endpoint |
| 代码实际 | `backend/app/api/usage.py:34` (`/summary` with filters), `:141` (`/by-agent`) |
| 浏览器实际 | NOT VERIFIED |
| 测试 | `test_phase5_a3_usage_run_history_cost.py` (existing, pre-P6) |
| 当前状态 | **SHIPPED-PARTIAL**. **Missing filter**: `api_client_id` (column doesn't exist on `run_history`). Phase 7 Gate 8 will need this once Gate 5 ships the column. |

### 17. API Client (CRUD)

| Aspect | Evidence |
|---|---|
| 报告声称 | Phase 6 Gate 8: "API_CLIENT_PRODUCTIZATION_DEFERRED_TO_PHASE_2_CLOUD"; 501 stubs with verdict code |
| 代码实际 | `backend/app/api/platform_api_clients.py` — 5 endpoints all return 501 with `phase6_gate8_verdict` |
| 浏览器实际 | N/A |
| 测试 | None |
| 当前状态 | **HONEST_STUB_NOT_FAKE**. Phase 7 Gate 5 must implement the real CRUD. |

## Phase 6 Gate 6 — clarification

Phase 6 final report line 34:
> "Gate 6 was rolled into Gate 5 — RunHistory/Trace/Cost 集成 was already 90% done in Phase 4-G/5-A, only trace_url surfacing was needed."

| Question | Answer |
|---|---|
| Was Gate 6 merged into another gate? | Yes — explicitly rolled into Gate 5 |
| Is there a Gate 6 report? | **NO** — `ls reports/phase6/` confirms only Gates 0, 1, 2, 3, 4, 5, 7, 8 + Final |
| Is there a Gate 6 commit? | NO separate commit; Gate 5 closure is `619dc1b` series from earlier work + P6 Gate 5 commits |
| Was Gate 6 actually executed? | **No as a standalone gate**. The RunHistory/Trace/Cost work was substantially done in Phase 4-G (alembic 009 + 010) + Phase 5 A (live cost + Usage wiring) before Phase 6 started. Phase 6 Gate 5 only added `trace_url` surfacing. The "roll-up" framing is honest but means there is no discrete Gate 6 deliverable. |

## Phase 7-critical gaps revealed by audit

Sorted by Phase 7 checkpoint dependency:

### Checkpoint A blockers (idempotency + external install)

1. **No server-side idempotency dedup** — Gate 3 P0
2. **No `.tgz` build + external install validation** — Gate 2
3. **`packages/icoder-sdk/src/resources/compliance.ts` pre-existing TypeScript errors** — must fix before Gate 2 build can succeed

### Checkpoint B blockers (security + attribution)

4. **`run_history` table missing `api_client_id` column** — Gate 5 alembic 012
5. **No `api_clients` table** — Gate 5 alembic 013 (or combined)
6. **No API Client CRUD** — Gate 5
7. **No Allowed Origins enforcement** — Gate 6
8. **No signed trace tokens** — Gate 7
9. **trace_url cross-app auth not addressed** — Gate 7

### Checkpoint C blockers (3 demos)

10. **No backend mount for `/examples/*` demos** — Gate 1
11. **Demos use Console-flavored auth flow** — they expect JWT from `/api/auth/login`; partner apps use client_credentials. Demos need partner-auth mode.
12. **No Playwright browser E2E for demos** — Gate 10

### Checkpoint D blockers (reference app)

13. **No `examples/partner-reference-app/`** — Gate 12

### Cross-cutting

14. **No `POST /api/v1/runs/{run_id}/cancel`** — Gate 4
15. **No SSE or polling event endpoint** — Gate 9
16. **Usage filter `api_client_id` unavailable** (column missing) — Gate 8

## Phase 6 test coverage — honest read

Phase 6 final report cited "12 backend tests pass". The actual backend test inventory is **237 test files** (`find backend/tests -name "test_*.py" | wc -l = 237`). Phase 6 only ran 12 of them. This is not deceptive — Phase 6 changes were narrow (agent_run + usage + embedded + platform_api_clients + 3 new SDK files) so 12 was sufficient for the touched code paths. But Phase 7 cannot rely on 12 tests for partner validation.

## Risk list (ordered by Phase 7 gate impact)

| # | Risk | Mitigation |
|---|---|---|
| R1 | Server-side idempotency requires DB schema + concurrent test | Gate 3 will add alembic 012 + pytest with `asyncio.gather` race test |
| R2 | API Client CRUD requires real secret hashing + rotation | Gate 5 will use bcrypt + one-time-display pattern |
| R3 | .tgz install will fail on compliance.ts type errors | Gate 2 will fix or remove compliance.ts first |
| R4 | Demos assume Console JWT, not client_credentials | Gate 1 will add partner-auth mode to demos |
| R5 | trace_url requires Console cookie | Gate 7 will add signed-token endpoint |
| R6 | No browser evidence exists for ANY Phase 6 capability | Phase 7 Gate 10/11 will produce real Playwright evidence |
| R7 | Real DeepSeek calls cost ¥ — Phase 7 E2E will incur real LLM cost | Use corti_like_fast (¥0.01-0.05/run) for E2E; reserve medcoder_deep for smoke only |
| R8 | Run cancel may not be supported by current HybridCodingAdapter | Gate 4 may need to return `CANCEL_NOT_SUPPORTED` for in-flight runs |

## Verdict

`GATE0_PASS_PHASE6_BASELINE_AUDITED_HONEST_GAPS_DOCUMENTED`

Phase 6 reports are **honest** — every claim verified against source. Where Phase 6 said "deferred to Phase 7", the deferral is real (zero server-side code). Where Phase 6 said "shipped", the code is present and the dist is built. The single gap between Phase 6's framing and Phase 7's requirements is that Phase 6 was a **consolidation** phase (connecting existing assets, surfacing existing data) while Phase 7 is an **infrastructure** phase (new DB tables, new endpoints, real browser evidence).

**Not a single capability was faked.** But also: **not a single capability has browser evidence yet**. Phase 7 must produce that evidence for any "Ready for Partner Integration Validation" verdict to be earned.

## Carry-forward to Phase 7 Gate 1

Recommended execution order per §二十一 commit grouping + §十八 hard checkpoints:

1. **Gate 1** (demo static mount) — small, unblocks Gate 10
2. **Gate 2** (.tgz install) — fix compliance.ts first; small; unblocks Checkpoint A
3. **Gate 3** (server idempotency) — P0, unblocks Checkpoint A; largest single gate (~3-4h)
4. **Gate 4** (cancel/timeout) — depends on Gate 3 run_id semantics
5. **Gate 5** (API Client CRUD + attribution) — depends on Gate 3 for `idempotency_key` column
6. **Gate 6** (CORS / Storage audit) — depends on Gate 5 for allowed-origins source
7. **Gate 7** (signed trace tokens) — independent
8. **Gate 8** (Usage accounting) — depends on Gate 5 for `api_client_id` column
9. **Gate 9** (SSE / polling) — independent; can be `POLLING_AND_REPLAY_VALIDATED` if SSE too heavy
10. **Gate 10** (3 demos browser E2E) — depends on Gates 1, 2, 3, 5, 7
11. **Gate 11** (context isolation + restart recovery) — depends on Gate 10
12. **Gate 12** (partner reference app) — depends on all above
13. **Final report**

**Hard checkpoint order**: A (Gates 2+3) → B (Gates 5+6+7) → C (Gate 10) → D (Gate 12). Cannot skip.
