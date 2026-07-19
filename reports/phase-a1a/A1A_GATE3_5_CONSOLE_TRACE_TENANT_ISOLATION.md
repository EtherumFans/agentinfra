# Phase A1A Gate 3.5 — Console RunTrace Tenant Isolation (F05 closed)

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.4 (`A1A_GATE3_4_SSE_TENANT_ISOLATION.md`)

Closes charter §3.5 requirements and the **F05 carry-over defect**
from Phase A1A Gate 2:

> Console RunTrace endpoint (`GET /api/runtime/runs/{run_id}/trace`)
> and the partner trace URL endpoint
> (`GET /api/v1/runs/{run_id}/trace?token=`) must both enforce
> tenant visibility classification on par with the other read paths.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| Console trace guard | `backend/app/api/run_trace.py::_get_run_trace_impl` |
| Partner trace URL guard | `backend/app/api/runs.py::get_run_trace_url` |
| Negative-path integration tests (11 cases) | `backend/tests/test_api/test_a1a_gate3_5_console_trace_isolation.py` |

---

## §2. Pre-Gate-3.5 state (the F05 gap)

**Console endpoint** (`/api/runtime/runs/{run_id}/trace`):
- Org-scoped via `get_request_tenant(request)` → `store.get_run_scoped`
- **Missing**: `RunHistory.organization_id` cross-check
- **Missing**: tenant visibility classification guard

**Partner trace URL endpoint** (`/api/v1/runs/{run_id}/trace?token=`):
- Token validation (Gate 7) ✅
- `RunHistory.organization_id` cross-check (returns 403 on mismatch
  — token is valid so existence is already authenticated) ✅
- **Missing**: tenant visibility classification guard

Both endpoints would surface traces for runs retroactively
classified as `QUARANTINED` / `LEGACY_TENANT_UNKNOWN` /
`LEGACY_TENANT_AMBIGUOUS` / `MODERN_SYSTEM`.

---

## §3. Post-Gate-3.5 state

### 3.1 Console endpoint

```python
async with AsyncSessionLocal() as db:
    console_row = await get_run_status(db, run_id=run_id)
if console_row is not None:
    # Org cross-check (NEW for Console)
    if (
        console_row.organization_id is not None
        and org_id is not None
        and console_row.organization_id != org_id
    ):
        _log.warning("console.trace.denied org_mismatch ...")
        raise HTTPException(404, ...)

    # Visibility classification guard (NEW)
    if not is_tenant_visible(console_row.tenancy_classification):
        _log.warning("console.trace.denied invisible_classification ...")
        raise HTTPException(404, ...)
```

### 3.2 Partner trace URL endpoint

After the existing org mismatch 403 block, added:

```python
if row is not None and not is_tenant_visible(
    getattr(row, "tenancy_classification", None)
):
    _log.warning("trace_url.denied invisible_classification ...")
    raise HTTPException(status_code=404, ...)
```

Note the asymmetry: org mismatch on a **valid token** returns 403
(token is valid, we already authenticated existence); classification
mismatch returns 404 (no leak that the run exists at all).

---

## §4. Test results

```
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py    11 passed in 40.79s
```

| Test | Endpoint | What it asserts |
|---|---|---|
| `test_console_trace_denied_on_org_mismatch` | Console | tenant=org-A, row org=B → 404 |
| `test_console_trace_denied_on_invisible_classification[QUARANTINED]` | Console | → 404 TRACE_NOT_FOUND |
| `test_console_trace_denied_on_invisible_classification[LEGACY_TENANT_UNKNOWN]` | Console | → 404 |
| `test_console_trace_denied_on_invisible_classification[LEGACY_TENANT_AMBIGUOUS]` | Console | → 404 |
| `test_console_trace_denied_on_invisible_classification[MODERN_SYSTEM]` | Console | → 404 |
| `test_console_trace_denied_on_null_classification` | Console | NULL → 404 |
| `test_console_trace_passes_for_visible_modern` | Console | MODERN + matching org → 200 |
| `test_partner_trace_url_denied_on_invisible_classification[QUARANTINED]` | Partner | → 404 |
| `test_partner_trace_url_denied_on_invisible_classification[LEGACY_TENANT_UNKNOWN]` | Partner | → 404 |
| `test_partner_trace_url_denied_on_invisible_classification[MODERN_SYSTEM]` | Partner | → 404 |
| `test_partner_trace_url_passes_for_modern` | Partner | MODERN + matching org → 200 |

---

## §5. Charter requirements — closure

| F05 item | Status |
|---|---|
| Console endpoint verifies run belongs to requesting tenant | ✅ RunHistory.organization_id cross-check |
| Console endpoint enforces visibility classification | ✅ reuses `is_tenant_visible` |
| Partner trace URL enforces visibility classification | ✅ same helper, post-token-validation |
| No cross-org existence leak | ✅ same 404 shape as "no events" |
| Denials audited | ✅ logger.warning now; system_audit wired in Gate 3.6 |

F05 (Console RunTrace tenant isolation) — **CLOSED**.

---

## §6. Verdict

```
PASS_A1A_GATE3_5_CONSOLE_TRACE_TENANT_ISOLATION_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3.6 (Audit log coverage & system/tenant separation) follows.
