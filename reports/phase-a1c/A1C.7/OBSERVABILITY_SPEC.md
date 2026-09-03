# A1C.7 — Observability Specification

**Phase**: A1C.7
**Date**: 2026-07-25
**Scope**: PDF §十二 observability requirements — logs / metrics / traces / alerts.

---

## §1 Three pillars of observability

| Pillar | Tool | Status | Source |
|--------|------|--------|--------|
| **Logs** | structured JSON stdout → Loki / ELK | IMPLEMENTED | backend/app/logging_config.py (Phase 4-D) |
| **Metrics** | Prometheus + Grafana | DESIGN | backend/app/api/health.py + (Prometheus exporter deferred to Pilot) |
| **Traces** | run_trace store (per-run) + Sentry performance | IMPLEMENTED + DESIGN | backend/app/models/run_trace.py + Phase 3 trace_capture |
| **Errors** | Sentry (CN relay) | DESIGN | sentry-sdk deferred to Pilot env |

## §2 Log channels (existing Phase 4-D)

### 2.1 Structured log schema

Every log line is JSON with these mandatory fields:

```json
{
  "timestamp": "2026-07-25T09:14:22.482Z",
  "level": "INFO|WARNING|ERROR|CRITICAL",
  "logger": "app.api.patient_context|app.services.agent_run|...",
  "event": "patient_context.created|agent_run.completed|...",
  "organization_id": "org-hospital-a",
  "user_id": "u-med-001",
  "trace_id": "tr_8f7b3c2a-...",
  "run_id": "run-8842",
  "request_id": "req-...",
  "audit_redacted": true,
  "message": "human-readable summary (PHI-redacted)"
}
```

### 2.2 Log emission paths

| Source | Output | Sample rate |
|--------|--------|-------------|
| FastAPI request/response middleware | stdout JSON | 100% (request), 1% (response body) |
| audit_middleware | stdout JSON + DB audit_logs row | 100% |
| LLMGateway | stdout JSON (prompt length + token count, NO content) | 100% |
| run_trace event emit | DB run_trace_events row + SSE stream | 100% |
| phi_encryption | stdout JSON (column, success/failed) | 100% |
| data_policy | stdout JSON (region, decision) | 100% |
| Background cron | stdout JSON + DB audit_logs row | 100% |

### 2.3 PHI redaction guarantee

`audit_detail_redactor` (A1A Gate 4) applies 11 regex patterns pre-INSERT to `audit_logs.details`. Patterns verified in `REDACTION_TEST_RESULTS.json`.

**Forbidden**:
- ❌ LLM prompt content in any log line (only prompt length + model name)
- ❌ Raw patient_id in any log line (only `<REDACTED>` marker)
- ❌ Raw API key / JWT in any log line (only `<REDACTED_KEY>` / `<REDACTED_JWT>`)

## §3 Metrics (DESIGN — Pilot wire-up)

### 3.1 Required Pilot metrics

| Metric | Type | Source | Alert threshold |
|--------|------|--------|-----------------|
| `http_requests_total{method,route,status}` | counter | FastAPI middleware | 5xx rate > 1% over 5 min |
| `http_request_duration_seconds{route}` | histogram | FastAPI middleware | p99 > 5s |
| `agent_run_duration_seconds{agent_id}` | histogram | agent_run service | p99 > 60s |
| `agent_run_cost_cny_total{agent_id}` | counter | billing_service | daily > 1000 CNY |
| `llm_tokens_total{model,kind=input\|output}` | counter | LLMGateway | hourly > 5M tokens |
| `db_connection_pool_size` | gauge | SQLAlchemy events | saturated > 5 min |
| `db_query_duration_seconds` | histogram | SQLAlchemy events | p99 > 1s |
| `run_trace_capture_queue_depth` | gauge | trace_capture | > 1000 events |
| `webhook_delivery_failed_total{reason}` | counter | webhook service | > 10 failures / 5 min |
| `audit_log_redaction_pattern_hits{pattern}` | counter | audit_detail_redactor | non-zero on suspicious patterns |
| `tenant_isolation_violation_total` | counter | tenant_read_policy | ANY non-zero → page |
| `phi_encryption_failures_total` | counter | phi_encryption | ANY non-zero → page |
| `kms_key_rotation_age_days` | gauge | CredentialVault | > 85 days |
| `idle_patient_context_active_count` | gauge | patient_contexts table | > 100 → warn |

### 3.2 Grafana dashboards (Pilot)

| Dashboard | Panels | Refresh |
|-----------|--------|---------|
| API Health | QPS / latency / 5xx rate / DB pool | 30s |
| Agent Run Health | duration histogram / cost / token / model mix | 1 min |
| Cost & Quota | daily CNY burn / per-tenant / per-agent / forecast | 5 min |
| Security | tenant_isolation violations / PHI redaction hits / auth failures | 30s |
| Data Residency | DeepSeek call count by region / data_policy deny count | 1 min |

## §4 Traces (existing run_trace + Sentry PERFORMANCE)

### 4.1 Per-run trace (IMPLEMENTED)

Every agent_run emits a sequence of `RunTraceEvent` rows (Phase 3 / A1A Gate 3R):

| Event type | Emitted on | Fields |
|------------|-----------|--------|
| `StepEvent` | stage transition | step, status, duration_ms |
| `ErrorEvent` | exception | error_type, message (PHI-redacted) |
| `TokenUsageEvent` | LLM call complete | model, input_tokens, output_tokens, cost_cny |
| `ToolCallEvent` | MCP/expert tool call | tool_name, success, duration_ms |
| `CaptureStatusEvent` | trace_capture_status state transition | old_status, new_status |

**Storage**: `run_trace_events` table + SSE stream (`/api/v1/runs/{id}/events?token=...`).

**Retention**: 90 days (cron).

### 4.2 Distributed tracing (DESIGN — Sentry Performance)

Pilot wire-up:
```python
# backend/app/main.py (Pilot env only)
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    environment="pilot-cn-hangzhou",
    traces_sample_rate=0.1,  # 10% sampling
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    before_send=phi_redact_sentry_event,  # redact PHI before emit
)
```

## §5 Alerts (Pilot)

| Alert | Trigger | Severity | Oncall action |
|-------|---------|----------|---------------|
| 5xx spike | 5xx rate > 1% / 5 min | P1 | Check Sentry + rollback if deploy-related |
| Tenant isolation violation | counter > 0 | P0 | Page security oncall immediately |
| PHI redaction failure | counter > 0 | P0 | Page security oncall + check audit_detail_redactor regex |
| DeepSeek outage | 5xx from api.deepseek.com > 50% / 5 min | P1 | Check DeepSeek status page; consider failover to azure-openai |
| DB connection saturation | pool_size > 90% sustained | P1 | Scale uvicorn workers; check slow queries |
| KMS key rotation overdue | age > 85 days | P2 | Rotate key via CredentialVault.rotate() |
| Webhook dead-letter queue | > 10 failed deliveries | P2 | Inspect dead_letter_queue table; retry or drop |
| Audit log write failure | counter > 0 | P0 | Check DB health + fail-closed guard |
| Cron job failure | retention / cleanup failed | P2 | Inspect cron.audit_log; manual rerun if safe |
| Idle patient_context count | > 100 active | P3 | Trigger 24h TTL cron manually |

## §6 Existing health check (IMPLEMENTED)

```python
# backend/app/main.py:1474
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "medcoder_index_ready": ...,
        "medcoder_index_loading": ...,
        "medcoder_index_error": ...,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
    }
```

**NGINX/Caddy health probe**: GET `/api/health` every 5s; 3 consecutive non-200 → remove from rotation.

## §7 Charter §22 forbidden verdicts honoured

- ❌ Not emitted: `OBSERVABILITY_VERIFIED` / `MONITORING_DEPLOYED` / `PRODUCTION_READY`
- ✓ Emitted (only): `PARTIAL_A1C_7_OBSERVABILITY_SPEC_AUTHORED_EXISTING_PIPELINE_VERIFIED_NEW_PIPELINE_DEFERRED_TO_PILOT`
