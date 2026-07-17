# A1A Gate 1 Deliverable #4 — Key Rotation (DEFERRED)

> Charter §6.8 requires this deliverable. Gate 1 Step 4 closes the
> related defense (fail-closed env policy) but full purpose-separation
> + rotation support exceeds the Gate 1 minimum. Documented here as
> A1A-G1-DEFERRED-01.
>
> Status: **DEFERRED to follow-up** — see §1 for rationale.

---

## §1. Why deferred

Splitting `SECRET_KEY` into purpose-separated keys requires touching 6
backend files + updating ~15 existing tests. The work is mechanical
but high-touch: each call site must use the correct new key, and any
mismatch produces a 401 / 500 that's hard to debug without
integration tests.

| File | Lines to change | What |
|---|---|---|
| `backend/app/config.py` | +15 | Add 3 new fields + validators + migration shim |
| `backend/app/api/oauth.py:75` | 1 | `jwt.encode(payload, settings.JWT_SIGNING_SECRET, ...)` |
| `backend/app/middleware/auth.py:66,78,107,112` | 4 | Use `JWT_SIGNING_SECRET` |
| `backend/app/services/preview_ticket.py:87-88` | 2 | Use `PREVIEW_TICKET_SIGNING_SECRET` |
| `backend/app/services/trace_token.py:94-96` | 2 | Use `TRACE_LINK_SIGNING_SECRET` |
| `.env.cloud.example` | +6 | Document 3 new vars |
| Test fixtures | ~15 | Update mocks |

**Estimated effort**: ~4-6 hours.

---

## §2. Why it's safe to defer

| Risk dimension | Current mitigation | Risk if deferred to Gate 2 |
|---|---|---|
| Compromised SECRET_KEY | Fail-closed policy blocks weak literals at boot (Step 4) | LOW — same mitigation applies |
| Compromised per-API-Client secret | DB hash + is_active (Phase A0.1R Gate 1) + audit event (Step 5) | LOW — independent of SECRET_KEY |
| Compromised JWT signing key | N/A — same SECRET_KEY used everywhere | MEDIUM — single point of failure |
| Cross-purpose key reuse | None — preview/trace keys derived via SHA-256 | LOW — derivation provides some separation |
| Operational rotation | Restart required (no online rotation) | LOW — cloud KMS supports rotation; redeploy picks it up |

The actual incident (Phase A0.1R) was NOT a SECRET_KEY issue — it was
a per-API-Client secret leak. Gate 1's fail-closed + audit emission +
DB invalidation already closes the incident class.

---

## §3. Target architecture (when implemented)

### Three purpose-separated keys

```python
# backend/app/config.py (target state)
JWT_SIGNING_SECRET: str = ""           # JWT encode + decode
PREVIEW_TICKET_SIGNING_SECRET: str = "" # preview.html bootstrap ticket HMAC
TRACE_LINK_SIGNING_SECRET: str = ""     # signed trace URL HMAC
```

### Migration shim (preserves backward compat)

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    # Gate 2 migration: each purpose-separated key falls back to SECRET_KEY
    # so existing deployments don't break on first deploy after upgrade.
    if not self.JWT_SIGNING_SECRET:
        self.JWT_SIGNING_SECRET = self.SECRET_KEY
    if not self.PREVIEW_TICKET_SIGNING_SECRET:
        # Derive via SHA-256 to preserve preview_ticket.py behavior
        import hashlib
        self.PREVIEW_TICKET_SIGNING_SECRET = hashlib.sha256(
            (self.SECRET_KEY + ":preview").encode()
        ).hexdigest()
    if not self.TRACE_LINK_SIGNING_SECRET:
        import hashlib
        self.TRACE_LINK_SIGNING_SECRET = hashlib.sha256(
            (self.SECRET_KEY + ":trace").encode()
        ).hexdigest()
    self._validate_fail_closed_policy()
```

### Rotation endpoint (Gate 2+)

```
POST /api/oauth/clients/{id}/rotate-secret
  → generates new secret
  → stores new hash in oauth_clients.client_secret_hash_new
  → old hash remains valid for ROTATION_GRACE_PERIOD_SECONDS (300s default)
  → audit event api_client.secret_rotated emitted
  → returns new plaintext ONCE
```

Dual-hash window allows zero-downtime rotation.

---

## §4. Acceptance criteria (when Gate 2 picks this up)

1. Three new config fields + validators + migration shim
2. All 4 JWT/HMAC call sites updated to use purpose-specific key
3. `.env.cloud.example` documents 3 new vars
4. Fail-closed policy extended: cloud mode requires all 3 keys non-empty
5. New endpoint `POST /api/oauth/clients/{id}/rotate-secret` with dual-hash window
6. New audit event `api_client.secret_rotated`
7. ~20 new tests covering rotation flow, dual-hash window, key separation
8. Frontend Console → Settings → API Clients → "Rotate secret" button
9. Documentation update in `docs/cloud/API_CLIENT_MODEL.md`

---

## §5. Charter compliance note

Phase A1A charter §3 lists Gate 1 deliverables but §6.4 explicitly
allows phasing:

> "Items requiring backend re-architecture (key rotation, secret
> lifecycle UI) may be deferred to Gate 2 with documented rationale
> and acceptance criteria."

This document provides both rationale (§1-§2) and acceptance criteria
(§4). The deferral is charter-compliant.

---

## §6. Tracking

| Field | Value |
|---|---|
| Ticket ID | A1A-G1-DEFERRED-01 |
| Severity | P2 (medium — single-key design has 18-month incident-free history) |
| Estimated effort | 4-6 hours |
| Target gate | Gate 2 (Tenancy and Data Isolation) or beyond |
| Blocking Gate 1 verdict | NO |

---

End of Key Rotation (deferred).
