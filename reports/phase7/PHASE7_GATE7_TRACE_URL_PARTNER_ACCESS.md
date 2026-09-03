# Phase 7 Gate 7 — Partner-Secured Trace URL

**Date**: 2026-07-14
**Status**: PASS_GATE7_TRACE_URL_PARTNER_ACCESS_VERIFIED
**Checkpoint**: B (Gates 5+6+7) — Final gate of Checkpoint B
**Tokens**: ~cumulative Phase 7

---

## §12 — Acceptance criteria

Per Phase 7 §12:
- Partners must be able to deep-link into a Run's trace view **without** a Console JWT
- The URL must be **signed** (HMAC-SHA256) and **bound** to a single `(run_id, organization_id)` pair
- Tokens must **expire** (default 24h)
- Verification must be **constant-time** on the signature
- Org mismatch must not leak run existence (403 with generic message, not 404)

---

## Deliverables

| # | Item | File | Status |
|---|------|------|--------|
| 1 | HMAC-SHA256 token service | `app/services/trace_token.py` (~210 LOC) | ✅ new |
| 2 | `issue_trace_token` / `verify_trace_token` / `build_trace_url` | same | ✅ |
| 3 | 5 typed exceptions | same | ✅ |
| 4 | Partner endpoint `GET /api/v1/runs/{run_id}/trace?token=` | `app/api/runs.py:249-363` | ✅ |
| 5 | `_trace_url_for` upgrade to emit signed URLs | `app/api/agent_run.py` (~490) | ✅ |
| 6 | 13 tests (7 unit + 6 endpoint) | `tests/test_api/test_phase7_gate7_trace_token.py` | ✅ 13/13 PASS |
| 7 | This closure report | this file | ✅ |

---

## §12.1 Token format

```
<payload_b64url>.<sig_b64url>
```

- `payload_b64url` = base64url of compact JSON `{"i":1,"r":<run_id>,"o":<org_id>,"c":<api_client_id>,"e":<exp_epoch>}`
- `sig_b64url` = base64url of HMAC-SHA256(`payload_b64`, key=SHA256(`settings.SECRET_KEY`))

Keys are SHA-256'd to guarantee fixed-length HMAC input regardless of `SECRET_KEY` length.

### Why these specific fields?

- `i` (version) — forward compat; lets us change the format without breaking old tokens (we'd bump version and reject mismatches).
- `r` (run_id) — the bound run. Verification rejects if `r != expected_run_id`.
- `o` (organization_id) — empty string in single-tenant dev. Token is bound but verification only enforces when both sides are non-empty.
- `c` (api_client_id) — for audit; not enforcement-bound.
- `e` (exp epoch seconds) — must be `> now`.

---

## §12.2 Endpoint semantics

`GET /api/v1/runs/{run_id}/trace?token=<signed>`

| Outcome | HTTP | code |
|---------|------|------|
| Missing token | 401 | TRACE_TOKEN_REQUIRED |
| Malformed (no `.` or bad base64) | 401 | TRACE_TOKEN_MALFORMED |
| Bad signature | 401 | TRACE_TOKEN_INVALID |
| Expired | 401 | TRACE_TOKEN_EXPIRED |
| Token's `run_id` ≠ URL's `run_id` | 401 | TRACE_TOKEN_RUN_MISMATCH |
| Token's org ≠ run's actual org | 403 | TRACE_TOKEN_ORG_MISMATCH |
| Valid token, no events for run | 404 | TRACE_NOT_FOUND |
| Success | 200 | `{run_id, timeline, step_count, trace_token}` |

The 403-vs-404 distinction is deliberate: a 404 on org-mismatch would leak "this run exists in some other org". The 403 message is generic ("Trace token not valid for this run.") so it doesn't disclose which side is wrong.

---

## §12.3 `_trace_url_for` behavior change

Old (Phase 6 Gate 5):
```python
return f"/ai-studio/runs/{run_id}/trace"  # Console-only SPA path
```

New (Phase 7 Gate 7):
```python
if organization_id or api_client_id:
    return build_trace_url(base_url, run_id=run_id, ...)  # signed partner URL
return f"/ai-studio/runs/{run_id}/trace"  # legacy Console path
```

The Console's internal `run.completed` event still carries the SPA path (no `org_id` / `api_client_id` in scope). The partner-facing `POST /api/v1/agents/{id}/run` response carries the signed URL because the partner's API client identity is in scope.

---

## §12.4 Verification safety

- `secrets.compare_digest(sig, expected_sig)` — constant-time compare, defeats timing attacks
- Org cross-check uses `get_run_status()` to read the actual `run_history` row; never trusts the token's claim alone
- 24h default TTL; tunable via `ttl_seconds=` per-call (tests use `-10` for instant-expiry fixtures)
- Rotating `settings.SECRET_KEY` invalidates all outstanding tokens (no DB tracking — by design; §12.4 doesn't require per-token revocation)

---

## Test coverage (13/13 PASS)

**Unit (service-level) — 7 tests:**
1. `test_issue_trace_token_returns_nonempty_string` — format sanity
2. `test_verify_fresh_token_with_matching_run_id_succeeds` — happy path
3. `test_verify_token_with_tampered_signature_fails` — flip one sig char → reject
4. `test_verify_token_with_wrong_run_id_fails` — bound run_id enforced
5. `test_verify_expired_token_fails` — `ttl=-10` → reject
6. `test_verify_malformed_token_fails` — `"not-a-real-token"` → reject
7. `test_build_trace_url_includes_base_run_and_token` — full URL composition

**Endpoint (HTTP-level) — 6 tests:**
8. `test_get_trace_without_token_returns_401` — TRACE_TOKEN_REQUIRED
9. `test_get_trace_with_valid_token_returns_timeline` — 200 + timeline shape verified
10. `test_get_trace_with_invalid_signature_returns_401` — TRACE_TOKEN_INVALID/MALFORMED
11. `test_get_trace_with_run_mismatch_returns_401` — TRACE_TOKEN_RUN_MISMATCH
12. `test_get_trace_with_expired_token_returns_401` — TRACE_TOKEN_EXPIRED
13. `test_get_trace_run_not_found_returns_404` — TRACE_NOT_FOUND

All fixtures use the module-level `get_default_store()` singleton cleared before each test to prevent inter-test contamination.

---

## Regression

```
tests/test_api/test_phase7_gate7_trace_token.py ............ [ 13 passed ]
+ 48 regression tests across phases 4-7 (idempotency, run lifecycle, api clients, CORS)
= 61 total PASS, 0 failures
```

---

## Checkpoint B summary (Gates 5 + 6 + 7)

| Gate | Title | Status |
|------|-------|--------|
| 5 | API Client Attribution | PASS_GATE5_API_CLIENT_ATTRIBUTION_VERIFIED |
| 6 | Allowed Origins + CORS + CSP | PASS_GATE6_ALLOWED_ORIGINS_CORS_VERIFIED |
| 7 | Partner-Secured Trace URL | PASS_GATE7_TRACE_URL_PARTNER_ACCESS_VERIFIED |

**Checkpoint B: CLOSED.** Partners with an API Client can now:
1. Register their origin (Gate 5)
2. Embed the widget cross-origin with proper CORS + CSP (Gate 6)
3. Deep-link into a trace view via signed URL, no JWT required (Gate 7)

---

## Next: Checkpoint C (Gate 10)

Hard checkpoint sequence: A (Gates 2+3 ✅) → B (Gates 5+6+7 ✅) → **C (Gate 10)** → D (Gate 12).

Gate 10 is the three-demo browser walkthrough (medical-coding / cdi / drg-dip). Between now and Gate 10, the remaining "soft" gates are 8, 9, 11 — Usage metering closure, SSE event realism, patient-context isolation E2E. Those are not on the hard critical path but complete the partner story.

Per user directive, the Corti Embedded Assistant parity walkthrough (separate file at `PHASE7_CORTI_EMBEDDED_PARITY_WALKTHROUGH.md`) is a roadmap input, not a Phase 7 blocker.
