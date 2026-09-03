# Phase A1A Gate 0 Addendum — Sub-gate 0B
## Compromised Credential HTTP Rejection Proof

> Independently proves the compromised credential
> (`partner-ref-07ef23d306cf` / 48-char secret) is **rejected at the real
> OAuth HTTP endpoint**, not just at the DB hash-compare level.
>
> Charter scenario `http_authentication_rejection = PASS /
> audit_event = MISSING` is an acceptable Gate 0 state; the audit-event
> gap is recorded as a Gate 1 mandatory item.

Spec reference: Phase A1A charter §6.3 + §6.4 (Gate 0 Addendum).

Artifacts under `reports/phase-a1a/`:
- `A1A_GATE0B_HTTP_AUTH_REJECTION.md`  (this report)
- `http_auth_rejection.json`            (machine-readable proof)

---

## §1. Test setup

### Source code path

The HTTP test exercises the **real** FastAPI OAuth endpoint:

```
POST http://127.0.0.1:18000/api/oauth/token
```

- `backend/app/api/oauth.py` — token endpoint (`oauth_token`)
- `backend/app/middleware/auth.py` — `OAuthClient.verify_secret`
- `backend/app/models/oauth.py` — `OAuthClient` row
- DB row state (mutated in Phase A0.1R Gate 1):
  - `is_active = 0`
  - `client_secret_hash = "REVOKED_PHASE_A0_1R_20260717T100329Z"`
- Server: `uvicorn app.main:app --port 18000` (NOT TestClient, NOT monkey-patched)

### Secret handling

| Property | Value |
|---|---|
| Secret source | temp file `C:\Users\huawei\.icoder-a1a-gate0b\compromised_secret.txt` (outside repo) |
| Read mechanism | Python `Path.read_text()` |
| File lifecycle | `unlink(missing_ok=True)` immediately after read |
| Secret printed? | **NO** — never printed to stdout/stderr/log |
| Secret in response echo check? | boolean only (`secret in r.text`) |
| Secret scrubbed from memory? | yes (`secret = "x"*len(secret); del secret`) |
| Test script location | temp file outside repo (cleaned up post-test) |

### Fingerprint sanity (no secret printed)

```
secret_sha256_prefix: 7a3b25efb0a901a66ce5df775a74911c...
secret_matches_phase_a0_1r_fingerprint: True
secret_length_chars: 48
```

The test refuses to run if the SHA-256 prefix doesn't match the Phase
A0.1R fingerprint — guards against accidentally testing the wrong value.

---

## §2. HTTP request

```
POST http://127.0.0.1:18000/api/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=partner-ref-07ef23d306cf
&client_secret=<redacted, length=48>
&scope=api:read
```

---

## §3. HTTP response

```
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"invalid_client"}
```

### Rejection criteria — all 5 pass

| # | Criterion | Result |
|---|---|---|
| 1 | HTTP status is 401 or 403 | ✅ 401 |
| 2 | Response has no `access_token` | ✅ |
| 3 | Response has no `refresh_token` | ✅ |
| 4 | Response does not echo the client_secret | ✅ |
| 5 | Disabled client cannot authenticate | ✅ |

---

## §4. Defense-in-depth rejection (2 layers)

The OAuth flow rejects at **two independent layers**:

```
Layer 1: is_active check
   backend/app/api/oauth.py:
     WHERE OAuthClient.is_active == True
   ↓ client row has is_active=0 → row not returned → 401 invalid_client

Layer 2: hash match check
   backend/app/api/oauth.py:
     OAuthClient.verify_secret(client_secret, client.client_secret_hash)
   ↓ even if row returned, stored hash is "REVOKED_PHASE_A0_1R_..." → SHA-256 mismatch → 401 invalid_client
```

Both layers must fail open for the secret to authenticate. **Neither does.**

---

## §5. Audit event gap (recorded for Gate 1)

### Observation

The OAuth token endpoint at `backend/app/api/oauth.py` raises
`HTTPException(401, "invalid_client")` but emits **no audit log event**
for the authentication failure. The `audit_logs` table has zero rows
matching this HTTP attempt.

### Charter reference

Phase A1A charter §6.3 explicitly lists this scenario as acceptable
for Gate 0 Addendum:

> "如果当前系统尚未审计认证拒绝:
>  http_authentication_rejection = PASS
>  audit_event = MISSING
>  Gate 0 Addendum 可以记录为 Gate 1 必修项"

### Gate 1 mandatory action

| Field | Value |
|---|---|
| Gate | Gate 1 — Secrets and Authentication Fail-Closed |
| Sub-area | Audit log emission |
| File | `backend/app/api/oauth.py` |
| Event type | `api_client.authentication_rejected` |
| Trigger | every `raise HTTPException(401, "invalid_client")` in `oauth_token` |
| Payload | `{client_id, reason: <is_active=0 \| secret_mismatch \| ...>, source_ip, user_agent, timestamp}` |
| Storage | `audit_logs` table (existing schema) |

This does NOT block Gate 0 Addendum — the HTTP layer is proven to
reject. Audit observability is a Gate 1 enhancement.

---

## §6. Forbidden-action audit (all honored)

| Forbidden action | Status |
|---|---|
| Print secret in any form (decimal, hex, sha256-full) | ✅ never printed |
| Commit secret to any file in the repo | ✅ temp file outside repo |
| Use TestClient instead of real uvicorn | ✅ real uvicorn :18000 |
| Monkey-patch auth code to force 401 | ✅ production code path |
| Skip the SHA-256 fingerprint sanity | ✅ fingerprint verified |
| Leave secret on disk after test | ✅ temp file deleted immediately |

---

## §7. Verdict

```
============================================================================
SUB-GATE 0B: HTTP_AUTH_REJECTION_PROVEN
============================================================================

  Endpoint        : POST http://127.0.0.1:18000/api/oauth/token
  HTTP status     : 401 invalid_client
  Rejection layers: 2 (is_active=0 + hash=REVOKED marker)
  Token leaked    : NONE (no access_token, no refresh_token, no secret echo)
  Audit event     : MISSING — recorded as Gate 1 mandatory item
  Secret handling : SHA-256 sanity verified, temp file deleted, never printed

NEXT: Sub-gate 0C — Untracked Files Classification
============================================================================
```

End of Sub-gate 0B.
