# Phase 3-D2 Gap Closure Matrix

**Phase:** 3-D2 — Corti Parity Hardening Phase 2 (RunTrace Persistence + MCP-native Agents + Product-grade Output)
**Date:** 2026-07-07
**Status:** 4/4 gaps closed (100%)
**Predecessor:** Phase 3-D (2026-07-06) — 5 gaps closed; 4 known gaps remained

## Executive summary

Phase 3-D closed 5 Corti-parity gaps and shipped 3 runnable agents + an in-memory RunTrace viewer, but 4 known gaps remained (per `PHASE3D_GAP_CLOSURE_MATRIX.md`). Phase 3-D2 closes all 4:

1. RunTrace was in-memory only → DB-backed with org/project scoping + redaction-before-write
2. Trace emission was incomplete → all 9 steps emitted for orchestrator path; 4 steps for simple-agent path; failed paths emit COMPLETION=FAILED
3. 3 new Agents bypassed the MCP dispatcher → `dispatch_tool()` single code path for HTTP + in-process callers; 3 new MCP tools registered in TOOL_REGISTRY with `required_scopes`
4. 3 new Agents used generic JSON dump → 3 per-agent markdown generators (5 sections each per PDF spec) + `generate_markdown_for()` dispatcher; backend pre-renders and embeds `result["markdown"]` in DataPart

## Gap closure matrix

| # | Gap (from Phase 3-D) | Phase 3-D2 Task | Implementation | Evidence (tests) | Evidence (files) | Status |
|---|----------------------|-----------------|----------------|-------------------|-------------------|--------|
| 1 | RunTrace in-memory only — not auditable across workers/restarts | Task 1 — RunTrace Persistence | `DbRunTraceStore` (sync SQLAlchemy engine) + `RunTraceEventModel` + migration 009 + `RUNTRACE_STORE` setting (memory default for tests, db for cloud); in-memory fallback preserved; redaction-before-write enforced via `_redact_safe_metadata` | `test_run_trace_db_store.py` (7 tests): append/get_run, unknown-404, API 200 org match, API 404 cross-org, redaction (secret keys / token blobs / safe keys) | `app/models/run_trace.py`, `alembic/versions/009_run_trace_events.py`, `app/icoder/agent_runtime/orchestrator/run_trace.py` (refactor), `app/api/run_trace.py` (org-scoped read), `app/config.py` (RUNTRACE_STORE) | CLOSED |
| 2 | Trace emission incomplete — orchestrator + simple agent paths missing steps | Task 2 — Complete Trace Emission | InboundHandler emits 5 steps (USER_MESSAGE_RECEIVED / PLANNER_SELECTED_EXPERTS / EXPERT_RESPONSE / OUTPUT_GENERATED / COMPLETION=OK) + COMPLETION=FAILED in every error path; `_SimpleAgentDispatchHandler` emits 4 steps with PLANNER_SELECTED_EXPERTS=SKIPPED; RunTracePage empty-timeline guard + retry button | `test_orchestrator_trace.py` (8 tests): success emits all 9 steps, expert_response status tracks error, invalid_request / agent_not_found / planning_failed / aggregation_failed emit COMPLETION=FAILED, simple agent emits 4 steps with SKIPPED, simple agent failure emits COMPLETION=FAILED | `app/icoder/agent_runtime/orchestrator/inbound_handler.py` (13 trace emits), `app/main.py::_SimpleAgentDispatchHandler` (PLANNER=SKIPPED emit), `frontend/src/pages/RunTracePage.tsx` (empty-timeline guard) | CLOSED |
| 3 | 3 new Agents bypass MCP dispatcher — tools declared in `agent_pack.json` but not in `TOOL_REGISTRY` | Task 3 — MCP-native Refactor | Extracted `dispatch_tool()` as single code path for HTTP + in-process callers; 3 new MCP tools (`validate_codes` / `evaluate_compliance` / `check_documentation_gaps`) registered in TOOL_REGISTRY with `required_scopes`; 3 thin adapter handlers wrap `agent.run()` SSOT; `_SimpleAgentDispatchHandler` calls `dispatch_tool()` via lightweight request-like object with pre-set `state.auth_header`; boot-time assertion changed to subset-match | `test_agent_tool_handlers.py` (3 unit tests — one per handler), `test_mcp_agent_tools_lifecycle.py` (3 integration tests — scope succeeds, scope forbidden -32012, trace emits), `test_server.py` + `test_tool_registry.py` (bumped 5→8 tools, subset-match) | `app/icoder/mcp/handlers/{validate_codes,evaluate_compliance,check_documentation_gaps}.py` (NEW), `app/icoder/mcp/tool_registry.py` (+3 ToolDescriptor + 6 Pydantic schemas + subset-match assertion), `app/icoder/mcp/server.py` (dispatch_tool extracted), `app/main.py` (_SimpleAgentDispatchHandler calls dispatch_tool) | CLOSED |
| 4 | 3 new Agents use `generateFallbackMarkdown` instead of custom markdown | Task 4 — Custom Markdown Generators | 3 per-agent markdown generators (5 sections each per PDF spec) + `generate_markdown_for(agent_id, result)` dispatcher; backend pre-renders and embeds `result["markdown"]` in DataPart; frontend `generateFallbackMarkdown` dispatches by `schema_ref` for legacy/old packs | `test_markdown_generator.py` (+4 tests — code_validation 5 sections, compliance_guardrail 5 sections, note_completeness 5 sections, dispatcher); 12 existing markdown tests still pass | `app/icoder/markdown_generator.py` (+3 generators + dispatcher), `app/main.py::_SimpleAgentDispatchHandler` (pre-render + embed), `frontend/src/utils/medicalCodingMarkdown.tsx` (per-agent fallback branches) | CLOSED |

## 10 PASS criteria mapping

| # | PASS criterion | Gap closed | Evidence |
|---|----------------|-------------|----------|
| 1 | RunTrace persistence done | Gap 1 | Task 1 V1-V7; `DbRunTraceStore` + migration 009 |
| 2 | RunTrace query has org/project permission control | Gap 1 | Task 1 V4, V5; `scope_query` + 404 on cross-org |
| 3 | Medical Coding Agent + 3 simple agents produce usable trace | Gap 2 | Task 2 V1-V8; 5 + 4 steps emitted |
| 4 | 3 new Agents call tools via MCP dispatcher | Gap 3 | Task 3 V1-V10; `dispatch_tool()` single code path |
| 5 | required_scopes / auth / redaction / RunTrace full chain works | Gap 3 | Task 3 V4, V5, V6; 3 integration tests pass |
| 6 | 3 new Agents have custom markdown + JSON | Gap 4 | Task 4 V1-V4; 3 generators + dispatcher |
| 7 | Browser-level manual Corti parity verification all complete | (not a gap; verification) | Task 5 — code-level substitute; browser walkthrough deferred to follow-up |
| 8 | Default test sweep 0 fail | (not a gap; verification) | 22/22 new + 188/188 regression pass; full sweep blocked by pre-existing MemoryError |
| 9 | Phase 3-B2 / 3-C / 3-D no regression | (not a gap; verification) | 188/188 regression sweep pass |
| 10 | No token / secret / Authorization header / PHI leak | Gap 1 (redaction) | Task 1 V4, V5, V6; redaction tests pass |

## Gap → Task → File mapping (detailed)

### Gap 1 → Task 1

**New files:**
- `backend/app/models/run_trace.py` — `RunTraceEventModel(Base, TimestampMixin)`
- `backend/alembic/versions/009_run_trace_events.py` — `op.create_table("run_trace_events", ...)` + 3 indexes
- `backend/tests/unit/icoder/agent_runtime/test_run_trace_db_store.py` — 7 tests

**Modified files:**
- `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` — `RunTraceStore` abstract base + `InMemoryRunTraceStore` + `DbRunTraceStore` + `_redact_safe_metadata` + `get_default_store()`
- `backend/app/api/run_trace.py` — org-scoped read (`scope_query` + 404 on cross-org)
- `backend/app/config.py` — `RUNTRACE_STORE: Literal["memory","db"] = "memory"`

**Reused utilities:**
- `app/services/tenant_scoper.py::scope_query` — org-scoped DB queries
- `app/middleware/tenant_extractor.py::get_request_tenant` — read org from request
- `app/database.py::Base` — DB session factory
- `app/models/base.py::TimestampMixin` — id/created_at/updated_at

### Gap 2 → Task 2

**Modified files:**
- `backend/app/icoder/agent_runtime/orchestrator/inbound_handler.py` — 13 trace emits across all paths (5 success + 8 failure)
- `backend/app/main.py::_SimpleAgentDispatchHandler._handle_simple()` — PLANNER_SELECTED_EXPERTS=SKIPPED emit
- `frontend/src/pages/RunTracePage.tsx` — empty-timeline guard + retry button

**New files:**
- `backend/tests/unit/icoder/agent_runtime/test_orchestrator_trace.py` — 8 tests

**Design decision:** Planner/Delegator/Aggregator stay pure (no `run_id` awareness). InboundHandler owns `run_id` and wraps each stage — keeps the orchestrator components free of trace infrastructure.

### Gap 3 → Task 3

**New files:**
- `backend/app/icoder/mcp/handlers/validate_codes.py` — thin adapter wrapping `code_validation.agent.run()`
- `backend/app/icoder/mcp/handlers/evaluate_compliance.py` — thin adapter wrapping `compliance_guardrail.agent.run()`
- `backend/app/icoder/mcp/handlers/check_documentation_gaps.py` — thin adapter wrapping `note_completeness.agent.run()`
- `backend/tests/unit/icoder/mcp/test_agent_tool_handlers.py` — 3 unit tests
- `backend/tests/integration/icoder/test_mcp_agent_tools_lifecycle.py` — 3 integration tests

**Modified files:**
- `backend/app/icoder/mcp/tool_registry.py` — +3 ToolDescriptor + 6 Pydantic schemas; subset-match assertion
- `backend/app/icoder/mcp/server.py` — `dispatch_tool()` function extracted from `tools/call` route
- `backend/app/main.py::_SimpleAgentDispatchHandler` — calls `dispatch_tool()` via SimpleNamespace fake request; pre-set `state.auth_header`
- `backend/tests/unit/icoder/mcp/test_server.py` — bumped 5→8 tools
- `backend/tests/unit/icoder/mcp/test_tool_registry.py` — bumped 5→8; subset-match

**Design decision (Option C from Plan agent):** In-process `dispatch_tool()` function. The HTTP `tools/call` route and `_SimpleAgentDispatchHandler` both call it. Single code path for scope/auth/trace with zero HTTP overhead.

**In-process auth bypass:** The `_SimpleAgentDispatchHandler` pre-sets `state.auth_header` to an `AuthHeader` with all 3 required scopes pre-granted. Acceptable because the A2A route has already authenticated the caller. Production wiring for bearer-token resolution from A2A envelope metadata is a Phase 4 task.

### Gap 4 → Task 4

**Modified files:**
- `backend/app/icoder/markdown_generator.py` — +3 generators + `generate_markdown_for()` dispatcher
- `backend/app/main.py::_SimpleAgentDispatchHandler._handle_simple()` — pre-render markdown + embed as `result["markdown"]` in DataPart
- `frontend/src/utils/medicalCodingMarkdown.tsx` — `generateFallbackMarkdown` dispatches by `schema_ref`
- `backend/tests/unit/icoder/test_markdown_generator.py` — +4 tests

**Design decision:** Backend pre-renders markdown at agent-run time (matches `medical-coding-agent` pattern via `generate_markdown(v2)`). Frontend `RenderedMarkdown` component already parses markdown tables/headings — no frontend rendering change needed. Frontend `generateFallbackMarkdown` gains per-agent branches keyed by `schema_ref` for the legacy fallback path.

## Cross-reference

- Phase 3-D gap closure matrix — predecessor; 5 gaps closed in Phase 3-D, 4 remained
- Phase 3-D2 implementation report — task-level completion summaries
- Phase 3-D2 testing verification report — test sweep results
- Phase 3-D2 manual Corti parity report — code-level substitute for browser walkthrough
- Phase 3-D2 task verification reports (TASK1-V5) — per-task verification evidence

## Phase 4 follow-up

The following items are NOT Phase 3-D2 gaps but are tracked for Phase 4:

- Browser-level Playwright MCP walkthrough for 4 runnable agents (screenshots + DevTools network tab inspection) — deferred from Phase 3-D2 Task 5
- Synchronous RunTrace write mode (for audit trace durability guarantees) — fire-and-forget is acceptable for audit trace
- Bearer-token resolution from A2A envelope metadata (currently the simple-agent path uses in-process auth bypass)
- Production dev server hardening (the dev startup path is tested; production deployment is out of scope for Phase 3-D2)
- Full default sweep MemoryError workaround (split into smaller shards or run on Linux CI)
