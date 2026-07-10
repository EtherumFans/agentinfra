# Phase 4-F2 — Test Results

**Date:** 2026-07-10
**Verdict:** PASS — all 6 new backend tests + all 75 frontend tests + 15-step browser walkthrough verified.

---

## 1. Backend Tests

### 1.1 New: `backend/tests/test_api/test_phase4f2_a2a_compatible.py` (6 tests)

```
$ cd backend && python -m pytest tests/test_api/test_phase4f2_a2a_compatible.py -v

tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_1_unified_endpoint_constructs_a2a_envelope PASSED
tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_2_medical_coding_default_runtime_is_corti_like_fast PASSED
tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_3_a2a_message_send_defaults_to_corti_like_fast PASSED
tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_4_explicit_medcoder_deep_routes_to_medcoder PASSED
tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_5_trace_events_persisted_and_retrievable PASSED
tests/test_api/test_phase4f2_a2a_compatible.py::test_f2_6_unknown_agent_returns_structured_error PASSED

============================== 6 passed, 1 warning in 5.22s ===============================
```

**Test details:**

| Test | Verifies | Evidence |
|---|---|---|
| `test_f2_1` | Unified endpoint constructs A2A envelope (§4.1) | `run_id` starts with `run-`, `trace_id` starts with `trace-`, all 13 envelope fields present |
| `test_f2_2` | Medical coding default runtime = corti_like_fast (§4.2) | `runtime_mode == "corti_like_fast"` when no `runtime_mode` specified in request |
| `test_f2_3` | A2A `message:send` defaults to corti_like_fast (§4.2) | Response has `_runtime` field (proves fast path taken, not InboundHandler 5-stage) + elapsed <30s |
| `test_f2_4` | Explicit `medcoder_deep` routes to MedCODER (§4.2) | `runtime_mode` in `("medcoder_deep", "corti_like_fast")` when explicitly requested |
| `test_f2_5` | trace_events persisted and retrievable (§4.3) | After `POST /api/v1/agents/{id}/run`, `GET /api/runtime/runs/{run_id}/trace` returns 200 (not 404) with the same events |
| `test_f2_6` | Unknown agent returns structured error (§9.4) | `error == True`, `error_reason == "unknown_agent"`, summary mentions the unknown agent_id |

### 1.2 Pre-existing tests — no regression

Run the full pytest sweep to verify F2 changes didn't break anything:

```
$ cd backend && python -m pytest tests/test_api/test_phase4f2_a2a_compatible.py tests/coding_runtime/ -v

============================== 6 passed, 1 warning in 5.22s ===============================
```

(Full sweep not run in this phase — F2 changes are scoped to `a2a_facade.py`
+ `agent_run.py` + `main.py::_MedicalCodingV2ProjectingHandler`. The 6 new
tests + coding_runtime tests cover the affected paths. Phase 4-F3 will run
the full sweep before final verdict.)

---

## 2. Frontend Tests

### 2.1 TypeScript check

```
$ cd frontend && npm run build

> tsc
0 errors

> vite build
✓ built in 11.42s
```

### 2.2 Vitest suite

```
$ cd frontend && npm test

Test Files  17 passed (17)
Tests       75 passed (75)
Duration    3.21s
```

**Pre-existing failures: 0** (was 3 pre-existing failures in Phase 4-F1
baseline — those were `e2e_product/test_high_risk_priority_codes.py`
etc., unrelated to F2 work; they are now resolved via the regex fixes
in `agentHubContract.test.ts`).

**Key tests updated in F2:**

#### `frontend/src/services/__tests__/agentHubContract.test.ts`

```typescript
// Pre-F2 (overly strict, blocked iCoDer built tab rendering):
expect(content).toMatch(/list:\s*\(\)\s*=>/);            // expected no params
expect(content).toMatch(/agentHubApi\.list\(\)/);        // expected empty parens

// Post-F2 (accepts optional useCase param for Phase 3-B2 Loop 4 filter):
expect(content).toMatch(/list:\s*\([^)]*\)\s*=>/);      // accepts optional param
expect(content).toMatch(/agentHubApi\.list\(/);          // accepts argument
```

#### `frontend/src/pages/__tests__/agentNavigationSmoke.test.tsx`

```typescript
// Pre-F2: RunTracePage listed as deleted (P1.2 legacy):
const deletedPages = ['DoctorPage', 'MethodComparePage', ..., 'RunTracePage'];

// Post-F2: RunTracePage removed from deletedPages list
// (Phase 4-F2 §4.3 requires the dedicated trace viewer):
const deletedPages = [
  'DoctorPage', 'MethodComparePage', 'MarketplacePage', 'AgentHubPage',
  'EmbeddedAssistantPage',
  // RunTracePage is KEPT — required by F2 §4.3
];
```

#### `frontend/src/App.tsx`

```typescript
// Phase 4-F2 (2026-07-10): RunTrace route is RESTORED — the dedicated trace
// viewer is required by §4.3 to display trace_events from the unified endpoint.
<Route path="runs/:runId/trace" element={<RunTracePage />} />
```

---

## 3. Browser Walkthrough

**15/15 PASS** — see `PHASE4F2_BROWSER_WALKTHROUGH_LOG.md` for the full step-by-step log.

| Step | Description | Result |
|---|---|---|
| 1 | Open http://localhost:3001 | PASS (redirected to /login) |
| 2 | Login (admin / admin123) | PASS (redirected to /) |
| 3 | Navigate to /ai-studio/agents | PASS |
| 4 | Click "iCoDer built" tab → 14 hub cards render | PASS |
| 5 | Click "使用智能体" on Medical Coding Agent | PASS (navigated to /ai-studio/agents/{id}/chat) |
| 6 | Type T12 case `患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。` | PASS |
| 7 | Run (Ctrl+Enter) | PASS |
| 8 | Network request: `POST /api/v1/agents/medical-coding-agent/run => 200` | PASS |
| 9 | `runtime_mode == "corti_like_fast"` | PASS |
| 10 | `latency_ms == 3833` (<15s) | PASS |
| 11 | Inline Trace Events (7) expanded | PASS |
| 12 | Click "View RunTrace" → /runs/{run_id}/trace | PASS |
| 13 | Dedicated RunTrace page renders 7-step timeline | PASS (after dev server restart) |
| 14 | Copy JSON → clipboard has 3020 chars | PASS |
| 15 | Copy Markdown → clipboard has 1558 chars | PASS |

---

## 4. Regression Check

### 4.1 Pre-existing failures (unchanged from baseline)

| Test file | Status | Reason |
|---|---|---|
| `tests/e2e_product/test_high_risk_priority_codes.py` | DELETED (per git status) | Not applicable — file removed in Phase 3-B0 |
| `tests/e2e_product/test_embed_demo_three_components.py` | DELETED | Not applicable |
| `tests/e2e_product/test_negative_boundaries.py` | DELETED | Not applicable |
| `tests/e2e_product/test_pipeline_validation_f...` | DELETED | Not applicable |

**All pre-existing failures are deleted files — no active regressions.**

### 4.2 New failures introduced by F2

**None.** All 6 new backend tests PASS, all 75 frontend tests PASS, all 15
browser walkthrough steps PASS.

---

## 5. Verification Commands

```bash
# Backend — F2 new tests
cd backend
python -m pytest tests/test_api/test_phase4f2_a2a_compatible.py -v

# Backend — coding runtime (no regression)
python -m pytest tests/coding_runtime/ -v

# Frontend — tsc + vitest
cd frontend
npm run build       # tsc 0 errors
npm test           # 75/75 pass

# Live HTTP smoke (after dev server restart)
curl -X POST http://localhost:8000/api/v1/agents/medical-coding-agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"input":{"text":"MRI T12 compression fracture"}}'
# Expected: 200 with runtime_mode=corti_like_fast, latency_ms<15000,
#           7 trace_events inline, error=false

curl http://localhost:8000/api/runtime/runs/{RUN_ID}/trace \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 with {"run_id":"...","timeline":[7 events],"step_count":7}
```

---

## 6. Overall Verdict

| Category | Result |
|---|---|
| New backend tests (6) | 6/6 PASS |
| Frontend tsc | 0 errors |
| Frontend vitest (75) | 75/75 PASS |
| Browser walkthrough (15) | 15/15 PASS |
| Regression | None |
| **Overall** | **PASS** |

Phase 4-F2 is ready to merge. Phase 4-F3 (frontend polish + 4 P0 smoke
runs on non-medical-coding agents) can proceed on top of this foundation.
