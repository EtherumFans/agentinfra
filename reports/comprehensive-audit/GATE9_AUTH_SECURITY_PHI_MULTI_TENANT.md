# Audit Gate 9 — Auth / Security / PHI / Multi-tenant (Tracks K1-K6)

> Per PDF §三 Track K: audits the authentication chain (password hashing, JWT lifecycle, OAuth grants), security headers, PHI redaction maturity, multi-tenant isolation, audit-log coverage, and secrets handling. Determines whether iCoDer can be deployed in a Chinese hospital without violating GB/T 35273-2020 (PII protection) or creating a credential-leak blast radius.

## K1. Authentication chain — REAL, with one P0 default-config hole

### K1.1 Password storage — bcrypt default, SHA-256 legacy

`backend/app/middleware/auth.py:25-51`:

```python
def hash_password(password: str) -> str:
    """Hash password using bcrypt (production default)."""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _needs_rehash(hashed_password: str) -> bool:
    """Check if a password hash should be upgraded to bcrypt."""
    return hashed_password.startswith("$sha256$")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored hash. Supports bcrypt ($2b$/$2a$) and legacy SHA-256."""
    if hashed_password.startswith("$sha256$"):
        # legacy path
        ...
        return hmac.compare_digest(computed_hash, stored_hash)
    elif hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
        return bcrypt.checkpw(...)
```

- ✅ Bcrypt is the production default
- ✅ SHA-256 legacy hashes are auto-upgraded on next login (`auth.py:145`)
- ✅ `hmac.compare_digest` constant-time comparison on legacy path
- ⚠️ Legacy SHA-256 still accepted → register as **G9-004 (P2)**: SHA-256 is cryptographically weaker than bcrypt; even though auto-rehash exists, an attacker who finds an old `$sha256$` row can crack it offline faster than bcrypt. Mitigation date unknown.

### K1.2 Password policy — weak

`backend/app/schemas/user.py`:

```python
class UserCreate(BaseModel):
    ...
    password: str = Field(..., min_length=8, max_length=64)
```

- Min length 8, max length 64
- ❌ No complexity requirement (uppercase / digit / symbol)
- ❌ No breach-password check (HIBP / common-password blocklist)
- ❌ No rotation enforcement, no history check

Register as **G9-005 (P2)**: password policy is 8-char-minimum only. Chinese hospital compliance (等保2.0 三级) typically requires complexity (upper+lower+digit+symbol, length ≥ 8). iCoDer would fail 等保 password-strength audit.

### K1.3 JWT lifecycle — HS256, 8h access + 7d refresh, token_version revocation

`backend/app/middleware/auth.py:54-78`:

```python
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = 480  # 8 hours
JWT_REFRESH_EXPIRE_DAYS: int = 7

def create_access_token(user_id, username, role, org_id, token_version):
    expire = datetime.now(UTC) + timedelta(minutes=480)
    payload = {"sub": user_id, "username": ..., "role": ..., "org_id": ...,
               "token_version": ..., "exp": expire, "iat": ..., "type": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

- ✅ HS256 JWT (symmetric)
- ✅ `token_version` claim enables revocation by bumping `user.token_version` (checked at `auth.py:144`)
- ✅ Bcrypt cost factor default (12)
- ❌ HS256 vs RS256/ES256: symmetric secret shared across all services — if one backend service leaks the key, anyone can forge tokens. Corti uses RS256 (asymmetric, public verify key + private sign key). Register as **G9-006 (P2)**.

### K1.4 OAuth client_credentials — 5-minute TTL (Corti parity)

`backend/app/config.py:53-55`:

```python
OAUTH_CLIENT_EXPIRE_SECONDS: int = 300  # 5 minutes
```

Short-lived M2M tokens — Corti-parity design. Verified live in DB:

```
oauth_tokens (3 rows, all from partner-ref-07ef23d306cf):
  client_id:  partner-ref-07ef23d306cf
  scopes:     agents:run runs:read
  expires_at: 2026-07-14 05:17:28  (41.5h ago)
  is_revoked: 0  ← expired but never GC'd
```

⚠️ Token GC is not active — expired tokens linger with `is_revoked=0`. Cosmetic, not a security issue (decode_token still rejects them via `exp` claim), but the registry will grow without cleanup. Register as **G9-007 (P3)**.

### K1.5 Scope enforcement — real

`backend/app/middleware/auth.py:303-341`:

```python
def require_scopes(*required_scopes: str):
    async def _checker(client: dict = Depends(get_current_client)) -> dict:
        granted = set(client.get("scopes") or [])
        missing = [s for s in required_scopes if s not in granted]
        if missing:
            raise HTTPException(403, detail={
                "error": "insufficient_scope",
                "required_scopes": list(required_scopes),
                "missing_scopes": missing,
                "granted_scopes": sorted(granted),
            })
        return client
    return _checker
```

- ✅ Token-side scope enforcement (intersect semantics)
- ✅ Capability aliases (`transcribe` / `streams` / `textgen` / `facts`)
- ✅ Phase 7 Gate 12 hybrid auth (`get_current_user_or_oauth_client`) — accepts both user JWT and client_credentials

### K1.6 Rate limiting — present, memory-default

`backend/app/middleware/rate_limit.py`:

- Memory backend (single-process)
- Redis backend optional via `REDIS_URL` env var
- Login endpoint: 5/min in cloud, 1000/min in dev
- General: `RATE_LIMIT_PER_MINUTE` per IP

⚠️ In dev mode (which is the current `.env` setting), login limit is 1000/min — effectively no protection against brute force.

## K2. Security headers — REAL but minimal

`backend/app/middleware/security_headers.py` (19 LOC):

```python
response.headers["X-Content-Type-Options"] = "nosniff"
response.headers["X-Frame-Options"] = "DENY"
response.headers["X-XSS-Protection"] = "1; mode=block"
response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
if request.url.scheme == "https":
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
```

- ✅ 5 standard security headers
- ❌ No `Content-Security-Policy` for general API responses (CSP is set on the embedded widget iframe only — Phase 7 Gate 6)
- ❌ No `Permissions-Policy` header
- ⚠️ `X-XSS-Protection: 1; mode=block` is deprecated by modern browsers (Chrome removed XSS Auditor in 2019). Not harmful, but cargo-cult.

## K3. PHI redaction — REAL with explicit non-compliance warning

### K3.1 The redactor

`backend/icoder_runtime/core/pii_redaction.py:1-15`:

```python
"""PII Redaction — simple rule-based redaction for hospital deployment.

WARNING: This is SIMPLE rule-based redaction, NOT production-grade medical de-identification.
It removes obvious PII patterns (names, IDs, phone numbers, addresses) but does NOT
guarantee HIPAA/GB/T 35273-2020 compliance. For production, integrate a certified
medical de-identification service.
"""
```

9 regex patterns:
1. `id_card` — 18-digit Chinese ID
2. `phone` — 11-digit mobile
3. `fixed_phone` — landline
4. `contact_phone` — prefix `联系人/家属/紧急`
5. `address_province` — 31 province patterns + street suffix
6. `address_street` — street patterns
7. `medical_record_no` — `病案号/住院号/...`
8. `bed_no` — `床号/床位`
9. `bank_card` — 16-19 digits
10. `email`

No patient name redaction (surnames listed in `_SURNAMES` constant but never applied to a pattern).

### K3.2 Where redaction is applied — EXPORT PATH ONLY

`backend/app/services/phi_redactor.py:7-10`:

```python
"""iCoDer M3-0 — PHI redaction for report export.

... For a hospital pilot the export path is the only
leak vector — the live workbench view continues to show the raw text
to the authenticated coder.
```

PHI redaction is applied **only to exports** (downloaded HTML/JSON reports). The live Console workbench shows raw patient text to the authenticated user. This is a design choice — coders need to see raw text to do their job — but it means:

- LLM-bound payloads are **NOT redacted** in the medical-coding fast-path (only the InboundHandler 5-stage path uses PHIRedactor)
- DB-stored `run_history.input_text` contains raw PHI
- Audit log entries that include request bodies contain raw PHI

Register as **G9-008 (P1)**: PHI redaction is export-only and the redactor itself carries an explicit `WARNING: NOT production-grade medical de-identification` docstring. Live LLM calls in the medical-coding fast-path (corti_like_fast, 35 runs) do NOT pass through PHIRedactor — they go straight to DeepSeek.

### K3.3 Where redaction IS in the live path

`backend/app/icoder/agent_runtime/orchestrator/inbound_handler.py:34,294,305`:

```python
from .phi_redactor import PHIRedactionError, PHIRedactor
...
# stage 1 = received
# stage 2 = phi_redacted
try:
    redacted = self._redactor.redact(message_text)
except PHIRedactionError as e:
    raise OrchestratorError(f"phi_redaction_failed: {e}")
sm = sm.transition(OrchestratorEvent.PHI_REDACTED)  # received → planning
```

The full 5-stage MedCodER path (`medcoder_deep`) DOES redact before planning. But `medcoder_deep` has **0 production invocations** (per Gate 7 §I2.3). The default path is `corti_like_fast` which bypasses InboundHandler entirely (Gate 6 §H2.4).

## K4. Multi-tenant isolation — design exists, but is OPT-IN and UNUSED

### K4.1 Tenant extractor middleware — only enforced in cloud mode

`backend/app/middleware/tenant_extractor.py:102-114`:

```python
# Cloud mode: require a tenant header for any authenticated path.
if settings.ICODER_DEPLOYMENT_MODE == "cloud":
    if not tenant_state:
        return JSONResponse(
            status_code=400,
            content={"detail": "tenant_header_required", ...},
        )
```

In `local` mode (the default), the tenant header is **optional**. Cross-checks against JWT `org_id` happen only if both are present.

`backend/app/config.py:13`:

```python
ICODER_DEPLOYMENT_MODE: str = "local"  # local | cloud
```

### K4.2 DB reality — tenancy is broken at row level

```
run_history.organization_id distribution:
  NULL    235  (98%)
  ff4d047cb533    3
  0188d65b1a3d    1
  b7feffe29b33    1
```

**235 of 240 runs (98%) have NULL organization_id.** This means the run lifecycle (Phase 7 Gate 4) is not stamping the org onto the row at write time. Cross-tenant data leakage is therefore plausible — any filter that doesn't pin `organization_id` would return data from all tenants.

Register as **G9-009 (P0)**: tenancy isolation is not enforced at the data layer. 235/240 run_history rows have NULL `organization_id`. The Tenant-Name middleware and JWT `org_id` claim exist, but the row-level stamping is broken — meaning any org-scoped query that joins on `organization_id` will return zero rows (NULL never matches), and any unscoped query will leak across tenants.

### K4.3 Org distribution — all 42 orgs are test artifacts

```
organizations: 42 total
  - "E2E Org e2e_*" (auto-generated test orgs)
  - "Healthcheck Org *"
  - "Gate 6 Sweep's Organization"
  - "P05 Gate2 After's Organization"
  - "Gate 7 Walkthrough Org" (g7org)
  - "Gate13's Organization"
  - "Phase 4B Walker's Organization"
  - "CDI Test's Organization"
  - 默认组织 (default)
```

**Zero real hospital tenants.** The 42 orgs are all audit / test / phase-gate artifacts.

### K4.4 Org-scoped queries — present but rely on NULL being explicit

Every list endpoint (`/api/usage/summary`, `/api/runs/*`, `/api/clients/*`) filters by `organization_id == current_org.id`. This is correct for the Console flow (which always carries an `org_id` from JWT). But:

- 235 runs are NULL-org → invisible to current Console users
- If a partner OAuth client issues a run, does the run get stamped with the client's org_id? **Yes**, per Phase 7 Gate 5 wiring — but only 1 such run exists (Gate 8 §J2.4).

## K5. Audit log — broken coverage (re-confirm G7-002)

`audit_logs.action` distribution:

```
user.login              160   (51%)
user.register            40   (13%)
preview_session.create   17   (5%)
preview_session.exchange  6
preview_session.revoke    5
```

Total: 228 entries, 5 distinct actions.

**NOT audited** (per Gate 7 §I4.4):
- Agent runs (240 runs in run_history, ZERO in audit_logs)
- CDI runs / queries / transitions
- Billing transactions / credits consumption
- OAuth token issuance (3 tokens issued, ZERO audit entries)
- MCP tool calls
- API Client CRUD (1 client created, ZERO audit entries)
- Run cancel (Phase 7 Gate 4)
- Password reset / change

Register as **G9-010 (P0)** (upgraded from G7-002 P1): For a product claiming "可审计的临床AI" (auditable clinical AI) in its login-page hero text, the audit log covers only 5 actions out of ~25 user-impacting actions. **This is the single biggest compliance gap in the system.** Hospital compliance officers cannot answer the question "who ran what on which patient when" from the audit log.

## K6. Secrets handling — P0 default-config hole

### K6.1 Committed `.env` has DEBUG=true + placeholder SECRET_KEY

`backend/.env`:

```env
APP_ENV=development
DEBUG=true
SECRET_KEY=change-me-in-production
```

The auto-generated SECRET_KEY fallback (`config.py:29`) only kicks in when `SECRET_KEY` is **empty**. Because `.env` sets it to the literal string `"change-me-in-production"`, the fallback is bypassed and **the JWT signing key is publicly known**.

Register as **G9-011 (P0)**: `backend/.env` is committed to git with `SECRET_KEY=change-me-in-production` + `DEBUG=true`. Anyone with repo access can forge valid JWTs for any user. The Phase 1 cloud-flip comment (`config.py:21`) says "cloud production must NEVER auto-seed admin/admin123" but does NOT say "must NEVER use the dev SECRET_KEY placeholder". This is a deploy-time foot-gun.

### K6.2 LLM API key — CredentialVault resolution

`backend/app/config.py:65-68`:

```python
# LLM_API_KEY is now resolved from CredentialVault at runtime.
# Set environment variable ICODER_CREDENTIAL_LLM before starting the server.
# The hardcoded fallback below is for development only.
LLM_API_KEY: str = ""
```

- ✅ Empty default
- ✅ Loaded from env var at runtime
- ⚠️ `.env` does NOT contain the actual key (correct), but no verification that production deploys set it

### K6.3 Encryption at rest — NOT IMPLEMENTED

```
users            — no encrypted columns
audit_logs       — no encrypted columns
run_history      — no encrypted columns (raw input_text + output_text on disk)
preview_sessions — no encrypted columns
```

SQLite data file `data/icoder.db` contains raw PHI at rest. The Phase 5 A2 memory notes the database is intended for SQLite (local) and managed Postgres (cloud), but neither layer implements column-level encryption or TDE (Transparent Data Encryption).

Register as **G9-012 (P1)**: no encryption-at-rest. For Chinese hospital compliance (等保2.0 三级 + GB/T 35273-2020), sensitive PHI columns (run_history.input_text, run_history.output_text, audit_logs.detail) must be encrypted at rest. Current implementation fails this requirement.

## K7. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G9-001** | P0 | secrets | Committed `backend/.env` contains `SECRET_KEY=change-me-in-production` + `DEBUG=true`. The auto-generated-secret fallback only triggers when SECRET_KEY is empty; the literal placeholder bypasses it. Anyone with repo access can forge JWTs. |
| **G9-002** | P0 | audit-coverage | `audit_logs` records only 5 actions (user.login / user.register / preview_session.*). Agent runs, CDI runs, billing, OAuth token issuance, API Client CRUD, MCP tool calls — all unaudited. The "可审计的临床AI" hero claim is broken by 80% of impactful actions having no audit trail. |
| **G9-003** | P0 | tenancy | 235 of 240 `run_history` rows have NULL `organization_id`. Tenant isolation is design-only — the Tenant-Name middleware and JWT `org_id` claim exist, but row-level stamping is broken. Cross-tenant data leakage is plausible. |
| **G9-004** | P1 | phi-redaction | PHI redaction is **export-only** with an explicit source-code docstring warning `NOT production-grade medical de-identification`. The default medical-coding fast-path (`corti_like_fast`, 35 production runs) bypasses PHIRedactor entirely. LLM-bound PHI is unredacted. |
| **G9-005** | P1 | encryption-at-rest | No column-level encryption, no TDE. SQLite data file (`data/icoder.db`) contains raw PHI on disk. Fails 等保2.0 三级 + GB/T 35273-2020 requirements. |
| **G9-006** | P2 | password-policy | Password policy is length-only (min 8, max 64). No complexity, no breach check, no rotation. Fails 等保2.0 三级 password strength audit. |
| **G9-007** | P2 | jwt-algorithm | HS256 (symmetric) used for JWT signing. Corti uses RS256 (asymmetric). Symmetric secret is shared across all verifying services, increasing blast radius of a single leak. |
| **G9-008** | P2 | legacy-crypto | Legacy SHA-256 password hashes (`$sha256$` prefix) still accepted. Auto-rehash on next login exists, but until then attacker can crack offline faster than bcrypt. |
| **G9-009** | P3 | token-gc | Expired OAuth tokens (3 in DB, 41.5h expired at audit time) are not garbage-collected. `is_revoked` remains 0. Registry will grow unbounded. |
| **G9-010** | P3 | header-deprecation | `X-XSS-Protection: 1; mode=block` header is deprecated by modern browsers (Chrome removed XSS Auditor 2019). Cargo-cult, not harmful. |
| **G9-011** | P3 | rate-limit-dev | In dev mode (current `.env`), login rate limit is 1000/min — effectively no brute-force protection. Cloud-mode default (5/min) is correct. |

## K8. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **K1 Auth chain** | `REAL_BCRYPT_+_JWT_+_OAUTHCLIENTCREDENTIALS_BUT_SECRETKEY_FOOTGUN` — bcrypt + JWT + 5-min OAuth + token_version revocation all real; committed dev SECRET_KEY is a P0 deploy foot-gun |
| **K2 Security headers** | `REAL_BUT_MINIMAL` — 5 standard headers, no general CSP, deprecated XSS-Auditor header |
| **K3 PHI** | `EXPORT_ONLY_REDACTOR_WITH_EXPLICIT_NON_COMPLIANCE_WARNING` — Rule-based 9-pattern redactor, source-code WARNING it's not HIPAA/GB-compliant, fast-path bypasses it |
| **K4 Multi-tenant** | `DESIGN_REAL_IMPLEMENTATION_BROKEN` — Tenant extractor + JWT org_id + scope enforcement all exist; 98% of run_history has NULL org_id |
| **K5 Audit log** | `AUTH_ONLY_5_ACTIONS_OF_25` — login + register + preview_session.* only; agent runs + CDI + billing + OAuth issuance unaudited |
| **K6 Secrets** | `DEV_DEFAULT_FOOTGUN_NO_ENCRYPTION_AT_REST` — Committed `.env` with placeholder SECRET_KEY; no column encryption; LLM key correctly env-loaded |

## K9. Gate 9 verdict

`AUTH_DESIGN_REAL_BUT_TENANCY_BROKEN_AT_ROW_LEVEL_AND_AUDIT_LOG_TOO_THIN_FOR_HOSPITAL_COMPLIANCE`

Specifically:

- ✅ Bcrypt password hashing with legacy SHA-256 auto-upgrade
- ✅ JWT with `token_version` revocation + 8h access / 7d refresh
- ✅ OAuth client_credentials with 5-min TTL + token-side scope enforcement + capability aliases
- ✅ Phase 7 Gate 12 hybrid auth (user JWT + client_credentials both accepted on partner routes)
- ✅ Tenant-Name + X-Tenant header middleware with cloud-mode enforcement
- ✅ Rate limiter (memory + Redis backends)
- ❌ **G9-001 P0**: committed `.env` with `SECRET_KEY=change-me-in-production` + `DEBUG=true`
- ❌ **G9-002 P0**: audit log covers 5/25 actions — "可审计的临床AI" hero claim is broken
- ❌ **G9-003 P0**: 235/240 run_history rows have NULL `organization_id` — tenancy isolation is design-only
- ❌ **G9-004 P1**: PHI redactor is export-only with explicit non-compliance warning; fast-path bypasses it
- ❌ **G9-005 P1**: no encryption-at-rest; SQLite file has raw PHI on disk
- ⚠️ Password policy is length-only (fails 等保2.0 三级)
- ⚠️ HS256 vs RS256 — symmetric secret shared across services
- ⚠️ All 42 organizations in DB are test/audit artifacts, zero real hospital tenants

Gate 9 closes. Proceed to **Gate 10 — Model, Data and Evaluation Assets**.
