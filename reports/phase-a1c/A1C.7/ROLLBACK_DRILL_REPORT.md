# A1C.7 — Rollback Drill Report

**Phase**: A1C.7
**Date**: 2026-07-25
**Scope**: PDF §十三 rollback procedure + drill verification.

> **Honest scope note**: This report is **DESIGN-only**. Live rollback drill (deploy v1.0 → break → rollback → verify) requires Pilot env with two replica versions. Static walk-through + dry-run plan below; live drill deferred to Pilot per Charter §22.

---

## §1 Rollback scenarios (5 classes)

| # | Scenario | Trigger | Strategy | RTO | RPO |
|---|----------|---------|----------|-----|-----|
| RB-1 | Bad code deploy (e.g. broken agent_run.py) | Post-deploy smoke test fails | Rolling deploy: revert to previous image | 10 min | 0 |
| RB-2 | Bad DB migration (e.g. Migration 030 drops column) | Migration post-verify fails | Alembic downgrade one revision | 15 min | 0 (downgrade is reversible) |
| RB-3 | Data corruption (e.g. PHI leak in audit_logs) | Sentry alert | Point-in-time recovery from nightly snapshot | 60 min | ≤24h |
| RB-4 | Bad config (e.g. wrong LLM_API_KEY) | DeepSeek 401 in production | Restart with previous config (env var rollback) | 5 min | 0 |
| RB-5 | DeepSeek outage | DeepSeek status page | Wait for DeepSeek recovery OR switch to azure-openai fallback (DESIGN) | 15 min | n/a |

## §2 RB-1: Code rollback — rolling deploy

### 2.1 Pre-conditions
- NGINX upstream has both `uvicorn-blue:8000` and `uvicorn-green:8000`
- New deploy goes to green; blue remains serving traffic for 5-min soak

### 2.2 Procedure
```bash
# 1. Identify bad deploy (smoke test fails)
curl -fsS https://api.cn.icoder.cloud/api/health
# If 5xx: rollback

# 2. Switch NGINX upstream back to blue
sed -i 's/server uvicorn-green:/server uvicorn-blue:/;s/server uvicorn-blue:/# server uvicorn-blue:/' /etc/nginx/conf.d/icoder.conf
nginx -t && nginx -s reload

# 3. Stop green workers
docker stop icoder-backend-green

# 4. Verify
curl -fsS https://api.cn.icoder.cloud/api/health
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run ...

# 5. Audit log inspection — verify rollback didn't drop in-flight requests
PGPASSWORD=<pw> psql ... -c \
  "SELECT status, COUNT(*) FROM audit_logs \
   WHERE created_at > now() - interval '10 minute' GROUP BY status;"
```

### 2.3 Static verification
- ✓ Rolling deploy pattern defined in `docker-compose.local-dev.yml` (single-replica in dev; multi-replica Pilot DESIGN)
- ✓ Health check endpoint exists (`/api/health`)
- ✓ Audit log continuity check pattern authored

## §3 RB-2: DB migration rollback — Alembic downgrade

### 3.1 Pre-conditions
- Every migration has paired `downgrade()` function
- `alembic downgrade -1` tested in CI for last 5 revisions

### 3.2 Procedure (example: Migration 029 patient_contexts)
```bash
# 1. Identify bad migration (post-apply schema drift or runtime error)
python backend/scripts/check_schema_drift.py
# If non-zero exit: rollback

# 2. Take pre-rollback snapshot (safety net)
PGPASSWORD=<pw> pg_dump -h <pg> -U icoder_app icoder > /backups/pre-rollback-$(date +%Y%m%d-%H%M).sql

# 3. Alembic downgrade ONE revision
DATABASE_URL='postgresql+asyncpg://...' alembic -c backend/alembic.ini downgrade -1

# 4. Verify
DATABASE_URL=... alembic current
# Expected: 028 (one revision back)

# 5. Restart backend (forces ORM cache flush)
docker restart icoder-backend

# 6. Smoke test
curl -fsS https://api.cn.icoder.cloud/api/health
curl -fsS https://api.cn.icoder.cloud/api/v1/patient-context/<id> -H "Authorization: Bearer <jwt>"
# Expected: 404 (table dropped) NOT 500
```

### 3.3 Static verification
- ✓ Every migration 001-029 has `downgrade()` (CI verified)
- ✓ Migration 029 (patient_contexts) has canonical `DROP TABLE IF EXISTS patient_contexts CASCADE` in downgrade
- ✓ `check_schema_drift.py` script exists (Phase 7)

## §4 RB-3: Data corruption — point-in-time recovery

### 4.1 Pre-conditions
- Postgres managed (RDS / PolarDB) with automated daily backup + 5-min transaction log archive
- 30-day backup retention
- pg_dump cron daily (in addition to managed backup)

### 4.2 Procedure (example: PHI leak in audit_logs)
```bash
# 1. Identify leak window
# Sentry alert: audit_logs row N-M contained unredacted patient_id

# 2. Stop writes to audit_logs (block audit_middleware)
# EMERGENCY: set env var ICODER_AUDIT_WRITE_PAUSED=true (DESIGN — would need new flag)
docker stop icoder-backend

# 3. Identify target PITR timestamp
# e.g. 2026-07-25 09:00:00 CN (5 min before first leak)

# 4. Restore via managed PITR
aliyun rds RestoreDBInstance --DBInstanceId <id> \
  --RestoreTime "2026-07-25T01:00:00Z" \
  --BackupType BackupSet
# ~60 min for restore to complete

# 5. Verify restoration
PGPASSWORD=<pw> psql ... -c \
  "SELECT COUNT(*) FROM audit_logs WHERE created_at BETWEEN '...' AND '...';"
# Should be 0 (leaked rows reverted)

# 6. Apply forward-only remediation (re-emit non-leaked audit events from app logs)
# (manual review — no automated replay of audit_logs)

# 7. Resume backend
docker start icoder-backend
```

### 4.3 Static verification
- ✓ `pg_dumpJob` DESIGN defined (Pilot env cron)
- ✓ Cloud volume snapshot DESIGN defined
- ⚠️ ICODER_AUDIT_WRITE_PAUSED flag NOT IMPLEMENTED — DESIGN deferred

## §5 RB-4: Config rollback

### 5.1 Procedure
```bash
# 1. Identify bad config (e.g. wrong DeepSeek endpoint)
# Sentry: DeepSeek 401 unauthorized

# 2. Revert env var
sed -i 's|LLM_API_KEY=badkey|LLM_API_KEY=<previous>|' /etc/icoder/cloud.env

# 3. Restart backend (env vars loaded at startup)
docker restart icoder-backend

# 4. Verify within 30s
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run ...
```

### 5.2 Static verification
- ✓ All secrets via env vars (not config file) — Settings model
- ✓ CredentialVault abstraction allows rotation without code change (A1C.5)

## §6 RB-5: DeepSeek outage — failover to fallback provider (DESIGN)

### 6.1 Procedure
```bash
# 1. Confirm DeepSeek outage
# DeepSeek status page: api.deepseek.com 503 > 5 min

# 2. Switch LLM_PROVIDER to fallback
sed -i 's|LLM_PROVIDER=deepseek|LLM_PROVIDER=azure-openai-cn|' /etc/icoder/cloud.env
docker restart icoder-backend

# 3. Verify
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run ...
# model field should now be "gpt-4o-cn" or similar
```

### 6.2 Static verification
- ✓ LLMGateway provider abstraction exists
- ⚠️ Azure-OpenAI / Qwen / Moonshot adapters NOT IMPLEMENTED — Gate 4R-I DESIGN

## §7 Drill plan (Pilot carry-forward)

### 7.1 Pre-Pilot drill (DESIGN)
1. Deploy v1.0 → smoke test PASS → deploy v1.1 (broken) → smoke test FAIL → execute RB-1 → verify v1.0 still serving
2. Apply Migration 030 (test only) → schema drift detected → execute RB-2 → verify Migration 029 head
3. Insert synthetic PHI leak → execute RB-3 → verify leak reverted
4. Wrong LLM_API_KEY → execute RB-4 → verify recovery
5. Block DeepSeek → execute RB-5 → verify failover (once fallback provider implemented)

### 7.2 Pilot cadence
- Weekly: RB-1 + RB-4 (low-risk, fast)
- Monthly: RB-2 (migration rollback)
- Quarterly: RB-3 (PITR — high-risk, coordinate with cloud admin)

## §8 Charter §22 forbidden verdicts honoured

- ❌ Not emitted: `ROLLBACK_VERIFIED` / `DISASTER_RECOVERY_READY` / `PRODUCTION_READY`
- ✓ Emitted (only): `PARTIAL_A1C_7_ROLLBACK_PROCEDURES_AUTHORED_LIVE_DRILL_DEFERRED_TO_PILOT`
