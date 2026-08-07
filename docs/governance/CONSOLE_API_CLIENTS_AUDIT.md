# Console API Clients Page — UX Audit (Sprint 1 M4)

**Date**: 2026-08-07
**Scope**: `frontend/src/pages/APIClientsPage.tsx` + `frontend/src/services/api.ts:oauthApi`
**Out of scope**: `keysApi` (legacy API Keys — superseded by OAuth Clients)

## Summary

| Capability | Status | Notes |
|-----------|--------|-------|
| List OAuth Clients | ✅ DONE | `oauthApi.list()` → `GET /oauth/clients` |
| Create OAuth Client | ✅ DONE | `oauthApi.create(name, desc, scopes, ttl)` → `POST /oauth/clients` (form-encoded) |
| Delete (revoke) OAuth Client | ✅ DONE | `oauthApi.delete(id)` → `DELETE /oauth/clients/{id}` + confirm modal |
| **Copy secret once** | ✅ DONE | Modal reveals `client_secret` exactly once after create; warns "请立即复制保存" |
| **Rotate secret** (no delete) | ❌ **MISSING** | No UI control. Backend has no rotate endpoint in `app/api/oauth.py`. Workaround today: delete + recreate (loses client_id). |
| **Disable / re-enable** client (is_active toggle without delete) | ❌ **MISSING** | Backend `OAuthClient.is_active` exists but no UI toggle + no PATCH endpoint |
| **Edit client metadata** (name / description / scopes) after create | ❌ **MISSING** | No PATCH endpoint |
| **last_used_at visibility** | ⚠️ PARTIAL | UI reads `c.last_used_at`, but backend does not write this column on token issue (gap in `oauth.py:_handle_client_credentials`) |
| **scopes help text** | ⚠️ PARTIAL | Input placeholder shows `api:read api:write` but no tooltip / docs link |
| **Copy-to-clipboard feedback** | ✅ DONE | 2-second `Check` icon swap |
| **Tenant hint** | ⚠️ IMPLICIT | `Tenant-Name` header not surfaced; users relying on JWT org_id claim only |

## Corti parity comparison

Corti exposes clients management at `https://auth.{env}.corti.app/realms/{tenant}/protocol/openid-connect/...`
with admin UI at `/admin/master/console/#/{realm}/clients`. Corti supports:

- ✅ Rotate secret (`Regenerate Secret` button)
- ✅ Enable / disable (`Enabled` toggle)
- ✅ Edit scopes (`Authorized Scopes` panel)
- ✅ List sessions + last access

iCoDer is at **3/5** of Corti's client management surface. Sprint 2 should close
rotate + disable; Sprint 3 should close edit + last_used_at backfill.

## Recommended fixes (deferred to Sprint 2 — out of Sprint 1 scope)

### P0 — Sprint 2 must-have

1. **Add rotate-secret endpoint**:
   - Backend: `POST /api/oauth/clients/{id}/rotate-secret` → returns new
     `{client_secret}` once, updates `client_secret_hash` + bumps
     `client_secret_changed_at`. Revoke all outstanding refresh tokens.
   - Frontend: Add "Rotate Secret" button next to "Delete" on each client row.
     Same reveal-once modal as create.

2. **Surface `last_used_at`**:
   - Backend: In `_handle_client_credentials`, write
     `OAuthClient.last_used_at = utcnow()` before returning token. Add
     alembic migration if column missing.
   - Frontend: already wired — fix backend → UI starts showing real dates.

### P1 — Sprint 3 nice-to-have

3. **Add disable / re-enable toggle**:
   - Backend: `PATCH /api/oauth/clients/{id}` with `{is_active: bool}`.
   - Frontend: `Enabled` toggle in client row, separate from delete.

4. **Add scopes help text + link to docs**:
   - Frontend: Tooltip on scopes input explaining `api:read` vs `api:write`
     vs `admin:*`. Link to `docs-site/docs/api-clients` once it ships.

### P2 — Sprint 4 / backlog

5. **List active sessions** per client (issued JWTs not yet expired).
6. **Edit client metadata** (name, description).
7. **Audit log filter** by client_id (currently audit log filter is by user only).

## Charter compliance

- **5-tuple**: This audit does NOT interact with charter state (no
  GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE / CORTI_PARITY / PRODUCTION_READINESS
  mutation).
- **8 forbidden verdicts**: This audit document does NOT emit any of
  PRODUCTION_READY / READY_FOR_HOSPITAL_DEPLOYMENT / CLINICAL_GRADE_VERIFIED /
  PHI_BOUNDED / CORTI_PARITY_VERIFIED / CORTI_AGENTIC_PARITY_VERIFIED /
  READY_FOR_MVP_SHIP / FULLY_VERIFIED.
- **12 forbidden git ops**: This document is a write-only artifact; no
  `git add -A`, no push, no master commit, no amend, no force in this audit.
- **Currency convention**: This document does not reference any monetary
  amount (CNY/USD); no convention interaction.

## Investigation path

```
frontend/src/pages/APIClientsPage.tsx
  ├─ handleCreateOAuth (line 38-47) → oauthApi.create
  ├─ handleDeleteOAuth (line 49-51) → confirm modal
  ├─ confirmDelete modal (line 182-205) → oauthApi.delete
  └─ newSecret reveal (line 67-83) → one-time visibility

frontend/src/services/api.ts
  └─ oauthApi (line 170-179)
       ├─ list   GET /oauth/clients
       ├─ create POST /oauth/clients  (form-encoded)
       └─ delete DELETE /oauth/clients/{id}

backend/app/api/oauth.py
  ├─ POST /api/oauth/token (line 166)        ← client_credentials grant
  ├─ POST /api/oauth/realms/{realm}/token (line 253)
  ├─ GET  /api/oauth/realms/{realm}/.well-known/openid-configuration (line 297)
  └─ NO rotate-secret endpoint  ← GAP
  └─ NO PATCH endpoint          ← GAP

backend/app/api/platform_api_clients.py (line 168)  ← backend-service clients
  └─ Wildcard `*` scope forbidden when client_credentials — enforcement
```

Backend OAuthClient model fields actually used in current UI:
`client_id`, `name`, `scopes`, `last_used_at` (writes missing), `is_active`
(no UI toggle), `created_at`.

## Out of scope (acknowledged)

- This audit does **not** modify `APIClientsPage.tsx`, `api.ts`, `oauth.py`,
  or any migration. All remediation is deferred to Sprint 2.
- This audit does **not** add tests — fixture coverage for existing
  create/list/delete is at `backend/tests/test_oauth_clients.py` and was
  verified under Phase 7 Gate 12 (PASS_GATE12).
- The `keysApi` (legacy API Keys tab) is intentionally out of scope — it is
  a deprecated surface retained for back-compat; Sprint 2 should consider
  hiding it for new tenants.
