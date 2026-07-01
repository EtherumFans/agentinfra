# Backend DB Recovery Runbook

This runbook covers recovery scenarios for the iCoDer backend SQLite
database at `backend/data/icoder.db`. It applies to **local development
only** — managed cloud SaaS deployments use region-shared PostgreSQL,
not this file.

## When to use this runbook

Reach for this doc when backend startup or an API call fails with one
of these symptoms:

| Symptom | Likely cause |
|---|---|
| `sqlite3.OperationalError: no such table: X` on an API call | Tables missing from `icoder.db` |
| `sqlalchemy.exc.OperationalError: ... no such column: X` | Schema drift (table exists but old shape) |
| Backend startup hangs or crashes on `init_db()` / `seed()` | Corrupted SQLite file |
| `alembic upgrade head` fails with "Target database is not up to date" | Stale `alembic_version` row |
| `RuntimeError: ... table already exists` during `alembic upgrade` | Tables created by `init_db()` collide with migration expectations |

## Diagnosis

Run this single-line probe from `backend/`:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
cur = conn.cursor()
try:
    cur.execute('SELECT version_num FROM alembic_version')
    print('alembic_version:', cur.fetchone())
except Exception as e:
    print('alembic_version: NOT PRESENT (clean)')
cur.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\")
print('table_count:', cur.fetchone())
cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name\")
print('tables:', [r[0] for r in cur.fetchall()])
print('integrity:', cur.execute('PRAGMA integrity_check').fetchone())
conn.close()
"
```

Compare against the **healthy baseline** (cycle 23, 2026-07-01):

| Field | Healthy value |
|---|---|
| `alembic_version` | `NOT PRESENT (clean)` |
| `table_count` | `33` |
| `integrity` | `ok` |

The 33 expected tables (current `Base.metadata`):
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

## Decision tree

```
alembic_version      table_count   action
─────────────────────────────────────────────────────────────────
NOT PRESENT          33            → no action, DB is healthy
NOT PRESENT          0             → Scenario A: empty DB (rebuild)
NOT PRESENT          < 33          → Scenario B: partial DB (rebuild)
'002'..'005'         any           → Scenario C: stale alembic (rebuild)
any                  33            → Scenario D: schema drift (rebuild)
'005'                33            → at-head; if API still fails, schema drift (rebuild)
```

All roads lead to "rebuild" except the no-action case — the rebuild is
cheap (~5s on dev SQLite) and idempotent, so when in doubt, rebuild.

## Recovery (dev only — destroys data)

**Warning**: this deletes all data in `icoder.db`. Dev DBs are
expendable (seed.py recreates demo users on startup), but if you have
manual test data you want to keep, do **Optional selective restore**
below *before* restarting.

### Step 1 — Back up the broken DB

```bash
cd backend
mv data/icoder.db "data/icoder.db.bak$(date +%Y%m%d)"
```

Use ISO date suffix (`YYYYMMDD`) — matches existing convention
(`icoder.db.bak20260701`, `icoder.db.bak2`).

If you've already done this dance today and the date suffix collides,
append `_HHMM` or `_2` to disambiguate.

### Step 2 — Restart uvicorn

```bash
# From backend/
python -m uvicorn app.main:app --port 8000
```

`init_db()` (in `app/database.py:51`) runs `Base.metadata.create_all`
on startup, which recreates all 33 tables. Then `seed.py` runs (dev
mode only) to create demo users — see `app/seed.py` for the demo
accounts.

Look for these log lines on successful startup:

```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO sqlalchemy.engine.Engine BEGIN (implicit)
... CREATE TABLE users ...
... CREATE TABLE organizations ...
... (33 tables) ...
INFO sqlalchemy.engine.Engine COMMIT
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 3 — Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/openapi.json
# expect: 200
```

Re-run the diagnosis probe from above; `alembic_version` should be
`NOT PRESENT` and `table_count` should be `33`.

## Optional selective restore

If the broken DB has data you want to preserve (e.g. manually curated
`gold_cases`, `code_tables`, or `templates`), restore them from the
`.bak` file **after** Step 2 completes.

### Restore a single table

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
conn.execute(\"ATTACH DATABASE 'data/icoder.db.bak20260701' AS bak\")
# Example: restore gold_cases
conn.execute('INSERT OR IGNORE INTO main.gold_cases SELECT * FROM bak.gold_cases')
conn.commit()
print('rows restored:', conn.execute('SELECT count(*) FROM gold_cases').fetchone())
conn.close()
"
```

### Restore with schema drift

If the `.bak` table shape doesn't match current (e.g. `bak20260701`
has deprecated `contexts` / `original_input_audit` tables that the
current schema dropped), explicit column lists are safer than `SELECT *`:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
conn.execute(\"ATTACH DATABASE 'data/icoder.db.bak20260701' AS bak\")
# Only restore columns that exist in both schemas
conn.execute('''
INSERT OR IGNORE INTO main.gold_cases
  (id, case_id, admission_text, gold_dx_codes, gold_px_codes, source, created_at, updated_at)
SELECT
  id, case_id, admission_text, gold_dx_codes, gold_px_codes, source, created_at, updated_at
FROM bak.gold_cases
''')
conn.commit()
conn.close()
"
```

To list the column intersection before restoring:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
conn.execute(\"ATTACH DATABASE 'data/icoder.db.bak20260701' AS bak\")
main_cols = {r[1] for r in conn.execute('PRAGMA table_info(main.gold_cases)').fetchall()}
bak_cols = {r[1] for r in conn.execute('PRAGMA table_info(bak.gold_cases)').fetchall()}
print('intersection:', sorted(main_cols & bak_cols))
print('main-only:', sorted(main_cols - bak_cols))
print('bak-only:', sorted(bak_cols - main_cols))
conn.close()
"
```

## Prevention

### Don't mix `init_db()` and `alembic upgrade` in dev

- `init_db()` (default on uvicorn startup) uses `Base.metadata.create_all`
  — idempotent, only creates missing tables, **does not** stamp
  `alembic_version`.
- `alembic upgrade head` (run via `python -m app.database migrate`) runs
  migration scripts 001→006 and stamps `alembic_version=006`.

If you run `alembic upgrade head` once and then later modify a model,
subsequent `init_db()` startups won't apply your model changes (because
the tables already exist). And `alembic upgrade head` won't re-run
migrations it thinks are done (because `alembic_version=006` says head).

**Dev rule of thumb**: use `init_db()` (default) for greenfield
development. Only run `alembic upgrade head` if you've actually written
a new migration script and want to apply it.

### Production (managed cloud SaaS)

Production uses PostgreSQL on managed cloud, not this SQLite file.
**Prod actually uses `init_db()` (uvicorn lifespan calls it on every
boot), not `alembic upgrade head`** — the alembic chain is a
dev/manual tool, kept in parity with `Base.metadata` so anyone who
needs a real migration (e.g. zero-downtime column add on PostgreSQL)
has a correct starting point. Cycle 24 closed a 5-table gap that had
accumulated between the alembic chain and the model definitions. See
`docs/cloud/CLOUD_DEPLOYMENT.md` §6 for the prod deploy pipeline.

## Known recovery scenarios (historical)

These `.bak` files exist in `backend/data/` (gitignored) as of
2026-07-01 and document the real recovery scenarios that motivated
this runbook:

### `icoder.db.bak20260701` (1.7 MB)

**State**: `alembic_version='002'`, 30 tables (4 deprecated: `contexts`,
`context_artifact_refs`, `context_messages`, `context_task_refs`,
`original_input_audit`).

**How it got there**: migration `002` ran via `alembic upgrade`, then
the schema evolved (context_* tables dropped, organization/templates/
tickets/customers/coding_review_runs tables added). The DB was never
migrated forward — `alembic_version` was stuck at `002`, but the table
shape reflected a partial state between `002` and `005`.

**Lesson**: never run `alembic upgrade head` mid-development unless
you're prepared to either roll forward to head or wipe and rebuild.
This is the canonical "stale alembic_version" scenario.

### `icoder.db.bak2` (872 KB)

**State**: `alembic_version` NOT PRESENT, 0 tables. File integrity OK
(`PRAGMA integrity_check = ok`).

**How it got there**: every table was `DROP TABLE`'d (probably via
`DROP TABLE IF EXISTS` for each, or a `Base.metadata.drop_all()` run).
The file size doesn't shrink because SQLite doesn't auto-VACUUM.

**Lesson**: `DROP TABLE` is not a recovery — `init_db()` will rebuild
the tables but you'll have lost all data. Use `mv data/icoder.db ...`
instead, which preserves the file intact as a `.bak` for selective
restore.

## Quick reference

```bash
# Diagnose
cd backend && python -c "
import sqlite3
c = sqlite3.connect('data/icoder.db'); cur = c.cursor()
try: print('alembic:', cur.execute('SELECT version_num FROM alembic_version').fetchone())
except: print('alembic: NOT PRESENT (clean)')
print('tables:', cur.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\").fetchone())
c.close()"

# Recover
cd backend && mv data/icoder.db "data/icoder.db.bak$(date +%Y%m%d)" \
  && python -m uvicorn app.main:app --port 8000

# Verify
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/openapi.json
```
