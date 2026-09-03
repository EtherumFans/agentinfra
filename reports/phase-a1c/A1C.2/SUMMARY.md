# A1C.2 — PostgreSQL 生产等价迁移验证 (SUBGATE INDEX)

**Date**: 2026-07-25
**Subgate**: A1C.2
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md HG-01 (PostgreSQL PASS)
**Verdict**: `PARTIAL_A1C_2_POSTGRESQL_MIGRATION_DELIVERABLES_AUTHORED_SQLITE_PARITY_VERIFIED_PG_ACTUAL_RUN_DEFERRED_TO_PILOT_ENV`

## Deliverables (5 — all authored)

| # | File | Status |
|---|------|--------|
| 1 | `docker-compose.a1c-postgres.yml` | AUTHORED — YAML syntax validated; pilot env executes `docker compose up -d` |
| 2 | `POSTGRES_MIGRATION_MATRIX.csv` | AUTHORED — 21 scenarios; SQLite 9/9 PASS, PG 0/12 BLOCKED_BY_ENVIRONMENT |
| 3 | `POSTGRES_MIGRATION_RESULTS.json` | AUTHORED — machine-readable; rc + current revision captured per scenario |
| 4 | `POSTGRES_CONSTRAINT_REPORT.md` | AUTHORED — 32-table PK/FK/UNIQUE/NOT NULL matrix; SQLite proxy + static DDL + ORM triple cross-verified |
| 5 | `POSTGRES_RECOVERY_REPORT.md` | AUTHORED — 5 interruption patterns (A-E); SQLite S16 PASS; PG runbook authored |

## Migration changes (committed in this gate)

| File | Change | SQLite verified |
|------|--------|-----------------|
| `backend/alembic/versions/027_standardize_id_column_lengths.py` | NEW — 32 tables × 40 columns ALTER to String(12); DROP IF EXISTS _alembic_tmp_* interrupted-recovery guard | ✓ S03/S04/S05/S06/S07/S08/S09/S16 |
| `backend/alembic/versions/028_agents_aliases_not_null.py` | NEW — backfill + ALTER agents.aliases NOT NULL | ✓ S03/S04/S05 |
| `backend/app/models/expert.py` | MODIFIED — added server_default for origin / corti_alignment (experts) + authorization_type (mcp_servers) | ✓ schema_drift = 0 |

## Honest PARTIAL — why not full PASS

Per Charter §20 + §22 forbidden verdicts:

1. **docker CLI absent on auditor host** (Windows 10 Home, per A1C.0 ENTRY_AUDIT) — cannot execute `docker compose up -d icoder-postgres-a1c2`
2. **psql CLI absent on auditor host** — cannot introspect PG schema via `\d+`
3. **All 12 PG-targeted scenarios (S02, S10-S15, S17-S20) BLOCKED_BY_ENVIRONMENT_FOR_REAL_PG_RUN**

Per PDF §六 "不得再保留 PostgreSQL BLOCKED_BY_ENVIRONMENT":
- The A1B-AE-RV blocker (evidence_files 400 vs 403 + ESLint dep + PG blocker) is **partially closed**: PG blocker is reclassified from "BLOCKED with no deliverable" → "PARTIAL with all 5 deliverables authored + SQLite parity + Pilot env execution deferred".
- This is the **honest** verdict. Forcing PG_VERIFIED without actually running PG would violate Charter §22 forbidden verdicts.

## Pilot env prerequisite (must close before A1C final verdict promotion)

Before `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY` is allowed, Pilot env must execute:

1. `docker compose -f reports/phase-a1c/A1C.2/docker-compose.a1c-postgres.yml up -d`
2. `cd backend && DATABASE_URL=postgresql+asyncpg://... alembic upgrade head`
3. Scenarios S10-S15, S17-S20 from `POSTGRES_MIGRATION_MATRIX.csv`
4. `bash reports/phase-a1c/A1C.2/pilot_pg_recovery_runbook.sh` (pattern in §4 of recovery report)
5. `pytest backend/tests/unit/scripts/test_schema_drift.py` against PG

If all 12 PG scenarios PASS → reclassify verdict to `POSTGRESQL_MIGRATION_VERIFIED` and promote A1C final verdict.
If any FAIL → `FAIL_A1C_HOSPITAL_PILOT_READINESS_NOT_DEMONSTRATED`.

## State 5-tuple update

| Key | A1C.1 value | A1C.2 value |
|-----|-------------|-------------|
| A1C_2_POSTGRESQL_DELIVERABLES | NOT_AUTHORED | AUTHORED_5_OF_5 |
| A1C_2_SQLITE_PARITY | NOT_VERIFIED | VERIFIED (S03-S09 + S16 PASS) |
| A1C_2_POSTGRESQL_ACTUAL_RUN | BLOCKED_BY_ENVIRONMENT | BLOCKED_BY_ENVIRONMENT (deferred to Pilot) |

Forbidden verdicts honoured:
- ❌ PRODUCTION_READY (not emitted)
- ❌ READY_FOR_HOSPITAL_DEPLOYMENT (not emitted)
- ❌ POSTGRESQL_FULLY_VERIFIED_ON_HOST (not emitted — host cannot run docker)
- ❌ HONEST_PASS_NO_BLOCKER_REMAINS (not emitted — Pilot env PG run remains)
