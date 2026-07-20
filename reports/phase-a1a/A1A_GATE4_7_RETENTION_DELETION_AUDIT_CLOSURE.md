# Phase A1A Gate 4.7 — Retention + Deletion + Audit Closure

**Date**: 2026-07-20
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.6 (`A1A_GATE4_6_BROWSER_EMBEDDED_PATIENT_AB.md`)
**Successor**: Gate 4.8 (Full security regression + evidence closure)

Charter §4.7: close three Gate 4.0 §6 carry-overs:

- **Item 31** — `tenant_owned_system_audit` helper for system-scope
  events that are ABOUT a specific tenant (per-tenant cron,
  rate-limit, retention-purge, key-rotation events).
- **Item 32** — `rotate_encrypted_columns` batch helper. Gate 4.4
  shipped encrypt/decrypt + key-id prefix; Gate 4.7 ships the batch
  re-encrypt that makes key rotation real.
- **Item 33** — `RetentionPolicy` + purge primitives. Healthcare
  compliance regimes (China's 网络安全法 §21 + PIPL, ISO 27001)
  require bounded retention windows.

---

## §1. tenant_owned_system_audit helper

`app/services/system_audit.py` now ships two sibling helpers:

| Helper | Use case |
|---|---|
| `system_audit(...)` (existing) | Genuine system-scope event; `organization_id=NULL` |
| `tenant_owned_system_audit(organization_id, ...)` (NEW) | Platform-emitted event about a specific tenant |

Pre-Gate-4.7 a per-tenant system event had two bad options:

1. `system_audit(...)` — loses tenant attribution (NULL org_id)
2. `log_action(allow_null_org=False)` — attaches org_id but loses
   MODERN_SYSTEM tag AND loses the action-allowlist guard

The new helper closes the gap: validates the action is in
`ALL_SYSTEM_AUDIT_ACTIONS`, attaches the supplied `organization_id`,
stamps `tenancy_classification = MODERN_SYSTEM` AND
`tenancy_attribution_source = security_event` with
`tenancy_original_org_id = <tenant>`.

**Allowlist extension**: `retention.purge` added to
`_SYSTEM_AUDIT_ACTIONS_EXTRA` so the audit emit helper itself can
record purge events.

---

## §2. rotate_encrypted_columns batch helper

`app/services/phi_encryption.py::rotate_encrypted_columns(db, columns, dry_run=False, batch_size=500) -> dict[str, int]`.

Operator rotation workflow (added to the runbook):

1. Generate new key: `python -c "from app.services.phi_encryption import generate_key; print(generate_key())"`
2. Set env vars:
   - `ICODER_PHI_ENCRYPTION_KEY_V1=<old key>` (so v1 values can still decrypt)
   - `ICODER_PHI_ENCRYPTION_KEY=<new key>` (the new active key)
   - `ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID=2`
3. Run `rotate_encrypted_columns(db, [(Encounter, "admission_reason"), (Document, "content"), ...])`.
4. Validate all values now carry the `v2:` prefix.
5. Unset `ICODER_PHI_ENCRYPTION_KEY_V1` (defence-in-depth — leaked
   env file should not yield decrypt capability).

**Behaviour**:

- **Fail-closed**: raises `RuntimeError` if no active key configured.
- **dry_run=True**: returns counts per column without modifying data.
- **Plaintext coexistence**: rows still carrying plaintext (the
  local-dev fallback) are encrypted for the first time. This is the
  "adopt encryption" path operators use when flipping from local-dev
  to cloud mode.
- **Idempotent**: rows already at the active key id are skipped.
- **Per-row error isolation**: a corrupt row is logged and skipped;
  the rotation continues with the next row.

---

## §3. RetentionPolicy + purge primitives

`app/services/retention.py` (NEW) ships:

### §3.1 RetentionPolicy dataclass

| Field | Default | Env var |
|---|---|---|
| `audit_log_ttl_days` | 2557 (7 years) | `ICODER_AUDIT_LOG_TTL_DAYS` |
| `run_history_ttl_days` | 90 | `ICODER_RUN_HISTORY_TTL_DAYS` |
| `run_trace_events_ttl_days` | 90 | `ICODER_RUN_TRACE_EVENTS_TTL_DAYS` |

`from_env()` reads env vars; invalid/zero/negative values fall back
to defaults (no infinite retention via env typo).

### §3.2 purge_expired_audit_logs

```python
async def purge_expired_audit_logs(
    db, policy, *, dry_run=False, organization_id=None
) -> int
```

Deletes audit_logs rows older than `policy.audit_log_ttl_days`.
Optional `organization_id` scopes the purge to one tenant.

### §3.3 purge_expired_run_history

```python
async def purge_expired_run_history(
    db, policy, *, dry_run=False, organization_id=None
) -> dict[str, int]
```

Deletes run_history rows older than TTL, cascading to
run_trace_events via the `run_id` FK.

### §3.4 emit_purge_audit

```python
async def emit_purge_audit(
    db, *, table_name, rows_deleted, cutoff,
    organization_id=None, dry_run=False
) -> None
```

Records a `retention.purge` audit event via
`tenant_owned_system_audit` (with org) or `system_audit` (without
org). The event's `details` JSON carries:

```json
{
  "table": "audit_logs",
  "rows_deleted": 42,
  "cutoff": "2026-07-20T...",
  "dry_run": false
}
```

A Security Admin can later answer "what was deleted when?" by
filtering the audit log on `action="retention.purge"`.

---

## §4. Tests

`backend/tests/test_api/test_a1a_gate4_7_retention_deletion_audit.py`
(15 tests):

- §1 tenant_owned_system_audit: 3 tests (accepts allowed action,
  rejects non-allowlist, rejects empty org_id)
- §2 RetentionPolicy.from_env: 4 tests (defaults, env override,
  invalid fallback, zero/negative fallback)
- §3 purge_expired_audit_logs: 3 tests (dry_run, real delete, org scope)
- §4 emit_purge_audit: 2 tests (with org → tenant_owned, without org → system)
- §5 rotate_encrypted_columns fail-closed: 2 tests (refuses when
  disabled, signature smoke)
- §6 rotate_encrypted_columns happy path: 1 test (writes with v1,
  rotates to v2, verifies decrypt round-trip)

Test report: `15 passed in 1.76s`.

---

## §5. Files touched

### Code

| File | Change |
|---|---|
| `backend/app/services/system_audit.py` | New `tenant_owned_system_audit` helper; `retention.purge` added to `_SYSTEM_AUDIT_ACTIONS_EXTRA` |
| `backend/app/services/phi_encryption.py` | New `rotate_encrypted_columns` batch helper (fail-closed, dry_run, per-column counts) |
| `backend/app/services/retention.py` | **NEW**. `RetentionPolicy`, `purge_expired_audit_logs`, `purge_expired_run_history`, `emit_purge_audit` |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_7_retention_deletion_audit.py` | **NEW**. 15 tests. |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_7_RETENTION_DELETION_AUDIT_CLOSURE.md` | This closure report. |

---

## §6. Forbidden list — re-confirmation

Gate 4.7 did NOT:

- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Wire the purge primitives into an in-process scheduler — operators
  wire them to their cron / systemd / Kubernetes CronJob of choice.
  An in-process scheduler is out of scope for Gate 4.7 (charter
  forbids the scope creep).
- Bypass the action-allowlist guard — `tenant_owned_system_audit`
  reuses the same `_is_allowed_system_action` check as `system_audit`.

---

## §7. Provisional verdict

```
PASS_A1A_GATE4_7_RETENTION_DELETION_AUDIT_CLOSURE_VERIFIED
```

Gate 4.0 §6 items 31/32/33 closed. The platform now has:

- A typed entry point for tenant-attributed system events.
- A survivable key-rotation workflow (decrypt-old + re-encrypt-new
  in batch, with dry_run validation).
- A defensible retention posture (audit logs ≥ 7y / China
  cybersecurity law compliant; run history bounded at 90d to
  constrain DB growth; every purge itself audited).

---

## §8. Next

Gate 4.8 — Full security regression + evidence closure.
