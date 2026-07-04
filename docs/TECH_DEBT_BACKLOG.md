# TECH_DEBT_BACKLOG

Pre-existing test failures + known technical debt carried forward from Phase 2.1-B.
Each entry includes: symptom, root cause, why deferred, and the condition that resolves it.

---

## TD-001 — test_templates_api 3 failures (org_id mismatch)

**Status**: Pre-existing (verified via `git stash` on master before Step 4)
**Symptom**: 3 tests fail in `backend/tests/unit/app/api/test_templates_api.py`:
- `TestListTemplates::test_list_after_seed_returns_builtins`
- `TestListTemplates::test_list_search_filters_by_name`
- `TestDeleteTemplate::test_delete_builtin_returns_403`

**Root cause**: The `seeded_templates` fixture (lines 40-81) inserts templates
directly into the DB via `async_session_factory()` for `TEST_ORG_ID =
"org_default1"`, but the test client's `get_current_organization` dependency
returns a different org_id (the conftest mock user's organization). The
templates router `list_templates` filters by `current_org.id` (line 92 of
`app/api/templates.py`), so the seeded rows are invisible to the API.

**Why deferred**: Not introduced by Phase 2.1-B. The failure exists on master
before any Step 4 change. Phase 2.1-B scope is legacy router deletion, not
test isolation hygiene.

**Resolution**: Either
1. Fix the conftest mock user's organization_id to match `org_default1`, or
2. Update the `seeded_templates` fixture to look up the test user's actual
   organization_id from the DB rather than hardcoding `org_default1`, or
3. Use a per-test organization fixture that both the seed and the
   `get_current_organization` dependency resolve to.

**Owner**: TBD (likely Phase 3 — Templates IA work)

---

## TD-002 — test_no_schema_drift_against_fresh_alembic_db flakiness

**Status**: Pre-existing (intermittent)
**Symptom**: `backend/tests/unit/scripts/test_schema_drift.py::test_no_schema_drift_against_fresh_alembic_db`
fails with "Schema drift detected (31 divergences)" when run after other tests
in the same session. Passes in isolation.

**Root cause**: Test isolation — the test creates a fresh alembic DB, runs
`alembic upgrade head`, and compares against the live dev DB. When other tests
run first and leave residual state (test data, partial migrations, uncleaned
tables), the comparison surfaces spurious divergences. The 31 divergences are
not real schema changes — they're artifacts of the test DB being polluted by
prior test runs.

**Why deferred**: Not introduced by Phase 2.1-B. The flakiness exists on
master and is documented in `project_cycle25_schema_drift_audit_2026_07_03.md`
memory: "Test isolation issues: pre-existing flakiness in
test_no_schema_drift_against_fresh_alembic_db". Phase 2.1-B scope is legacy
router deletion, not conftest DB isolation hygiene.

**Resolution**: Either
1. Run the test in a subprocess with a fresh pytest instance (isolated
   alembic DB, no prior test state), or
2. Add a stronger `conftest.py` fixture that drops and recreates the test DB
   between tests, or
3. Move the test to a separate `tests/isolation/` directory that runs in its
   own pytest session.

**Owner**: TBD (likely Phase 3 — test infrastructure hardening)

---

## TD-003 — agents.py legacy router (deferred from Phase 2.1-B Step 3)

**Status**: Deferred per user decision (Phase 2.1-B Step 3 scope reduction)
**Symptom**: `app/api/agents.py` (693 LOC) still mounted on `app/main.py`.
The router exposes 9 management endpoints (create/update/delete/templates/
version/clone/etc.) that the new A2A mainline does not provide — A2A only
exposes discovery (list + card).

**Root cause**: The frontend `agentsApi` (in `services/api.ts`) has 9
hardcoded calls to `/api/agents/*` for agent management. Migrating these to
the Corti-style `/rest/v1/agent_definitions` router requires both backend
implementation and frontend migration — too large for a single Step 3 cut.

**Why deferred**: User chose Option A in Step 3 ("仅删 m2a.py, agents.py 推迟
(Recommended)") to avoid breaking the frontend AgentsPage. Migration scope is
Phase 2.1-C.

**Resolution**: Phase 2.1-C — implement Corti-style
`/rest/v1/agent_definitions` router (create/update/delete/version/list) and
migrate the 9 frontend `agentsApi` calls. Then delete `agents.py` and its
tests.

**Owner**: Phase 2.1-C (target this session)

---

## TD-004 — FastAPI duplicate operation_id warnings (A2A + MCP)

**Status**: Pre-existing (surfaced in Phase 2.1-B test runs)
**Symptom**: FastAPI emits `Duplicate Operation ID` warnings for:
- `get_task` / `cancel_task` in `app/icoder/agent_runtime/a2a/routes_task_stub.py`
- `tools_list` / `tools_call` in `app/icoder/mcp/server.py`

**Root cause**: The A2A + MCP routers are mounted via lifespan (not
`include_router`), so when `app.openapi()` is called (e.g. by
`export_openapi.py` or by the OpenAPI schema endpoint), the routes are
registered twice — once from the lifespan mount, once from the test client
re-triggering startup.

**Why deferred**: Cosmetic — the warnings don't break anything; the
OpenAPI schema is regenerated with stub paths (see `export_openapi.py`).
Phase 2.1-B scope is router deletion, not A2A/MCP mount hygiene.

**Resolution**: Either
1. Move the A2A + MCP mount out of lifespan into a synchronous
   `include_router` call (requires resolving the lifespan-time dependency
   on `app.state.agent_provider`), or
2. Add `operation_id` overrides on the route declarations to make them
   unique, or
3. Suppress the warning at the export_openapi.py level.

**Owner**: TBD (likely Phase 3 — A2A/MCP server hardening)

---

## TD-005 — RuntimeAgentRegistry thread-level locking (no inter-process)

**Status**: Pre-existing (surfaced in health_check)
**Symptom**: `runtime_status` returns `registry_safety.safe = False` with
warning: "RuntimeAgentRegistry uses thread-level locking only. With 8 CPUs,
multi-worker uvicorn deployments may corrupt the registry. Use --workers=1
or switch to a DB-backed registry for production."

**Root cause**: `RuntimeAgentRegistry` uses `threading.Lock` for mutation
safety. Under multi-worker uvicorn (default in production), each worker has
its own registry instance and they can diverge.

**Why deferred**: Phase 2.1-B scope is router deletion, not registry
persistence. The warning is informational; production deployment recommends
`--workers=1` until this is fixed.

**Resolution**: Either
1. Switch `RuntimeAgentRegistry` to use the DB (the `agents` table) as the
   source of truth, with thread-local caching, or
2. Move to a Redis-backed registry for multi-worker safety, or
3. Document `--workers=1` as a hard production requirement and remove the
   warning.

**Owner**: TBD (Phase 4 — production hardening)

---

## Adding a new entry

Before adding an entry, ask: can the debt be paid down now? Each entry must
have:
1. Symptom — what the user/developer sees
2. Root cause — the underlying reason (not just "it's broken")
3. Why deferred — why fixing it is out of scope for the current phase
4. Resolution — the condition or action that pays down the debt
5. Owner — which phase or person will resolve it
