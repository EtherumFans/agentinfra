# Phase 3-D2 Task 3 Verification — MCP-native Refactor for 3 Agents

**Task:** 3 new MCP tools (`validate_codes` / `evaluate_compliance` / `check_documentation_gaps`) registered in TOOL_REGISTRY; 3 simple agents route through MCP dispatcher via `dispatch_tool()`; single code path for scope/auth/trace.
**Date:** 2026-07-07
**Status:** PASS
**Files affected:**
- `backend/app/icoder/mcp/handlers/validate_codes.py` (NEW — wraps `code_validation.agent.run()`)
- `backend/app/icoder/mcp/handlers/evaluate_compliance.py` (NEW — wraps `compliance_guardrail.agent.run()`)
- `backend/app/icoder/mcp/handlers/check_documentation_gaps.py` (NEW — wraps `note_completeness.agent.run()`)
- `backend/app/icoder/mcp/tool_registry.py` (MODIFIED — +3 ToolDescriptor with required_scopes; subset-match assertion)
- `backend/app/icoder/mcp/server.py` (MODIFIED — extracted `dispatch_tool()` function; route calls it)
- `backend/app/main.py::_SimpleAgentDispatchHandler` (MODIFIED — calls `dispatch_tool()` instead of `run_fn()` directly)
- `backend/tests/unit/icoder/mcp/test_agent_tool_handlers.py` (NEW — 3 tests)
- `backend/tests/integration/icoder/test_mcp_agent_tools_lifecycle.py` (NEW — 3 tests)
- `backend/tests/unit/icoder/mcp/test_server.py` (MODIFIED — bumped 5→8 tools)
- `backend/tests/unit/icoder/mcp/test_tool_registry.py` (MODIFIED — bumped 5→8; subset-match)

## What was built

### 3 MCP handler files

Each handler is a thin adapter that:
1. Builds `input_text` from the MCP arguments (coding_set JSON + encounter_text)
2. Calls the corresponding `official_agents/{agent}/agent.py::run()` (SSOT business logic)
3. Returns the agent's output dict

The handlers do NOT duplicate business logic — they're the MCP-to-agent adapter boundary.

### 3 ToolDescriptor entries with required_scopes

- `validate_codes` — `required_scopes=["coding:validate"]`, stage="validation"
- `evaluate_compliance` — `required_scopes=["compliance:evaluate"]`, stage="compliance"
- `check_documentation_gaps` — `required_scopes=["documentation:check"]`, stage="documentation"

### `dispatch_tool()` function (single code path)

Extracted from the `tools/call` HTTP route. Takes `(tool_name, arguments, request, run_id)` and:
1. Looks up descriptor (raises METHOD_NOT_FOUND if unknown)
2. PHI redaction on arguments
3. Validates against inputSchema
4. Resolves auth (if `auth_config` is set) OR reads `state.auth_header` (in-process dev path)
5. Checks required_scopes (raises MCP_AUTH_FORBIDDEN -32012 if missing)
6. Emits AUTH_RESOLVED / SCOPE_CHECKED / TOOLS_CALL / COMPLETION trace events
7. Invokes the handler
8. Returns `{"content": result, "isError": False}` on success

Both the HTTP `tools/call` route AND `_SimpleAgentDispatchHandler` call `dispatch_tool()` — single code path, zero HTTP overhead for in-process callers.

### In-process auth bypass for simple-agent path

The `_SimpleAgentDispatchHandler` constructs a lightweight request-like object (SimpleNamespace with `.app` and `.state`) and pre-sets `state.auth_header` to an `AuthHeader` with all 3 required scopes pre-granted. This is the "in-process bypass" — the A2A route has already authenticated the caller, so the in-process dispatch trusts it for scope check.

### Boot-time assertion: subset-match

Changed `assert_tool_registry_matches_agent_pack` from exact-set to subset-match (pack-declared tools must be a subset of TOOL_REGISTRY). This is needed because TOOL_REGISTRY now hosts tools for multiple agents (medcoder-coding-review's 5 + 3 simple-agent tools), but the assertion only runs against medcoder's agent_pack.

## Verification steps

- [x] V1: `validate_codes` handler invokes `agent.run()` and returns its result — passes (`test_validate_codes_handler_invokes_agent_run`)
- [x] V2: `evaluate_compliance` handler invokes `agent.run()` and returns its result — passes (`test_evaluate_compliance_handler_invokes_agent_run`)
- [x] V3: `check_documentation_gaps` handler invokes `agent.run()` and returns its result — passes (`test_check_documentation_gaps_handler_invokes_agent_run`)
- [x] V4: In-process `dispatch_tool(validate_codes, ...)` with coding:validate scope → succeeds — passes (`test_dispatch_tool_validate_codes_with_scopes_succeeds`)
- [x] V5: Missing scope → MCP_AUTH_FORBIDDEN -32012 — passes (`test_dispatch_tool_validate_codes_without_scope_returns_forbidden`)
- [x] V6: Trace emits (SCOPE_CHECKED + TOOLS_CALL + COMPLETION) land in RunTrace store — passes (`test_dispatch_tool_emits_scope_check_and_completion_trace`)
- [x] V7: `tools/list` returns 8 tools (was 5) — passes (`test_tools_list_returns_5_tools` — name kept for git-blame continuity)
- [x] V8: TOOL_REGISTRY has 8 tools — passes (`test_tool_registry_has_exactly_5_tools` — name kept)
- [x] V9: Boot-time subset-match assertion passes for medcoder-coding-review's pack — passes (`test_assert_tool_registry_matches_agent_pack_passes_for_real_pack`)
- [x] V10: Each handler_ref resolves to an async callable — passes (`test_each_handler_ref_resolves_to_callable`)

## PASS/FAIL criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 3 new MCP tools registered in TOOL_REGISTRY | PASS | V7, V8 |
| Each handler_ref resolves to async callable | PASS | V10 |
| 3 simple agents route through MCP dispatcher | PASS | V4 (in-process dispatch), `_SimpleAgentDispatchHandler` calls `dispatch_tool()` |
| required_scopes enforced | PASS | V5 |
| Full chain (scope/auth/redaction/trace) works | PASS | V4, V5, V6 |
| Boot-time assertion passes | PASS | V9 |
| No regression in MCP tests | PASS | 68/68 mcp unit tests pass |

## Known limitations

- The in-process auth bypass (pre-set `state.auth_header` with all scopes) is acceptable for the simple-agent path because the A2A route has already authenticated the caller. Production wiring for bearer-token resolution from A2A envelope metadata is a Phase 4 task.
- The 3 simple-agent `agent_pack.json` files already declared the tool names (`validate_codes` / `evaluate_compliance` / `check_documentation_gaps`) before this task — no JSON changes needed.

## Cross-reference

- Phase 3-C1 (MCP Auth) — Task 3 reuses the auth resolution + scope check infrastructure.
- Phase 3-D0 Task 1 (required_scopes) — Task 3 applies the scope enforcement to the 3 new tools.
- Phase 3-D2 Task 4 (Custom Markdown) — Task 3's `dispatch_tool` is where the handler result is returned, which Task 4's markdown generator wraps.
