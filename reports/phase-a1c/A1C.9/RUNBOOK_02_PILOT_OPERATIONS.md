# A1C.9 — Runbook 02: Pilot Operations

**Phase**: A1C.9
**Date**: 2026-07-25
**Scope**: Day-to-day Pilot operations (not deploy / not incident — those are 01 + 03).

---

## §1 Daily operations checklist

### 1.1 Morning check (09:00 CN, on-call SRE)

```bash
# 1. Health probe
curl -fsS https://api.cn.icoder.cloud/api/health | jq .

# 2. Grafana dashboard sanity
# Open: https://grafana.cn.icoder.cloud/d/api-health
# Verify: 5xx rate < 1%, p99 latency < 5s, DB pool < 80%

# 3. Sentry error review
# Open: https://sentry.cn-relay.icoder.cloud/organizations/icoder/issues/?query=is:unresolved
# Triage any new P0/P1 issues

# 4. Audit log volume sanity
PGPASSWORD=$PW psql ... -c \
  "SELECT date_trunc('hour', created_at), COUNT(*) FROM audit_logs \
   WHERE created_at > now() - interval '24 hours' GROUP BY 1 ORDER BY 1;"
# Expected: smooth volume; no sudden 10x spike

# 5. Cost burn rate
PGPASSWORD=$PW psql ... -c \
  "SELECT SUM(cost_cny) FROM run_history WHERE created_at::date = current_date;"
# Verify: daily burn within Pilot budget (¥10,000/day target)
```

### 1.2 Mid-day check (13:00 CN)

```bash
# 1. Webhook delivery health
PGPASSWORD=$PW psql ... -c \
  "SELECT COUNT(*) FROM dead_letter_queue WHERE created_at > now() - interval '6 hours';"
# Expected: < 10

# 2. Idle patient_context count
PGPASSWORD=$PW psql ... -c \
  "SELECT COUNT(*) FROM patient_contexts WHERE status='active' AND organization_id='<hospital-a>';"
# Expected: < 100 (24h TTL should naturally bound this)

# 3. KMS key age
aliyun kms DescribeKey --KeyId $ICODER_KMS_KEY_ID | jq .KeyMetadata.Rotation
# Alert if age > 85 days

# 4. Fernet envelope usage audit
PGPASSWORD=$PW psql ... -c \
  "SELECT COUNT(*) FILTER (WHERE encrypted_content IS NOT NULL) AS encrypted, \
          COUNT(*) FILTER (WHERE encrypted_content IS NULL) AS unencrypted \
   FROM documents;"
# Expected: encrypted > 0; unencrypted = 0
```

### 1.3 End-of-day check (18:00 CN)

```bash
# 1. Daily backup verify
ls -lh /backups/$(date +%Y%m%d)*
# Expected: pg_dump + snapshot both present

# 2. Cron job success audit
PGPASSWORD=$PW psql ... -c \
  "SELECT action, status, COUNT(*) FROM audit_logs \
   WHERE action LIKE 'cron.%' AND created_at::date = current_date \
   GROUP BY 1, 2;"
# Expected: all status=success

# 3. Cost daily report (auto-emailed)
curl -fsS https://api.cn.icoder.cloud/api/v1/billing/daily-report | jq .
```

## §2 Weekly operations

### 2.1 Monday 09:00 — Pilot status review

- Review Sentry unresolved issues (target: 0 P0, < 5 P1)
- Review Grafana week-over-week trends
- Review cost vs budget (target: < 100% weekly budget = 70K CNY)
- Review dead_letter_queue (target: < 50 cumulative weekly)
- Review tenant isolation violation count (target: 0)

### 2.2 Wednesday 14:00 — Cron maintenance

```bash
# 1. Run idempotency cleanup
docker exec icoder-backend-blue python -m app.cron.cleanup_idempotency

# 2. Run retention cron
docker exec icoder-backend-blue python -m app.services.retention

# 3. Run cleanup_orphan_runs
docker exec icoder-backend-blue python -m app.cron.cleanup_orphan_runs

# 4. Verify cron audit emits
PGPASSWORD=$PW psql ... -c \
  "SELECT action, status, created_at FROM audit_logs \
   WHERE action LIKE 'cron.%' AND created_at > now() - interval '1 hour';"
```

### 2.3 Friday 16:00 — Backup restore spot-check

```bash
# Pick a random nightly backup from past 7 days
BACKUP_FILE=$(ls /backups/$(date -d '3 days ago' +%Y%m%d)*.sql | head -1)

# Restore to test database
PGPASSWORD=$PW psql -h $PG_HOST -U icoder_app -d icoder_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
PGPASSWORD=$PW pg_restore -h $PG_HOST -U icoder_app -d icoder_test $BACKUP_FILE

# Spot-check row counts
PGPASSWORD=$PW psql -h $PG_HOST -U icoder_app -d icoder_test -c \
  "SELECT (SELECT COUNT(*) FROM organizations) AS orgs, \
          (SELECT COUNT(*) FROM users) AS users, \
          (SELECT COUNT(*) FROM audit_logs) AS audits, \
          (SELECT COUNT(*) FROM run_history) AS runs;"

# Compare against production counts
# Expected: deltas within 5%

# Cleanup
PGPASSWORD=$PW psql -h $PG_HOST -U icoder_app -d icoder_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

## §3 Monthly operations

### 3.1 KMS key rotation

```bash
# 1. Trigger rotation in cloud KMS
aliyun kms RotateKey --KeyId $ICODER_KMS_KEY_ID

# 3. Backend picks up new key version on next CredentialVault cache refresh
# (currently requires manual restart — A1C-B-008)

# 3. Restart backend to invalidate CredentialVault cache
docker restart icoder-backend-blue
sleep 30 && docker logs icoder-backend-blue --tail 20 | grep "key version"

# 4. Verify with end-to-end test
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run ...

# 5. Audit log inspection
PGPASSWORD=$PW psql ... -c \
  "SELECT action, details->>'key_version' FROM audit_logs \
   WHERE action = 'kms.key_rotated' ORDER BY created_at DESC LIMIT 5;"
```

### 3.2 Cost & usage report

```bash
# Generate monthly cost report
curl -fsS https://api.cn.icoder.cloud/api/v1/billing/monthly-report?month=$(date -d 'last month' +%Y-%m) | jq .

# Review per-tenant cost
PGPASSWORD=$PW psql ... -c \
  "SELECT organization_id, SUM(cost_cny) AS total_cost, COUNT(*) AS run_count \
   FROM run_history WHERE created_at >= date_trunc('month', current_date - interval '1 month') \
   GROUP BY 1 ORDER BY 2 DESC;"
```

## §4 On-call escalation

| Severity | Trigger | Page | Response SLA | Escalation |
|----------|---------|------|--------------|-----------|
| P0 | Tenant isolation violation / PHI leak / data loss | Security oncall + SRE oncall + CTO | 5 min | CTO → CEO |
| P1 | 5xx spike / DeepSeek outage / DB saturation | SRE oncall | 15 min | SRE lead → Eng director |
| P2 | Cron failure / webhook dead-letter growth | SRE oncall (business hours) | 1 hour | SRE lead |
| P3 | Cost trend anomaly / minor metric drift | Email only | 1 business day | — |

## §5 Pilot success criteria (90-day soak)

Pilot is considered successful at 90 days IF:

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Uptime | ≥ 99.5% | NGINX logs |
| Tenant isolation violations | 0 | audit_logs counter |
| PHI leak incidents | 0 | Sentry regex alert |
| Mean agent_run p99 latency | < 30s | run_history |
| Daily cost within budget | < ¥10K/day | billing_service |
| Hospital user NPS | ≥ 30 | monthly survey |
| Code suggestion acceptance rate | ≥ 60% | run_history.review_outcome |
| DeepSeek outage incidents | < 5 | Sentry |
| Mean time to recovery (P1) | < 30 min | on-call log |
| Audit completeness | 12/12 fields | quarterly audit report |

**Pilot success → next phase boundary (Pilot Production Recommendation)** — outside this Charter.

## §6 Charter §22 forbidden verdicts honoured

- ❌ Not emitted: `PILOT_OPERATIONS_VERIFIED` / `PILOT_SUCCESS_VERIFIED`
- ❌ Not emitted: `PRODUCTION_READY`

This runbook DOES emit (only):
- `PARTIAL_A1C_9_RUNBOOK_02_PILOT_OPERATIONS_AUTHORED_LIVE_EXECUTION_REQUIRES_OPEN_BLOCKER_RESOLUTION`
