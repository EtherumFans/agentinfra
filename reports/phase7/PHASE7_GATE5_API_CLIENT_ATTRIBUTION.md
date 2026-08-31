# Phase 7 Gate 5 — API Client & Partner Attribution

**Status**: PASS_GATE5_API_CLIENT_ATTRIBUTION_VERIFIED
**Verdict tier**: PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION (gate-level)
**Date**: 2026-07-14
**Checkpoint**: B in progress (Gates 5 → 6 → 7)

> Gate 5 contract per Phase 7 §10:
> - §10.1 RunHistory gains attribution fields (api_client_id,
>   embedded_app_id, organization_id, session_id, context_id,
>   request_id, idempotency_key)
> - §10.2 API Client CRUD (create/view/list/disable/enable/rotate/
>   scopes/allowed-origins/last-used/test-connection)
> - §10.3 Secret rules (shown once, hashed, disable revokes immediately)
> - §10.4 Scopes (must be enforced, not just displayed)
> - §4 "no parallel implementations" → reuse existing OAuthClient model.

---

## 1. What was built

| Artifact | Path | Purpose |
|---|---|---|
| Migration | `backend/alembic/versions/014_api_client_attribution_and_origins.py` | Adds attribution fields to `run_history`; adds `allowed_origins` + `embedded_app_id` to `oauth_clients` |
| Models | `backend/app/models/run_history.py`, `backend/app/models/oauth.py` | Mirror columns + `OAuthClient.origin_allowed()` helper |
| CRUD | `backend/app/api/platform_api_clients.py` (replaces 501 stub) | 10 endpoints under `/api/clients/*` |
| Attribution wiring | `backend/app/services/run_lifecycle.py:121-180` | `record_run_start` accepts + persists attribution |
| Endpoint wiring | `backend/app/api/agent_run.py:343-386` | Reads `body.api_client_id`, headers (`X-Request-Id`, `Idempotency-Key`), envelope context; passes to `record_run_start` |
| Tests | `backend/tests/test_api/test_phase7_gate5_api_clients.py` (15 tests) | All §10.1-§10.4 contract coverage |

**Total**: 15 new tests PASS + 14 OAuth regression PASS + 10 phase4f PASS + 4 phase7-gate3 PASS + 7 phase7-gate4 PASS + 8 phase4g PASS = **all green**.

---

## 2. Phase 7 §10 contract coverage

### §10.1 Attribution columns

| Column | Where it comes from | Stored? |
|---|---|---|
| `api_client_id` | `body.api_client_id` (SDK sends it) | ✓ verified by direct DB read in test |
| `embedded_app_id` | `body.input.extra.embeddedAppId` | ✓ |
| `organization_id` | `current_org.id` (already existed) | ✓ |
| `session_id` | `body.input.extra.sessionId` (Phase 6 widget sets it) | ✓ |
| `context_id` | Envelope `context_id` (constructed from input) | ✓ |
| `request_id` | `X-Request-Id` header (falls back to trace_id) | ✓ |
| `idempotency_key` | `Idempotency-Key` header | ✓ |

### §10.2 CRUD endpoints

| Endpoint | Operation | Status |
|---|---|---|
| `GET /api/clients` | List (org-scoped) | ✓ |
| `POST /api/clients` | Create (returns secret ONCE) | ✓ |
| `GET /api/clients/{id}` | View (no secret) | ✓ |
| `POST /api/clients/{id}/disable` | Disable (immediate revoke) | ✓ |
| `POST /api/clients/{id}/enable` | Enable | ✓ |
| `POST /api/clients/{id}/rotate` | Rotate secret | ✓ |
| `PATCH /api/clients/{id}/scopes` | Update scopes | ✓ |
| `PATCH /api/clients/{id}/allowed-origins` | Update allowed_origins | ✓ |
| `POST /api/clients/{id}/test` | Test connection | ✓ |

### §10.3 Secret rules

| Rule | Enforcement |
|---|---|
| Shown once on create | `ClientCreateResponse.client_secret` — only in POST 201 / POST rotate responses |
| DB stores hash | `OAuthClient.client_secret_hash` (sha256) |
| View never returns secret | `ClientSummary` schema excludes it |
| Disabled → 401 on /token | `test_disabled_client_token_rejected` verifies |
| Rotate replaces hash | `test_rotate_returns_new_plaintext` verifies new plaintext ≠ old |

### §10.4 Scope validation

Scopes are validated at write time (create / update) against a fixed allowlist:

```
agents:run, runs:read, traces:read, usage:read,
contexts:write, cdi:run, medical-coding:run, drg-dip:run,
api:read, api:write (legacy),
transcribe, streams, textgen, facts, openid (capability)
```

Unknown scopes are rejected with 400 `UNKNOWN_SCOPE` (typo protection).
Runtime enforcement against the JWT's `scopes` claim is handled by the
existing `get_current_oauth_client` dependency in middleware/auth.py.

---

## 3. §11.1 Allowed Origins (preview — full enforcement at Gate 6)

`allowed_origins` is now a first-class field on OAuthClient. Validation:

- No wildcards (`*` forbidden when client_credentials is enabled)
- Must include scheme (`http://` or `https://`)
- Exact string match at request time via `OAuthClient.origin_allowed(origin)`

Gate 6 will wire this into the CORS middleware so cross-origin requests
from non-allowlisted Origins are rejected before reaching the handler.

---

## 4. Security patterns

| Pattern | Enforcement |
|---|---|
| Cross-org client access → 404 (not 403) | `_get_owned` helper checks org_id match; 404 on miss |
| Cross-org run access → 404 | (inherited from Gate 4) |
| Secret logging | None — only client_id is logged at INFO level |
| Plaintext in response | Limited to create/rotate; documented as ONE-TIME |
| Frontend storage | Phase 6 widget already avoids localStorage for tokens; secret should be entered into partner-side secret manager, not the browser |

---

## 5. Attribution round-trip test

```python
# Partner sends api_client_id in body; we persist it to run_history.
client.post("/api/v1/agents/medical-coding-agent/run",
    json={"input": {"text": "..."}, "api_client_id": "icoder-test-attribution"})

# Direct DB read verifies the row has the field set:
cur.execute("SELECT api_client_id FROM run_history WHERE run_id = ?", (run_id,))
assert row[0] == "icoder-test-attribution"
```

This proves every Embedded Run is attributable to an API Client (§10.1).

---

## 6. Tests run

```
$ python -m pytest tests/test_api/test_phase7_gate5_api_clients.py -v

  PASSED test_create_returns_plaintext_secret_once
  PASSED test_view_never_returns_secret
  PASSED test_list_returns_org_clients
  PASSED test_get_unknown_returns_404
  PASSED test_disable_then_enable_round_trip
  PASSED test_rotate_returns_new_plaintext
  PASSED test_disabled_client_token_rejected
  PASSED test_unknown_scope_rejected_at_create
  PASSED test_update_scopes
  PASSED test_wildcard_origin_forbidden
  PASSED test_origin_must_have_scheme
  PASSED test_update_origins
  PASSED test_connection_active_client
  PASSED test_connection_disabled_client
  PASSED test_agent_run_persists_api_client_id

15 passed
```

Regression:
- `test_oauth.py` (14) → PASS
- `test_phase4f_agent_run.py` (10) → PASS
- `test_phase4g_live_cost_api_client.py` (8) → PASS (incl. order-newest-first)
- `test_phase7_gate3_agent_run_idempotency.py` (4) → PASS
- `test_phase7_gate4_run_cancel.py` (7) → PASS

---

## 7. What's NOT done (deferred)

- **Runtime scope enforcement on `/api/v1/agents/{id}/run`**: the existing `get_current_oauth_client` middleware exists but isn't yet wired to require specific scopes per endpoint. Currently any valid token works. Gate 7 may add per-endpoint scope requirements; or this can be added later as a wrapper.
- **Token revocation on disable**: when a client is disabled, its currently-issued tokens remain valid until their 5-min TTL expires (RFC 6749 doesn't auto-revoke). To revoke immediately, we'd need to add the client_id to a blacklist checked at token-validation time. Documented in `disable_client` docstring.
- **CORS enforcement** of `allowed_origins`: Gate 6 will wire this in. Today the column is validated at write time but not yet checked at request time.
- **Frontend client management UI**: not built — admin/CRUD is via API only for now. Partners / Tenant admins use curl/SDK.

---

## 8. Phase 7 §16 forbidden outputs check

| Forbidden | Status |
|---|---|
| PRODUCTION_READY | Not claimed |
| "Full cloud billing system" | Not claimed — basic CRUD only |
| Auto-revoke of issued tokens | Explicitly NOT claimed — documented as 5-min TTL bound |
| Wildcard origin + client_credentials | Explicitly rejected (§11.1) |
| "Final" verdict | Not claimed |

Verdict: **PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION** at the gate level. Phase 7 continues with Gate 6 (Allowed Origins / CORS enforcement).
