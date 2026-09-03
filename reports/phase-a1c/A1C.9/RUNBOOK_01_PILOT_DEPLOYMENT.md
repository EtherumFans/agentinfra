# A1C.9 — Runbook 01: Pilot Deployment

**Phase**: A1C.9
**Date**: 2026-07-25
**Scope**: Step-by-step procedure to deploy iCoDer to Pilot hospital env (cn-hangzhou region).

> **Honest scope note**: This runbook extends `A1C.7/DEPLOYMENT_RUNBOOK.md` with Pilot-specific operational detail. Live execution requires cloud account + DNS + KMS provider (all deferred per A1C_OPEN_BLOCKERS.csv A1C-B-005/013).

---

## §1 Pre-deploy gating

Before commencing Pilot deploy, all of the following MUST be true:

| # | Gate | Check command | Expected |
|---|------|--------------|----------|
| 1 | All A1C.* commits stacked on audit branch | `git log --oneline phase-a1a/emergency-containment \| head -15` | Includes A1C.0..A1C.9 |
| 2 | No Charter §22 forbidden verdicts | `git log --grep="PRODUCTION_READY\|HOSPITAL_DEPLOYED\|CLINICAL_GRADE\|PHI_BOUNDED\|CORTI_PARITY_VERIFIED\|FULLY_VERIFIED"` | empty |
| 3 | No real secrets in repo | `git ls-files \| xargs grep -l "sk-[a-zA-Z0-9-]\{20,\}\|BEGIN PRIVATE KEY" 2>/dev/null` | empty |
| 4 | Schema drift = 0 | `python backend/scripts/check_schema_drift.py` | exit 0 |
| 5 | Tests pass | `pytest backend/tests -x --tb=line` | all PASS |
| 6 | OpenAPI export clean | `python backend/scripts/export_openapi.py` | exit 0 |
| 7 | Pilot env account provisioned | `aliyun cli DescribeAccount` | success |
| 8 | DNS CNAME registered | `dig api.cn.icoder.cloud +short` | Pilot LB DNS |
| 9 | TLS cert issued | `openssl s_client -connect api.cn.icoder.cloud:443` | cert OK |
| 10 | Cloud KMS provisioned | `aliyun kms DescribeKey --KeyId <id>` | status=Enabled |
| 11 | LLM_API_KEY injected to KMS | `aliyun kms Decrypt --CiphertextBlob <blob>` | returns valid key |
| 12 | Hospital IdP metadata procured | manual review | OIDC discovery URL valid |
| 13 | Hospital API client pre-registered | `psql ... -c "SELECT id FROM api_clients WHERE tenant_id='<hospital>'"` | 1+ row |

If ANY of 7-13 fail, **abort deploy** and resolve first.

## §2 Provisioning sequence (sequential)

### 2.1 Cloud infra (60 min)
```bash
# 1. Resource group
aliyun resourcemgr CreateResourceGroup --DisplayName "icoder-pilot-cn-hangzhou"

# 2. KMS key (per-tenant)
aliyun kms CreateKey --KeyUsage ENCRYPT/DECRYPT --Origin Aliyun_KMS \
  --Description "icoder-pilot-cn-hangzhou-fernet-envelope"
# Record key_id → ICODER_KMS_KEY_ID

# 3. RDS PostgreSQL 16
aliyun rds CreateDBInstance --Engine postgresql --EngineVersion 16 \
  --DBInstanceClass pg.n2.medium.2c --DBInstanceStorage 200 \
  --ZoneId cn-hangzhou-i --SecurityIPList "10.0.0.0/8"
# Wait ~10 min for "Running"

# 4. OSS bucket for assets (public-read for ICD dictionaries; private for everything else)
aliyun oss mb oss://icoder-assets-cn-hangzhou
aliyun oss cp -r E:/iCoDerA/DataAsset/ oss://icoder-assets-cn-hangzhou/ --recursive
```

### 2.2 Configuration injection (15 min)
```bash
# Secrets via KMS (NEVER write to /etc/icoder/cloud.env plaintext)
KMS_KEY_ID=<from-2.1> LLM_API_KEY=<deepseek-key> python scripts/kms_inject.py
# This writes encrypted blobs to /etc/icoder/cloud.enc

# Reference /etc/icoder/cloud.env (with placeholder values; real values fetched at startup via CredentialVault)
cat > /etc/icoder/cloud.env <<EOF
ICODER_DEPLOYMENT_MODE=cloud
ICODER_ENVIRONMENT=cn
ICODER_REGION=cn-hangzhou
ICODER_HOSTED_URL=https://api.cn.icoder.cloud
DATABASE_URL=postgresql+asyncpg://icoder_app:@pg-master:5432/icoder
ICODER_KMS_KEY_ID=<from-2.1>
SENTRY_DSN=https://<key>@sentry.cn-relay.icoder.cloud/1
ICODER_AI_ENABLED=true
ICODER_ASSET_BUCKET=icoder-assets-cn-hangzhou
EOF
chmod 600 /etc/icoder/cloud.env
```

### 2.3 Backend deploy (20 min)
```bash
# Pull image
docker pull registry.cn-hangzhou.aliyuncs.com/icoder/backend:a1c-pilot

# Run container with cloud env
docker run -d --name icoder-backend-blue \
  --env-file /etc/icoder/cloud.env \
  -p 8000:8000 \
  -v /var/lib/icoder/medcoder:/app/data/medcoder:ro \
  -v /etc/icoder/cloud.enc:/etc/icoder/cloud.enc:ro \
  --restart unless-stopped \
  registry.cn-hangzhou.aliyuncs.com/icoder/backend:a1c-pilot

# Wait 30s for uvicorn workers to bind
sleep 30 && docker logs icoder-backend-blue --tail 50 | grep "Uvicorn running on"

# Run alembic migrations
docker exec icoder-backend-blue alembic -c backend/alembic.ini upgrade head
docker exec icoder-backend-blue alembic -c backend/alembic.ini current
# Expected: 029
```

### 2.4 Frontend SPA deploy (10 min)
```bash
cd frontend && npm run build
aliyun oss cp -r dist/ oss://icoder-console-cn-hangzhou/ --recursive
# Configure CDN CNAME: console.cn.icoder.cloud → oss-cn-hangzhou.aliyuncs.com
```

### 2.5 NGINX reverse proxy (10 min)
```bash
# Install nginx + certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Get TLS cert
sudo certbot --nginx -d api.cn.icoder.cloud -d console.cn.icoder.cloud

# Configure upstream + SSE-aware proxy
sudo tee /etc/nginx/conf.d/icoder.conf <<'EOF'
upstream icoder_backend {
  server 127.0.0.1:8000;
  keepalive 32;
}

server {
  listen 443 ssl http2;
  server_name api.cn.icoder.cloud;
  ssl_certificate /etc/letsencrypt/live/api.cn.icoder.cloud/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.cn.icoder.cloud/privkey.pem;

  location / {
    proxy_pass http://icoder_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
  }

  location ~ ^/api/v1/runs/.*/events$ {
    proxy_pass http://icoder_backend;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    add_header X-Accel-Buffering no;
  }
}
EOF

sudo nginx -t && sudo systemctl reload nginx
```

### 2.6 HIS/EMR partner onboarding (30 min, hospital-coordinated)
```bash
# 1. Hospital IT provides OIDC discovery URL
curl -fsS https://his.hospital-a.cn/.well-known/openid-configuration | jq .

# 2. iCoDer platform admin registers tenant
curl -X POST https://api.cn.icoder.cloud/api/platform/tenants \
  -H "Authorization: Bearer $PLATFORM_ADMIN_JWT" \
  -d @reports/phase-a1c/A1C.4/tenant_intake.json

# 3. Generate API Client credentials (RETURNED ONCE)
curl -X POST https://api.cn.icoder.cloud/api/platform/tenants/<tid>/api-clients \
  -H "Authorization: Bearer $PLATFORM_ADMIN_JWT" \
  -d '{"client_name":"hospital-A-backend-service","scopes":["agent_run","patient_context","webhook"]}'
# SAVE client_secret to hospital KMS immediately

# 4. Configure HIS/EMR simulator (during Pilot soak only)
docker run -d --name his-sim \
  -p 9443:443 \
  -v /etc/icoder/his-sim-certs:/certs:ro \
  icoder/his-emr-simulator:a1c
```

### 2.7 Monitoring + alerting wire-up (20 min)
```bash
# Prometheus node_exporter
docker run -d --name node-exporter --net=host prom/node-exporter

# Postgres exporter
docker run -d --name pg-exporter \
  -e DATA_SOURCE_NAME="postgresql://icoder_app:@<pg>:5432/icoder?sslmode=disable" \
  -p 9187:9187 prometheuscommunity/postgres-exporter

# Sentry relay (CN)
docker run -d --name sentry-relay \
  -e SENTRY_DSN=$SENTRY_DSN \
  -e SENTRY_ENVIRONMENT=pilot-cn-hangzhou \
  sentry/relay:latest

# Grafana
docker run -d --name grafana -p 3000:3000 grafana/grafana
# Import dashboards from reports/phase-a1c/A1C.7/grafana/ (TBD)
```

## §3 Post-deploy soak test (15 min)

```bash
# 1. Health check
curl -fsS https://api.cn.icoder.cloud/api/health | jq .

# 2. Tenant isolation attack (must 404)
curl -i https://api.cn.icoder.cloud/api/v1/organizations/other-tenant/patients \
  -H "Authorization: Bearer $HOSPITAL_A_JWT"

# 3. Patient context lifecycle
PC=$(curl -s -X POST https://api.cn.icoder.cloud/api/v1/patient-context \
  -H "Authorization: Bearer $HOSPITAL_A_JWT" \
  -d @reports/phase-a1c/A1C.3/test_payload.json | jq -r .id)
curl -fsS https://api.cn.icoder.cloud/api/v1/patient-context/$PC -H "Authorization: Bearer $HOSPITAL_A_JWT"
curl -i -X DELETE https://api.cn.icoder.cloud/api/v1/patient-context/$PC -H "Authorization: Bearer $HOSPITAL_A_JWT"
curl -i https://api.cn.icoder.cloud/api/v1/patient-context/$PC -H "Authorization: Bearer $HOSPITAL_A_JWT"
# Expected: 404

# 4. Real DeepSeek call
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run \
  -H "Authorization: Bearer $HOSPITAL_A_JWT" \
  -d @reports/phase-a1c/A1C.5/test_agent_run.json | jq '.cost.currency'
# Expected: "CNY"

# 5. Audit log inspection
PGPASSWORD=$PG_PW psql -h $PG_HOST -U icoder_app -d icoder -c \
  "SELECT action, status, organization_id, tenancy_classification, created_at \
   FROM audit_logs ORDER BY created_at DESC LIMIT 20;"

# 6. Run A1C.8 20-journey Pilot replay
python scripts/a1c8_pilot_journey_runner.py --base-url https://api.cn.icoder.cloud
# Verify 20/20 PASS + secret_leak_count = 0
```

## §4 Deploy abort criteria

ABORT deploy if ANY of:
- Health check returns 5xx for > 30s
- Tenant isolation attack returns 200 (CRITICAL — page security oncall)
- DeepSeek real call returns 5xx
- Audit log write fails
- secret_leak_count > 0 in any journey

## §5 Charter §22 forbidden verdicts honoured

This runbook does NOT emit:
- ❌ `DEPLOYMENT_VERIFIED` / `PILOT_DEPLOYED_VERIFIED`
- ❌ `PRODUCTION_READY`

This runbook DOES emit (only):
- `PARTIAL_A1C_9_RUNBOOK_01_PILOT_DEPLOYMENT_AUTHORED_LIVE_EXECUTION_REQUIRES_OPEN_BLOCKER_RESOLUTION`
