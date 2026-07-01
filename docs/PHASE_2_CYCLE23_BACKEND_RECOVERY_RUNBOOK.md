# Phase 2 Cycle 23 — Backend DB Recovery Runbook

## 1. Context

Cycle 21 §5.2 flagged a pre-existing backend dev startup issue:

> backend dev startup occasionally hits a stale `alembic_version=005` +
> empty schema state (pre-existing — not cycle 21). The fix this cycle
> was `mv data/icoder.db data/icoder.db.bak20260701` + restart so
> `init_db()` rebuilds from scratch. Document a recovery runbook in
> `docs/dev/BACKEND_RECOVERY.md` (cycle 22).

Cycle 22 deferred the runbook to ship the markdown evidence parser
(cycle 22 §5.1). This cycle (23) closes that follow-up by writing the
runbook against the two real `.bak` files that exist in
`backend/data/` and the current 33-table healthy baseline.

## 2. Audit — what the `.bak` files actually contain

Both files were probed with `sqlite3` to ground the runbook in real
state, not hypothetical scenarios.

### `icoder.db.bak20260701` (1.7 MB, dated 2026-07-01 16:19)

```
alembic_version: ('002',)
table_count: 30
tables (deprecated, not in current schema):
  contexts, context_artifact_refs, context_messages,
  context_task_refs, original_input_audit
users_count: 0
gold_cases_count: 0
```

This is the **stale alembic_version** scenario: migration `002` ran
via `alembic upgrade head`, then the schema evolved (context_* tables
dropped in favour of `runtime_sessions`/`runtime_transitions`/
`runtime_audit_records`/`runtime_duc_decisions`; organization/
templates/tickets/customers/coding_review_runs tables added). The DB
was never migrated forward, so `alembic_version` is stuck at `002`
while the actual table shape reflects a partial state between `002`
and `005`.

### `icoder.db.bak2` (872 KB, dated 2026-07-01 16:31)

```
alembic_version: NOT PRESENT
table_count: 0
integrity_check: ok
schema_version: 169
```

This is the **all-tables-dropped** scenario: SQLite header intact,
file integrity OK, but every table was `DROP TABLE`'d. File size
doesn't shrink because SQLite doesn't auto-VACUUM.

### Healthy baseline (fresh `icoder.db`, post-rebuild, 2026-07-01)

```
alembic_version: NOT PRESENT
table_count: 33
integrity_check: ok
users_count: 6 (demo seed)
```

The 33 expected tables (current `Base.metadata`, cycle 23):

```
agents, api_keys, audit_logs, clinical_evidences, code_candidates,
code_mappings, code_tables, coding_review_runs, coding_reviews,
conversation_memories, customers, documents, encounters, experts,
gold_cases, mcp_servers, oauth_clients, oauth_tokens,
organization_invites, organization_members, organizations,
password_reset_tokens, runtime_audit_records, runtime_duc_decisions,
runtime_sessions, runtime_transitions, team_invites, team_members,
templates, tickets, token_blacklist, transactions, users
```

## 3. Spec — what cycle 23 ships

### 3.1 `docs/dev/BACKEND_RECOVERY.md` (NEW)

A standalone runbook covering:

1. **When to use** — symptom table mapping failures to likely causes
2. **Diagnosis** — single-line Python probe (alembic_version,
   table_count, integrity_check) compared against the healthy baseline
3. **Decision tree** — 5 scenarios → all roads lead to "rebuild" except
   the no-action case
4. **Recovery** (dev only) — `mv data/icoder.db data/icoder.db.bakYYYYMMDD`
   + restart uvicorn; `init_db()` rebuilds all 33 tables; `seed.py`
   recreates demo users
5. **Optional selective restore** — `ATTACH DATABASE` pattern with
   column-intersection safety check for schema-drift cases (e.g.
   `bak20260701` has deprecated `contexts` table that current schema
   dropped)
6. **Prevention** — don't mix `init_db()` and `alembic upgrade` in dev;
   dev rule of thumb: stick with default `init_db()` unless you've
   written a new migration
7. **Historical scenarios** — the two real `.bak` files documented as
   teaching examples
8. **Quick reference** — diagnose/recover/verify one-liners

### 3.2 Why no code changes this cycle

The runbook documents an existing recovery procedure (the one already
used in cycle 21 to ship commit 312b931). The fix path
(`mv` + restart) already works — `init_db()` in
`backend/app/database.py:51` uses `Base.metadata.create_all` which is
idempotent and rebuilds missing tables on next startup.

What was missing was the **documentation**: a developer hitting this
for the first time would burn 30+ minutes re-deriving the diagnosis
(`alembic_version` lookup, table count, integrity check) and the
recovery (`mv` + restart). The runbook collapses that to 60 seconds.

## 4. Verification

### 4.1 Runbook accuracy

Every command in the runbook was executed during cycle 23 to verify
output:

- Diagnosis probe against fresh `icoder.db` → `alembic_version NOT
  PRESENT`, `table_count 33` ✓
- Same probe against `icoder.db.bak20260701` → `alembic_version 002`,
  `table_count 30` ✓
- Same probe against `icoder.db.bak2` → `alembic_version NOT PRESENT`,
  `table_count 0` ✓
- `PRAGMA integrity_check` on all three → `ok` ✓
- `curl http://localhost:8000/openapi.json` after fresh rebuild →
  `200` ✓

### 4.2 No regression

This cycle adds a docs file only. No backend, frontend, test, or
contract changes. No tests to re-run — `pytest tests/unit/icoder_runtime/`
still passes 18/18 (cycle 22 baseline), `icoder_ui_diff.py
--feature medical-coding` still 7/7.

## 5. Cycle 24+ follow-up

1. **`alembic` upgrade path audit**: the `alembic/versions/` dir has 5
   migration scripts (`001_initial`, `002_agent_versioning`,
   `003_multi_tenant`, `004_coding_review_run`, `005_context_tables`).
   But the current `Base.metadata` includes tables not in any
   migration (e.g. `customers`, `templates`, `tickets`,
   `organization_invites`). These were added directly to models
   without a migration script — `init_db()` creates them, but
   `alembic upgrade head` does not. Either write the missing
   migrations (so prod deploys don't miss them) or document that prod
   uses `init_db()` (not alembic). Out of scope for cycle 23.
2. **Automated recovery smoke test**: a pytest fixture that creates a
   corrupted `icoder.db` (stale `alembic_version=005` + missing
   tables), runs `init_db()` on it, asserts the result matches the
   healthy baseline. Would catch regressions in `create_all` behaviour
   if SQLAlchemy ever changes the idempotency guarantee. Out of scope
   for cycle 23.

## 6. Files touched

```
docs/dev/BACKEND_RECOVERY.md                              (NEW, runbook)
docs/PHASE_2_CYCLE23_BACKEND_RECOVERY_RUNBOOK.md          (NEW, this cycle spec)
```

No code, test, or contract changes.
