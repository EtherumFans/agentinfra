# A1A Gate 1 Deliverable #2 — Secret Inventory

> Catalogues every secret and secret-like configuration value
> referenced by `backend/app/`. Each entry includes purpose, storage
> location, current value classification, and Gate 1 action.

Machine-readable companion: `secret_inventory.json`

---

## SEC-01 — `SECRET_KEY`

| Property | Value |
|---|---|
| Purpose | JWT signing (user sessions + machine tokens); HMAC derivation for preview tickets + trace URL tokens |
| Storage | Process env `ICODER_SECRET_KEY` → `Settings.SECRET_KEY` |
| Default | Empty string; auto-generated via `secrets.token_urlsafe(48)` if missing |
| Current value in `backend/.env` | `"change-me-in-production"` (literal — Phase A0.1 Gate 0 finding) |
| Cloud required | YES |
| Used by | `backend/app/api/oauth.py:75`, `backend/app/middleware/auth.py:66,78,107,112`, `backend/app/services/preview_ticket.py:87-88`, `backend/app/services/trace_token.py:94-96` |
| Gate 1 action | **CLOSED** — fail-closed policy refuses cloud boot if value is weak/missing (10 tests). Purpose-separation deferred to A1A-G1-DEFERRED-01. |

## SEC-02 — `LLM_API_KEY`

| Property | Value |
|---|---|
| Purpose | DeepSeek API authentication for LLM calls |
| Storage | `Settings.LLM_API_KEY` (resolved at runtime from `CredentialVault`) |
| Default | Empty string |
| Cloud required | YES — injected via cloud KMS, never written to file |
| Used by | `backend/app/main.py:176-191`, `backend/app/services/llm_service.py:52-53` |
| Gate 1 action | **MAINTAIN** — already correctly sourced from CredentialVault; no leak paths in logging. |

## SEC-03 — `ICODER_API_CLIENT_SECRET`

| Property | Value |
|---|---|
| Purpose | Backend-service OAuth client_credentials secret for partner API Clients |
| Storage | `Settings.ICODER_API_CLIENT_SECRET` (cloud env var) |
| Default | Empty string |
| Cloud required | YES if backend-service flow used |
| Used by | `backend/app/api/examples.py:198` (server-side only, never shipped to client) |
| Gate 1 action | **MAINTAIN** — already correctly handled server-side. |

## SEC-04 — `oauth_clients.client_secret_hash` (DB column)

| Property | Value |
|---|---|
| Purpose | Per-API-Client secret hash (bcrypt or similar) |
| Storage | Postgres/SQLite column `oauth_clients.client_secret_hash` |
| Compromised credential state | `REVOKED_PHASE_A0_1R_20260717T100329Z` (Phase A0.1R Gate 1 mutation) |
| Verification | `OAuthClient.verify_secret(secret, hash)` constant-time compare |
| Gate 1 action | **CLOSED** for compromised credential. Lifecycle (rotation, dual-hash) deferred to A1A-G1-DEFERRED-02. |

## SEC-05 — Compromised credential (reference)

| Property | Value |
|---|---|
| Client ID | `partner-ref-07ef23d306cf` |
| Public fingerprint | `862b7cf5` (chars 1-8, published in audit reports) |
| Non-public status | chars 9-16: ONLY in immutable Commit B blob (4573c81); chars 17-48: NOT IN ANY GIT OBJECT |
| DB state | `is_active=0`, `client_secret_hash=REVOKED_PHASE_A0_1R_20260717T100329Z` |
| Auth rejection proof | Sub-gate 0B (HTTP 401 invalid_client via real uvicorn :18000) |
| Audit event emission | Gate 1 Step 5 (api_client.authentication_rejected) |
| Gate 1 action | **CLOSED** — 2-layer DB rejection + HTTP rejection + audit event all in place. |

---

## Aggregate counts

| Metric | Value |
|---|---|
| Total secrets in inventory | 5 |
| Weak/default values currently in repo | 1 (`backend/.env:10` SECRET_KEY=change-me-in-production) |
| Compromised credentials DB-invalidated | 1 (SEC-05) |
| Purpose-separation refactor needed | 1 (SEC-01 → 3 split secrets) |
| Rotation endpoint needed | 1 (SEC-04 client secret rotation) |
| Audit log emission gaps closed in Gate 1 | 1 (OAuth rejection) |

---

## Char-count reduction progress (chars 9-16 leak surface)

| Timepoint | Source location | Char count leaked |
|---|---|---|
| Phase A0.1R Gate 9 (Commit B 606dc5d) | `scripts/audit/validate_phase_a0_1r.py:35` | 16 chars (`862b7cf5b001b5b7`) |
| A1A Gate 1 Step 1 (commit f6bbd60) | `scripts/audit/validate_phase_a0_1r.py:37` | 8 chars (`fc2cdc2b`) |
| Reduction | 50% current-leak surface | |
| Residual (immutable historical blob 4573c81) | chars 9-16 forever in git object database | cannot amend per charter |

---

End of Secret Inventory.
