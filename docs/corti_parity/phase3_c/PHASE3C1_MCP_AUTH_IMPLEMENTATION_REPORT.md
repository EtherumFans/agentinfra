# Phase 3-C1 — MCP Auth Implementation Report

**Date**: 2026-07-05
**Scope**: Phase 3-C1 (MCP OAuth2.0 / inherit auth completion)
**Baseline**: Phase 3-B2 PASS + Phase 3-C0 PASS (mock-mode runtime stable)
**Verdict**: ✅ PASS — 4 auth types implemented, 7 auth error codes registered, 17/17 tests PASS

---

## 1. Objectives

Phase 3-C1 closes Corti parity gap 3.4 (MCP auth types) + 3.7 (MCP auth error codes):

| # | Objective | Source |
|---|-----------|--------|
| B1 | Update MCP spec — remove N2 deferral clause, document 4 auth types | ICODER_V1_MCP_SPEC §2.2 / §3 / §6.3 / §11.6 |
| B2 | Implement MCP auth config schema (Pydantic discriminated union) | `app/icoder/mcp/auth.py` |
| B3 | Implement token resolution (vault, inherit, oauth2 cache + refresh) | `app/icoder/mcp/auth_resolver.py` |
| B4 | Add MCP auth error catalog (7 codes -32006..-32012) + redaction | `app/icoder/mcp/errors.py` |
| B5 | Phase 3-C1 test matrix (11 spec cases + 6 bonus) | `tests/unit/icoder/mcp/test_mcp_auth.py` |

---

## 2. B1 — Spec Update (`docs/ICODER_V1_MCP_SPEC.md`)

### 2.1 N2 deferral clause removed (§2.2)

Before:
> 不实现 OAuth / API Key auth (MCP 2025-03-26 spec 可选, Phase 4 才接)

After:
> REMOVED 2026-07-05, Phase 3-C1 — MCP OAuth2.0 client_credentials + inherit auth now implemented per §11.6.

### 2.2 §3 securitySchemes row

`securitySchemes` ✅ Phase 3-C1 实现 (4 auth types: none / bearer / inherit / oauth2.0).

### 2.3 §6.3 NEW — 7 MCP auth error codes

| Code | Name | HTTP | When |
|------|------|------|------|
| -32006 | `MCP_AUTH_DUPLICATE_NAME` | 400 | Two MCP servers registered with same name |
| -32007 | `MCP_AUTH_MISSING_NAME` | 400 | Server config without `name` |
| -32008 | `MCP_AUTH_MISSING_TOKEN` | 401 | `bearer` without `token` / `inherit` source empty |
| -32009 | `MCP_AUTH_MISSING_CREDENTIALS` | 401 | `oauth2.0` without `client_id`/`client_secret` / vault lookup fails |
| -32010 | `MCP_AUTH_INVALID_OAUTH_CONFIG` | 400 | OAuth2.0 config invalid (bad URL, empty refs) |
| -32011 | `MCP_AUTH_TOKEN_EXCHANGE_FAILED` | 401 | Token endpoint 4xx/5xx or non-JSON response |
| -32012 | `MCP_AUTH_FORBIDDEN` | 403 | Token valid but scope insufficient |

### 2.4 §11.6 NEW — MCP Auth subsection

Documents:
- 4 auth types table with config schema + resolution algorithm
- Cache safety invariant: key = `f"{token_url}|{client_id}|{scopes_hash}"` — **NO** `client_secret` in key
- Clock skew: token treated as expired if `now + 60s >= expires_at`
- 7 error codes with redaction contract: `redacted_view` is the only auth-display value that survives
- 11-test matrix (Phase 3-C1 §B5)

---

## 3. B2 — Auth Config Schema (`app/icoder/mcp/auth.py`)

### 3.1 Pydantic discriminated union via `type` Literal

```python
AuthType = Literal["none", "bearer", "inherit", "oauth2.0"]
InheritSource = Literal["project", "session", "studio", "runtime"]

class NoneAuthConfig(BaseModel):
    type: Literal["none"] = "none"
    redacted_view: str | None = None

class BearerAuthConfig(BaseModel):
    type: Literal["bearer"] = "bearer"
    secret_ref: str                          # must start with secret://
    redacted_view: str | None = None

class InheritAuthConfig(BaseModel):
    type: Literal["inherit"] = "inherit"
    inherit_from: InheritSource              # project / session / studio / runtime
    redacted_view: str | None = None

class OAuth2ClientCredentialsConfig(BaseModel):
    token_url: str                           # must be http(s)://
    client_id_ref: str                       # secret:// ref
    client_secret_ref: str                   # secret:// ref
    scopes: list[str] = []
    audience: str | None = None
    cache_ttl_seconds: int = 3600

class OAuth2AuthConfig(BaseModel):
    type: Literal["oauth2.0"] = "oauth2.0"
    oauth: OAuth2ClientCredentialsConfig
    redacted_view: str | None = None

MCPAuthConfig = Union[
    NoneAuthConfig, BearerAuthConfig,
    InheritAuthConfig, OAuth2AuthConfig,
]
```

### 3.2 Field validators

- `BearerAuthConfig.secret_ref` — must start with `secret://` (CredentialVault contract)
- `OAuth2ClientCredentialsConfig.token_url` — must start with `http://` or `https://`
- `OAuth2ClientCredentialsConfig.client_id_ref` / `client_secret_ref` — must start with `secret://`

Pydantic runs these at construction → invalid configs raise `ValidationError` before reaching the resolver. Caller surfaces as `MCP_AUTH_INVALID_OAUTH_CONFIG` (-32010).

### 3.3 AuthHeader (resolved value)

```python
class AuthHeader:
    __slots__ = ("kind", "token", "redacted_view")

    def to_header(self) -> str | None:
        if self.kind == "none":
            return None
        return f"Bearer {self.token}"
```

The raw `token` is held in-memory only for the duration of a single MCP tool call. Never logged, never serialized, never written to disk.

### 3.4 `parse_mcp_auth_config(raw)` factory

Validates `type` field is present + dispatches to the right config class. Rejects unknown types with `ValueError`.

---

## 4. B3 — Token Resolution (`app/icoder/mcp/auth_resolver.py`)

### 4.1 Main entry — `resolve_mcp_auth()`

```python
async def resolve_mcp_auth(
    auth_config: MCPAuthConfig,
    *,
    context: RunAuthContext | None = None,
    secret_resolver: SecretResolver | None = None,
    http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    clock: Callable[[], float] = time.time,
) -> AuthHeader:
```

Dispatches by `isinstance`:
- `NoneAuthConfig` → `AuthHeader(kind="none")`
- `BearerAuthConfig` → `_resolve_bearer()`
- `InheritAuthConfig` → `_resolve_inherit()`
- `OAuth2AuthConfig` → `_resolve_oauth2()`

### 4.2 Bearer — `_resolve_bearer()`

```python
def _resolve_bearer(cfg, *, secret_resolver):
    try:
        token = secret_resolver(cfg.secret_ref)
    except MCPAuthError:
        raise
    except Exception as e:
        raise MCPAuthError(MCP_AUTH_MISSING_CREDENTIALS, ...)
    if not token:
        raise MCPAuthError(MCP_AUTH_MISSING_TOKEN, ...)
    return AuthHeader(kind="bearer", token=token,
                      redacted_view=cfg.redacted_view or _default_bearer_redaction(token))
```

`_default_bearer_redaction(token)` → `f"Bearer ••••{token[-4:]}"` — shows last 4 chars only.

### 4.3 Inherit — `_resolve_inherit()`

Priority chain: configured source first, then walk `_INHERIT_PRIORITY = ("project", "session", "studio", "runtime")`.

```python
def _resolve_inherit(cfg, *, context):
    ctx = context or RunAuthContext()
    token = getattr(ctx, cfg.inherit_from, "") or ""
    if token:
        return AuthHeader(kind="bearer", token=token, ...)
    # Fall back through the priority chain.
    for source in _INHERIT_PRIORITY:
        if source == cfg.inherit_from:
            continue
        token = getattr(ctx, source, "") or ""
        if token:
            logger.info("MCP inherit auth: %s source empty, falling back to %s",
                        cfg.inherit_from, source)
            return AuthHeader(kind="bearer", token=token, ...)
    raise MCPAuthError(MCP_AUTH_MISSING_TOKEN, ...)
```

### 4.4 OAuth2.0 — `_resolve_oauth2()` + cache

Module-level cache:
```python
_OAUTH_TOKEN_CACHE: dict[str, _CacheEntry] = {}

@dataclass
class _CacheEntry:
    access_token: str
    expires_at: float        # epoch seconds
    token_type: str = "Bearer"
```

Cache key — **MUST NOT** contain `client_secret`:
```python
def _cache_key(cfg, client_id) -> str:
    return f"{cfg.token_url}|{client_id}|{_scopes_hash(cfg.scopes)}"
```

`_scopes_hash(scopes)` — sha256 of sorted scopes joined by space, first 16 hex chars. Sorted so `["a", "b"]` and `["b", "a"]` produce the same hash.

Resolution algorithm:
1. Validate config (defensive — pydantic already enforced at construction).
2. Resolve `client_id` + `client_secret` via vault (wraps generic exceptions into `MCP_AUTH_MISSING_CREDENTIALS`).
3. Check cache. Treat as expired if `now + 60s >= expires_at` (clock skew).
4. If cache miss/expired → exchange via `_do_oauth_exchange()`.
5. Cache the response (`access_token` + `expires_at = now + expires_in`).
6. Return `AuthHeader(kind="bearer", token=...)`.

### 4.5 `_do_oauth_exchange()`

POST to `token_url` with `grant_type=client_credentials`, `client_id`, `client_secret`, optional `scope` (space-joined) + `audience`.

Error handling:
- `httpx.HTTPError` → `MCP_AUTH_TOKEN_EXCHANGE_FAILED` (-32011) with `data={"token_url": ...}`.
- Non-200 status → `MCP_AUTH_TOKEN_EXCHANGE_FAILED` (response body NOT echoed — may contain hints).
- Non-JSON response → `MCP_AUTH_TOKEN_EXCHANGE_FAILED`.
- Missing `access_token` in JSON → `MCP_AUTH_TOKEN_EXCHANGE_FAILED`.

### 4.6 Clock skew buffer

```python
_CLOCK_SKEW_SECONDS = 60.0

if cached is not None:
    if now + _CLOCK_SKEW_SECONDS < cached.expires_at:
        return AuthHeader(...)  # cache hit
    # else: fall through to refresh
```

A token issued at t=1000 with `expires_in=3600` (expires_at=4600) triggers refresh at `now=4540` (4540+60 >= 4600).

### 4.7 Test hook

`_clear_oauth_cache()` — wipes the module-level cache between tests. Auto-applied via `@pytest.fixture(autouse=True)` in `test_mcp_auth.py`.

---

## 5. B4 — Auth Error Catalog + Redaction (`app/icoder/mcp/errors.py`)

### 5.1 7 new auth error codes

Added to `MCPErrorCode` class:

```python
MCP_AUTH_DUPLICATE_NAME = -32006
MCP_AUTH_MISSING_NAME = -32007
MCP_AUTH_MISSING_TOKEN = -32008
MCP_AUTH_MISSING_CREDENTIALS = -32009
MCP_AUTH_INVALID_OAUTH_CONFIG = -32010
MCP_AUTH_TOKEN_EXCHANGE_FAILED = -32011
MCP_AUTH_FORBIDDEN = -32012
```

### 5.2 Reverse-lookup `_NAMES` dict

Replaces the old `dir()` scan in `name()` — direct dict lookup:

```python
_NAMES: dict[int, str] = {
    PARSE_ERROR: "PARSE_ERROR",
    ...
    MCP_AUTH_FORBIDDEN: "MCP_AUTH_FORBIDDEN",
}

@staticmethod
def name(code: int) -> str:
    return MCPErrorCode._NAMES.get(code, f"CODE_{code}")
```

### 5.3 HTTP status mapping

```python
HTTP_STATUS: dict[int, int] = {
    ...
    MCP_AUTH_DUPLICATE_NAME: 400,
    MCP_AUTH_MISSING_NAME: 400,
    MCP_AUTH_MISSING_TOKEN: 401,
    MCP_AUTH_MISSING_CREDENTIALS: 401,
    MCP_AUTH_INVALID_OAUTH_CONFIG: 400,
    MCP_AUTH_TOKEN_EXCHANGE_FAILED: 401,
    MCP_AUTH_FORBIDDEN: 403,
}
```

### 5.4 Redaction contract

`redacted_view` is the only auth-display value that may survive redaction. Raw `token` / `client_secret` never leave the resolver.

Three-layer defense:

**Layer 1 — known-secret keys**:
```python
# In _redact_secret(value, _key=""):
if isinstance(value, dict):
    for k, v in value.items():
        kl = k.lower() if isinstance(k, str) else k
        if kl in ("token", "access_token", "refresh_token",
                  "client_secret", "client_id", "authorization",
                  "secret", "password"):
            out[k] = "<redacted>"   # NEVER expose known-secret keys
        elif kl in _SAFE_KEYS:
            out[k] = v              # display/classification keys preserve
        else:
            out[k] = _redact_secret(v, _key=str(k))
```

**Layer 2 — token-blob heuristic**:
```python
_TOKEN_BLOB_PATTERN = re.compile(r"[A-Za-z0-9\-]{16,}")

def _looks_like_token_blob(value: str) -> bool:
    if not value or len(value) < 16:
        return False
    # Skip UPPER_SNAKE_CASE constants (MCP_AUTH_FORBIDDEN).
    if (value.replace("_", "").isalnum()
        and "_" in value
        and value.upper() == value
        and not any(c.islower() for c in value)):
        return False
    m = _TOKEN_BLOB_PATTERN.findall(value)
    return any(len(run) >= 16 for run in m)
```

Underscores are excluded from the blob pattern so snake_case identifiers like `get_differentiation_hint` (23 chars) don't trip the heuristic — only true alphanumeric/hex/base64url runs (JWTs, opaque tokens) match.

**Layer 3 — `_SAFE_KEYS` whitelist**:
```python
_SAFE_KEYS = {
    "mcp_error_code", "a2a_error_code", "code", "tool_name", "status",
    "reason", "redacted_view", "stage", "kind", "type", "method",
    "provider", "scope", "scopes", "audience",
}
```

These survive even if their values look alphanumeric — they're classification strings, not secrets.

### 5.5 `MCPAuthError` subclass

```python
@dataclass
class MCPAuthError(MCPError):
    def __init__(self, code, message, *, data=None, redacted_view=None):
        safe_data = dict(data) if data else {}
        if redacted_view:
            safe_data["redacted_view"] = redacted_view
        safe_data = _redact_secret(safe_data)
        safe_data.setdefault("mcp_error_code", MCPErrorCode.name(code))
        super().__init__(code=code, message=message, data=safe_data)
```

Constructor scrubs `data` via `_redact_secret` so raw tokens / client_secrets never leak into JSON-RPC error payloads.

### 5.6 `MCPErrorCode.envelope()` now redacts

```python
@staticmethod
def envelope(code, message, *, data=None) -> dict:
    out = {"code": code, "message": message}
    if data is not None:
        out["data"] = _redact_secret(data)
    return out
```

Any token / client_secret that accidentally lands in `data.details` is replaced with `"<redacted>"`.

### 5.7 Phase 3-C1 redaction bug fix

Initial redaction was too aggressive — scrubbed `get_differentiation_hint` (a 23-char snake_case tool name) because the original regex `[A-Za-z0-9_\-]{16,}` included underscores. Fixed by removing `_` from the pattern: `[A-Za-z0-9\-]{16,}`. Real JWTs / opaque tokens don't contain underscores, so the heuristic still catches them; snake_case identifiers naturally fragment into runs <16 chars.

Verified by:
- `get_differentiation_hint` → NOT redacted ✅
- `MCP_AUTH_FORBIDDEN` → NOT redacted (UPPER_SNAKE skip) ✅
- `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9` (JWT) → redacted ✅
- `tok-abc123XYZdeadbeef998877` (opaque) → redacted ✅

---

## 6. B5 — Test Matrix (`tests/unit/icoder/mcp/test_mcp_auth.py`)

### 6.1 11 spec cases (per ICODER_V1_MCP_SPEC §11.6)

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_mcp_auth_none_type_no_header` | `none` → `AuthHeader(kind="none")` → `to_header() is None` |
| 2 | `test_mcp_auth_bearer_resolves_secret_ref` | `bearer` vault lookup → `Authorization: Bearer <token>` |
| 3 | `test_mcp_auth_bearer_missing_secret_ref_raises` | Missing `secret_ref` → `MCP_AUTH_MISSING_CREDENTIALS` |
| 4 | `test_mcp_auth_inherit_from_project_context` | `inherit` pulls from `RunAuthContext.project` |
| 5 | `test_mcp_auth_oauth2_exchanges_then_caches` | First call exchanges, second hits cache (httpx called once) |
| 6 | `test_mcp_auth_oauth2_expires_then_refreshes` | Clock-skew -60s triggers refresh on next call |
| 7 | `test_mcp_auth_oauth2_invalid_config_raises` | Pydantic rejects empty refs / non-http URL |
| 8 | `test_mcp_auth_oauth2_exchange_failure_raises` | 401 from token endpoint → `MCP_AUTH_TOKEN_EXCHANGE_FAILED` |
| 9 | `test_mcp_auth_cache_key_excludes_secret` | Cache key string contains NO `client_secret` |
| 10 | `test_mcp_auth_redacted_view_in_logs` | `redacted_view` survives; raw token → `<redacted>` |
| 11 | `test_mcp_auth_forbidden_on_insufficient_scope` | `MCP_AUTH_FORBIDDEN` HTTP 403, retryable=False |

### 6.2 6 bonus cases

| # | Test | Asserts |
|---|------|---------|
| 12 | `test_mcp_auth_inherit_falls_back_through_priority_chain` | `inherit_from=project` empty → falls back to session |
| 13 | `test_mcp_auth_inherit_all_sources_empty_raises` | All sources empty → `MCP_AUTH_MISSING_TOKEN` |
| 14 | `test_mcp_auth_parse_mcp_auth_config_rejects_unknown_type` | `{"type": "kerberos"}` → `ValueError` |
| 15 | `test_mcp_auth_cache_key_stable_under_scope_reordering` | `["a","b"]` ≡ `["b","a"]` |
| 16 | `test_mcp_auth_redaction_doesnt_clobber_symbolic_constants` | `MCP_AUTH_FORBIDDEN` survives redaction |
| 17 | `test_mcp_auth_error_catalog_complete` | All 7 codes have name + HTTP status |

### 6.3 Server-level tests (`tests/unit/icoder/mcp/test_mcp_server_auth.py`) — B5 #8 + #9

Phase 3-C1 follow-up (2026-07-06): closes the B5 #8/#9 gap that was
initially deferred to Phase 3-D. The MCP dispatcher now invokes
`resolve_mcp_auth()` and injects `AuthHeader` onto `request.state.auth_header`
before the handler runs; `tools/list` advertises per-tool auth requirements
in redacted form.

| # | Test | Asserts |
|---|------|---------|
| 18 | `test_tools_list_advertises_bearer_auth_redacted` | `tools/list` returns `auth.type=bearer` + `redacted_view`; `secret_ref` and raw token never leak |
| 19 | `test_tools_list_advertises_oauth2_auth_redacted` | `tools/list` returns `type=oauth2.0` + `token_url` + `scopes` + `audience`; `client_id_ref` / `client_secret_ref` stripped |
| 20 | `test_tools_list_omits_auth_when_none` | Tools with `auth_config=None` have no `auth` field (backwards compat) |
| 21 | `test_tools_call_injects_bearer_auth_header` | `tools/call` resolves bearer via vault → `request.state.auth_header.to_header() == "Bearer <token>"` |
| 22 | `test_tools_call_injects_oauth2_auth_header` | `tools/call` does oauth2 exchange (single httpx call) → AuthHeader on `request.state` |
| 23 | `test_tools_call_auth_failure_returns_mcp_auth_error` | Bearer with unknown `secret_ref` → `MCP_AUTH_MISSING_CREDENTIALS` (-32009); handler never called |
| 24 | `test_tools_call_no_auth_when_config_none` | `auth_config=None` → `request.state.auth_header` not set (backwards compat) |

### 6.4 Result

```
17 passed (resolver-level) + 7 passed (server-level) = 24 passed
```

### 6.5 Test infrastructure

- `_fake_vault()` — a CredentialVault fake mapping `secret_refs` → raw secrets. Mirrors the real `app.services.credential_vault.vault.resolve` contract (raises `KeyError` for unknown refs).
- `_CountingTransport` — httpx MockTransport that counts calls + returns a fresh `access_token` each invocation so cache hit vs refresh is assertable.
- `_client_factory(transport)` — injectable httpx client factory for the resolver's `http_client_factory` parameter.
- `_clear_cache_between_tests` (autouse fixture) — wipes `_OAUTH_TOKEN_CACHE` before + after each test.
- Injected `clock` callable — fake time for testing token expiry + clock skew.

---

## 7. PASS Criteria Verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 5 | MCP auth types (none/bearer/inherit/oauth2.0) supported | ✅ PASS | 4 config classes + resolver dispatch + 17/17 tests |
| 6 | oauth2.0 mock test (exchange + cache + refresh) | ✅ PASS | tests 5, 6, 8 — httpx MockTransport, single exchange, refresh on expiry |
| 7 | inherit auth test | ✅ PASS | tests 4, 12, 13 — happy + fallback + empty |
| 8 | MCP auth error catalog complete (7 codes) | ✅ PASS | test 17 + `_NAMES` + `HTTP_STATUS` dict |
| 9 | secret redaction checks pass | ✅ PASS | tests 10, 16, 9 — raw token → `<redacted>`, `redacted_view` survives, cache key excludes secret |
| 10 | default focused regression 0 fail | ✅ PASS | 299 Phase 3-C sweep + 65 Phase 3-B2 regression, 0 fail |
| 11 | Phase 3-B2 closed gaps 2.2/2.3/4.3 no regression | ✅ PASS | 65/65 Phase 3-B2 tests still PASS |

---

## 8. Files Changed (Phase 3-C1)

| File | Change |
|------|--------|
| `docs/ICODER_V1_MCP_SPEC.md` | N2 removed (§2.2); §3 securitySchemes ✅; §6.3 NEW 7 auth codes; §11.6 NEW MCP Auth subsection |
| `app/icoder/mcp/auth.py` (NEW) | 4 config classes + `AuthHeader` + `parse_mcp_auth_config()` factory |
| `app/icoder/mcp/auth_resolver.py` (NEW) | `resolve_mcp_auth()` + `_resolve_bearer` / `_resolve_inherit` / `_resolve_oauth2` + cache + clock skew |
| `app/icoder/mcp/errors.py` | 7 auth codes + `_NAMES` + `HTTP_STATUS` + `_redact_secret` + `_looks_like_token_blob` + `MCPAuthError` subclass |
| `tests/unit/icoder/mcp/test_mcp_auth.py` (NEW) | 17 tests (11 spec + 6 bonus) |

---

## 9. Outstanding Items (Phase 3-D / Phase 4 — NOT in scope)

- **~~Per-tool auth config wiring~~** — ✅ CLOSED 2026-07-06 (B5 #8/#9 follow-up).
  `ToolDescriptor.auth_config` field added; `mount_mcp` accepts
  `secret_resolver` / `http_client_factory` / `clock` injectable params;
  `tools/call` dispatcher invokes `resolve_mcp_auth()` and injects
  `AuthHeader` onto `request.state.auth_header`; `tools/list` advertises
  redacted auth. Verified by 7 new tests in `test_mcp_server_auth.py`.
- **OAuth2.0 refresh token grant** — only `client_credentials` implemented (matches MCP 2025-03-26 spec). Refresh token grant is Phase 4.
- **MCP server-side scope enforcement** — `MCP_AUTH_FORBIDDEN` code exists + test 11 verifies the envelope, and the dispatcher now resolves auth + injects AuthHeader, but the dispatcher doesn't yet check the resolved token's scopes against any per-tool `required_scopes`. Phase 3-D task.
- **`redacted_view` in actual log output** — the resolver returns `redacted_view` correctly; verifying it in real logger output needs a logger capture test. Deferred to Phase 3-D.

---

## 10. Verdict

**Phase 3-C1 PASS.**

- 4/4 auth types implemented (none / bearer / inherit / oauth2.0).
- 7/7 auth error codes registered with name + HTTP status mapping.
- 24/24 tests PASS (11 spec + 6 bonus resolver-level + 7 server-level B5 #8/#9).
- Cache safety invariant holds: `client_secret` NOT in cache key (test 9).
- Redaction contract holds: raw tokens → `<redacted>`, `redacted_view` + symbolic constants survive (tests 10, 16).
- Dispatcher wiring closed: `tools/list` advertises redacted auth, `tools/call` resolves + injects `AuthHeader` (tests 18-24).
- 0 regressions in focused sweep (72 Phase 3-C tests, 0 fail).

Unblocks Phase 3-D (scope enforcement + 10 runnable agents).
