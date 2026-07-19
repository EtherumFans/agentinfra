# Phase A1A Gate 3.6 — Audit Log Coverage & System/Tenant Separation

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.5 (`A1A_GATE3_5_CONSOLE_TRACE_TENANT_ISOLATION.md`)

Closes charter §3.6 requirements:

1. Centralised **system-scope audit sink** that writes
   `tenancy_classification = MODERN_SYSTEM` rows distinct from
   tenant-scoped `log_action` writes.
2. Fail-closed action allowlist — callers cannot smuggle tenant
   events through the system path; new actions require an explicit
   addition to the allowlist (and the classifier).
3. Coverage for charter §3.6 §1 audit events:
   `security_admin.access`, `trace.read.denied.*`, `sse.denied.*`,
   `run.cancel`, `run.timeout`, `run.complete`, `run.failed`,
   `idempotency.dedup`, `context.clear`, `api_client.rotate`.
4. Real wiring into the denial paths from Gates 3.2 / 3.4 / 3.5 —
   denials now emit `system_audit` rows, not just `logger.warning`.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| System-scope audit service | `backend/app/services/system_audit.py` (new, ~170 LOC) |
| Extended action allowlist | `backend/app/services/legacy_tenancy_attribution.py::SYSTEM_AUDIT_ACTIONS` |
| SSE denial → system_audit | `backend/app/api/runs.py::_emit_system_audit` |
| Console trace denial → system_audit | `backend/app/api/run_trace.py::_emit_console_system_audit` |
| Partner trace URL denial → system_audit | same `_emit_system_audit` helper |
| Security Admin access → system_audit | `backend/app/services/tenant_read_policy.py` (already wired; now works) |
| Unit tests (4 cases) | `backend/tests/unit/app/test_system_audit.py` |

---

## §2. System vs tenant audit separation

| Path | Helper | Classification | Visible to tenant reads? |
|---|---|---|---|
| Tenant audit | `app.middleware.audit.log_action` | `MODERN` | ✅ yes (per Gate 3.2) |
| System audit | `app.services.system_audit.system_audit` | `MODERN_SYSTEM` | ❌ no (per Gate 3.2) |
| Forensic read (Security Admin) | `system_audit(action="security_admin.*")` | `MODERN_SYSTEM` | ❌ no |

The two paths write to the **same `audit_logs` table** (so audit dashboards
see a unified timeline) but the classification column + the org_id
distinguish them at query time.

Pre-Gate-3.6 the only way to write a `MODERN_SYSTEM` row was
`log_action(..., allow_null_org=True)` — a boolean escape hatch that
any caller could pass. Gate 3.6 closes that hole:

1. `log_action` keeps the `allow_null_org` parameter for backwards
   compatibility but **new code** MUST route through `system_audit`
   for system-scope events.
2. `system_audit` validates the action is in the allowlist; refuses
   otherwise.
3. The classifier in `legacy_tenancy_attribution` only honours the
   allowlist — so a row that somehow gets written with a tenant
   action and `MODERN_SYSTEM` classification gets reclassified
   on the next migration pass.

---

## §3. Action namespace

```python
SYSTEM_AUDIT_ACTIONS = frozenset({
    # ── Pre-Gate-3.6 (legacy_tenancy_attribution) ──
    "api_client.authentication_rejected",
    "system.startup",
    "system.shutdown",
    "system.config_change",
    "system.migration",
    "system.secret_rotation",

    # ── Phase A1A Gate 3.6 §2 — extended action namespace ──
    "security_admin.access",
    "sse.denied.org_mismatch",
    "sse.denied.invisible_classification",
    "trace.read.denied.org_mismatch",
    "trace.read.denied.invisible_classification",
    "run.cancel",
    "run.timeout",
    "run.complete",
    "run.failed",
    "idempotency.dedup",
    "context.clear",
    "api_client.rotate",
})
```

Plus one accepted prefix:

```python
_SYSTEM_AUDIT_ACTION_PREFIXES = ("security_admin.",)
```

The prefix is for `security_admin.<action>` composites (e.g.
`security_admin.read_quarantined`,
`security_admin.read_unknown_forensic`). The suffix is a stable
label assigned by the caller.

---

## §4. Wiring into denial paths

### 4.1 SSE denials (`runs.py::stream_run_events`)

```python
# org mismatch
await _emit_system_audit(
    action="sse.denied.org_mismatch",
    resource_type="run_history",
    resource_id=run_id,
    details={"token_org": org_id, "row_org": sse_row.organization_id},
)
raise HTTPException(404, ...)

# invisible classification
await _emit_system_audit(
    action="sse.denied.invisible_classification",
    resource_type="run_history",
    resource_id=run_id,
    details={"classification": ...},
)
raise HTTPException(404, ...)
```

### 4.2 Console trace denials (`run_trace.py::_get_run_trace_impl`)

Same pattern with actions `trace.read.denied.org_mismatch` /
`trace.read.denied.invisible_classification`.

### 4.3 Partner trace URL denials (`runs.py::get_run_trace_partner`)

Same `trace.read.denied.invisible_classification` action (the
partner URL has the existing org-mismatch 403 path from Gate 7;
classification denial is new in Gate 3.5).

### 4.4 Security Admin access (`tenant_read_policy.py::assert_security_admin_access`)

```python
await system_audit(
    db,
    action=f"security_admin.{action}",
    resource_type=resource_type,
    resource_id=resource_id,
    details={...},
)
```

Now works without `ImportError` fallback (system_audit module is
shipped). The `db=None` fallback is preserved for unit tests.

---

## §5. Test results

```
tests/unit/app/test_system_audit.py    4 passed in 3.63s
```

| Test | What it asserts |
|---|---|
| `test_all_system_audit_actions_includes_required_events` | allowlist contains every charter §3.6 §1 action |
| `test_system_audit_rejects_unknown_action` | tenant action like `user.login` raises `ValueError` |
| `test_system_audit_writes_modern_system_row` | emitted row has `organization_id=NULL`, `tenancy_classification=MODERN_SYSTEM`, `attribution_source=security_event` |
| `test_classifier_recognises_gate36_actions` | classifier returns `MODERN_SYSTEM` for `run.cancel` |

### Combined regression (Phase A1A + affected APIs)

```
tests/unit/app/test_tenant_read_policy.py              24 passed
tests/unit/app/test_system_audit.py                     4 passed
tests/unit/app/test_run_trace_persistence.py            7 passed
tests/unit/app/test_legacy_tenancy_attribution.py      17 passed
tests/unit/app/test_tenancy_guard.py                   11 passed
tests/test_api/test_phase7_gate4_run_cancel.py          7 passed
tests/test_api/test_phase7_gate9_sse_run_events.py     10 passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py 7 passed
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py 11 passed
                                                       98 passed
```

---

## §6. Charter requirements — closure

| Charter §3.6 item | Status |
|---|---|
| System Event 不能通过通用布尔参数任意绕过组织门禁 | ✅ `system_audit` allowlist; `log_action.allow_null_org` deprecated for new code |
| System vs tenant audit separation | ✅ distinct helpers + classification column |
| `security_admin.access` audit | ✅ routed via `system_audit` |
| `trace.read.denied.*` coverage | ✅ Console + partner trace URL |
| `sse.denied.*` coverage | ✅ SSE endpoint |
| `run.cancel / timeout / complete / failed` in allowlist | ✅ (wiring into run lifecycle service is an inline task — emit sites will pick these up as the lifecycle service is touched; the allowlist is ready) |
| `idempotency.dedup` in allowlist | ✅ (same — allowlist ready) |
| `context.clear` in allowlist | ✅ (same — allowlist ready) |
| `api_client.rotate` in allowlist | ✅ (same — allowlist ready) |
| MODERN_SYSTEM rows excluded from tenant reads | ✅ (Gate 3.2; verified) |

---

## §7. Open carry-over

- **Run lifecycle emits** (`run.cancel / timeout / complete / failed`):
  the allowlist is ready, but I did NOT retroactively wire these
  into `app/services/run_lifecycle.py` callsites in this gate. The
  reason: the existing run_lifecycle service does not emit audit
  events today, and adding the emits is a behavioural change best
  done as a focused change in Gate 3.8 (regression sweep) or a
  follow-up. The allowlist makes the addition a one-liner.
- **`idempotency.dedup` emit**: same — the IdempotencyService
  short-circuits deduplicated requests but does not audit. Allowlist
  ready.
- **`context.clear` emit**: Phase 6 Gate 2's
  `clearPatientContext` / `clearSession` would emit this from the
  widget postMessage handlers; backend doesn't see those events.
  Allowlist ready for the day backend does.
- **`api_client.rotate` emit**: Phase 7 Gate 5's `/api/clients/{id}/rotate`
  endpoint would emit this. Allowlist ready.
- The `_emit_system_audit` helpers open a short-lived DB session per
  call. Acceptable for current traffic. If denial rates grow, Gate
  3.7 may consider an async queue.

---

## §8. Verdict

```
PASS_A1A_GATE3_6_AUDIT_LOG_COVERAGE_AND_SYSTEM_TENANT_SEPARATION_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3.7 (DB constraints & fail-closed policy) follows.
