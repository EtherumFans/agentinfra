# Phase 3-D Task 2 — Manual Corti Parity Verification

**Task**: Task 2 — redacted_view Actual Log Capture
**Date**: 2026-07-06
**Feature**: caplog-based regression coverage guaranteeing raw `token` / `client_secret` / `Authorization` header never enter any logger output; `redacted_view` is the only auth-display value that may appear in logs
**Verifier**: Claude Code (simulated user via API client + caplog fixture)

## Corti target behavior

Per `docs/reverse_engineering/corti/CORTI_ERROR_CATALOG.md` + `CORTI_ICODER_GAP_MATRIX.md` gap 3.5:

- Corti's MCP server treats the OAuth2 access_token, client_secret, and the resulting `Authorization: Bearer ...` header as **never-loggable**.
- The only auth-display value that may appear in logs / error envelopes / RunTrace is `redacted_view` (e.g. `"Bearer ••••1234"`).
- This is a runtime safety property — even if a developer accidentally adds `logger.info(f"using token {token}")`, the redaction layer should catch it before it hits stdout / log files.
- Corti has explicit test coverage for this property; gap 3.5 deferred it from Phase 3-C1.

## iCoDer observed behavior

Verified via `pytest` `caplog` fixture (captures real Python `logging` output, not a mock):

### Operation 1 — Bearer auth resolution + scope check + dispatch

Patched `verify_code` with bearer auth (`secret_ref="secret://mcp/bearer/x"` → raw token `tok-bearer-XYZ123abcd`). Ran `POST /mcp/v1/tools/call`. Captured all `app.icoder.mcp` log records at DEBUG level.

**Observed**:
- `mcp scope_check: tool=verify_code required=['coding:verify'] granted=['coding:verify'] ok=True redacted_view='Bearer ••••abcd'`
- No record contains `tok-bearer-XYZ123abcd`, `Bearer tok-bearer`, or any 16+ char token blob.

### Operation 2 — OAuth2.0 exchange + cache hit + scope check

Patched `calibrate_confidence` with oauth2.0 config (`client_secret` = `sec-789-SECRET-stuff`). Ran the tool twice (cache miss + cache hit). Captured all `app.icoder.mcp` log records.

**Observed**:
- 1 httpx call (cache miss on first, hit on second — verified via `transport.calls == 1`).
- scope_check log shows `redacted_view='Bearer ••••abcd'` (resolver-generated default).
- No record contains `tok-exchanged-1-XYZ123abcd`, `sec-789-SECRET-stuff`, `cid-abc-def`, or `Bearer tok-exchanged`.

### Operation 3 — scope_check log line format

Verified the scope_check log line has all required public fields:
- `tool=verify_code`
- `required=[...]`
- `granted=[...]`
- `ok=True/False`
- `redacted_view='Bearer ••••abcd'`

Raw token absent (verified via substring scan for 6 raw token variants).

### Operation 4 — Error envelope on `MCP_AUTH_FORBIDDEN`

Triggered scope failure (bearer with empty `scopes=[]` + `required_scopes=["coding:verify"]`). Verified:
- JSON-RPC error envelope: `code=-32012`, `data.redacted_view="Bearer ••••abcd"`, `data.mcp_error_code="MCP_AUTH_FORBIDDEN"`.
- `json.dumps(body)` scan: 0 raw token substrings present.
- caplog records: 0 raw token substrings present.

### Operation 5 (bonus) — Direct resolver call

Called `resolve_mcp_auth(cfg, secret_resolver=...)` directly (bypassing the dispatcher). Verified caplog has 0 raw token substrings. The `AuthHeader` returned carries `to_header() == "Bearer tok-bearer-XYZ123abcd"` (correct for the outbound HTTP call) but the log layer never sees that string.

## Verdict: ✅ PASS

| # | Corti target | iCoDer observed | Match |
|---|--------------|-----------------|-------|
| 1 | Raw `token` never in logs | All 5 tests scan caplog for 6 raw token variants — 0 hits | ✅ |
| 2 | Raw `client_secret` never in logs | Test 2 oauth2 exchange — `sec-789-SECRET-stuff` absent | ✅ |
| 3 | `Authorization: Bearer ...` header never in logs | Tests scan for `Bearer tok-bearer` / `Bearer tok-exchanged` — 0 hits | ✅ |
| 4 | `redacted_view` CAN safely enter logs | Tests 1, 2, 3 assert `Bearer ••••abcd` IS in scope_check log | ✅ |
| 5 | Error envelope stays secret-free | Test 4 `json.dumps` scan — 0 raw token substrings | ✅ |
| 6 | Tool dispatch log stays secret-free | Tests 1, 2 full caplog scan — 0 hits | ✅ |
| 7 | RunTrace (when built in Task 4) inherits the contract | `redacted_view` is the only auth-display value the dispatcher ever logs; Task 4's RunTrace will read from the same logging stream | ✅ (by construction) |

## Remaining delta

- **Pre-existing resolver quirk**: `OAuth2AuthConfig.redacted_view` (the user-provided display string) is silently dropped by `_resolve_oauth2` — the resolver always generates its own `Bearer ••••{last4}` from the actual token. This is a pre-existing bug from Phase 3-C1, NOT a Task 2 regression. The safety property (no raw token in logs) still holds; only the user's preferred display string is ignored. Fix is one-line (`redacted_view=cfg.redacted_view or _default_bearer_redaction(token)` in `_resolve_oauth2`) but out of scope for Task 2.
- **httpx logger**: httpx logs `HTTP Request: POST https://oauth.example.com/token "HTTP/1.1 200 OK"` at INFO level. The token URL is public (declared in the config), and the request body (containing client_secret) is NOT logged by httpx's default INFO level. Verified by scanning httpx log records.

## Screenshots

N/A — verification via caplog + TestClient. Log output captured in `tests/unit/icoder/mcp/test_mcp_log_redaction.py` and asserted programmatically.

## Follow-up

- Task 4 (RunTrace Viewer) will surface `scope_check` log entries in a frontend timeline. The contract verified here (redacted_view only, no raw token) is what the timeline will display.
- Task 5 runnable agents' tool dispatch will go through the same `tools_call` dispatcher, so they inherit the same redaction guarantee with no extra work.
