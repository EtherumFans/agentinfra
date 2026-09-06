# PostgreSQL integration compatibility

The integration workflow keeps the complete historical suite on its isolated
SQLite database while promoting database-sensitive contracts to PostgreSQL in
reviewable waves. Tests in the PostgreSQL matrix carry the
`postgresql_compat` marker.

## Promotion criteria

A promoted test must:

- run against the Alembic-built PostgreSQL schema rather than ORM `create_all`;
- use a session-scoped asyncio loop when sharing the session-scoped asyncpg
  engine;
- provision and clean up its own tenant-scoped data;
- avoid SQLite-only SQL and implicit coercions;
- remain green in the full SQLite integration suite.

## Current waves

| Wave | Coverage | Test modules |
| --- | --- | --- |
| Foundational | role provisioning, Alembic schema, cross-process trace persistence | dedicated PostgreSQL contract tests |
| Wave 1 | 13 A2A context/task/artifact, observability, feedback, retention, and tenant-isolation contracts | `test_agentic_context_resources.py`, `test_agentic_observability_feedback.py` |
| Wave 2 | 40 Connector CRUD, execution-policy, transport, audit, and graph-runtime contracts | `test_agent_connectors.py`, `test_connector_executor.py`, `test_connector_graph_runtime.py` |
| Wave 3 | 62 Context repository, lifecycle, garbage-collection, audit-retention, and isolation contracts | `test_context_repository.py`, `test_context_lifecycle.py`, `test_context_garbage_collector.py`, `test_context_audit.py` |
| Wave 4 | 30 Context schema and Local Expert/Memory contracts, including application-role RLS checks | `test_db_schema.py`, database-marked cases in `test_a1b_ae_r_4_local_expert_completion.py` |

Wave 2 also aligns the persisted Agent identifier contract with public stable
keys: `agents.id` and every relational Agent reference use `VARCHAR(128)`.
This is required for built-in identifiers such as `medical-coding-agent`,
whose length SQLite accepted despite the former `VARCHAR(12)` declaration.

## Wave 4 boundaries and execution

Wave 4 covers 13 schema contracts and 17 memory/interview contracts. It checks
round-trips after clearing the ORM identity map, server defaults, foreign keys,
composite primary keys, task-state constraints, cascading children, retained
audit rows, memory encryption/recall/profile/session scope, sequential ingest
replay, and persisted interview state. Calculator-only tests are not counted
as PostgreSQL evidence.

Both dialects enable foreign-key enforcement and seed real Organization/User
dependencies. PostgreSQL uses the Alembic-built schema without ORM DDL. A
transaction listener rebinds the fixture's tenant after commit/rollback; the
tests do not claim to validate request authentication through this listener.

The PostgreSQL gate requires a non-superuser, non-BYPASSRLS application role
without schema CREATE permission or parent-role membership. Three PostgreSQL-
only cases cover missing/wrong tenant access and same-connection pool reuse.
They intentionally skip on SQLite, which cannot provide PostgreSQL RLS. The
separate SQLite legacy-overlong-key regression is not in the PostgreSQL marker.
Existing Wave 1–3 jobs retain their prior role configuration; this is not a
claim that all historical business tests now run under the application role.

Two runtime incompatibilities were reproduced and fixed:

- Memory recall now binds naive UTC against its legacy TIMESTAMP WITHOUT TIME
  ZONE column, avoiding asyncpg's aware/naive datetime error.
- Context/message keys longer than VARCHAR(64) now use the full SHA-256 hex
  digest, not truncation. Short keys are unchanged and original identifiers
  remain in encrypted source metadata. Session-context reads accept the
  original key, and replay checks also recognize historical SQLite overlong
  keys. Sequential idempotence is tested; concurrent exactly-
  once ingest remains outside this wave (there is no uniqueness/upsert change).

No schema migration or production schema revision change is required.

CI executes the marked cases in both the Integration workflow and the PR PHI
gate. Integration provisions/verifies the app role after Wave 3; the PR gate
starts with a separate migration identity and then runs Wave 4 as the app role.
Both produce always-uploaded JUnit evidence and are required steps in the
same-commit release verifier. The tests disable native embedding loading and
external LLM calls and use ephemeral test encryption keys, not clinical data.

Against an isolated PostgreSQL database already migrated to Alembic head,
set both `DATABASE_URL` and `ICODER_DATABASE_URL` to the application-role
`postgresql+asyncpg://...` URL and `ICODER_TEST_USE_PREMIGRATED_SCHEMA=1`, then
run from `backend`:

```text
python -m pytest tests/integration/icoder/context/test_db_schema.py tests/test_api/test_a1b_ae_r_4_local_expert_completion.py -m postgresql_compat -o asyncio_default_test_loop_scope=session -v --tb=short
```

For SQLite, set both URLs to an isolated SQLite test database, unset the
pre-migrated flag, and omit `-m postgresql_compat` to include calculator and
legacy-key tests. Never use a business database: the root SQLite test fixture
recreates its schema.

## Local verification (2026-09-06)

- PostgreSQL 18.6, Alembic head `075`, separate migration/app identities:
  Wave 4 **30 passed**, with no skips in the marked gate.
- PostgreSQL Wave 3 regression using its existing administrator-role test
  configuration: **62 passed** after the shared-fixture change.
- Combined SQLite Context schema/repository, Local Expert/Memory, safety,
  Context unit and related API regression: **196 passed, 4 skipped**. Three
  skips are PostgreSQL-only RLS cases; one legacy file-inspection test skips
  because this local run used an in-memory SQLite database.
- CI evidence/release-validator contracts: **55 passed**. `git diff --check`
  passed; role verification found no privilege drift across 92 objects and
  9 functions. Wave 4 tenant/user fixture rows were cleaned up.

Local Python was 3.12. The wired GitHub jobs use Python 3.11 / PostgreSQL 16;
their new remote runs remain to be executed after commit/push. These local
results do not claim a full historical Integration sweep, live-provider
validation, or clinical quality. The isolated local PostgreSQL instance was
stopped after validation; no existing service or business database was changed.

## Remaining scope

The full historical Integration suite still runs on SQLite. Further work
includes promoting other database-heavy modules and expanding business-level
application-role coverage beyond Wave 4. Full-suite PostgreSQL compatibility,
concurrent exactly-once memory ingestion, live embedding/model quality, and
production deployment approval are not established by this gate.
