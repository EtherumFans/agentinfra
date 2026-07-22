# A1B-AE-R.1.a — Task State Machine + ThreadAuthRegistry DB Migration

**Sub-gate**: R.1.a (first commit of R.1 — Agent Runtime closure)
**Date**: 2026-07-22
**Branch**: `phase-a1b/agent-expert-runtime-verification`
**Predecessor**: R.0 charter (`b7bde8f`)

## Verdict

```
PASS_A1B_AE_R_1_A_TASK_STATE_MACHINE_AND_THREAD_AUTH_DB_MIGRATION_FILED
```

FILED, not VERIFIED — per A1B-AE-R.0 charter §10, sub-gate verdicts use `_FILED` until the phase terminal R.6 promotes the bundle to `_VERIFIED` (or downgrades to `PARTIAL_..._FILED`).

## Scope

R.1.a closes the first half of A1B-AE's Agent Runtime tech debt:

| A1B-AE gap | R.1.a fix |
|---|---|
| `routes_task_stub.py` returns HTTP 501 `UNSUPPORTED_OPERATION` on `GET /tasks/{id}` and `POST /tasks/{id}/cancel` | Replaced with real `routes_task.py` backed by `context_task_refs.state` state machine |
| `ThreadAuthRegistry` uses in-process dict (`"production deployments should replace it with a Redis/DB-backed store"`) | Rewritten DB-backed: `is_first_message()` queries `context_messages` count for `context_id` |
| `context_task_refs.state` has no CHECK constraint (any string accepted) | Migration 024 bakes `CHECK (state IN ('submitted', 'working', 'completed', 'failed', 'canceled'))` into the DDL |

R.1.b (next commit) will add `DELETE /api/icoder/contexts/{id}` real scrub + cross-tenant 404 negative tests.
R.1.c (optional) may add an end-to-end DeepSeek Message→Task→Artifact run.

## Files added / modified

**Added**:
- `backend/alembic/versions/024_context_task_state_check.py` — re-creates 5 `context_*` tables (migration 006 had dropped them) with inline CHECK on `context_task_refs.state`
- `backend/app/icoder/agent_runtime/a2a/task_state.py` — `TaskState` enum + `_TRANSITIONS` table + `InvalidTaskTransition` + `next_state()` / `is_terminal()` helpers
- `backend/app/icoder/agent_runtime/a2a/routes_task.py` — `build_task_router()` returning APIRouter with `GET /{task_id}` + `POST /{task_id}/cancel`, uses `Depends(get_db)`
- `backend/tests/test_api/test_a1b_ae_r_1_task_state_machine.py` — 16 tests covering schema, state machine, endpoints, ThreadAuthRegistry DB-backed

**Modified**:
- `backend/app/icoder/agent_runtime/a2a/__init__.py` — export `build_task_router` (was `build_task_stub_router`)
- `backend/app/icoder/agent_runtime/a2a/a2a_routes.py` — include real task router; routers dict key `"task"` (was `"task_stub"`)
- `backend/app/icoder/agent_runtime/a2a/thread_auth.py` — `ThreadAuthRegistry.__init__` now requires `session: AsyncSession`; all methods are coroutines; in-memory `_ThreadState` and module-level singleton removed
- `backend/app/icoder/agent_runtime/context/db_models.py` — `ContextTaskRefRow.__table_args__` adds `CheckConstraint(name="ck_context_task_refs_state", ...)` so `Base.metadata.create_all()` path also emits the CHECK
- `backend/tests/integration/icoder/a2a/test_endpoints.py` — 2 tests previously asserting 501 now assert 404 `TASK_NOT_FOUND`; `routers` key `"task"` (was `"task_stub"`)
- `backend/tests/test_api/test_a1b_ae_5_message_task_context.py` — 3 in-memory `ThreadAuthRegistry` tests replaced with 1 structural signature assertion (the DB-backed rewrite made the in-memory tests obsolete; DB-backed coverage lives in `test_a1b_ae_r_1_task_state_machine.py`)
- `backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py` — head version assertions bumped from `"021"` → `"024"` (A1B-AE.3/022 + A1B-AE.4/023 + A1B-AE-R.1.a/024 — this cleanup was missed by A1B-AE.3 and A1B-AE.4)
- `backend/tests/test_api/test_a1a_gate3r_8_regression_security_negative.py` — L11 test head assertion bumped from `"021"` → `"024"`

**Deleted**:
- `backend/app/icoder/agent_runtime/a2a/routes_task_stub.py`

## Design decisions

### Migration 024 — CREATE TABLE IF NOT EXISTS (not ALTER TABLE)

Migration 006 (P1.2) dropped the 5 `context_*` tables because the P1.2 runtime no longer persisted Context server-side. A1B-AE.5 re-introduced the SQLAlchemy models but did not restore the alembic chain — every test that hit `init_db()` got the tables via `Base.metadata`, but alembic stayed gap-ful.

Three rewrite attempts:

1. **`op.create_check_constraint`** → failed: SQLite `NotImplementedError: No support for ALTER of constraints in SQLite dialect`.
2. **`op.batch_alter_table`** → failed: `NoSuchTableError: context_task_refs` (migration 006 dropped it, so there's nothing to batch on).
3. **`CREATE TABLE IF NOT EXISTS`** with inline CHECK → passes. The downgrade path `DROP TABLE IF EXISTS` mirrors migration 006 so the chain round-trips.

The `IF NOT EXISTS` qualifiers mean `init_db()` + `alembic upgrade head` compose cleanly: whichever path runs first creates the tables; the second is a no-op.

### ThreadAuthRegistry — DB-derived, not auxiliary-state

The A1B-AE.5 in-memory dict tracked "first message seen" per `context_id`. The DB-backed rewrite uses a simpler invariant:

```
is_first_message(context_id) := (SELECT COUNT(*) FROM context_messages
                                 WHERE context_id = ?) == 0
```

This survives process restart, works across replicas, and needs no extra column. The `register_first_message()` method is now a no-op kept only so legacy callers compile — the actual persistence is the `ContextMessageRow` insert by the inbound handler.

### Task state machine — 5 states, explicit transition table

```
submitted → working
working   → completed | failed | canceled
submitted → canceled  (cancel-before-start)
```

`TERMINAL_STATES = {completed, failed, canceled}`. `POST /tasks/{id}/cancel` returns:
- `200` with `state=canceled` envelope if transition legal
- `409 TASK_NOT_CANCELABLE` if current state is terminal
- `404 TASK_NOT_FOUND` if `task_id` absent

## Test evidence

```
tests/test_api/test_a1b_ae_r_1_task_state_machine.py     16 passed
tests/integration/icoder/a2a/test_endpoints.py           10 passed / 4 pre-existing fail *
tests/test_api/test_a1b_ae_5_message_task_context.py     11 passed
tests/test_api/test_a1a_gate3r_5_migration_portability.py 7 passed
tests/test_api/test_a1a_gate3r_8_regression_security_negative.py::test_L11_...  1 passed
```

\* The 4 `test_endpoints.py` failures (`test_well_known_agent_json_lists_cards`, `test_llms_txt_renders_markdown`, `test_agents_list_returns_simplified_cards`, `test_agent_card_returns_full_card`) assert English `"MedCodER Coding Review Agent"` but the Agent Card returns Chinese `"MedCodER 编码审核智能体"` after A1B-AE.3 localized the card. Verified pre-existing at baseline `b7bde8f` via `git stash` + re-run. Not a regression introduced by R.1.a.

## 5-tuple state (unchanged)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

R.1.a does not promote any of these — that is reserved for the R.6 terminal reconciliation.

## Forbidden verdicts (8) — honoured

None of the 8 forbidden verdicts (`PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`) appears in this sub-gate, its report, or its commit message.

## Charter §11 forbidden ops — honoured

- No `git push` (branch remains local)
- No `merge --no-ff` to master
- No `amend` (R.1.a creates a fresh commit)
- No `rebase`
- No `reset --hard`
- No `git add -A` / `-a` (explicit file list below)
- No force-push

## Next

R.1.b — Context scrub (real delete) + cross-tenant 404 negative tests.
