# Phase 3-C — Gap Closure Matrix

**Date**: 2026-07-05 (last updated 2026-07-06)
**Scope**: Phase 3-C0 (Runtime Stabilization) + Phase 3-C1 (MCP Auth) + Phase 3-C1 follow-up (Server-level auth injection)
**Baseline**: Phase 3-B2 (3 Corti parity gaps closed: 2.2 / 2.3 / 4.3)
**Verdict**: ✅ PASS — 4 stabilization blockers closed + 3 Corti parity gaps closed (3.1 / 3.4 / 3.7)

---

## 1. Carried-in Blockers (from Phase 3-B2)

| # | Blocker | Source | Status | Closed by |
|---|---------|--------|--------|-----------|
| A1 | `LLM_PROVIDER=mock` still tries real DeepSeek → A2A `PLANNING_FAILED` | Phase 3-B2 §E #5 | ✅ CLOSED | MockLLMProvider planner detection + lifespan reads `os.environ` directly |
| A2 | E1 startup `TimeoutError` after "Database initialized" | Phase 3-B2 Round 5 caveats | ✅ CLOSED | `LifespanManager(app, startup_timeout=60.0)` + `_check_timeouts` task cleanup |
| A3 | `smoke_recall` OOM on Windows CPU/torch | E1.9/E1.10 known issue | ✅ ISOLATED | `pytest.ini` `addopts = -m "not heavy and not retrieval"` + `heavy` + `retrieval` markers |
| A4 | MCP OAuth2.0 / inherit auth still deferred by spec N2 | Phase 3-B2 §F 3.4 / 3.7 | ✅ CLOSED | Phase 3-C1 — 4 auth types + 7 error codes + 17 tests |

---

## 2. Corti Parity Gap Matrix

### 2.1 Gaps closed in Phase 3-C1

| Gap # | Title | Severity | Before | After | Evidence |
|-------|-------|----------|--------|-------|----------|
| 3.4 | MCP auth types (4) | Medium | iCoDer only `none`+`bearer` (deferred by N2). | 4 auth types fully implemented: `none` / `bearer` / `inherit` / `oauth2.0` (client_credentials grant + cache + refresh). | `app/icoder/mcp/auth.py` + `app/icoder/mcp/auth_resolver.py` + 17 tests in `test_mcp_auth.py` |
| 3.7 | MCP auth error codes | Small | iCoDer had 5 custom JSON-RPC codes + 0 auth-specific. | 7 MCP auth codes (`-32006..-32012`) registered with name + HTTP status mapping + redaction contract. | `app/icoder/mcp/errors.py` `MCPErrorCode.MCP_AUTH_*` + `_NAMES` + `HTTP_STATUS` + `MCPAuthError` subclass |

### 2.2 Gaps closed in Phase 3-B2 (regression check — still closed)

| Gap # | Title | Severity | Status | Evidence |
|-------|-------|----------|--------|----------|
| 2.2 | Click-to-Chat | Medium | ✅ STILL CLOSED | 65/65 Phase 3-B2 tests PASS in Phase 3-C regression sweep |
| 2.3 | Hub Clone | Medium | ✅ STILL CLOSED | 65/65 Phase 3-B2 tests PASS |
| 4.3 | Markdown+JSON output | Medium | ✅ STILL CLOSED | 65/65 Phase 3-B2 tests PASS |

### 2.3 Gaps NOT in Phase 3-C scope (Phase 3-D / Phase 4)

| Gap # | Title | Severity | Defer to | Rationale |
|-------|-------|----------|----------|-----------|
| 2.4 | Cost tracking UI | Small | Phase 3-D | Requires billing service stub |
| 2.5 | Region-prefixed API routing | Small | Phase 3-D | Requires region router middleware |
| 2.6 | FHIR context | Medium | Phase 4 | FHIR R4 resources not yet modeled |
| 2.7 | ICD-10-CN differentiator | Medium | Phase 3-D | Partial — `get_differentiation_hint` tool exists; UI surface pending |
| 2.8 | RunTracePage | Medium | Phase 3-D | P1.0-E RunTracePage exists; Corti-parity trace viewer pending |
| 3.2 | OAuth2.0 refresh token grant | Small | Phase 4 | MCP 2025-03-26 spec only requires `client_credentials` |
| 3.3 | MCP server-side scope enforcement | Small | Phase 3-D | `MCP_AUTH_FORBIDDEN` code exists; dispatcher check pending |
| 3.5 | `redacted_view` in actual log output | Small | Phase 3-D | Resolver returns correctly; logger capture test pending |
| 4.1 | Marketplace | Large | Phase 4 | Out of scope per prompt |
| 4.2 | SDK | Large | Phase 4 | Out of scope per prompt |
| 4.4 | 10 runnable agents | Large | Phase 3-D | Out of scope per prompt |

### 2.4 Gap 3.1 closed in Phase 3-C1 follow-up (2026-07-06)

| Gap # | Title | Severity | Before | After | Evidence |
|-------|-------|----------|--------|-------|----------|
| 3.1 | Per-tool auth config wiring | Medium | Resolver wired (Phase 3-C1 §9) but dispatcher didn't invoke yet — deferred to Phase 3-D. | `ToolDescriptor.auth_config` field + `tools/list` redacted advertisement + `tools/call` `resolve_mcp_auth()` → `request.state.auth_header` injection. | `app/icoder/mcp/tool_registry.py` + `app/icoder/mcp/server.py` (`_redact_auth_config`, `tools_list`, `tools_call`, `mount_mcp` resolver params) + 7 server-level tests in `test_mcp_server_auth.py` |

---

## 3. PASS Criteria Burn-down

| # | Criterion | Source | Status | Evidence |
|---|-----------|--------|--------|----------|
| 1 | `LLM_PROVIDER=mock` no real external LLM | prompt §1 | ✅ PASS | `test_mock_llm_no_external_http.py` 7/7 — MockTransport raises AssertionError if called |
| 2 | A2A live smoke stable PASS in mock | prompt §1 | ✅ PASS | `test_phase3c0_a2a_mock_smoke.py` 2/2 — response state ≠ `PLANNING_FAILED` |
| 3 | E1 startup timeout fixed | prompt §1 | ✅ PASS | `test_e1_real_app_startup.py` 2/2 with `startup_timeout=60.0` |
| 4 | `smoke_recall` OOM isolated | prompt §1 | ✅ PASS | `pytest.ini` `addopts = -m "not heavy and not retrieval"`; default sweep 0 OOM |
| 5 | MCP auth types (none/bearer/inherit/oauth2.0) | prompt §1 | ✅ PASS | 4 config classes + resolver dispatch + 17/17 tests |
| 6 | oauth2.0 mock test | prompt §1 | ✅ PASS | tests 18, 19, 21 — exchange + cache + refresh + failure |
| 7 | inherit auth test | prompt §1 | ✅ PASS | tests 17, 25, 26 — happy + fallback + empty |
| 8 | MCP auth error catalog complete | prompt §1 | ✅ PASS | 7 codes `-32006..-32012` + `_NAMES` + `HTTP_STATUS` + test 30 |
| 9 | secret redaction checks pass | prompt §1 | ✅ PASS | tests 22, 23, 29 — cache key excludes secret, raw token → `<redacted>`, symbolic constants survive |
| 10 | default focused regression 0 fail | prompt §1 | ✅ PASS | 75/75 Phase 3-C focused + 65/65 Phase 3-B2 regression, 0 fail |
| 11 | Phase 3-B2 closed gaps 2.2/2.3/4.3 no regression | prompt §1 | ✅ PASS | 65/65 Phase 3-B2 tests still PASS |

**Verdict: 11/11 PASS criteria met.**

---

## 4. Files Changed (Phase 3-C)

### 4.1 Production code

| File | Phase | Change |
|------|-------|--------|
| `icoder_runtime/core/llm_gateway.py` | 3-C0 | MockLLMProvider planner prompt detection + `_extract_first_expert` / `_extract_subtask_input` helpers |
| `app/main.py` | 3-C0 | DeepSeek registration reads `os.environ` directly; `_check_timeouts` task stored + cancelled on shutdown |
| `app/icoder/mcp/auth.py` (NEW) | 3-C1 | 4 config classes + `AuthHeader` + `parse_mcp_auth_config()` factory |
| `app/icoder/mcp/auth_resolver.py` (NEW) | 3-C1 | `resolve_mcp_auth()` + `_resolve_bearer` / `_resolve_inherit` / `_resolve_oauth2` + cache + clock skew |
| `app/icoder/mcp/errors.py` | 3-C1 | 7 auth codes + `_NAMES` + `HTTP_STATUS` + `_redact_secret` + `_looks_like_token_blob` + `MCPAuthError` subclass |
| `app/icoder/mcp/tool_registry.py` | 3-C1 follow-up | `ToolDescriptor.auth_config` field + `from_pydantic()` accepts `auth_config` param |
| `app/icoder/mcp/server.py` | 3-C1 follow-up | `_redact_auth_config()` for tools/list + `tools_call` resolver dispatch → `request.state.auth_header` + `mount_mcp()` accepts `secret_resolver` / `http_client_factory` / `clock` |

### 4.2 Test code

| File | Phase | Change |
|------|-------|--------|
| `tests/unit/icoder/test_mock_llm_no_external_http.py` (NEW) | 3-C0 | 7 tests — mock LLM never invokes real HTTP |
| `tests/integration/icoder/test_phase3c0_a2a_mock_smoke.py` (NEW) | 3-C0 | 2 tests — A2A message:send in mock mode ≠ PLANNING_FAILED |
| `tests/integration/icoder/test_e1_real_app_startup.py` | 3-C0 | `LifespanManager(app, startup_timeout=60.0)` in both async tests |
| `tests/integration/icoder/retrieval/test_smoke_recall.py` | 3-C0 | `pytestmark` list with `heavy` + `retrieval` + `skipif` |
| `tests/unit/app/api/test_runtime_platform_v2_projection.py` (NEW) | 3-C0 | 2 tests — v1→v2 projection wrapper (carry-over from Phase 3-B1) |
| `tests/unit/icoder/mcp/test_mcp_auth.py` (NEW) | 3-C1 | 17 tests — 11 spec + 6 bonus |
| `tests/unit/icoder/mcp/test_mcp_server_auth.py` (NEW) | 3-C1 follow-up | 7 tests — B5 #8 (tools/list redacted) + B5 #9 (tools/call AuthHeader injection) |
| `pytest.ini` (NEW) | 3-C0 | Marker registry + `addopts = -m "not heavy and not retrieval"` |

### 4.3 Spec docs

| File | Phase | Change |
|------|-------|--------|
| `docs/ICODER_V1_MCP_SPEC.md` | 3-C1 | N2 removed (§2.2); §3 securitySchemes ✅; §6.3 NEW 7 auth codes; §11.6 NEW MCP Auth subsection |

---

## 5. Test Count Summary

| Category | Count | Status |
|----------|-------|--------|
| Phase 3-C0 new tests | 13 | ✅ all PASS |
| Phase 3-C1 new tests (resolver-level) | 17 | ✅ all PASS |
| Phase 3-C1 follow-up tests (server-level) | 7 | ✅ all PASS |
| Phase 3-B2 regression (no regression check) | 65 | ✅ all PASS |
| Phase 3-C focused sweep | 75 | ✅ all PASS |
| Full default sweep (excl. heavy + retrieval + e2e_product + real-deepseek) | 299 + 1 skipped | ✅ 0 Phase 3-C-related failures |
| Pre-existing failures (NOT Phase 3-C) | 1 flaky + 4 infra + 8 stale | documented, out of scope |

---

## 6. Outstanding Items (Phase 3-D / Phase 4 — NOT in scope per prompt)

### 6.1 Phase 3-D (next phase)

- 10 runnable agents
- MCP server-side scope enforcement (dispatcher doesn't yet check scopes)
- `redacted_view` in actual log output (logger capture test)
- ICD-10-CN differentiator UI surface
- RunTracePage Corti-parity viewer
- Cost tracking UI
- Region-prefixed API routing
- Cleanup stale tests (`tests/e2e_product/test_embed_demo_three_components.py`)
- Cleanup pytest asyncio warnings on non-async tests

### 6.2 Phase 4 (later)

- Marketplace
- SDK
- OAuth2.0 refresh token grant
- FHIR R4 context resources

---

## 7. Verdict

**Phase 3-C PASS.**

- 4/4 carried-in stabilization blockers closed (A1-A4).
- 2/2 Corti parity gaps closed (3.4, 3.7).
- 1/1 follow-up gap closed in Phase 3-C1 (3.1 — per-tool auth config wiring, 2026-07-06).
- 3/3 Phase 3-B2 closed gaps still closed (2.2, 2.3, 4.3) — no regression.
- 11/11 PASS criteria met.
- 37 new tests + 2 re-verified, all PASS.
- 0 Phase 3-C-related regressions in default sweep.

Unblocks Phase 3-D (scope enforcement + 10 runnable agents + Corti parity 2.4/2.5/2.7/2.8/3.3/3.5).
