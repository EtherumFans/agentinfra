# A1B-AE-R.1.b — Context Scrub + Cross-Tenant Isolation

**Sub-gate**: R.1.b (second commit of R.1 — Agent Runtime closure)
**Date**: 2026-07-22
**Branch**: `phase-a1b/agent-expert-runtime-verification`
**Predecessor**: R.1.a (`1b7c750`)

## Verdict

```
PASS_A1B_AE_R_1_B_CONTEXT_SCRUB_AND_CROSS_TENANT_ISOLATION_FILED
```

FILED per charter §10 — phase terminal R.6 decides promotion to `_VERIFIED`.

## Scope

R.1.b closes the second half of A1B-AE Agent Runtime tech debt:

| A1B-AE gap | R.1.b fix |
|---|---|
| Context deletion was soft-only (`status=EXPIRED` via `update_status`) — no real row scrub | `ContextLifecycle.destroy_now(context_id, organization_id=...)` issues a physical DELETE that removes the `contexts` row + all 4 child tables |
| No user-facing `DELETE` endpoint | New `routes_context.py` exposes `DELETE /api/icoder/contexts/{id}` returning 200 with `{kind: "context", deleted: true}` envelope |
| Task / Context queries were not org-scoped — any tenant could read or mutate any row | `routes_task.py` GET + POST now join `context_task_refs → contexts.organization_id` and filter by `current_org.id`; cross-tenant reads return 404 (no leak) |
| `contexts` table had no tenant column | Migration 025 adds `contexts.organization_id` (NOT NULL, default `org_default1`) |

## Files added / modified

**Added**:
- `backend/alembic/versions/025_context_organization_id.py` — `contexts.organization_id` column via batch_alter (nullable → backfill → NOT NULL), following the Phase A1A Gate 2 / Gate 4.2 pattern
- `backend/app/icoder/agent_runtime/a2a/routes_context.py` — `build_context_router()` returning APIRouter with `DELETE /api/icoder/contexts/{id}` (auth-bound, cross-tenant-safe)
- `backend/tests/test_api/test_a1b_ae_r_1_b_context_scrub_cross_tenant.py` — 11 tests (schema, hard_delete, destroy_now, DELETE endpoint, cross-tenant DELETE/GET/cancel, same-org control)

**Modified**:
- `backend/app/icoder/agent_runtime/context/db_models.py` — `ContextRow.organization_id` mapped column + index
- `backend/app/icoder/agent_runtime/context/context.py` — `Context.organization_id` field (default `org_default1`)
- `backend/app/icoder/agent_runtime/context/context_repository.py` — `_row_to_context` reads org; `create_context` writes org; new `get_for_org(context_id, organization_id)` for tenant-scoped lookup; new `hard_delete_context(context_id)` manual scrub of all 5 tables
- `backend/app/icoder/agent_runtime/context/context_lifecycle.py` — `create()` accepts `organization_id`; new `destroy_now(context_id, organization_id=None, reason=...)` for user-initiated scrub (raises `ContextIsolationError` on org mismatch)
- `backend/app/icoder/agent_runtime/a2a/routes_task.py` — GET + POST now depend on `get_current_organization`; query joins through `contexts` for org filter
- `backend/app/icoder/agent_runtime/a2a/a2a_routes.py` — mounts context router; `build_a2a_routers()` returns 6 keys (was 5)
- `backend/app/icoder/agent_runtime/a2a/errors.py` — new `CONTEXT_NOT_FOUND` code + factory
- `backend/app/icoder/agent_runtime/a2a/__init__.py` — re-exports `context_not_found` and `build_context_router`
- `backend/tests/integration/icoder/a2a/test_endpoints.py` — standalone client fixture installs `get_current_organization` override (R.1.b requires auth); router count 6 (was 5)
- `backend/tests/integration/icoder/context/test_context_repository.py` — task state `"x"` → `"submitted"` (must satisfy R.1.a CHECK constraint)
- `backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py` — head version assertions `024` → `025`
- `backend/tests/test_api/test_a1a_gate3r_8_regression_security_negative.py` — L11 head assertion `024` → `025`

## Design decisions

### Cross-tenant query pattern — join through `contexts`

The Task tables don't carry their own `organization_id`; instead they reference `context_id`, which in turn references `contexts.organization_id`. The tenant filter is therefore a JOIN:

```python
select(ContextTaskRefRow)
    .join(ContextRow, ContextRow.id == ContextTaskRefRow.context_id)
    .where(
        ContextTaskRefRow.task_id == task_id,
        ContextRow.organization_id == organization_id,
    )
```

A task that exists under a different tenant returns `None` — the caller translates both "not found" and "wrong tenant" to `404 TASK_NOT_FOUND`. Never leak existence.

### `destroy_now` — explicit child scrub (no PRAGMA dependency)

SQLite's default is `PRAGMA foreign_keys=OFF`, and the app does not currently install a connect-time listener to flip it. The FK `ON DELETE CASCADE` declared in migration 024 therefore doesn't actually fire. R.1.b's `hard_delete_context` manually issues `DELETE` against each child table in dependency order — the scrub is correct regardless of PRAGMA state. A follow-up could install the PRAGMA listener globally and simplify `hard_delete_context` back to `session.delete(parent)`, but that is broader blast radius than R.1.b.

### `organization_id` default — `org_default1`

The default matches:
- the test-bypass mock org id (see `tests/conftest.py::_make_mock_org`)
- the dev DB's default tenant
- the convention used by Phase A1A Gate 2 (migration 016) and Gate 4.2 (migration 021)

So rows created without an explicit org land in the same bucket as the test-bypass JWT. Production callers (`lifecycle.create(organization_id=current_org.id, ...)`) override the default.

## Test evidence

```
tests/test_api/test_a1b_ae_r_1_b_context_scrub_cross_tenant.py   11 passed
tests/test_api/test_a1b_ae_r_1_task_state_machine.py             16 passed
tests/test_api/test_a1b_ae_5_message_task_context.py             11 passed
tests/test_api/test_a1a_gate3r_5_migration_portability.py         7 passed
tests/test_api/test_a1a_gate3r_8_...::test_L11_...                1 passed
tests/integration/icoder/a2a/test_endpoints.py                   10 passed / 4 pre-existing *
tests/integration/icoder/context/test_context_repository.py      22 passed / 0 failed
```

\* The 4 `test_endpoints.py` failures are the pre-existing English/Chinese card name mismatch (A1B-AE.3 localization, verified at baseline `b7bde8f` via `git stash`). Not a regression introduced by R.1.b.

## Cross-tenant negative tests (mandatory per charter)

| Scenario | Setup | Expected | Verified |
|---|---|---|---|
| Cross-tenant DELETE context | Row under ORG_A, DELETE with ORG_B JWT | 404 CONTEXT_NOT_FOUND, row survives | ✓ |
| Cross-tenant GET task | Task under ORG_A, GET with ORG_B JWT | 404 TASK_NOT_FOUND | ✓ |
| Cross-tenant POST cancel | Task under ORG_A working, POST with ORG_B | 404 TASK_NOT_FOUND, state unchanged | ✓ |
| Same-org control | All above with ORG_A JWT | 200 / state transition succeeds | ✓ |

## 5-tuple state (unchanged)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Forbidden verdicts (8) — honoured

None of `PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` appears in this sub-gate, its report, or its commit message.

## Charter §11 forbidden ops — honoured

- No `git push` (branch remains local)
- No `merge --no-ff` to master
- No `amend`
- No `rebase`
- No `reset --hard`
- No `git add -A` / `-a` (explicit file list)
- No force-push

## R.1 status — complete

R.1 (Agent Runtime closure) is now complete in 2 commits:
- R.1.a (`1b7c750`) — Task state machine + ThreadAuth DB migration
- R.1.b (this commit) — Context scrub + cross-tenant isolation

R.1.c (end-to-end DeepSeek Message→Task→Artifact) is optional per plan; deferred unless R.5 surfaces a gap that needs it.

## Next

R.2 — Preset Agent materialization (cdi / drg-dip / claim-check Packs + legacy orphan deletion + Journey 7 clone fix).
