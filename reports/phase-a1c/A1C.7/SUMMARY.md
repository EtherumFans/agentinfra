# A1C.7 — Deployment, Observability, Failure Recovery & Rollback (SUBGATE INDEX)

**Phase**: A1C.7
**Date**: 2026-07-25
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md §6 (部署 / 可观测性 / 故障恢复 / 回滚)
**Verdict**: `PARTIAL_A1C_7_DEPLOYMENT_OBSERVABILITY_FAILURE_RECOVERY_ROLLBACK_AUTHORED_STATIC_VERIFIED_LIVE_DRILL_DEFERRED_TO_PILOT`

## Deliverables (PDF §十一/十二/十三 5 outputs)

| # | File | Status |
|---|------|--------|
| 1 | `PILOT_DEPLOYMENT_ARCHITECTURE.md` | AUTHORED — 3-tier cloud model + Pilot cn-hangzhou topology + 9-component layout + 11-row acceptance matrix |
| 2 | `DEPLOYMENT_RUNBOOK.md` | AUTHORED — 10-check pre-flight + 8-step provisioning + 6-step post-deploy verification |
| 3 | `OBSERVABILITY_SPEC.md` | AUTHORED — 4-pillar (logs/metrics/traces/alerts) + 14 metrics + 5 dashboards + 10 alerts |
| 4 | `FAILURE_INJECTION_RESULTS.json` | AUTHORED + JSON VALIDATED — 17 failure scenarios (4 PASS_PRIOR + 8 DESIGN_VERIFIED + 3 DESIGN_ONLY + 1 PARTIAL + 1 DESIGN_AUTHORED) |
| 5 | `ROLLBACK_DRILL_REPORT.md` | AUTHORED — 5 rollback scenarios (RB-1..RB-5) + static walk-through + Pilot drill plan |

## Existing infrastructure reused

| 组件 | 状态 |
|------|------|
| FastAPI + uvicorn (4 workers) | ✓ 实现完整 |
| `/api/health` health check (Phase 4-D) | ✓ 实现完整 |
| Structured JSON logging (Phase 4-D logging_config) | ✓ 实现完整 |
| run_trace event store (Phase 3 + A1A Gate 3R) | ✓ 实现完整 |
| audit_middleware + audit_detail_redactor (A1A Gate 4) | ✓ 实现完整 |
| fail-closed guard at 4 write surfaces (A1A Gate 2) | ✓ 实现完整 |
| tenant_read_policy visibility filter (A1A Gate 3R) | ✓ 实现完整 |
| phi_encryption Fernet envelope (A1A Gate 4.4) | ✓ 实现完整 |
| CredentialVault abstraction (A1C.5) | ✓ 实现完整 |
| DeepSeek LLMGateway with tenacity retry (Phase 5 + A1C.5) | ✓ 实现完整 |
| Webhook delivery + dead-letter queue (A1C.3 DESIGN) | ⚠️ DESIGN — Postgres LISTEN/NOTIFY fallback; Redis Stream deferred |
| Docker compose local dev | ✓ 实现完整 |
| Cloud deployment design (docs/cloud/CLOUD_DEPLOYMENT.md) | ✓ 实现完整 (design doc) |
| PG migration test parity (A1C.2) | ✓ SQLite PASS; PG actual run DEFERRED |

## Coverage summary

| Area | Coverage | Count |
|------|----------|-------|
| Pre-flight checks authored | DESIGN_VERIFIED | 10/10 |
| Deployment steps authored | DESIGN | 8/8 (Pilot execution deferred) |
| Observability pillars | 2 IMPLEMENTED (logs + traces) + 2 DESIGN (metrics + Sentry wire-up) | 4/4 |
| Failure injection scenarios | 4/17 PASS_PRIOR + 8/17 DESIGN_VERIFIED + 4/17 DESIGN_ONLY/PARTIAL + 1/17 DESIGN_AUTHORED | 17/17 authored |
| Rollback scenarios | 5/5 walk-throughs authored | 5/5 |

## Honest PARTIAL — deferred to Pilot

### Deployment
- **Pilot cloud account provisioning** (Aliyun / Tencent Cloud / 华为云)
- **DNS CNAME** `api.cn.icoder.cloud` registration
- **TLS certificate** issuance (Let's Encrypt or cloud-managed)
- **Live `alembic upgrade head` on PG 16 production**
- **Multi-replica uvicorn** (blue/green or k8s rolling deploy)

### Observability
- **Prometheus exporter** implementation
- **Sentry CN relay** provisioning
- **Loki / ELK** ingestion pipeline
- **Grafana dashboards** import + on-call alert routing

### Failure injection
- **toxiproxy** Pilot env setup
- **17 scenarios** live injection within 5-minute windows
- **PILOT_FAILURE_INJECTION_RESULTS.json** evidence capture

### Rollback drill
- **Multi-replica env** for blue/green
- **PITR test** on cloud-managed Postgres
- **ICODER_AUDIT_WRITE_PAUSED flag** implementation (RB-3 DESIGN gap)
- **Azure-OpenAI / Qwen fallback provider** (RB-5 DESIGN gap)

## Charter §22 forbidden verdicts honoured

- ❌ Not emitted: DEPLOYMENT_VERIFIED / DEPLOYMENT_READY / OBSERVABILITY_VERIFIED
- ❌ Not emitted: FAILURE_INJECTION_FULLY_VERIFIED / ALL_FAILURE_MODES_COVERED
- ❌ Not emitted: ROLLBACK_VERIFIED / DISASTER_RECOVERY_READY
- ❌ Not emitted: PRODUCTION_READY / HOSPITAL_PILOT_DEPLOYED / CORTI_PARITY_VERIFIED (Charter §22 global forbiddens)

## State 5-tuple update

| Key | A1C.6 value | A1C.7 value |
|-----|-------------|-------------|
| A1C_7_DELIVERABLES | NOT_AUTHORED | AUTHORED_5_OF_5 |
| A1C_7_DEPLOYMENT_ARCHITECTURE | NOT_DESIGNED | DESIGNED (3-tier + cn-hangzhou + 11-row acceptance) |
| A1C_7_DEPLOYMENT_RUNBOOK | NOT_AUTHORED | AUTHORED (10 pre-flight + 8 provisioning + 6 verify) |
| A1C_7_OBSERVABILITY_SPEC | NOT_AUTHORED | AUTHORED (4 pillar + 14 metric + 5 dashboard + 10 alert) |
| A1C_7_FAILURE_INJECTION | NOT_AUTHORED | AUTHORED (17 scenarios; 12 PASS/DESIGN_VERIFIED + 5 DESIGN_ONLY/PARTIAL) |
| A1C_7_ROLLBACK_DRILL | NOT_AUTHORED | AUTHORED (5 scenarios; static walk-through) |
| A1C_7_LIVE_DRILL | NOT_RUN | DEFERRED_TO_PILOT |

## Cross-references

- `reports/phase-a1c/A1C.2/docker-compose.a1c-postgres.yml` — PG 16 docker-compose
- `reports/phase-a1c/A1C.3/RESULT_CALLBACK_SCHEMA.json` — webhook delivery design
- `reports/phase-a1c/A1C.5/KMS_INTEGRATION_REPORT.md` — KMS adapter design
- `reports/phase-a1c/A1C.6/AUDIT_EVENT_SCHEMA.json` — audit fields used by observability
- `docs/cloud/CLOUD_DEPLOYMENT.md` — original 3-tier cloud design (2026-06-27)
- `docs/cloud/MULTI_REGION.md` — region routing rules
- `docker-compose.local-dev.yml` — local dev infra
