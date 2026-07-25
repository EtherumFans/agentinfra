# A1C.7 — Pilot Deployment Architecture

**Phase**: A1C.7
**Date**: 2026-07-25
**Scope**: PDF §十一 deployment architecture for hospital pilot entry.

---

## §1 Three-tier cloud SaaS model (Corti-aligned)

```
┌─────────────────────────────────────────────────────────────────┐
│  Environment: cn (China data residency — 网络安全法 + 数据安全法)  │
│  Region:     cn-hangzhou (Aliyun) | cn-beijing (Tencent Cloud)   │
│  Tenant:     hospital-A (iCoDer Organization row)                │
│  API Client: backend-service (server-to-server)                  │
│              ROPC embedded (browser widget)                      │
└─────────────────────────────────────────────────────────────────┘
```

## §2 Component topology (Pilot scope)

```
                        HIS/EMR (Hospital)
                              │
                              │ HTTPS + OAuth client_credentials
                              ▼
                    ┌─────────────────────┐
                    │ NGINX/Caddy (TLS)   │  ← icoder.cloud CNAME
                    │  443 → 8000         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────────┐
              │                │                    │
              ▼                ▼                    ▼
       ┌────────────┐  ┌──────────────┐  ┌──────────────────┐
       │ FastAPI    │  │ Static SPA   │  │ Webhook delivery │
       │ backend    │  │ (build/)     │  │ (background)     │
       │ uvicorn x4 │  │              │  │                  │
       └──────┬─────┘  └──────────────┘  └──────────────────┘
              │
              │ SQLAlchemy async + pgthreadpool
              ▼
       ┌────────────────────┐         ┌─────────────────────────┐
       │ PostgreSQL 16      │ ◄─────► │ KMS (Aliyun KMS / 腾讯) │
       │ primary + replica  │         │  - Fernet envelope key  │
       │ daily pg_dump      │         │  - JWT signing key      │
       │ 30-day retention   │         │  - DeepSeek API key     │
       └────────────────────┘         └─────────────────────────┘
              │
              │ httpx.AsyncClient → api.deepseek.com (CN region)
              ▼
       ┌────────────────────┐
       │ DeepSeek Cloud     │
       │ deepseek-v4-flash  │
       └────────────────────┘

       Sidecars / Observability:
       ┌──────────────────────────────────────────────────┐
       │ • Prometheus / Grafana (metrics + alerting)      │
       │ • Sentry (error / performance trace, CN region)  │
       │ • Loki / ELK (structured logs, 30-day retention) │
       │ • pg_dump cron (daily, 30-day)                   │
       │ • Snapshot cron (daily, 30-day)                  │
       │ • retention.py cron (90-day trace / 6-year audit)│
       │ • audit_detail_redactor (pre-INSERT)             │
       └──────────────────────────────────────────────────┘
```

## §3 Process model

| Service | Process count | Replicas | Resource | Startup |
|---------|--------------|----------|----------|---------|
| FastAPI uvicorn | 4 workers | 2 (rolling deploy) | 2 vCPU + 4GB each | `uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000` |
| Background worker | 1 worker | 1 | 1 vCPU + 2GB | asyncio create_task on app startup |
| Postgres 16 | 1 primary | 1 read replica | 4 vCPU + 16GB + 200GB SSD | managed (RDS / PolarDB) |
| KMS | n/a | n/a | managed | managed |
| NGINX | 1 | stateless | 1 vCPU + 1GB | systemd |
| MedCodER index | shared | shared | 2.3GB FAISS + metadata.pkl | lazy load on first agent_run |

## §4 Configuration surface (env vars)

| Var | Pilot value | Source |
|-----|-------------|--------|
| `ICODER_DEPLOYMENT_MODE` | `cloud` | Charter §4 |
| `ICODER_ENVIRONMENT` | `cn` | data residency |
| `ICODER_REGION` | `cn-hangzhou` | Aliyun |
| `ICODER_HOSTED_URL` | `https://api.cn.icoder.cloud` | DNS CNAME |
| `DATABASE_URL` | `postgresql+asyncpg://...@pg-master:5432/icoder` | Pilot secret via KMS |
| `LLM_API_KEY` | (rotated monthly) | KMS |
| `SECRET_KEY` | (16-char fingerprint chars 41-48) | KMS |
| `FERNET_KEY` | (rotation deferred to Gate 4R-I) | KMS |
| `SENTRY_DSN` | (cn relay) | Sentry CN |
| `ICODER_AI_ENABLED` | `true` (Pilot) | Charter §4 |
| `ICODER_ASSET_BUCKET` | `icoder-assets-cn-hangzhou` | OSS |

## §5 Pilot environment acceptance

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Kubernetes/Docker-compose manifests authored | DESIGN_VERIFIED | docker-compose.local-dev.yml + reports/phase-a1c/A1C.2/docker-compose.a1c-postgres.yml |
| Cloud secrets NOT in repo | PASS (A1A Gate 1) | Settings._validate_fail_closed_policy |
| Database migration path verified | PARTIAL (SQLite parity proven; PG actual run deferred — A1C.2) | reports/phase-a1c/A1C.2/POSTGRES_MIGRATION_RESULTS.json |
| DeepSeek client wire verified | PASS (prior Phase 7 Gate 12 — 5462ms E2E) | reports/phase7/gate12/SUMMARY.md |
| KMS abstraction wired | PASS (A1C.5 CredentialVault) | reports/phase-a1c/A1C.5/KMS_INTEGRATION_REPORT.md |
| Observability pipeline (logs + metrics + traces) | PARTIAL (DESIGN — Phase 4-D structured logs PASS; Sentry/Prometheus/Loki wiring deferred to Pilot cloud account) | §3 OBSERVABILITY_SPEC |
| Webhook delivery queue | DESIGN (A1C.3 RESULT_CALLBACK_SCHEMA — Redis Stream deferred) | reports/phase-a1c/A1C.3/RESULT_CALLBACK_SCHEMA.json |
| Backup + restore | DESIGN (pg_dumpJob + snapshot cron) | §4 ROLLBACK_DRILL_REPORT |
| Rollback drill | DESIGN_VERIFIED (static walk-through; live drill deferred) | reports/phase-a1c/A1C.7/ROLLBACK_DRILL_REPORT.md |

## §6 Charter §22 forbidden verdicts honoured

This document does NOT emit:
- ❌ `DEPLOYMENT_VERIFIED` / `PRODUCTION_DEPLOYED` — Pilot env not provisioned
- ❌ `CLOUD_DEPLOYMENT_COMPLETE` — Charter §22 forbids
- ❌ `PRODUCTION_READY`

This document DOES emit (only):
- `PARTIAL_A1C_7_DEPLOYMENT_ARCHITECTURE_DESIGNED_STATIC_VERIFIED_LIVE_PROVISIONING_DEFERRED_TO_PILOT`
