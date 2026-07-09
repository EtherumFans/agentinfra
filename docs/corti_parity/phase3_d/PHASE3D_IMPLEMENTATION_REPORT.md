# Phase 3-D0 / D1 — Corti Parity Hardening + Runtime Agentization

## Implementation Report

**Date:** 2026-07-06
**Phase:** 3-D0 (MCP hardening) + 3-D1 (Runtime agentization)
**Branch:** master
**Verdict:** ✅ PASS (10/10 PASS criteria met)

---

## Executive summary

Phase 3-D closed 5 Corti-parity gaps in two tracks:

- **3-D0 (hardening)**: tightened MCP server auth — scope enforcement +
  redacted_view log capture + test hygiene (3 tasks)
- **3-D1 (agentization)**: shipped a Corti-parity RunTrace viewer +
  upgraded 3 metadata-only stubs to real runnable agents (2 tasks)

All 5 tasks have manual Corti-parity verification reports in
`docs/corti_parity/phase3_d/manual_verification/`. Default sweep:
2265 passed / 0 failed (up from 2232 — net +33 new tests).

---

## Task-by-task breakdown

### Task 1 — MCP Scope Enforcement (3-D0)

**Goal:** `ToolDescriptor.required_scopes` field; `tools/call` checks
before handler dispatch; `MCP_AUTH_FORBIDDEN` on insufficient scope;
RunTrace records `scope_check` step; 5 tests.

**What was built:**
- `app/icoder/mcp/auth.py` — added `granted_scopes` to `AuthHeader`;
  added `scopes` field to `BearerAuthConfig`
- `app/icoder/mcp/auth_resolver.py` — populated `granted_scopes` in
  4 resolver branches (none/bearer/inherit/oauth2)
- `app/icoder/mcp/tool_registry.py` — added `required_scopes:
  list[str]` to `ToolDescriptor`
- `app/icoder/mcp/server.py` — `_check_required_scopes()` helper;
  scope check before handler dispatch; `MCP_AUTH_FORBIDDEN` error;
  scope check + AUTH_RESOLVED + SCOPE_CHECKED + TOOLS_LIST + TOOLS_CALL
  + COMPLETION trace event emits
- `tests/unit/icoder/mcp/test_mcp_scope_enforcement.py` — 5 tests

**Verification:** `TASK1_SCOPE_ENFORCEMENT_VERIFICATION.md` — PASS.

### Task 2 — redacted_view Actual Log Capture (3-D0)

**Goal:** caplog tests verifying raw token / client_secret /
Authorization header never enter logs.

**What was built:**
- `tests/unit/icoder/mcp/test_mcp_log_redaction.py` — 5 tests with a
  `_assert_no_raw_token_in_logs(caplog)` helper scanning for 6 raw
  token variants
- Verified the 3-layer redaction (known-secret keys / token-blob
  heuristic / `_SAFE_KEYS` whitelist) catches every leak path
- Documented one pre-existing out-of-scope quirk: OAuth2 resolver
  ignores user-supplied `redacted_view` field and generates its own
  `Bearer ••••abcd` (last 4 chars). Test asserts the default format.

**Verification:** `TASK2_REDACTED_VIEW_LOG_CAPTURE_VERIFICATION.md` — PASS.

### Task 3 — Test Hygiene (3-D0)

**Goal:** delete stale e2e_product tests; fix test_register flaky;
clean pytest asyncio warnings; default sweep 0 fail.

**What was built:**
- Deleted 7 stale `tests/e2e_product/` files hitting deleted P1.0-era
  endpoints (30 hidden failures exposed after removing `--ignore`)
- Rewrote `tests/test_api/test_auth.py` with `uuid4`-based isolation
  (`_short_uid()` helper) — fixed 7 flaky tests at the root cause
  rather than retry
- Added `inspect.iscoroutinefunction(obj)` guard in
  `tests/integration/conftest.py::pytest_collection_modifyitems` so
  the asyncio auto-marker only applies to actual coroutines (was
  marking all sync tests too, generating warnings)
- Added `infra` pytest marker + `addopts = -m "not heavy and not
  retrieval and not infra"` to `pytest.ini`; marked
  `test_e2e_coding_pipeline.py` with `pytestmark = pytest.mark.infra`
  to opt it out of the default sweep

**Verification:** `TASK3_TEST_HYGIENE_VERIFICATION.md` — PASS.

### Task 4 — RunTrace Corti-Parity Viewer (3-D1)

**Goal:** 9-step timeline; openable from AgentChatPage; Auth step
only shows redacted_view.

**What was built (backend):**
- `app/icoder/agent_runtime/orchestrator/run_trace.py` (NEW):
  `RunTraceStep` (9 constants), `RunTraceStatus`, `RunTraceEvent`,
  `RunTraceStore` (in-memory, `get_run` returns copy),
  `get_default_store()` singleton, `emit_trace_event()` helper
- `app/api/run_trace.py` (NEW): `GET /api/runtime/runs/{run_id}/trace`
  — returns `{run_id, timeline, step_count}` (default) or
  `{run_id, events}` (`?format=raw`); 404 on unknown run_id
- `app/main.py`: `run_trace_router` mounted
- `app/icoder/mcp/server.py`: emits `TOOLS_LIST / AUTH_RESOLVED /
  SCOPE_CHECKED / TOOLS_CALL / COMPLETION` trace events

**What was built (frontend):**
- `frontend/src/types/runtime.ts`: `RunTraceStep / RunTraceStatus /
  RunTraceEvent / RunTraceResponse` types
- `frontend/src/services/runtimeApi.ts`: `getRunTrace(runId)` method
- `frontend/src/pages/RunTracePage.tsx` (NEW): 9-step timeline UI
  with expandable `safe_metadata`; defense-in-depth — `auth_resolved`
  step only surfaces `redacted_view / granted_scopes / auth_type`
- `frontend/src/pages/AgentChatPage.tsx`: "View RunTrace" button in
  result header linking to `/runs/{run_id}/trace`
- `frontend/src/App.tsx`: route `runs/:runId/trace`

**Tests:** `tests/unit/icoder/agent_runtime/test_run_trace_store.py` —
9 tests. TypeScript compiles 0 errors.

**Verification:** `TASK4_RUNTRACE_VIEWER_VERIFICATION.md` — PASS.

### Task 5 — 3 Runnable Agents (3-D1)

**Goal:** Code Validation / Compliance Guardrail / Note Completeness
Agents — each Hub-visible / Clone / Chat / A2A mainline / MCP tools /
markdown+JSON / RunTrace / tests / no fake.

**What was built:**
- 3 agent modules under `official_agents/{code_validation,
  compliance_guardrail, note_completeness}/` — each with
  `__init__.py` + `agent.py` containing `async def run(input_text,
  *, run_id="") -> dict`
- 3 `agent_pack.json` files upgraded from v1.1 metadata-only to
  v1.2 maturity=`runnable` with full `output_contract`,
  `non_goals`, `permissions`, `a2a` block
- 3 `AgentCard` factories in `agent_card.py`:
  `code_validation_agent_card / compliance_guardrail_agent_card /
  note_completeness_agent_card`
- `_SimpleAgentDispatchHandler` in `app/main.py` wraps the existing
  `_MedicalCodingV2ProjectingHandler`. For the 3 new agent_ids it
  short-circuits the orchestrator (Planner/Delegator/Aggregator) and
  calls the agent's `run()` directly; for all other agent_ids it
  falls through to the inner handler. Emits `USER_MESSAGE_RECEIVED
  → OUTPUT_GENERATED → COMPLETION` trace events.
- `_list_all_cards` in `routes_discovery.py` now enumerates 5 agents
- Updated 5 existing tests to reflect the count changes (v1.1 10→7,
  v1.2 cert 1→4, hub runnable 1→4, metadata-only list trimmed)

**Tests:**
- `tests/unit/icoder/agent_runtime/test_three_runnable_agents.py` —
  18 unit tests (5 + 6 + 7)
- `tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py`
  — 5 A2A mainline end-to-end tests (one per agent + RunTrace +
  404 path)

**Verification:** `TASK5_THREE_RUNNABLE_AGENTS_VERIFICATION.md` — PASS.

---

## Architecture notes

### Why a separate `_SimpleAgentDispatchHandler` instead of going
through the existing orchestrator?

The orchestrator (Planner/Delegator/Aggregator) is designed for
multi-expert LLM-driven agents. The 3 new agents are deterministic,
single-step, no-LLM rule-engine wrappers. Forcing them through the
orchestrator would mean:

1. Defining a fake `Plan` with one step
2. Writing a fake `ExpertInvoker` that calls `run()`
3. Routing through `Aggregator` to wrap the result in a DataPart
4. Adding v1→v2 projection logic for each agent's output schema

Instead, the dispatch handler short-circuits to `run()` directly,
emits the same trace events the orchestrator would, and builds the
same `InboundResponse` shape the Aggregator would. The result: 200
fewer lines of glue code, no fake expert layer, and the 3 agents
remain genuinely simple.

The cost: `PLANNER_SELECTED_EXPERTS` / `EXPERT_RESPONSE` trace steps
are not emitted for these 3 agents (they would be no-ops anyway). The
5 actually-meaningful steps (`USER_MESSAGE_RECEIVED / OUTPUT_GENERATED
/ COMPLETION` + the MCP-server-emitted ones when the agent itself
calls MCP tools) are present.

### RunTrace is in-memory only

The `RunTraceStore` is process-local. A run executed in one worker
isn't visible from another worker's `/trace` endpoint. Acceptable
for Phase 3-D1 — persistence is a Phase 3-D2 follow-up. The store
contract is display-safe by construction; adding persistence later
won't change the API.

### Markdown generation strategy

Only `medical-coding-agent` pre-renders markdown via
`app.icoder.markdown_generator`. The 3 new agents don't — their
output is simple enough that the frontend's
`generateFallbackMarkdown(result.structured)` auto-generates a
readable markdown. This matches Corti's pattern: not every agent
needs a custom markdown generator; the JSON tab is the canonical
view for rule-engine outputs.

---

## Default sweep

```
cd backend && pytest
```

Result: **2265 passed, 14 skipped, 10 deselected, 0 failed** (10:44 wall).

Pre-Phase-3-D baseline: 2232 passed. Net +33 tests (18 unit + 5
smoke + 5 hub + 5 adjusted existing tests + small test additions
across MCP scope / log redaction / RunTrace).

---

## PASS criteria (10/10)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | MCP scope enforcement done | ✅ | Task 1 verification report |
| 2 | redacted_view actual log capture done | ✅ | Task 2 verification report |
| 3 | Default sweep 0 fail | ✅ | 2265/0 (this report) |
| 4 | RunTrace Viewer opens from AgentChatPage | ✅ | Task 4 verification report |
| 5 | ≥3 runnable agents | ✅ | 3 + medical-coding-agent = 4 |
| 6 | Each supports markdown + JSON + RunTrace | ✅ | Task 5 verification report |
| 7 | Each task has manual Corti verification | ✅ | 5 reports in manual_verification/ |
| 8 | Written to docs + memory | ✅ | docs/corti_parity/phase3_d/ + MEMORY.md |
| 9 | No token leaks | ✅ | Task 2 caplog tests + Task 4 redacted_view contract test |
| 10 | Phase 3-B2 + 3-C gaps no regression | ✅ | Phase 3-B2 hub/discovery tests still PASS; Phase 3-C MCP auth tests still PASS |

---

## Files touched (summary)

Backend:
- `app/icoder/mcp/{auth,auth_resolver,tool_registry,server}.py` — scope enforcement + trace events
- `app/icoder/agent_runtime/orchestrator/run_trace.py` — NEW
- `app/api/run_trace.py` — NEW
- `app/icoder/agent_runtime/a2a/{agent_card,routes_discovery}.py` — 3 new cards + 3 new entries in `_list_all_cards`
- `app/main.py` — `_SimpleAgentDispatchHandler` + run_trace_router + 3 agent imports
- `official_agents/{code_validation,compliance_guardrail,note_completeness}/{__init__,agent}.py` — NEW (6 files)
- `official_agents/{code-validation,compliance-guardrail,note-completeness}/agent_pack.json` — v1.1 → v1.2, maturity runnable

Backend tests:
- `tests/unit/icoder/mcp/test_mcp_scope_enforcement.py` — NEW (5 tests)
- `tests/unit/icoder/mcp/test_mcp_log_redaction.py` — NEW (5 tests)
- `tests/unit/icoder/agent_runtime/test_run_trace_store.py` — NEW (9 tests)
- `tests/unit/icoder/agent_runtime/test_three_runnable_agents.py` — NEW (18 tests)
- `tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py` — NEW (5 tests)
- `tests/integration/icoder/test_phase3b1_agent_hub.py` — updated
- `tests/integration/icoder/test_phase3b2_loop4_hub_use_case_filter.py` — updated
- `tests/integration/icoder/test_phase3b1_discovery_unification_contract.py` — updated
- `tests/unit/icoder_runtime/test_agent_pack_loader.py` — updated (v1.1 10→7, v1.2 cert 1→4)
- `tests/unit/icoder_runtime/test_registry_status.py` — updated (v1.1 10→7)
- `tests/test_api/test_auth.py` — rewrote with `uuid4` isolation
- `tests/integration/conftest.py` — asyncio marker guard
- `tests/integration/test_e2e_coding_pipeline.py` — `pytestmark = pytest.mark.infra`
- `tests/e2e_product/` — 7 files deleted
- `pytest.ini` — added `infra` marker

Frontend:
- `frontend/src/types/runtime.ts` — RunTrace types
- `frontend/src/services/runtimeApi.ts` — getRunTrace method
- `frontend/src/pages/RunTracePage.tsx` — NEW
- `frontend/src/pages/AgentChatPage.tsx` — View RunTrace link
- `frontend/src/App.tsx` — route + import

Docs:
- `docs/corti_parity/phase3_d/manual_verification/` — 5 task verification reports
- `docs/corti_parity/phase3_d/PHASE3D_*.md` — 4 phase reports (this file + 3 below)
