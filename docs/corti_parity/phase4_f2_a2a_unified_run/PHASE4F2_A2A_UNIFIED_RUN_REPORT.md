# Phase 4-F2 — A2A-Compatible Unified Agent Run Architecture Report

**Date:** 2026-07-10
**Sub-phase:** Phase 4-F2 (A2A-Compatible Unified Agent Run Architecture)
**Predecessor:** Phase 4-F1 (AgentChatPage unified run wiring, 2026-07-10)
**Successor:** Phase 4-F3 (frontend polish + 4 P0 smoke runs, pending)
**Status:** PASS — all 6 backend tests + 15-step browser walkthrough verified

---

## 1. Executive Summary

Phase 4-F2 closes the 3-way architectural gap between:

1. **The unified Agent Run endpoint** `POST /api/v1/agents/{agent_id}/run` (Phase 4-F1 facade)
2. **The A2A mainline** `POST /api/icoder/agents/{agent_id}/v1/message:send` (Phase 3-B1 InboundHandler)
3. **The dedicated RunTrace page** `/runs/{run_id}/trace` (Phase 3-D1 Task 4)

Before F2, these three paths were **siloed**: the unified endpoint did not
construct an A2A envelope; the A2A path for medical-coding-agent defaulted
to the MedCodER 5-stage pipeline (60s+ timeout vs Corti's ~8s); and trace
events from the unified endpoint were returned inline but **never persisted**
to RunTraceStore, so the dedicated `/runs/{run_id}/trace` page rendered
"未找到 RunTrace" even when the run produced 7 inline events.

F2 introduces a **shared A2A-compatible facade** (`a2a_facade.py`) that owns
the envelope construction + medical-coding fast-path dispatch + trace
persistence. Both entry points (unified endpoint + A2A `message:send`) call
into this facade, eliminating the siloed paths and ensuring A2A protocol
semantics (run_id / trace_id / context_id / message_id / parts / metadata)
are preserved even when the underlying dispatch is a lightweight
CodingRuntimeDispatcher call rather than the full InboundHandler 5-stage
state machine.

**Three-layer architecture (validated):**

```
A2A protocol layer       → a2a_facade.construct_envelope()
  (InboundRequest envelope with TextPart + metadata.runtime_mode)
                              ↓
Entry/facade layer        → POST /api/v1/agents/{id}/run (agent_run.py)
                          → POST /api/icoder/agents/{id}/v1/message:send (main.py handler)
                              ↓
Runtime execution layer   → CodingRuntimeDispatcher (corti_like_fast / medcoder_deep)
                          → ProviderRegistry (a2a_pure_llm / rule_engine / llm_with_tools)
```

**Per §6.1 of the F2 prompt:** "如现有 A2A handler 过重，可先做一层轻量
A2A-compatible adapter，但必须保留 A2A envelope 语义". The `a2a_facade.py`
module IS this lightweight adapter — it preserves A2A envelope semantics
without forcing every unified-endpoint run through the full InboundHandler
5-stage state machine.

---

## 2. Goals (per F2 prompt §1)

| # | Goal | Status |
|---|------|--------|
| 1 | `/api/v1/agents/{id}/run` constructs A2A-compatible envelope internally | ✅ PASS |
| 2 | Medical Coding Agent default runtime = `corti_like_fast` on BOTH unified endpoint AND A2A `message:send` | ✅ PASS |
| 3 | `trace_events` persisted to RunTraceStore so `/runs/{run_id}/trace` works | ✅ PASS |
| 4 | iCoDer built tab renders 14 hub cards on `/ai-studio/agents` | ✅ PASS |
| 5 | Three-layer architecture (A2A protocol / entry facade / runtime execution) | ✅ PASS |
| 6 | 6 backend tests + 15-step browser walkthrough | ✅ PASS |

---

## 3. Corti Reference (per F2 prompt §3)

Corti's `medical-coding-icd-10-cpt-agent` console flow:

- **Run URL:** `POST /api/v1/agents/{agent_id}/run` — Corti returns a 13-field
  envelope (`agent_id`, `run_id`, `trace_id`, `runtime_mode`, `latency_ms`,
  `cost`, `summary`, `result`, `evidence`, `warnings`,
  `manual_review_required`, `trace_events`, `error`, `error_reason`).
- **Runtime mode:** `corti_like_fast` is the default (~6-8s on T12 fracture
  case under real DeepSeek; Corti does NOT default to MedCodER 5-stage).
- **Trace events:** Every run emits 7 lifecycle events
  (`input_received`, `language_detect`, `build_prompt`, `llm_call`,
  `parse_json`, `project_result`, `return`) that are:
  - returned inline in the response body, AND
  - persisted to a server-side trace store retrievable via
    `GET /api/runtime/runs/{run_id}/trace`.
- **A2A parity:** Corti's A2A `message:send` path returns the same v2 contract
  as the unified endpoint (no protocol bifurcation between "Run API" and
  "A2A mainline").

iCoDer F2 implements the same envelope + same trace persistence + same
default runtime + same A2A parity.

---

## 4. iCoDer Implementation

### 4.1 New file: `backend/app/icoder/agent_runtime/a2a_facade.py` (~345 LOC)

The shared A2A-compatible facade. Owns:

- `construct_envelope()` — builds `InboundRequest` with `InboundMessage(role="user", parts=[TextPart, DataPart?], interaction_id=trace_id)` + metadata carrying `runtime_mode` / `include_trace` / `include_evidence` / `run_id` / `trace_id` / `agent_id` / `user_id` / `tenant_id` / `phi_redacted` / `production_writeback_blocked`.
- `dispatch_medical_coding_fast()` — routes to `CodingRuntimeDispatcher` with the requested `RuntimeMode` (`corti_like_fast` default, `medcoder_deep` opt-in). Returns `(CodingResult, out_run_id, out_trace_id)`.
- `build_medical_coding_inbound_response()` — projects a `CodingResult` into an A2A `InboundResponse` with v2 parts + `_runtime` envelope (used by A2A `message:send` handler in `main.py`).
- `persist_trace_events()` — emits each inline `trace_event` to `RunTraceStore` via `emit_trace_event()` so `GET /api/runtime/runs/{run_id}/trace` returns the events.

### 4.2 Modified: `backend/app/api/agent_run.py`

`run_agent()` endpoint now:

1. Calls `construct_envelope()` to build the A2A envelope (preserves
   run_id / trace_id / context_id / message_id).
2. Logs "agent_run: A2A envelope constructed ..." at INFO level.
3. Dispatches to `_run_medical_coding()` (medical-coding path) or
   `_run_via_provider_registry()` (generic path).
4. After the run, calls `persist_trace_events()` if
   `response.trace_events and not response.error`.

`_run_medical_coding()` now delegates to `dispatch_medical_coding_fast()`
from the facade (shared with the A2A path).

`_run_via_provider_registry()` now:
- Accepts `context_id` parameter (from the envelope).
- Emits `USER_MESSAGE_RECEIVED` at start (so `/runs/{run_id}/trace` has
  content even for non-medical-coding agents).
- Emits `OUTPUT_GENERATED` + `COMPLETION` (ok/failed) after
  `provider.invoke()`.

`_map_backend_response()` now includes 3 lifecycle `trace_events` in the
response body (mirroring the events emitted to the store).

### 4.3 Modified: `backend/app/main.py` (`_MedicalCodingV2ProjectingHandler`)

The A2A `message:send` handler for `medical-coding-agent` now:

1. Reads `runtime_mode` from request metadata (default `corti_like_fast`).
2. If `runtime_mode != "medcoder_deep"`:
   - Extracts text from request parts.
   - Calls `dispatch_medical_coding_fast()` directly (bypasses InboundHandler
     5-stage state machine — the 60s+ timeout root cause).
   - Persists `trace_events` from the `CodingResult` to `RunTraceStore`.
   - Returns `build_medical_coding_inbound_response()` (v2 contract +
     `_runtime` envelope).
3. If `runtime_mode == "medcoder_deep"`: passes through to `InboundHandler`
   (5-stage MedCodER pipeline, opt-in only).

This means A2A `message:send` for medical-coding-agent now defaults to
`corti_like_fast` (~6-8s), matching Corti parity.

### 4.4 Frontend updates

- `frontend/src/App.tsx`: comment updated to note RunTrace route is
  RESTORED (Phase 4-F2 §4.3 requires it).
- `frontend/src/pages/__tests__/agentNavigationSmoke.test.tsx`: removed
  `RunTracePage` from `deletedPages` list (it must remain routed).
- `frontend/src/services/__tests__/agentHubContract.test.ts`: fixed
  overly-strict regex patterns (`list:\s*\([^)]*\)\s*=>` accepts the
  optional `useCase` param for Phase 3-B2 Loop 4 filter; `agentHubApi\.list\(`
  accepts the call with argument).

---

## 5. Architecture Diagram (per F2 prompt §9.2)

```
┌────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React SPA)                          │
│                                                                    │
│  AgentsPage (iCoDer built tab)  →  AgentChatPage  →  RunTracePage   │
│         │                              │                  ↑        │
│         │ 14 hub cards            POST /api/v1/        GET /api/    │
│         │ render via              agents/{id}/run     runtime/     │
│         │ agentHubApi.list()          ↓                runs/{id}/  │
│         │                              ↓                trace       │
└─────────┼──────────────────────────────┼────────────────┼──────────┘
          │                              │                │
┌─────────▼──────────────────────────────▼────────────────▼──────────┐
│                    BACKEND (FastAPI on :8000)                       │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  ENTRY/FACADE LAYER                                          │  │
│  │                                                              │  │
│  │  POST /api/v1/agents/{id}/run        (agent_run.py)          │  │
│  │     ↳ construct_envelope()                                  │  │
│  │     ↳ dispatch_medical_coding_fast()  ────┐                 │  │
│  │     ↳ _run_via_provider_registry()        │                 │  │
│  │     ↳ persist_trace_events() ←───────────┘                 │  │
│  │                                                              │  │
│  │  POST /api/icoder/agents/{id}/v1/message:send  (main.py)    │  │
│  │     ↳ _MedicalCodingV2ProjectingHandler                     │  │
│  │           ├─ runtime_mode=corti_like_fast (default)         │  │
│  │           │    → dispatch_medical_coding_fast() ────┐       │  │
│  │           │    → build_medical_coding_inbound_response()  │  │
│  │           └─ runtime_mode=medcoder_deep                │  │
│  │                → InboundHandler 5-stage state machine │  │
│  └──────────────────────────────────────────────────────│─┘  │
│                                                        │     │
│  ┌─────────────────────────────────────────────────────▼──┐  │
│  │  A2A PROTOCOL LAYER (shared facade)                    │  │
│  │                                                        │  │
│  │  app/icoder/agent_runtime/a2a_facade.py                │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │ construct_envelope()                            │    │  │
│  │  │   → InboundRequest(message=InboundMessage(     │    │  │
│  │  │       role="user",                              │    │  │
│  │  │       parts=[TextPart, DataPart?],              │    │  │
│  │  │       interaction_id=trace_id),                 │    │  │
│  │  │       metadata={runtime_mode, run_id, trace_id, │    │  │
│  │  │                  context_id, message_id, ...})  │    │  │
│  │  ├────────────────────────────────────────────────┤    │  │
│  │  │ dispatch_medical_coding_fast()                  │    │  │
│  │  │   → CodingRuntimeDispatcher.dispatch(request)   │    │  │
│  │  ├────────────────────────────────────────────────┤    │  │
│  │  │ build_medical_coding_inbound_response()         │    │  │
│  │  │   → InboundResponse(kind="message",            │    │  │
│  │  │       parts=[DataPart(v2_dict + _runtime)])     │    │  │
│  │  ├────────────────────────────────────────────────┤    │  │
│  │  │ persist_trace_events()                         │    │  │
│  │  │   → emit_trace_event(run_id, step, ...)         │    │  │
│  │  │   → RunTraceStore.append(event)                │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  └────────────────────────────────────────────────────────┘  │
│                        │                                     │
│  ┌─────────────────────▼──────────────────────────────────┐  │
│  │  RUNTIME EXECUTION LAYER                               │  │
│  │                                                        │  │
│  │  CodingRuntimeDispatcher (app/coding_runtime/)         │  │
│  │  ├─ FastCodingRuntime (corti_like_fast, ~6-8s)          │  │
│  │  │    └─ 7-step trace: input_received → language_detect│  │
│  │  │       → build_prompt → llm_call → parse_json        │  │
│  │  │       → project_result → return                    │  │
│  │  └─ MedCoderRuntime (medcoder_deep, 5-stage, 30-60s+)  │  │
│  │                                                        │  │
│  │  ProviderRegistry (icoder_runtime/backends/)           │  │
│  │  ├─ PureLLMProvider (a2a_pure_llm)                     │  │
│  │  ├─ LLMWithToolsProvider (llm_with_tools)             │  │
│  │  └─ RuleEngineProvider (rule_engine)                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                        │                                     │
│  ┌─────────────────────▼──────────────────────────────────┐  │
│  │  RunTraceStore (in-memory or DB-backed)                │  │
│  │  ┌────────────────────────────────────────────────┐    │  │
│  │  │ emit_trace_event()                             │    │  │
│  │  │   → RunTraceEvent(run_id, step, status, ts,     │    │  │
│  │  │                   duration_ms, safe_metadata)    │    │  │
│  │  │   → store.append(event)                        │    │  │
│  │  └────────────────────────────────────────────────┘    │  │
│  │                                                        │  │
│  │  GET /api/runtime/runs/{run_id}/trace (run_trace.py)   │  │
│  │    → store.get_run(run_id) → 7 events → 200 timeline   │  │
│  └────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. Failure Contract (per F2 prompt §9.4)

| Failure mode | HTTP | `error` | `error_reason` | `summary` |
|---|---|---|---|---|
| Unknown `agent_id` | 200 | `True` | `"unknown_agent"` | mentions the unknown agent_id |
| Provider not registered | 200 | `True` | `"provider_not_registered"` | mentions the agent_id + missing provider |
| Runtime crash | 200 | `True` | `"runtime_crash"` | mentions exception type + first 200 chars |
| LLM call failed | 200 | `True` | `"llm_call_failed"` | (deferred to Phase 4-F3) |
| Empty input | 200 | `True` | `"empty_input"` | "输入为空,请提供病历文本后重试。" |
| Input too long (>16000 chars) | 200 | `True` | `"input_too_long"` | "输入过长..." |

The endpoint **never raises** to the caller and **never silently times out**.
All failures return HTTP 200 with `error=True` so the frontend can render
a friendly retry UI.

---

## 7. Test Results

### 7.1 Backend pytest (`tests/test_api/test_phase4f2_a2a_compatible.py`)

```
test_f2_1_unified_endpoint_constructs_a2a_envelope          PASS
test_f2_2_medical_coding_default_runtime_is_corti_like_fast PASS
test_f2_3_a2a_message_send_defaults_to_corti_like_fast      PASS
test_f2_4_explicit_medcoder_deep_routes_to_medcoder         PASS
test_f2_5_trace_events_persisted_and_retrievable            PASS
test_f2_6_unknown_agent_returns_structured_error            PASS

6 passed, 1 warning in 5.22s
```

### 7.2 Frontend tsc + vitest

```
$ cd frontend && npm run build
tsc: 0 errors

$ npm test
Test Files  17 passed (17)
Tests       75 passed (75)
```

Pre-existing failures: 3 (unchanged from Phase 4-F1 baseline, all
stash-verified unrelated to F2 work — `test_high_risk_priority_codes.py`
and friends in `tests/e2e_product/`).

### 7.3 Browser walkthrough (15 steps)

All 15 steps PASS — see `PHASE4F2_BROWSER_WALKTHROUGH_LOG.md` for full log.

---

## 8. Known Issues

1. **Chat history loss on browser back**: When the user clicks "View RunTrace"
   and then navigates back, the chat message history on AgentChatPage is
   cleared (the chat result is not persisted to local storage). This is a
   pre-existing UX issue, not an F2 regression. Mitigation: right-click
   "View RunTrace" → "Open in new tab".
2. **In-memory RunTraceStore**: Production deployments must set
   `RUNTRACE_STORE=db` to persist across server restarts and share state
   across workers. Dev mode (`RUNTRACE_STORE=memory`) is fine for
   single-worker local development.
3. **Chat result not persisted**: After the unified run completes, the
   result is rendered inline in the chat but not written to a server-side
   RunHistory table. This means a page refresh loses the result. Phase 4-F3
   will wire RunHistory persistence for the "Run History" tab.

---

## 9. Next Steps

| # | Phase | Task | Priority |
|---|---|---|---|
| 1 | 4-F3 | 4 P0 smoke runs (Coding Evidence, Principal Dx Review, DRG/DIP Risk Review) | P0 |
| 2 | 4-F3 | Frontend polish (Settings/Code/Tools shared components, curl in code tab) | P1 |
| 3 | 4-F3 | 8 agent spec standardization (5 new fields on remaining packs) | P1 |
| 4 | 4-G | Live cost backend wiring (currently shows $50.00 flat credit) | P2 |
| 5 | 4-G | API Client selector real binding (currently placeholder) | P2 |
| 6 | 4-H | Agent fork (clone an iCoDer built agent → user-owned editable copy) | P3 |
| 7 | 4-I | Web Component SDK (ROPC embedded for HIS/EMR integration) | P3 |

---

## 10. References

- F2 prompt: `C:\Users\huawei\Downloads\Phase 4-F2 Prompt — A2A-Compatible Unified Agent Run Architecture.pdf`
- Plan file: `C:\Users\huawei\.claude\plans\jolly-bubbling-swing.md`
- Predecessor: `docs/corti_parity/phase4_f1_agent_chat_unified_run/`
- Backend tests: `backend/tests/test_api/test_phase4f2_a2a_compatible.py`
- Shared facade: `backend/app/icoder/agent_runtime/a2a_facade.py`
- Walkthrough log: `docs/corti_parity/phase4_f2_a2a_unified_run/PHASE4F2_BROWSER_WALKTHROUGH_LOG.md`
- Test results: `docs/corti_parity/phase4_f2_a2a_unified_run/PHASE4F2_TEST_RESULTS.md`
- Architecture notes: `docs/corti_parity/phase4_f2_a2a_unified_run/PHASE4F2_ARCHITECTURE_NOTES.md`
- Remaining backlog: `docs/corti_parity/phase4_f2_a2a_unified_run/PHASE4F2_REMAINING_BACKLOG.md`
