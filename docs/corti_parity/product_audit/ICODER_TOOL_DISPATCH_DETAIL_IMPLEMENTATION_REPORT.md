# Phase 3-D2.5 Part A — Tool Dispatch Detail Implementation Report

**Date:** 2026-07-07
**Status:** DONE — 9/9 tests PASS, 0 regressions
**Component:** `backend/app/icoder/mcp/server.py` + `frontend/src/pages/RunTracePage.tsx`

## 1. Goal

Close the "Tool Dispatch Detail" gap surfaced in Phase 3-D2 review: the
RunTrace viewer showed the 9-step timeline + raw `safe_metadata`, but
provided no concentrated view of a single MCP tool dispatch lifecycle.
Reviewers had to mentally reconstruct 4 separate trace events
(AUTH_RESOLVED + SCOPE_CHECKED + TOOLS_CALL + COMPLETION) to understand
why a tool call failed.

## 2. Spec — 15-field `dispatch_detail` dict

Per the docx contract, every `dispatch_tool()` invocation must accumulate
a `dispatch_detail` dict with exactly 15 display-safe fields, emitted
under `TOOLS_CALL.safe_metadata.dispatch_detail`:

| # | Field | Type | Source |
|---|-------|------|--------|
| 1 | `tool_name` | str | param |
| 2 | `dispatch_mode` | "http" \| "in_process" | `isinstance(request, Request)` |
| 3 | `handler_ref` | str \| None | descriptor.handler_ref |
| 4 | `input_schema_validation` | "passed" \| "failed" \| "skipped" | pydantic result |
| 5 | `phi_redaction` | "passed" \| "skipped" | redactor result |
| 6 | `auth_type` | str \| None | descriptor.auth_config.type |
| 7 | `auth_resolved` | bool | resolve_mcp_auth success |
| 8 | `required_scopes` | list[str] | descriptor.required_scopes |
| 9 | `granted_scopes` | list[str] | auth_header.granted_scopes |
| 10 | `scope_check` | "passed" \| "failed" \| "skipped" | _check_scopes result |
| 11 | `handler_status` | "ok" \| "failed" | handler invoke result |
| 12 | `duration_ms` | float | `(time.time() - t_dispatch_start) * 1000` |
| 13 | `result_shape` | str \| None | `f"{type}({{{keys}}}, size={N}B)"` |
| 14 | `error_code` | int \| None | MCPError.code on failure |
| 15 | `error_stage` | "schema" \| "phi" \| "auth" \| "scope" \| "handler_resolve" \| "handler_invoke" \| None | first failing stage |

**Display-safe invariant:** no raw token, Authorization header,
client_secret, secret_ref, or PHI. The existing
`_redact_safe_metadata` sweep still runs before DB persist as
defense-in-depth; the frontend additionally re-renders `—` for any
null field so the row count is always 15.

## 3. Backend implementation — `dispatch_tool()`

8 surgical Edits to `backend/app/icoder/mcp/server.py:287+`:

1. **Initialize accumulator** at function top (line 334):
   ```python
   dispatch_detail: dict[str, Any] = {
       "tool_name": tool_name,
       "dispatch_mode": "http" if isinstance(request, Request) else "in_process",
       ...
   }
   t_dispatch_start = time.time()
   ```
2. **Schema validation** — set `input_schema_validation` to "passed" / "failed" / "skipped" based on pydantic result.
3. **PHI redaction** — set `phi_redaction` to "passed" / "skipped".
4. **Auth resolution success** — populate `auth_type`, `auth_resolved=True`, `required_scopes`, `granted_scopes`.
5. **Auth resolution failure** (MCPAuthError) — set `auth_resolved=False`, `error_stage="auth"`, `error_code=e.code`, emit AUTH_RESOLVED=FAILED + TOOLS_CALL=FAILED + dispatch_detail, then re-raise.
6. **Scope check failure** — set `scope_check="failed"`, `error_stage="scope"`, `error_code=MCP_AUTH_FORBIDDEN (-32012)`, emit TOOLS_CALL=FAILED + dispatch_detail, raise MCPAuthError.
7. **Handler resolve failure** — set `handler_status="failed"`, `error_stage="handler_resolve"`, `error_code=INTERNAL_ERROR`.
8. **Handler invoke success/failure** — set `handler_status`, `duration_ms`, `result_shape` (for success) or `error_stage="handler_invoke"`, `error_code` (for failure). Moved TOOLS_CALL OK emit from pre-handler to post-handler so the dispatch_detail reflects the actual handler outcome.

`result_shape` format: `f"{result_type}({{{keys_str}}}, size={result_size}B)"`
where `keys_str = ", ".join(result_keys[:8])` and `result_size` is the
UTF-8 encoded JSON byte length. Example:
`dict({review_conclusion, issues_found, ...}, size=824B)`.

## 4. Frontend implementation — `ToolDispatchDetail.tsx`

New exported component in `frontend/src/pages/RunTracePage.tsx`:

- 15-row grid layout, label-value pairs.
- Default collapsed; expands on header click.
- **Auto-expand on `handler_status === "failed"`** so the failure stage is visible immediately without manual click.
- Null fields render as `—` so row count is always 15.
- Scope diff row shows `required_scopes` vs `granted_scopes` (delta visualization).
- SECRET_KEY_RE defense-in-depth regex applied to all string values before render.

Embedded in `renderDispatcherDetail` for `tools_call` step when
`meta.dispatch_detail` exists:

```tsx
const dispatchDetail = meta.dispatch_detail as DispatchDetail | undefined;
if (dispatchDetail && typeof dispatchDetail === 'object') {
  rows.push(<ToolDispatchDetail key="tdd" detail={dispatchDetail} t={t} />);
}
```

## 5. i18n keys

9 new keys added to `frontend/src/i18n/locales.ts` (zh + en sections +
type definition):

- `runTraceToolDispatchDetail` — "Tool Dispatch Detail" / "工具调度详情"
- `runTraceDispatchMode` — "Dispatch Mode" / "调度模式"
- `runTraceSchemaValidation` — "Schema Validation" / "输入校验"
- `runTracePhiRedaction` — "PHI Redaction" / "PHI 脱敏"
- `runTraceScopeCheck` — "Scope Check" / "范围检查"
- `runTraceHandlerStatus` — "Handler Status" / "处理器状态"
- `runTraceResultShape` — "Result Shape" / "结果形状"
- `runTraceErrorStage` — "Error Stage" / "错误阶段"
- `runTraceDurationMs` — "Duration" / "耗时"

## 6. Tests — 9/9 PASS

### 6.1 Backend tests — `backend/tests/unit/icoder/mcp/test_dispatch_detail.py` (6 tests)

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_dispatch_detail_success_emits_all_15_fields` | all 15 fields present, `handler_status=ok`, `error_code=None`, `error_stage=None` |
| 2 | `test_dispatch_detail_schema_validation_failure` | `input_schema_validation=failed`, `error_stage=schema`, `error_code=INVALID_PARAMS (-32602)` |
| 3 | `test_dispatch_detail_scope_failure` | `scope_check=failed`, `error_stage=scope`, `error_code=MCP_AUTH_FORBIDDEN (-32012)` |
| 4 | `test_dispatch_detail_handler_raises` | `handler_status=failed`, `error_stage=handler_invoke`, `error_code=INTERNAL_ERROR (-32603)` |
| 5 | `test_dispatch_detail_no_token_or_secret_or_phi` | recursive sweep: no token/secret/Authorization/PHI in detail_json; "患者" / "呼吸困难" not present |
| 6 | `test_get_run_trace_returns_dispatch_detail` | GET `/api/runtime/runs/{run_id}/trace` returns `dispatch_detail` under `tools_call` step |

### 6.2 Frontend tests — `frontend/src/pages/__tests__/RunTracePage.dispatch_detail.test.tsx` (3 tests)

| # | Test | Verifies |
|---|------|----------|
| 1 | `renders collapsed by default for successful dispatch` | header label visible, body rows NOT visible (validate_codes value absent) |
| 2 | `expands on click and shows all 15 fields` | click header → body visible; all 15 values render (validate_codes, in_process, passed, skipped, in-process, 12.3ms, —) |
| 3 | `auto-expands when handler_status=failed` | body visible without click; `handler_invoke` + `-32603` visible |

**jsdom workaround:** the store import chain calls
`window.matchMedia` at module load. Stubbed in `beforeAll` before
dynamic `import('../RunTracePage')` (Vitest hoists static imports
above `beforeAll`, so dynamic import is required).

## 7. Regression — 0 failures

- Backend Phase 3-D2 core regression: 66/66 PASS
- Frontend tsc: 0 errors
- Frontend vitest: 9/9 PASS (3 new + 6 existing RunTracePage tests)
- No changes to agent_pack.json, agent names, or A2A protocol surface

## 8. Browser walkthrough — verified

Live dev server walkthrough confirmed (see
`ICODER_BROWSER_MANUAL_VERIFICATION_REPORT.md`):

- `runtrace_simple_agent.png` — compliance-guardrail run trace shows
  `tools_call` step with "dispatcher detail" section.
- `tool_dispatch_detail_success.png` — expanded Tool Dispatch Detail
  shows all 15 fields for `evaluate_compliance` dispatch:
  - `tool_name: evaluate_compliance`
  - `dispatch_mode: in_process`
  - `handler_ref: app.icoder.mcp.handlers.evaluate_compliance:handle`
  - `input_schema_validation: passed`
  - `phi_redaction: passed`
  - `auth_type: in-process`
  - `auth_resolved: true`
  - `required_scopes: [compliance:evaluate]`
  - `granted_scopes: [coding:validate, compliance:evaluate, documentation:check]`
  - `scope_check: passed`
  - `handler_status: ok`
  - `duration_ms: 18.0ms`
  - `result_shape: dict({review_conclusion, issues_found, manual_review_required, drg_suggestion, compliance_checks, rule_set, fired_rules, trace_refs}, size=824B)`
  - `error_stage: —`
  - `mcp_error_code: —`

## 9. Files changed

| File | Lines | Type |
|------|-------|------|
| `backend/app/icoder/mcp/server.py` | +85 / -12 | MODIFIED (8 Edits to `dispatch_tool`) |
| `frontend/src/pages/RunTracePage.tsx` | +120 / -3 | MODIFIED (new `ToolDispatchDetail` component + embed) |
| `frontend/src/i18n/locales.ts` | +36 / -0 | MODIFIED (9 new i18n keys × zh + en + types) |
| `backend/tests/unit/icoder/mcp/test_dispatch_detail.py` | +220 / -0 | NEW (6 backend tests) |
| `frontend/src/pages/__tests__/RunTracePage.dispatch_detail.test.tsx` | +127 / -0 | NEW (3 frontend tests) |

## 10. Status

**DONE** — All 15 fields implemented, 9/9 tests pass, 0 regressions,
browser walkthrough verified the success case live. The forbidden case
(scope_check=failed) is covered by backend test #3 at the unit level;
the browser screenshot was substituted with the success case because
triggering a real scope failure from the UI requires a crafted OAuth
token with limited scopes (not exposed in the dev environment).
