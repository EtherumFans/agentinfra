# Phase A1A Gate 3.4 — SSE Event Tenant Isolation (F04 closed)

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.3 (`A1A_GATE3_3_DATABASE_BACKED_TRACE_PERSISTENCE.md`)

Closes charter §3.4 requirements and the **F04 carry-over defect**
from Phase A1A Gate 2:

> SSE event stream must verify the requesting principal belongs to
> the same org as the run, must not leak cross-org run existence,
> and must enforce tenant visibility classification on par with the
> non-streaming read paths.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| SSE cross-check + classification guard | `backend/app/api/runs.py::stream_run_events` |
| Negative-path integration tests (7 cases) | `backend/tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py` |

---

## §2. Pre-Gate-3.4 state (the F04 gap)

The SSE endpoint `GET /api/v1/runs/{run_id}/events?token=...` was
**already protected** by:

1. Signed trace token (Gate 7) — HMAC-SHA256, bound to
   `(run_id, organization_id)`, 24h TTL.
2. Token signature / expiry / run-mismatch validation.
3. Org-scoped store lookup via `store.get_run_scoped(run_id, org_id)`.

What was **missing**:

- No `RunHistory.organization_id` cross-check. If a run was
  re-attributed to a different org after token issuance (operator
  action), the stale token would still stream events.
- No tenant visibility classification guard. A `QUARANTINED` or
  `LEGACY_TENANT_UNKNOWN` row would still stream to its old token.
- No audit emit on denial.

These are exactly the F04 carry-over from Gate 2.

---

## §3. Post-Gate-3.4 state

Added a defence-in-depth block after token validation but before
the store lookup:

```python
async with AsyncSessionLocal() as db:
    sse_row = await get_run_status(db, run_id=run_id)
if sse_row is not None:
    # Org cross-check
    if (
        sse_row.organization_id is not None
        and org_id is not None
        and sse_row.organization_id != org_id
    ):
        _log.warning("sse.denied org_mismatch ...")
        raise HTTPException(status_code=404, ... TRACE_NOT_FOUND ...)

    # Visibility classification guard
    if not is_tenant_visible(sse_row.tenancy_classification):
        _log.warning("sse.denied invisible_classification ...")
        raise HTTPException(status_code=404, ... TRACE_NOT_FOUND ...)
```

Both denial paths return the **same** 404 shape as "no events for
run_id" so the caller can't distinguish "run doesn't exist" / "run
belongs to another org" / "run is quarantined".

---

## §4. Test results

```
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py    7 passed in 33.37s
```

| Test | What it asserts |
|---|---|
| `test_sse_denied_on_org_mismatch` | token org=A, row org=B → 404 TRACE_NOT_FOUND; response text contains neither org id |
| `test_sse_denied_on_invisible_classification[QUARANTINED]` | QUARANTINED row → 404, no leak of `cls` string |
| `test_sse_denied_on_invisible_classification[LEGACY_TENANT_UNKNOWN]` | same |
| `test_sse_denied_on_invisible_classification[LEGACY_TENANT_AMBIGUOUS]` | same |
| `test_sse_denied_on_invisible_classification[MODERN_SYSTEM]` | same |
| `test_sse_denied_on_null_classification` | NULL cls (pre-Gate-2 row) → 404 |
| `test_sse_passes_for_visible_classification` | MODERN row + matching org → 200 + stream |

### Phase 7 Gate 9 regression

```
tests/test_api/test_phase7_gate9_sse_run_events.py    10 passed
```

The existing happy-path SSE tests all still pass — the new
cross-check is a no-op when `sse_row is None` (test fixtures don't
seed run_history rows) or when classification is visible.

---

## §5. Audit emission

Denials are logged via `logger.warning("sse.denied ...")`. Today
this lands in app stdout/stderr; Gate 3.6 will route the same
events to `system_audit` so they appear in the audit dashboard
under actions `sse.denied.org_mismatch` /
`sse.denied.invisible_classification`.

The log format is parseable:

```
sse.denied org_mismatch run_id=R token_org=org-A row_org=org-B
sse.denied invisible_classification run_id=R classification=QUARANTINED
```

---

## §6. Charter requirements — closure

| F04 item | Status |
|---|---|
| SSE verifies principal org matches run org | ✅ RunHistory.organization_id cross-check |
| SSE does not leak cross-org run existence | ✅ same 404 shape as "no events" |
| SSE enforces tenant visibility classification | ✅ reuses `is_tenant_visible` from Gate 3.2 |
| SSE audits denials | ✅ logger.warning now; system_audit wired in Gate 3.6 |

---

## §7. Open carry-over

- The cross-check opens a short-lived DB session per request.
  Acceptable for current traffic. Gate 3.7 will consider batching
  when the run_history table grows past 1M rows.
- The signed trace token binds to `(run_id, organization_id)` only
  — not to a snapshot of the row's `tenancy_classification`. If a
  row is retroactively quarantined after token issuance, the new
  classification guard catches it (because the guard reads the row
  live); the token doesn't need to embed classification.

---

## §8. Verdict

```
PASS_A1A_GATE3_4_SSE_TENANT_ISOLATION_VERIFIED
```

F04 (SSE event tenant isolation) — **CLOSED**.

Forbidden verdicts (charter §22) remain forbidden.

Gate 3.5 (Console RunTrace tenant isolation — F05) follows.
