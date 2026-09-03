# A1C.7 — Pilot Deployment Runbook

**Phase**: A1C.7
**Date**: 2026-07-25
**Scope**: PDF §十一 step-by-step Pilot deployment procedure for hospital pilot entry.

> **Honest scope note**: This runbook is **DESIGN-only**. Actual Pilot env provisioning requires cloud account credentials + KMS provider selection + DNS CNAME that exist only in Pilot env. Static walk-through + pre-flight checklists below; live execution deferred to Pilot per Charter §22.

---

## §1 Pre-flight checklist (must PASS before deploy)

| # | Check | Command | Pass criterion |
|---|-------|---------|----------------|
| 1 | Branch HEAD clean | `git status --short` | empty |
| 2 | HEAD on audit branch | `git rev-parse --abbrev-ref HEAD` | `phase-a1a/emergency-containment` |
| 3 | Latest A1C.* commits stacked | `git log --oneline -20` | includes A1C.0..A1C.7 |
| 4 | Charter §22 verdicts check | `git log --grep="PRODUCTION_READY\|HOSPITAL_DEPLOYED"` | empty |
| 5 | Tests pass | `pytest backend/tests -x --tb=short` | all PASS |
| 6 | Schema drift = 0 | `python backend/scripts/check_schema_drift.py` | exit 0 |
| 7 | OpenAPI export clean | `python backend/scripts/export_openapi.py` | exit 0 |
| 8 | ESLint (deferred — A1C.1 BLOCKED_BY_MISSING_DEV_DEPENDENCY) | — | skip |
| 9 | Secrets NOT in repo | `git ls-files \| xargs grep -l "sk-\|gAAAAAB\|BEGIN PRIVATE KEY" 2>/dev/null` | empty |
| 10 | PDF §十四 21 hard gates | `cat docs/phase-a1c/A1C_CHARTER.md §九` | A1C.0-A1C.6 PASS |

## §2 Provisioning steps (Pilot env — requires cloud admin)

### 2.1 Cloud account + region

```bash
# 1. Login to Aliyun (or Tencent Cloud) Pilot account
aliyun cli configure --region cn-hangzhou

# 2. Create resource group
aliyun resourcemgr CreateResourceGroup --DisplayName "icoder-pilot-cn-hangzhou"

# 3. Create KMS key (per-tenant — Gate 4R-I DESIGN, currently shared)
aliyun kms CreateKey --KeyUsage ENCRYPT/DECRYPT --Origin Aliyun_KMS
# Record the key_id for ICODER_KMS_KEY_ID env var
```

### 2.2 Database provisioning

```bash
# Provision RDS PostgreSQL 16
aliyun rds CreateDBInstance --Engine postgresql --EngineVersion 16 \
  --DBInstanceClass pg.n2.medium.2c \
  --DBInstanceStorage 200 \
  --DBInstanceNetType Intranet \
  --SecurityIPList "10.0.0.0/8" \
  --ZoneId cn-hangzhou-i

# Wait for instance to become "Running" (~10 min)
aliyun rds DescribeDBInstances --InstanceIds <instance_id>

# Create icoder database + icoder_app user
PGPASSWORD=<admin_password> psql -h <pg-host> -U <admin> -c \
  "CREATE DATABASE icoder ENCODING='UTF8';"
PGPASSWORD=<admin_password> psql -h <pg-host> -U <admin> -c \
  "CREATE USER icoder_app WITH ENCRYPTED PASSWORD '<from-kms>';"
PGPASSWORD=<admin_password> psql -h <pg-host> -U <admin> -c \
  "GRANT ALL ON DATABASE icoder TO icoder_app;"

# Run migrations
DATABASE_URL='postgresql+asyncpg://icoder_app:<pw>@<pg-host>:5432/icoder' \
  alembic -c backend/alembic.ini upgrade head

# Verify Migration 029 (patient_contexts) applied
PGPASSWORD=<pw> psql -h <pg-host> -U icoder_app -d icoder -c \
  "SELECT version_num FROM alembic_version;"
# Expected: 029
```

### 2.3 Backend deploy

```bash
# Pull Docker image (or build from repo)
docker pull registry.cn-hangzhou.aliyuncs.com/icoder/backend:a1c-pilot
# OR
docker build -f backend/Dockerfile -t icoder-backend:a1c-pilot backend/

# Run with cloud env
docker run -d --name icoder-backend \
  --env-file /etc/icoder/cloud.env \
  -p 8000:8000 \
  -v /var/lib/icoder/medcoder:/app/data/medcoder:ro \
  --restart unless-stopped \
  icoder-backend:a1c-pilot

# Health check
curl -fsS http://localhost:8000/api/health | jq .
# Expected: {"status": "healthy", "medcoder_index_ready": true, ...}
```

### 2.4 Frontend SPA deploy

```bash
# Build static assets
cd frontend && npm run build
# Upload to OSS bucket
aliyun oss cp -r dist/ oss://icoder-console-cn-hangzhou/ --recursive

# CDN CNAME: console.cn.icoder.cloud → oss-cn-hangzhou.aliyuncs.com
```

### 2.5 NGINX/Caddy reverse proxy

```nginx
server {
  listen 443 ssl http2;
  server_name api.cn.icoder.cloud;
  ssl_certificate /etc/letsencrypt/live/api.cn.icoder.cloud/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.cn.icoder.cloud/privkey.pem;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # SSE — disable buffering
  location ~ ^/api/v1/runs/.*/events$ {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
  }
}
```

### 2.6 HIS/EMR partner onboarding

```bash
# 1. Hospital IT provides their IdP metadata (OIDC)
# 2. iCoDer platform admin creates Tenant row
curl -X POST https://api.cn.icoder.cloud/api/platform/tenants \
  -H "Authorization: Bearer <platform-admin-jwt>" \
  -d @tenant_intake.json

# 3. Generate API Client credentials (returned ONCE)
curl -X POST https://api.cn.icoder.cloud/api/platform/tenants/<tid>/api-clients \
  -H "Authorization: Bearer <platform-admin-jwt>" \
  -d '{"client_name":"hospital-A-backend-service","scopes":["agent_run","patient_context","webhook"]}'
# Response: {"client_id":"...","client_secret":"<shown-once>"} ← SAVE TO HOSPITAL KMS
```

### 2.7 Webhook delivery setup

```bash
# A1C.3 RESULT_CALLBACK_SCHEMA — wire delivery queue
# (DESIGN — Pilot uses Postgres LISTEN/NOTIFY; Redis Stream deferred)
curl -X POST https://api.cn.icoder.cloud/api/v1/webhooks \
  -H "Authorization: Bearer <integration-jwt>" \
  -d '{"url":"https://his.hospital-a.cn/icoder/callback","events":["run.completed","review.generated"]}'
```

### 2.8 Monitoring wiring

```bash
# Sentry (CN relay)
docker run -d --name icoder-sentry-relay \
  -e SENTRY_DSN=<from-kms> \
  -e SENTRY_ENVIRONMENT=pilot-cn-hangzhou \
  sentry/relay:latest

# Prometheus node_exporter + postgres_exporter
# Grafana dashboard: icoder-cloud-cn-hangzhou
```

## §3 Post-deploy verification (15 min)

```bash
# 1. Health check
curl -fsS https://api.cn.icoder.cloud/api/health | jq .

# 2. Tenant isolation: cross-tenant 404
curl -i https://api.cn.icoder.cloud/api/v1/organizations/<other-tenant-id>/patients \
  -H "Authorization: Bearer <hospital-A-jwt>"
# Expected: 404 Not Found (NOT 403 — tenant_read_policy visibility filter)

# 3. Patient context lifecycle
PC_ID=$(curl -s -X POST https://api.cn.icoder.cloud/api/v1/patient-context \
  -H "Authorization: Bearer <jwt>" \
  -d '{"patient_id":"P-001","encounter_id":"E-001",...}' | jq -r .id)
curl https://api.cn.icoder.cloud/api/v1/patient-context/$PC_ID -H "Authorization: Bearer <jwt>"
curl -X DELETE https://api.cn.icoder.cloud/api/v1/patient-context/$PC_ID -H "Authorization: Bearer <jwt>"

# 4. AI-enabled real DeepSeek call (small test)
curl -X POST https://api.cn.icoder.cloud/api/v1/agent-run \
  -H "Authorization: Bearer <jwt>" \
  -d '{"agent_id":"icoder/medical-coding-agent@1.0.0","prompt":"..."}'
# Expected: 200 + cost.currency="CNY"

# 5. Audit log inspection
PGPASSWORD=<pw> psql -h <pg> -U icoder_app -d icoder -c \
  "SELECT action, status, organization_id, created_at FROM audit_logs \
   ORDER BY created_at DESC LIMIT 20;"

# 6. Webhook delivery (if hospital HIS test endpoint ready)
# Hospital-side: tail his-callback.log → expect run.completed event
```

## §4 Charter §22 forbidden verdicts honoured

This runbook does NOT emit:
- ❌ `DEPLOYMENT_RUNBOOK_VERIFIED` — live execution deferred to Pilot
- ❌ `PRODUCTION_READY` / `HOSPITAL_DEPLOYED`

This runbook DOES emit (only):
- `PARTIAL_A1C_7_DEPLOYMENT_RUNBOOK_AUTHORED_LIVE_EXECUTION_DEFERRED_TO_PILOT`
