# Phase 3-C0/C1 Implementation Plan

**Date**: 2026-07-05
**Scope**: Phase 3-C0 (Runtime Stabilization & Test Gate) + Phase 3-C1 (MCP OAuth2.0 / inherit auth completion).
**Baseline**: Phase 3-B2 PASS (27/27 new tests, 779/0 focused regression, 11 Quick Tests 9/2/1).

---

## 1. Reading Summary (Required Reading)

### 1.1 Phase 3-B2 final state
- 3 Corti parity gaps closed: 2.2 (Click-to-Chat), 2.3 (Hub Clone), 4.3 (Markdown+JSON).
- Hub → Clone → Chat → Run → Markdown/JSON e2e flow wired.
- 4 known blockers for Phase 3-C (per prompt preamble):
  1. `LLM_PROVIDER=mock` still tries real DeepSeek → live A2A smoke returns `PLANNING_FAILED`.
  2. Full integration suite has 2 pre-existing fails (E1 startup 5s timeout).
  3. `smoke_recall` OOM on Windows CPU/torch/sentence-transformers — known heavy test.
  4. MCP OAuth2.0 / inherit auth still deferred by spec N2 → Phase 3-C main gap.

### 1.2 Corti gap matrix (Section F) — relevant rows
- **3.4 MCP auth types (4)** — Medium — iCoDer only `none`+`bearer` (deferred by N2). Remediation: add `inherit` + `oauth2.0`.
- **3.7 MCP 5 error codes** — Small — iCoDer has 8 generic JSON-RPC but not the 5 MCP-auth-specific. Remediation: add 5 MCP-auth error codes.

### 1.3 Corti error catalog (Section D)
Corti MCP auth error codes per `docs.corti.ai/agentic/mcp-authentication`:
- `mcp_auth_duplicate_name` — two MCP servers registered with same name
- `mcp_auth_missing_name` — server config without `name`
- `mcp_auth_missing_token` — `bearer` without `token`
- `mcp_auth_missing_credentials` — `oauth2.0` without `client_id`/`client_secret`
- (1 generic catch-all)

### 1.4 iCoDer MCP spec (current state — `docs/ICODER_V1_MCP_SPEC.md`)
- §2.2 N2 clause: "不实现 OAuth / API Key auth (MCP 2025-03-26 spec 可选, Phase 4 才接)" — must remove.
- §3 table row: `securitySchemes` ❌端点暴露, 不实现 Phase 4 留 — must update to ✅.
- §4-7: no auth flow described — must add new section for auth types + token resolution.

### 1.5 iCoDer MCP implementation (current state — `app/icoder/mcp/`)
- `server.py` — `tools/list` + `tools/call` endpoints, no auth handling at all. The `_context_id_middleware` stashes `contextId` but does no auth.
- `errors.py` — has 5 custom codes (CATALOG_MISS / RETRIEVER_UNAVAILABLE / LLM_TIMEOUT / PHI_REDACTION_FAILED / PRODUCTION_WRITEBACK_BLOCKED). No auth error codes.
- `tool_registry.py` — 5 tools (search_icd/verify_code/get_differentiation_hint/rerank_codes/calibrate_confidence), no per-tool auth config.

### 1.6 iCoDer runtime startup (for A2)
The current lifespan (per Phase 3-B1 memory + E1 startup test failure):
- Database init (fast)
- PlatformRuntime loading + 16 pack discovery (medium — synchronous pack loading)
- Seed agents (7 registered, 4 stubs skipped, 1 internal engine registered)
- MedCodER retriever (BGE-M3 + FAISS — heavy on first load, ~2-5s)
- AgentRegistrySyncService (DB sync — 28 issues found on first run)
- MCP server mount (fast)
- A2A v0.3 router mount (fast)

The 5s `asgi_lifespan` timeout in `test_e1_real_app_startup.py` is too tight for this workload.

---

## 2. Implementation Plan — Part A (Phase 3-C0 Runtime Stabilization)

### A1. Fix LLM_PROVIDER=mock leakage

**Investigation** (where does mock mode leak to real DeepSeek?):
1. Find `LLM_PROVIDER` env var reads in `app/`.
2. Find `LLMGateway` / `llm_gateway` / DeepSeek client construction.
3. Identify the branch that should return mock responses when `LLM_PROVIDER=mock`.
4. Identify why the mock branch falls through to real DeepSeek (likely: mock only handles chat-completions, but orchestrator's planner uses a different endpoint or a different env var).

**Fix strategy**:
- Add a `MockLLMClient` that returns deterministic canned responses for ANY endpoint (chat/completions, embeddings, etc.) without any HTTP call.
- When `LLM_PROVIDER=mock`, LLMGateway uses `MockLLMClient` exclusively — no real httpx call.
- Mock planner returns a deterministic `Plan` with `experts=["medical-coding/coding-expert"]` so `Plan.experts` is never empty in mock mode.

**Hard test** (A1.5):
- Test that uses `httpx.MockTransport` (or `respx`) to assert NO external HTTP call is made when `LLM_PROVIDER=mock`.
- Test that A2A `message:send` smoke returns success (not `PLANNING_FAILED`) in mock mode.

**Acceptance**: `LLM_PROVIDER=mock pytest` no DeepSeek 401, no `PLANNING_FAILED`, A2A smoke PASS.

### A2. Fix E1 startup timeout

**Investigation**:
1. Read `test_e1_real_app_startup.py` to see what timeout it uses (likely `asgi_lifespan.LifespanManager(startup_timeout=5)`).
2. Profile the lifespan — add `time.perf_counter()` markers around each phase to identify the slow segment.
3. If medcoder retriever is the bottleneck (likely — BGE-M3 + FAISS load on first call), make it lazy-load: defer to first tool call instead of lifespan startup.

**Fix strategy**:
- Increase `startup_timeout` from 5s → 30s in the test (matches real-world lifespan budget).
- Add startup phase markers in `app/main.py` lifespan so future regressions are diagnosable.
- If a specific phase takes >10s, make it lazy (deferred to first request) — but only if it's safe to defer (medcoder retriever is safe — it's already lazy-optional per `medcoder_index_ready` health check).
- NO `sleep()` added.

**Acceptance**: `test_e1_real_app_startup.py` 2 tests PASS.

### A3. Isolate smoke_recall OOM

**Investigation**:
1. Read `tests/integration/icoder/retrieval/test_smoke_recall.py` to confirm the OOM is from BGE-M3 model loading.
2. Add `@pytest.mark.heavy` + `@pytest.mark.retrieval` markers.
3. Update `pytest.ini` / `pyproject.toml` to register the markers + add `-m "not heavy and not retrieval"` to default test selection.
4. Add a docstring explaining: "This test requires ~2GB RAM for BGE-M3 model + FAISS index. Excluded from default suite. Run explicitly with `pytest -m retrieval`."

**Fix strategy**:
- Add `pytest.ini` markers section (or update existing).
- Add a `conftest.py` hook that auto-skips `heavy` / `retrieval` markers unless `--run-heavy` is passed.
- Document in test docstring.

**Acceptance**: Default `pytest tests/integration/icoder/` runs 0 fails. `pytest -m retrieval` can opt-in. Without `--run-heavy`, retrieval tests show clear skip reason.

---

## 3. Implementation Plan — Part B (Phase 3-C1 MCP OAuth2.0 / inherit auth)

### B1. Update MCP spec

Edit `docs/ICODER_V1_MCP_SPEC.md`:
- §2.2: Remove N2 clause. Replace with: "实现 OAuth 2.0 + inherit + bearer + none 4 auth types (Phase 3-C1)".
- §3 table: `securitySchemes` row → ✅ 完整实现 (Phase 3-C1).
- New §X: "MCP Auth" — describe 4 auth types, config schema, token resolution, error catalog, redaction rules.

### B2. Implement MCP auth config schema

New file `app/icoder/mcp/auth_config.py`:
- Pydantic models: `AuthNone`, `AuthBearer`, `AuthInherit`, `AuthOAuth2`, plus a discriminated union `MCPAuthConfig` (field `type` is the discriminator).
- Validator: required fields per type (bearer requires `token_ref`; oauth2 requires `token_url`+`client_id`+`client_secret_ref`+`grant_type`).
- `redacted_view()` method that returns a copy with all `*_ref` fields replaced with `<redacted>`.
- Validation errors raise `MCPError` with `mcp_auth_invalid_oauth_config` / `mcp_auth_missing_token` / `mcp_auth_missing_credentials`.

### B3. Implement token resolution

New file `app/icoder/mcp/auth_resolver.py`:
- `resolve_mcp_auth(auth_config, context) -> AuthHeader` (returns dict like `{"Authorization": "Bearer xxx"}` or `{}` for none).
- Bearer: reads secret from `secret_resolver` (pluggable; for Phase 3-C1 a `EnvSecretResolver` reads from env vars).
- Inherit: pulls token from `context` (a dict-like with `project_studio_token`, `session_token`, etc.).
- OAuth2.0: client_credentials grant via httpx, with:
  - Token cache keyed by `(provider_url, client_id, scopes_hash)` — NO raw secret in cache key.
  - `expires_in` - 60s clock skew buffer.
  - Refresh on expiry.
  - Failure → `MCPError(mcp_auth_token_exchange_failed)`.
- All branches return `AuthHeader` (a dict) or raise typed errors.

### B4. Add MCP auth error catalog

Update `app/icoder/mcp/errors.py`:
- Add 7 new error codes to `MCPErrorCode`:
  - `MCP_AUTH_DUPLICATE_NAME = -32006`
  - `MCP_AUTH_MISSING_NAME = -32007`
  - `MCP_AUTH_MISSING_TOKEN = -32008`
  - `MCP_AUTH_MISSING_CREDENTIALS = -32009`
  - `MCP_AUTH_INVALID_OAUTH_CONFIG = -32010`
  - `MCP_AUTH_TOKEN_EXCHANGE_FAILED = -32011`
  - `MCP_AUTH_FORBIDDEN = -32012`
- Each error's `data` field is sanitized via `redacted_view()` so no secret leaks.
- Update spec `docs/ICODER_V1_MCP_SPEC.md` error section with these 7 codes.

### B5. Tests

New file `tests/unit/icoder/mcp/test_auth.py` (or split into multiple files):
1. `test_auth_config_none_valid` — `{"type":"none"}` parses.
2. `test_auth_config_bearer_valid` — `{"type":"bearer","token_ref":"secret://..."}` parses.
3. `test_auth_config_bearer_missing_token` — `{"type":"bearer"}` raises `mcp_auth_missing_token`.
4. `test_auth_config_oauth2_valid` — full oauth2 config parses.
5. `test_auth_config_oauth2_missing_credentials` — `{"type":"oauth2.0","token_url":"..."}` (no client_id/secret) raises `mcp_auth_missing_credentials`.
6. `test_auth_config_oauth2_invalid` — `{"type":"oauth2.0","grant_type":"password"}` raises `mcp_auth_invalid_oauth_config`.
7. `test_resolve_bearer_returns_header` — bearer resolution returns `{"Authorization": "Bearer xxx"}`.
8. `test_resolve_inherit_from_context` — inherit pulls token from context dict.
9. `test_resolve_oauth2_token_exchange_mock` — uses `respx`/`httpx.MockTransport` to mock token endpoint, asserts cache works on second call.
10. `test_resolve_oauth2_cache_expiry` — second call within TTL hits cache; after TTL calls endpoint again.
11. `test_resolve_oauth2_failure_returns_typed_error` — token endpoint returns 401 → `mcp_auth_token_exchange_failed`.
12. `test_redaction_in_logs_and_runtrace` — auth config redacted_view doesn't leak secret_ref.
13. `test_tools_call_injects_auth_header` — `tools/call` with auth-configured server injects header (mock server-side).
14. `test_mock_llm_no_external_http` — A1.5 regression test (LLM_PROVIDER=mock makes 0 httpx calls).

### Wiring (server.py changes)

- Add `auth: MCPAuthConfig | None` field to `ToolDescriptor` (per-tool auth override) and to MCP server config (default auth).
- In `tools/call` handler: call `resolve_mcp_auth(tool_auth or server_auth, request.state.context)` to get AuthHeader. Pass AuthHeader to handler via `request.state.mcp_auth_header` (handlers that need to call external services read it).
- For Phase 3-C1, no built-in tool actually uses external auth (the 5 MedCodER tools are local). The auth infrastructure is for **future** MCP client mode (iCoDer Expert calling external MCP server) — so we implement the schema + resolver + tests, but don't wire any tool to actually call external services with auth yet. That's Phase 3-C2 scope (per "10 runnable agents" exclusion).

---

## 4. Files Involved

### Backend (Phase 3-C0)
- `app/icoder_runtime/.../llm_gateway.py` (or wherever mock provider is set up) — fix mock to be a complete no-op for external HTTP.
- `app/main.py` — startup phase markers, possibly defer medcoder retriever to lazy.
- `tests/integration/icoder/test_e1_real_app_startup.py` — increase startup_timeout to 30s.
- `tests/integration/icoder/retrieval/test_smoke_recall.py` — add `@pytest.mark.heavy` + `@pytest.mark.retrieval`.
- `pytest.ini` / `pyproject.toml` — register markers + default exclusion.
- New: `tests/unit/icoder/test_mock_llm_no_external_http.py` (A1.5 regression test).

### Backend (Phase 3-C1)
- New: `app/icoder/mcp/auth_config.py` — Pydantic models for 4 auth types.
- New: `app/icoder/mcp/auth_resolver.py` — `resolve_mcp_auth()` implementation.
- Modified: `app/icoder/mcp/errors.py` — add 7 auth error codes.
- Modified: `app/icoder/mcp/server.py` — wire auth into `tools/call` (inject AuthHeader on `request.state`).
- Modified: `app/icoder/mcp/tool_registry.py` — add `auth` field to `ToolDescriptor` (optional, defaults to None).
- New: `tests/unit/icoder/mcp/test_auth.py` — 10+ tests per B5.

### Docs
- Modified: `docs/ICODER_V1_MCP_SPEC.md` — remove N2, add auth types section.
- New: `docs/corti_parity/phase3_c/PHASE3C0_RUNTIME_STABILIZATION_REPORT.md`
- New: `docs/corti_parity/phase3_c/PHASE3C1_MCP_AUTH_IMPLEMENTATION_REPORT.md`
- New: `docs/corti_parity/phase3_c/PHASE3C_TESTING_VERIFICATION_REPORT.md`
- New: `docs/corti_parity/phase3_c/PHASE3C_GAP_CLOSURE_MATRIX.md`

---

## 5. spec N2 Clause Removal Plan

Current text (line 100 of `docs/ICODER_V1_MCP_SPEC.md`):
```
2. **N2**: 不实现 OAuth / API Key auth (MCP 2025-03-26 spec 可选, Phase 4 才接)
```

Replace with:
```
2. **N2** (revised 2026-07-05, Phase 3-C1): 实现 4 auth types — `none` / `bearer` / `inherit` / `oauth2.0`。OAuth2.0 仅支持 `client_credentials` grant (其他 grant_type 留 Phase 4)。API Key auth 不实现 (Corti 也不支持, 用 bearer 替代)。
```

Also update §3 table row `securitySchemes` from `❌ Phase 4 留` → `✅ 完整实现 (Phase 3-C1, 4 auth types)`.

---

## 6. Still Deferred (After Phase 3-C0/C1)

Per the prompt's "非目标" (NOT in scope for Phase 3-C0/C1):
- Phase 3-D (region prefix DNS routing, embedded subdomain)
- Marketplace
- SDK
- "10 runnable agents" (iCoDer currently has 1 runnable Medical Coding MVP + 10 metadata-only; Corti has 20 runnable)

Per the MCP spec non-goals that remain:
- N3 (MCP Sampling) — Phase 6
- N4 (MCP Roots) — Phase 4
- N5 (third-party MCP server registration) — Phase 4
- N6 (Orchestrator rewrite) — out of MCP scope
- N7 (8 atomic Agent migration) — Phase 3 (separate from C0/C1)
- N8 (MCP over WebSocket) — Phase 6

Also deferred within Phase 3-C:
- **3.5 MCP DataPart per-message auth override** — gap 3.5 (Medium), not in Phase 3-C0/C1 scope (only 3.4 + 3.7 are targeted).
- **3.6 MCP thread-bound tool registration** — gap 3.6 (Small), not in Phase 3-C0/C1 scope.

---

## 7. Phase 3-C2 Launch Decision

After Phase 3-C0/C1 completes, the question is whether to proceed to Phase 3-C2 (gap 3.5 DataPart auth override + gap 3.6 thread-bound tool registration + gap 3.9 expert ecosystem expansion).

**Decision criteria** (per the prompt's report requirements):
1. Did Phase 3-C0/C1 close all its target gaps? (3.4, 3.7 + the 3 runtime stability items)
2. Are there regressions in Phase 3-B2's closed gaps (2.2, 2.3, 4.3)?
3. Is the test suite stable (0 fails in default profile)?
4. Is the auth infrastructure sufficient to support 3.5 (DataPart override) without rework?

If all 4 are YES, recommend Phase 3-C2 launch. If any are NO, document the blocker.

---

## 8. Execution Order

1. ✅ Required reading (this plan is the output)
2. **A1** — Fix LLM_PROVIDER=mock leakage (highest priority — blocks live smoke verification)
3. **A3** — Isolate smoke_recall OOM (quick win, unblocks full integration runs)
4. **A2** — Fix E1 startup timeout (depends on A1/A3 being done so we know what's left)
5. **B4** — Add MCP auth error catalog (foundation for B2/B3)
6. **B2** — Implement MCP auth config schema (depends on B4 errors)
7. **B3** — Implement token resolution (depends on B2)
8. **B1** — Update MCP spec (depends on B2/B3/B4 being final)
9. **B5** — Tests (depends on B2/B3/B4)
10. **C** — Generate 4 reports

Begin execution.
