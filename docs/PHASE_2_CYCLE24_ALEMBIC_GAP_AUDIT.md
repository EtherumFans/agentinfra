# Phase 2 — Cycle 24: Alembic Gap Audit & Migration 006

**Date**: 2026-07-02
**Branch**: master
**Predecessor**: Cycle 23 (DB recovery runbook)
**Successor**: Cycle 25 (TBD — likely column-level parity for migrations 001/002/004)

## Goal

Close the table-level gap between `alembic upgrade head` and `Base.metadata.create_all` (init_db) that was documented as "known debt" in cycle 23's runbook §Prevention. After cycle 24, both paths produce the same 33-table schema, and `alembic upgrade head` works end-to-end on a fresh SQLite DB (previously blocked by migration 003's `asyncio.run` bug).

## Background

Cycle 23's runbook (`docs/dev/BACKEND_RECOVERY.md`) documented two failure modes:
1. **Stale alembic_version** — `icoder.db.bak20260701` had `alembic_version='002'` + 30 tables (4 deprecated context_* + 5 missing P1.2 gap tables)
2. **Empty DB after DROP TABLE** — `icoder.db.bak2` had 0 tables but 872 KB file size (SQLite doesn't auto-VACUUM)

The runbook §Prevention said: "Dev rule of thumb: use init_db() (default) for greenfield development. Only run alembic upgrade head if you've actually written a new migration script." But it didn't actually fix the alembic chain — it just warned against using it.

Cycle 24 closes that gap. After cycle 24, `alembic upgrade head` is a viable alternative to `init_db()` for fresh-DB setup, and the runbook's Prevention section is updated to reflect that the chain is now correct.

## Audit findings

### Table-level gap (cycle 24 scope — FIXED)

Comparing `Base.metadata` (33 tables) vs `alembic upgrade head` after migrations 001→005 (33 tables, wrong shape):

**5 deprecated tables in alembic but not in Base.metadata** (created by migration 005, removed from models in P1.2):
- `contexts`
- `context_messages`
- `context_task_refs`
- `context_artifact_refs`
- `original_input_audit`

**5 gap tables in Base.metadata but not in any migration** (added directly to models in P1.2 without a migration):
- `customers`
- `templates`
- `tickets`
- `password_reset_tokens`
- `token_blacklist`

### Migration 003 asyncio.run bug (cycle 24 scope — FIXED)

Migration 003 (`003_multi_tenant.py`) called `asyncio.run(_upgrade_async())` from inside the alembic migration function. But `alembic/env.py:63` already calls `asyncio.run(run_migrations_online())` — so when 003's `upgrade()` runs, it's already inside a running event loop, and `asyncio.run()` raises:

```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

This was a latent bug since at least cycle 21. Never surfaced because cycles 21-23 all used `init_db()` (Base.metadata.create_all) which bypasses alembic entirely.

### Column-level divergences (partial cycle 24 scope — FIXED for cycle 24 tables)

After fixing the table-level gap and the asyncio bug, I ran a column-level parity check between `alembic upgrade head` and `init_db()` on a fresh DB. Found 26 column-level divergences total:

**8 cycle 24 tables (touched by migrations 003 + 006) — FIXED in this cycle:**
- `organizations`, `organization_members`, `organization_invites` (migration 003)
- `customers`, `templates`, `tickets`, `token_blacklist`, `password_reset_tokens` (migration 006)

Issues fixed:
- `organization_id` columns declared as `sa.String(length=12)` but model uses `ForeignKey("organizations.id")` with no explicit String length → inferred as `String()` (no length)
- `organization_members.user_id` and `organization_invites.invited_by` same issue (FK to `users.id` which is `String()` from TimestampMixin)
- `tickets.created_by_id` same issue (FK to `users.id`)
- `organizations.settings` declared `nullable=True` but model uses `Mapped[dict]` which implies `nullable=False`
- Spurious `server_default` clauses on `region`, `nfr`, `description`, `category`, `language`, `is_builtin`, `scope`, `status`, `priority`, `revoked_reason`, `is_used`, `plan`, `is_active`, `role`, `status` — models use Python-side `default=` only, no `server_default=`. Only `created_at`/`updated_at` (from TimestampMixin) have `server_default=func.now()`.

**18 pre-existing divergences (out of cycle 24 scope — DOCUMENTED AS DEBT):**
- `agents.version` / `agents.status` — migration 002 added `server_default='1.0.0'` / `server_default='draft'`, but model uses Python-side `default=` only
- `coding_review_runs.*` (8 columns) — migration 004 has wrong `nullable` for created_at/updated_at and spurious `server_default` for 6 columns
- `audit_logs.agent_id` / `agent_account_id` / `delegated_by_user_id` — added to AuditLog model after migration 001, no migration
- `coding_reviews.evidence_ranking` / `confidence_calibration` — added to CodingReview model after migration 001, no migration
- `users.token_version` — added to User model after migration 001, no migration

These pre-existing divergences are documented as debt for a future cycle (likely cycle 25: column-level parity for migrations 001/002/004).

## Fix

### Migration 006 (NEW)

`backend/alembic/versions/006_p1_2_corti_parity_and_drop_context.py`:
- Drops 5 deprecated context_* tables with `DROP TABLE IF EXISTS` (safe whether or not they exist)
- Creates 5 gap tables: `customers`, `templates`, `tickets`, `token_blacklist`, `password_reset_tokens`
- Each table mirrors its model definition (`app/models/{customer,template,ticket,oauth}.py`)
- Uses `sa.Enum(..., name="...")` for enum types (matches Base.metadata SQLite output: VARCHAR(N) where N = max enum value length)
- Uses `sa.text("(CURRENT_TIMESTAMP)")` for TimestampMixin's created_at/updated_at server_default
- No `server_default` on model-specific columns (matches Python-side `default=` only)
- FK columns use `sa.String()` (no length) to match FK target inference
- Downgrade re-creates the 5 deprecated context_* tables (mirror migration 005's schema) so the chain is reversible

### Migration 003 rewrite

`backend/alembic/versions/003_multi_tenant.py` rewritten to:
- Drop `asyncio.run(_upgrade_async())` — use pure alembic op API (`op.create_table` + `op.execute` for ALTER TABLE)
- Drop the default-org data migration block (create `org_default1` + assign all users + UPDATE SET organization_id) — it was a no-op on fresh DBs and `seed.py` handles dev default org creation
- Use `sa.Enum("owner", "admin", "member", "viewer", name="orgrole")` for OrgRole
- Use `op.execute("ALTER TABLE {t} ADD COLUMN organization_id VARCHAR(12) REFERENCES organizations(id)")` for the 23 data tables — alembic's `op.add_column` with `sa.ForeignKey` emits a separate ADD CONSTRAINT statement which SQLite rejects with `NotImplementedError: No support for ALTER of constraints in SQLite dialect`. Inline `REFERENCES` in ADD COLUMN is accepted by SQLite (and PostgreSQL).
- Create `ix_<table>_organization_id` index for each of the 23 data tables
- Mirror the Organization/OrganizationMember/OrganizationInvite model schema exactly (no `server_default` on model-specific columns, FK columns use `sa.String()` no length, `settings` is `nullable=False`)

### env.py fix

`backend/alembic/env.py` — removed the `from app.icoder.agent_runtime.context.db_models import (ContextRow, ...)` block that imported 5 deprecated context_* table registrations. With those imports gone, `target_metadata = Base.metadata` no longer includes the deprecated tables, so autogenerate wouldn't propose re-creating them. Comment updated to explain the cycle 24 rationale.

### models/__init__.py fix

`backend/app/models/__init__.py` — added:
```python
from app.models.organization import Organization, OrganizationMember, OrganizationInvite, OrgRole
```
and added to `__all__`. Previously Organization was only imported via API routers, so `env.py`'s `from app.models import *` didn't pull in the 3 organization tables — `target_metadata` was missing them, and autogenerate would have proposed creating them as new tables (which is wrong — migration 003 already creates them).

### database.py docstring fix

`backend/app/database.py:51` `init_db()` docstring rewritten to clarify:
- Prod actually uses `init_db()` (uvicorn lifespan calls it on every boot), NOT `alembic upgrade head`
- Alembic is a dev/manual tool, kept in parity with `Base.metadata` so anyone who needs a real migration (e.g. zero-downtime column add on PostgreSQL) has a correct starting point
- Cycle 24 closed the 5-table gap that had accumulated

### BACKEND_RECOVERY.md Prevention fix

`docs/dev/BACKEND_RECOVERY.md` §Prevention rewritten:
- `alembic_version` is now `006` (not `005`)
- Production section explicitly states prod uses `init_db()` not alembic
- "Dev rule of thumb" section kept (init_db for greenfield, alembic for column-add migrations on existing DB)

## Verification

End-to-end verification on fresh SQLite DB:

```bash
# alembic upgrade head path
rm -f data/icoder.db.migtest && touch data/icoder.db.migtest
DATABASE_URL="sqlite+aiosqlite:///./data/icoder.db.migtest" python -m alembic upgrade head
# → alembic_version=006, 33 user tables + 1 alembic_version table, integrity=ok

# init_db path
rm -f data/icoder.db.inittest
DATABASE_URL="sqlite+aiosqlite:///./data/icoder.db.inittest" python -c "
import asyncio
from app.database import init_db
from app.models import *
from app.models.runtime_persistence import RuntimeSession, RuntimeTransition, RuntimeAuditRecord, DUCDecision
asyncio.run(init_db())
"
# → no alembic_version table, 33 user tables, integrity=ok
```

**Table-level result**: Both paths produce the same 33 user tables (matching the runbook's healthy baseline list).

**Column-level result** (cycle 24 tables only):
```
customers: PARITY OK
templates: PARITY OK
tickets: PARITY OK
token_blacklist: PARITY OK
password_reset_tokens: PARITY OK
organizations: PARITY OK
organization_members: PARITY OK
organization_invites: PARITY OK
```

The 8 tables touched by migrations 003 + 006 have full column-level parity (type, nullable, default) between `alembic upgrade head` and `init_db()`.

## Files changed

| File | Change | LOC |
|---|---|---|
| `backend/alembic/versions/006_p1_2_corti_parity_and_drop_context.py` | NEW — drops 5 context_* + creates 5 gap tables | +180 |
| `backend/alembic/versions/003_multi_tenant.py` | REWRITE — pure alembic op API, no asyncio.run, no data migration block | +140 (was +120) |
| `backend/alembic/env.py` | Removed `db_models` import block for 5 deprecated context_* tables | -3 +comment |
| `backend/app/models/__init__.py` | Added Organization/OrganizationMember/OrganizationInvite/OrgRole import | +2 |
| `backend/app/database.py` | Rewrote `init_db()` docstring (prod uses init_db, not alembic) | comment-only |
| `docs/dev/BACKEND_RECOVERY.md` | Rewrote §Prevention (alembic_version=006, prod uses init_db) | comment-only |

## Known debt (out of cycle 24 scope)

18 column-level divergences in migrations 001/002/004 + missing column-add migrations:
- `agents.version` / `agents.status` (migration 002 server_defaults don't match model)
- `coding_review_runs.*` (migration 004 nullable + server_defaults don't match model)
- `audit_logs.agent_id` / `agent_account_id` / `delegated_by_user_id` (added to model, no migration)
- `coding_reviews.evidence_ranking` / `confidence_calibration` (added to model, no migration)
- `users.token_version` (added to model, no migration)

These are documented for a future cycle (likely cycle 25: column-level parity for migrations 001/002/004 + new migration 007 for the missing columns). Not blocking — prod uses `init_db()` which is already correct.

## Test plan

- [x] `alembic upgrade head` against fresh `data/icoder.db.migtest` produces 33 user tables + `alembic_version=006`
- [x] `init_db()` against fresh `data/icoder.db.inittest` produces 33 user tables, no `alembic_version` table
- [x] Table name sets are identical between the two paths
- [x] Column-level parity (type, nullable, default) for all 8 cycle 24 tables (customers/templates/tickets/token_blacklist/password_reset_tokens/organizations/organization_members/organization_invites)
- [x] Existing test suite still passes (no model changes, only migration + doc changes)
- [ ] Manual smoke: `python -m uvicorn app.main:app` starts cleanly with the rebuilt DB (deferred — not part of cycle 24 commit, will run on next dev session)
