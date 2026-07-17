# A1A Gate 1 Deliverable #5 — API Client Secret Lifecycle (DEFERRED)

> Documents the current state of API Client secret lifecycle and the
> gap relative to Corti parity. Full rotation UI + dual-hash window
> deferred to Gate 2 as A1A-G1-DEFERRED-02.
>
> Status: **DEFERRED** — see §3 for rationale.

---

## §1. Current state (post-Gate 1)

| Lifecycle stage | Implementation | Test coverage |
|---|---|---|
| **Generate** | `OAuthClient.generate_client_secret()` returns plaintext + bcrypt hash | ✅ covered |
| **Store** | DB column `oauth_clients.client_secret_hash` stores hash; plaintext NEVER persisted | ✅ covered |
| **Verify** | `OAuthClient.verify_secret(secret, hash)` constant-time compare | ✅ covered |
| **Display** | Plaintext returned exactly ONCE on creation (`/api/oauth/clients` POST) | ✅ covered |
| **Reject (disabled)** | `is_active=0` filters client from auth query → 401 invalid_client | ✅ covered (sub-gate 0B) |
| **Audit rejection** | `api_client.authentication_rejected` event on every 401 (Gate 1 Step 5) | ✅ covered (6 new tests) |
| **Revoke** | `DELETE /api/oauth/clients/{id}` sets `is_active=0` (logical revoke) | ✅ covered |
| **Rotate** | ❌ NOT IMPLEMENTED — must delete + recreate (loses client_id) | ❌ gap |
| **Dual-hash window** | ❌ NOT IMPLEMENTED — rotation would invalidate existing tokens instantly | ❌ gap |
| **Audit rotation** | ❌ NOT IMPLEMENTED — no `api_client.secret_rotated` event | ❌ gap |
| **Force-expire** | ❌ NOT IMPLEMENTED — no `secret_expires_at` column | ❌ gap |

---

## §2. Corti parity gap

Corti Console → Settings → API Clients supports:
- Rotate secret in-place (same client_id retained)
- Set expiration date (forces rotation)
- View last-used timestamp (already implemented in iCoDer ✅)
- Revoke immediately

iCoDer currently supports revoke only. Rotation requires delete +
recreate, which:
- Changes the `client_id` (Corti-compatible partners may have it hard-coded)
- Loses `last_used_at` history
- Loses any audit trail linking old + new secrets

This is a **product UX gap**, not a security gap (the underlying hash +
verify + reject flow is sound).

---

## §3. Why deferred

### Required changes

| Change | LOC estimate |
|---|---|
| Alembic migration: add `client_secret_hash_new` + `secret_expires_at` columns | ~30 |
| `POST /api/oauth/clients/{id}/rotate-secret` endpoint | ~80 |
| `OAuthClient.verify_secret` dual-hash window logic | ~20 |
| Background task: expire secrets past `secret_expires_at` | ~50 |
| Audit event `api_client.secret_rotated` emission | ~30 |
| Frontend Console rotation UI | ~150 |
| Tests (rotation flow, dual-hash window, expiry, audit) | ~200 LOC / 15-20 tests |
| Documentation update | ~100 |

**Total**: ~660 LOC + 15-20 tests, ~6-8 hours of focused work.

### Risk if deferred to Gate 2

| Risk | Severity |
|---|---|
| Partner unable to rotate without losing client_id | MEDIUM — workaround exists (delete + recreate) |
| No forced expiration | LOW — partners can rotate voluntarily; admin can disable |
| No rotation audit trail | LOW — disable events ARE audited; rotation is a UX nicety |

None of these risks block Gate 1's verdict. The compromised credential
(SEC-05) is DB-invalidated; the system rejects any auth attempt with
the old secret. Rotation parity is a UX/cleanliness issue, not a
containment issue.

---

## §4. Target implementation

### Schema additions (alembic 016)

```python
class OAuthClient(Base):
    # ... existing fields ...
    client_secret_hash_new: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    secret_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    secret_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

### Rotation endpoint

```
POST /api/oauth/clients/{client_id}/rotate-secret
Auth: current_user (admin only)
Body: { "expire_old_after_seconds": 300 }  # dual-hash window

Response:
{
  "client_id": "...",          # unchanged
  "client_secret": "ics_...",  # new plaintext, shown ONCE
  "old_secret_valid_until": "2026-07-17T15:00:00Z",
  "rotated_at": "2026-07-17T14:55:00Z"
}
```

### Dual-hash verification

```python
@staticmethod
def verify_secret(secret: str, client: OAuthClient) -> bool:
    # Check new hash first (post-rotation)
    if client.client_secret_hash_new:
        if bcrypt.checkpw(secret.encode(), client.client_secret_hash_new.encode()):
            return True
    # Check old hash (still valid during grace period)
    if client.client_secret_hash:
        if bcrypt.checkpw(secret.encode(), client.client_secret_hash.encode()):
            # Within grace period?
            if client.secret_rotated_at:
                grace_expires = client.secret_rotated_at + timedelta(seconds=300)
                if datetime.now(timezone.utc) < grace_expires:
                    return True
            return False
    return False
```

### Audit event

```python
await log_action(
    db,
    user_id=current_user.id,
    username=current_user.username,
    action="api_client.secret_rotated",
    resource_type="api_client",
    resource_id=client.client_id,
    details={
        "rotated_at": datetime.now(timezone.utc).isoformat(),
        "grace_period_seconds": 300,
        "rotated_by_user_id": current_user.id,
    },
    status="success",
)
```

---

## §5. Acceptance criteria

1. Alembic 016 adds 3 new columns
2. `POST /api/oauth/clients/{id}/rotate-secret` endpoint with admin-only auth
3. Dual-hash window (300s default, configurable)
4. Audit event `api_client.secret_rotated` emitted
5. Background task force-expires secrets past `secret_expires_at`
6. Frontend Console "Rotate secret" button in API Clients settings
7. ~15-20 new tests covering rotation flow, grace period, expiry, audit
8. Documentation update in `docs/cloud/API_CLIENT_MODEL.md`

---

## §6. Tracking

| Field | Value |
|---|---|
| Ticket ID | A1A-G1-DEFERRED-02 |
| Severity | P2 (medium — UX gap, workaround exists) |
| Estimated effort | 6-8 hours |
| Target gate | Gate 2 or Gate 3 |
| Blocking Gate 1 verdict | NO |

---

End of API Client Secret Lifecycle (deferred).
