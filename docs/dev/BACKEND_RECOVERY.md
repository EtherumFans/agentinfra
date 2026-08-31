# Backend SQLite recovery and migration reconciliation

This runbook applies only to the local development SQLite database at
`backend/data/icoder.db`. Cloud deployments use PostgreSQL and require the
platform migration, backup, restore, and change-approval procedures.

The recovery rule is: **inspect the source read-only, build a separate Alembic
head candidate, verify it, and never cut over automatically**. Do not delete,
rename, stamp, or run migrations directly against the only copy of a database.

## Safe inspection

From the repository root:

```powershell
python backend/scripts/stage_sqlite_migration.py `
  --source backend/data/icoder.db
```

Inspection is the default mode. The tool opens the source with SQLite
`mode=ro` and reports only schema names, aggregate counts, and hashed tenant
identifiers. It does not print row values.

The expected schema authority is the single Alembic head reported by:

```powershell
Push-Location backend
python -m alembic heads
Pop-Location
```

Do not use a hard-coded table count as a health signal. A database is ready
only when all of the following are true:

- `PRAGMA integrity_check` is `ok`;
- it has exactly the current single Alembic head;
- `PRAGMA foreign_key_check` has no violations;
- the schema-drift validator reports zero divergences from ORM metadata;
- application data fingerprints are preserved during reconciliation.

## Current development finding (2026-08-22)

The checked development database is internally readable but not ready for a
direct migration or cutover:

- source revision: `041`; repository head: `049`;
- source integrity: `ok`;
- 827 foreign-key violations, all caused by six missing `organizations`
  parent identifiers;
- tables introduced after 041 already exist because historical `create_all`
  startup behavior mixed model-created schema with Alembic state.

A direct `alembic upgrade head` can therefore collide with existing tables.
The source database must remain untouched until a reviewed candidate is
approved.

## Stage a reconciled candidate

Choose a new, empty output directory. The command refuses to overwrite any
artifact:

```powershell
python backend/scripts/stage_sqlite_migration.py `
  --source backend/data/icoder.db `
  --stage-copy-upgrade `
  --quarantine-orphan-organizations `
  --output-dir reports/agent_hub/sqlite_reconciliation_review
```

This command:

1. creates a transactionally consistent SQLite backup of the read-only source;
2. creates a separate clean database by applying Alembic through the current
   single head;
3. copies source tables using explicit common columns;
4. creates inactive quarantine organization parents in the candidate only,
   and only when every violation points to a missing organization;
5. compares PHI-safe row fingerprints, integrity, foreign keys, Alembic head,
   and ORM schema drift;
6. verifies the source size, SHA-256 digest, revision, and integrity again;
7. writes `sqlite_migration_stage_report.json` with
   `cutover_performed: false`.

Quarantine is containment, not attribution. An inactive quarantine parent does
not establish the real hospital, tenant, owner, consent, or lawful data
boundary. The six historical identifiers require authorized owner review
before any production-like use.

## Candidate review gate

Do not consider a candidate eligible for operator cutover unless its report
contains all of these values:

```text
passed = true
checks.source_unchanged = true
checks.candidate_integrity_ok = true
checks.candidate_foreign_keys_ok = true
checks.candidate_at_single_head = true
checks.preexisting_data_preserved = true
checks.candidate_matches_orm = true
cutover_performed = false
```

An authorized reviewer must additionally decide the disposition of every
quarantined organization, approve a rollback copy, define the maintenance
window, and approve the exact source and candidate paths. This repository tool
intentionally has no cutover command.

## Operator cutover and rollback

Cutover is an external, explicitly approved operation. Before it begins:

- stop all backend processes that could write SQLite;
- verify the approved candidate and source SHA-256 values against the signed
  review record;
- preserve a recoverable copy of the original source outside the replacement
  path;
- use one filesystem and an atomic rename procedure suitable for Windows;
- start one backend process and run authenticated smoke tests;
- if any gate fails, stop the backend and restore the preserved original.

This runbook deliberately does not provide a copy-paste replacement or deletion
command. The operator must resolve and verify the exact paths and approval
record at execution time.

## Prevention

- Alembic migrations are the schema authority for persistent environments.
- Do not use `Base.metadata.create_all()` as a migration mechanism for an
  existing database.
- Run the fresh-Alembic schema-drift test whenever a model or migration changes.
- Run the staged reconciliation tests before using this tool on a real copy.
- Never infer healthy state from startup success alone.
- Never log SQLite row values or credentials in reconciliation evidence.
