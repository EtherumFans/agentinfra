# Phase A1A Gate 3R.1 — Authoritative Tenant-owned Run Resolver

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.0 (`A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md`)

Closes charter §3R.1 carry-over:

> SSE、Console Trace 和 Partner Trace 在缺少权威 ``RunHistory`` 行时
> 可能继续访问 Event/Trace Store.

The orphan-run defence. Before this gate, three trace-read endpoints
fell through to read the trace store directly when no authoritative
``run_history`` row existed. After this gate, those endpoints refuse
with a generic 404 — and emit a Security Admin-visible ``orphan_run``
audit row.

---

## §1. Charter §3R.1 requirements

| Item | Status |
|---|---|
| SSE event stream refuses when no authoritative RunHistory row | ✅ |
| Console trace endpoint refuses when no authoritative RunHistory row | ✅ |
| Partner trace URL endpoint refuses when no authoritative RunHistory row | ✅ |
| Denial path applies regardless of token's org claim presence | ✅ |
| Denial emits a Security Admin-visible system_audit row | ✅ |
| Denial body uses generic "no trace events" shape (no leak) | ✅ |
| Regression: authoritative MODERN rows still served | ✅ |
| system_audit allowlist recognises the new actions | ✅ |
| legacy_tenancy_attribution classifier recognises the new actions | ✅ |

---

## §2. Deliverables

| Artifact | Path |
|---|---|
| Allowlist extension (system_audit) | `backend/app/services/system_audit.py` |
| Allowlist extension (legacy classifier) | `backend/app/services/legacy_tenancy_attribution.py` |
| SSE orphan-run guard | `backend/app/api/runs.py::stream_run_events` (line 547-602) |
| Partner trace orphan-run guard | `backend/app/api/runs.py::get_run_trace_partner` (line 380-441) |
| Console trace orphan-run guard | `backend/app/api/run_trace.py::_get_run_trace_impl` (line 76-170) |
| Negative + regression test file (12 cases) | `backend/tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py` |
| This closure report | `reports/phase-a1a/A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md` |

---

## §3. Allowlist extension

Two new actions added to both allowlists (Gate 3.6 invariants
require BOTH):

```python
# app/services/system_audit.py::_SYSTEM_AUDIT_ACTIONS_EXTRA
"trace.read.denied.orphan_run",   # Console + Partner denials
"sse.denied.orphan_run",          # SSE denials

# app/services/legacy_tenancy_attribution.py::SYSTEM_AUDIT_ACTIONS
"trace.read.denied.orphan_run",
"sse.denied.orphan_run",
```

The dual-list requirement (charter §3.6) ensures:
1. ``system_audit()`` accepts the action (no ValueError on emit)
2. The historical classifier recognises the action as MODERN_SYSTEM
   so future historical re-classification doesn't demote the row

---

## §4. SSE orphan-run guard

### §4.1 Before Gate 3R.1

```python
async with AsyncSessionLocal() as db:
    sse_row = await get_run_status(db, run_id=run_id)
if sse_row is not None:
    # org-mismatch check
    # visibility classification check
    ...

# FALL-THROUGH: if sse_row is None, code reaches the trace store
events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
```

The signed trace token is valid (HMAC, not expired, run_id matches),
and trace events ARE in the store. The token-holder could read
events for a run with no authoritative row.

### §4.2 After Gate 3R.1

```python
async with AsyncSessionLocal() as db:
    sse_row = await get_run_status(db, run_id=run_id)
if sse_row is None:
    # Orphan-run denial — no authoritative RunHistory row.
    _log.warning("sse.denied orphan_run run_id=%s token_org=%s", ...)
    await _emit_system_audit(
        action="sse.denied.orphan_run",
        resource_type="run_history",
        resource_id=run_id,
        details={"token_org": org_id, "path": "sse"},
    )
    raise HTTPException(status_code=404, detail={
        "code": "TRACE_NOT_FOUND",
        "message": f"no trace events for run_id {run_id!r}",
    })
# Only if the row EXISTS do we proceed to org-mismatch / visibility guards.
```

---

## §5. Partner trace orphan-run guard

### §5.1 Before Gate 3R.1

```python
if claims.organization_id:
    async with AsyncSessionLocal() as db:
        row = await get_run_status(db, run_id=run_id)
    if row is not None and row.organization_id and row.organization_id != claims.organization_id:
        raise HTTPException(status_code=403, ...)
    if row is not None and not is_tenant_visible(...):
        raise HTTPException(status_code=404, ...)

# FALL-THROUGH: if row is None (or token has no org claim), code reaches
# the trace store directly.
```

Two orphan paths existed:
1. Token with org claim + ``row is None`` → falls through
2. Token without org claim → entire if-block skipped, falls through

### §5.2 After Gate 3R.1

```python
async with AsyncSessionLocal() as db:
    row = await get_run_status(db, run_id=run_id)
if row is None:
    _log.warning("trace_url.denied orphan_run run_id=%s token_org=%s", ...)
    await _emit_system_audit(
        action="trace.read.denied.orphan_run",
        resource_type="run_history",
        resource_id=run_id,
        details={"token_org": claims.organization_id, "path": "partner_trace_url"},
    )
    raise HTTPException(status_code=404, detail={
        "code": "TRACE_NOT_FOUND",
        "message": f"no trace events for run_id {run_id!r}",
    })
# Org mismatch / visibility guards follow only when row exists.
if claims.organization_id and row.organization_id and row.organization_id != claims.organization_id:
    raise HTTPException(status_code=403, ...)
if not is_tenant_visible(...):
    raise HTTPException(status_code=404, ...)
```

The orphan check now fires regardless of whether the token carries
an org claim — even a system / diagnostic token can't bypass it.

---

## §6. Console trace orphan-run guard

### §6.1 Before Gate 3R.1

```python
async with AsyncSessionLocal() as db:
    console_row = await get_run_status(db, run_id=run_id)
if console_row is not None:
    # org-mismatch check
    # visibility classification check
    ...

# FALL-THROUGH: if console_row is None, code reaches the trace store.
```

### §6.2 After Gate 3R.1

```python
async with AsyncSessionLocal() as db:
    console_row = await get_run_status(db, run_id=run_id)
if console_row is None:
    _log.warning("console.trace.denied orphan_run run_id=%s request_org=%s", ...)
    await _emit_console_system_audit(
        action="trace.read.denied.orphan_run",
        run_id=run_id,
        details={"request_org": org_id, "path": "console"},
    )
    raise HTTPException(
        status_code=404,
        detail=f"no trace events for run_id {run_id!r}",
    )
# Org / visibility guards follow only when row exists.
```

---

## §7. Test results

```
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py    12 passed

  §1 Console path
    test_console_trace_orphan_run_returns_404             1
    test_console_trace_orphan_run_emits_system_audit      1

  §2 Partner path
    test_partner_trace_orphan_run_returns_404_with_org_token     1
    test_partner_trace_orphan_run_returns_404_with_no_org_token  1

  §3 SSE path
    test_sse_orphan_run_returns_404_with_org_token        1
    test_sse_orphan_run_returns_404_with_no_org_token     1
    test_sse_orphan_run_emits_system_audit                1

  §4 Regression (authoritative MODERN rows still served)
    test_console_trace_modern_row_still_served            1
    test_partner_trace_modern_row_still_served            1
    test_sse_modern_row_still_served                      1

  §5 Allowlist invariants
    test_orphan_run_actions_in_system_audit_allowlist     1
    test_legacy_classifier_recognizes_orphan_run_actions  1
                                                       ──
                                                       12 passed
```

### §7.1 Regression sweep (Gate 3.4 / 3.5 / 3.8 + system_audit unit)

```
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py        11 passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py            7 passed
tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py 19 passed
tests/unit/app/test_system_audit.py                                4 passed
                                                                  ──
                                                                  41 passed
```

No regressions. The orphan-run guard is layered on top of the
existing tenancy guards; it does not change the behaviour for any
path that previously produced 200 or 404.

---

## §8. Defence-in-depth after Gate 3R.1

```
   agent_run endpoint
     → Layer 1: app-level classify_modern_write (Gate 2)
     → Layer 2: DB CHECK chk_*_tenancy_cls (Gate 3.7)
     → Layer 3: tenant_read_policy.is_tenant_visible (Gate 3.2)
     → Layer 4: Authoritative RunHistory row required (Gate 3R.1)
     → Layer 5: Security Admin forensic bypass (Gate 3.2 / 3.6)
```

The new layer closes the "orphan-run attack surface": an attacker
who somehow obtains a valid trace token (e.g. via log leak, support
engineer with stale token) cannot use it to read trace events for a
run that has no authoritative row. The trace store is no longer a
read-path bypass.

---

## §9. Operational implications

- **Failure mode**: a backend restart between ``run_history`` INSERT
  commit and the trace store write would have left the run orphaned
  in trace reads. With Gate 3R.1, those reads now refuse. The
  operator sees ``trace.read.denied.orphan_run`` /
  ``sse.denied.orphan_run`` in the Security Admin audit log and can
  investigate which run was affected.

- **Diagnostic tokens**: any future admin / support tooling that
  issues trace tokens without an org claim (``organization_id=None``)
  is still subject to the orphan-run guard. The token is no longer
  sufficient on its own; an authoritative row must exist.

- **Trace store data from before Gate 3R.1**: if trace events
  exist for runs whose ``run_history`` rows were later purged, those
  reads now refuse. This is the intended behaviour — the alternative
  (silently serving orphan events) is the security gap Gate 3R.1
  closes.

---

## §10. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No ``git push`` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (``d1447f3``)
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No ``git add -A`` (explicit file list in Gate 3R.9)
- No falsification of historical data

---

## §11. Open carry-over to Gate 3R.2

The 11 audit actions identified in Gate 3R.0 §12-13 still have no
material emit sites:

- ``run.cancel`` (partial — only in idempotency test path)
- ``run.timeout``
- ``run.complete``
- ``run.failed``
- ``idempotency.dedup``
- ``api_client.rotate``
- ``context.clear`` (marked N/A per charter)

These are the responsibility of Gate 3R.2.

---

## §12. Verdict

```
PASS_A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.2 (Material audit emit wiring) follows.
