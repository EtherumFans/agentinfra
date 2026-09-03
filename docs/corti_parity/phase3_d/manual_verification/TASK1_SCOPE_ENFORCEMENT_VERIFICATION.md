# Phase 3-D Task 1 — Manual Corti Parity Verification

**Task**: Task 1 — MCP Scope Enforcement
**Date**: 2026-07-06
**Feature**: Per-tool `required_scopes` + dispatcher scope check + `MCP_AUTH_FORBIDDEN` on insufficient scope + `scope_check` log step (redacted_view only)
**Verifier**: Claude Code (simulated user via API client + caplog)

## Corti target behavior

Per `docs/reverse_engineering/corti/CORTI_API_CONTRACTS.md` + `CORTI_ICODER_GAP_MATRIX.md` gap 3.3:

- MCP 2025-03-26 spec §11.6 requires the server to enforce scopes declared by `ToolDescriptor` — a tool that requires `["coding:verify"]` must reject tokens that don't carry that scope.
- Corti's MCP server returns `MCP_AUTH_FORBIDDEN` (-32012, HTTP 403, retryable=False) when the resolved auth lacks a required scope.
- The error envelope carries `redacted_view` only — never the raw `token` / `client_secret` / `Authorization` header.
- Corti's trace viewer shows a `scope_check` step with `redacted_view` + required + granted scopes.

## iCoDer observed behavior

Verified via FastAPI TestClient (simulating the API client a browser-driven SPA would call):

### Operation 1 — `POST /mcp/v1/tools/list`

```bash
curl -X POST http://localhost:8000/mcp/v1/tools/list \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"r1","method":"tools/list"}'
```

**Observed**: every tool entry now carries `required_scopes: []` (default empty list, backwards compat). Bearer-auth tools surface `auth.scopes` (the scopes the bearer token grants). `secret_ref` is stripped. Raw token does not appear.

### Operation 2 — `POST /mcp/v1/tools/call` with scope satisfied

Patched `verify_code` to declare `required_scopes=["coding:verify"]` + bearer auth carrying `scopes=["read","coding:verify"]`:

```bash
curl -X POST http://localhost:8000/mcp/v1/tools/call \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"r2","method":"tools/call",
       "params":{"name":"verify_code","arguments":{"code":"I50.900"}}}'
```

**Observed**: `result.isError=false`, handler executed, `request.state.auth_header` carried `Bearer tok-bearer-xyz` + `granted_scopes=["read","coding:verify"]`.

### Operation 3 — `POST /mcp/v1/tools/call` with scope missing

Same tool, but bearer auth carrying `scopes=["read"]` only (missing `coding:verify`):

**Observed**:
```json
{"jsonrpc":"2.0","id":"r2","error":{
  "code":-32012,
  "message":"tool 'verify_code' requires scopes ['coding:verify', 'read'] but resolved auth carries ['read']",
  "data":{
    "tool_name":"verify_code",
    "required_scopes":["coding:verify","read"],
    "granted_scopes":["read"],
    "redacted_view":"Bearer ••••-xyz",
    "mcp_error_code":"MCP_AUTH_FORBIDDEN"
  }
}}
```

- Raw token `tok-bearer-xyz` does NOT appear in the envelope (verified via `json.dumps` scan).
- Handler never invoked (asserted in test).

### Operation 4 — `auth_config=None` + `required_scopes` non-empty → FORBIDDEN

Patched `verify_code` with `auth_config=None` + `required_scopes=["coding:verify"]`:

**Observed**: same `-32012` envelope, `granted_scopes=[]`, `redacted_view` omitted (no auth → no view).

### Operation 5 — `scope_check` log line (caplog capture)

**Observed** log entry:
```
INFO app.icoder.mcp.server: mcp scope_check: tool=verify_code
     required=['coding:verify'] granted=['coding:verify'] ok=True
     redacted_view='Bearer ••••-xyz'
```

- `Bearer ••••-xyz` present (safe).
- `tok-bearer-xyz` absent (verified via caplog record scan).
- `required` + `granted` + `ok` present (operator can trace).
- `Bearer tok-bearer-xyz` (full header) absent.

## Verdict: ✅ PASS

iCoDer's MCP scope enforcement matches Corti's target behavior:

| # | Corti target | iCoDer observed | Match |
|---|--------------|-----------------|-------|
| 1 | `required_scopes` on ToolDescriptor | `ToolDescriptor.required_scopes: list[str]` field added | ✅ |
| 2 | Dispatcher checks before handler dispatch | `_check_required_scopes` runs after auth resolution, before handler | ✅ |
| 3 | Insufficient scope → `-32012 MCP_AUTH_FORBIDDEN` | Test 2 asserts code=-32012, handler never called | ✅ |
| 4 | `auth_config=None` + required_scopes → FORBIDDEN | Test 3 asserts code=-32012, granted_scopes=[] | ✅ |
| 5 | `scope_check` log step with redacted_view, no raw token | Test 4 caplog: `Bearer ••••-xyz` present, `tok-bearer-xyz` absent | ✅ |
| 6 | `tools/list` advertises required_scopes | Test 5 asserts `required_scopes` field appears on every tool entry | ✅ |
| 7 | Raw token / Authorization header never in envelope or logs | All 5 tests scan `json.dumps` + caplog for `tok-bearer` — 0 matches | ✅ |

## Remaining delta

- **No browser-based verification run** (dev server not running during this task). The 5 unit tests exercise the full dispatcher path via `fastapi.testclient.TestClient`, which is API-equivalent to what a browser SPA would call. A live browser verification will be folded into Task 4 (RunTrace Viewer) which is the first task with a user-visible frontend surface.
- **Default 5 MCP tools don't declare required_scopes yet** — they have `auth_config=None` and `required_scopes=[]` (backwards compat). When a future ISV agent (e.g. Code Validation Agent in Task 5) needs scoped tools, it will declare `required_scopes` in its agent_pack.json tool entries.

## Screenshots

N/A — verification run via API client (no browser surface). caplog + JSON response payloads captured in `tests/unit/icoder/mcp/test_mcp_scope_enforcement.py`.

## Follow-up

- Task 5 runnable agents may declare `required_scopes` on their MCP tool entries; verify end-to-end scope enforcement via a real runnable agent at that point.
- `redacted_view` is currently only logged at INFO level on the `app.icoder.mcp.server` logger. Task 2 will add caplog-based regression coverage so a future refactor can't silently leak a raw token.
