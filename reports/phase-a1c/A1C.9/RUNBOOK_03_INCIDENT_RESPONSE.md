# A1C.9 — Runbook 03: Incident Response

**Phase**: A1C.9
**Date**: 2026-07-25
**Scope**: Pilot incident response procedures for severity-graded events.

---

## §1 Severity definitions

| Severity | Criteria | Page | Response | Resolution target |
|----------|----------|------|----------|-------------------|
| **P0-CRITICAL** | Patient data leak / tenant isolation break / data loss / ransomware | Security + SRE + CTO + CEO | 5 min | 1 hour |
| **P1-HIGH** | 5xx > 5% sustained / DeepSeek outage / DB unavailable | SRE oncall | 15 min | 4 hours |
| **P2-MEDIUM** | Single tenant unable to use product / cron failure / webhook DLQ growth | SRE oncall (business hours) | 1 hour | 1 business day |
| **P3-LOW** | Cost anomaly / metric drift / single-user bug | Email only | 1 business day | 1 week |

## §2 P0: PHI leak (suspected or confirmed)

### 2.1 Symptoms
- Sentry alert: PHI regex match in logs / network / error
- Manual report: hospital user reports seeing another patient's data
- Audit log review: unredacted patient_id in audit_logs.details

### 2.2 Immediate response (0-5 min)

```bash
# 1. VERIFY the leak
PGPASSWORD=$PW psql ... -c \
  "SELECT id, action, details, created_at FROM audit_logs \
   WHERE details::text ~ '(patient_id|patient_name|1[3-9][0-9]{9})' \
   ORDER BY created_at DESC LIMIT 20;"

# 2. If leak confirmed: FREEZE audit writes (requires A1C-B-018 implementation)
# EMERGENCY PAUSE: 
export ICODER_AUDIT_WRITE_PAUSED=true  # DESIGN — flag not yet implemented
docker restart icoder-backend-blue

# 3. Page oncall
# Use PagerDuty: trigger "PHI Leak P0" incident

# 4. Preserve evidence
# DO NOT modify any logs or DB rows
# Take snapshot of affected window:
PGPASSWORD=$PW pg_dump -h $PG_HOST icoder --table=audit_logs --table=run_trace_events \
  --where "created_at BETWEEN '<leak_start>' AND '<now>'" \
  > /evidence/phi-leak-$(date +%Y%m%d-%H%M).sql
```

### 2.3 Containment (5-60 min)

```bash
# 1. Identify leak vector (which audit emit path skipped redaction?)
# Inspect audit_detail_redactor patterns + recent audit emit callers
grep -r "log_action" backend/app/api/ | head -20

# 2. Patch the redaction gap
# (e.g. add new regex pattern to audit_detail_redactor.py)
# EMERGENCY HOTFIX: deploy via RB-1 rolling deploy (Runbook 01)

# 3. Reverse-leak remediation
# Inspect each leaked row's content; for hospital reporting:
PGPASSWORD=$PW psql ... -c \
  "SELECT id, action, details, ip_address, user_id FROM audit_logs \
   WHERE id IN (<list-of-leaked-ids>);"

# 4. Notify hospital compliance officer (per Pilot contract §bilateral-disclosure)
# Use encrypted channel only
```

### 2.4 Recovery (60 min - 24h)

```bash
# Option A: PITR if leak window is identifiable (Runbook 01 §RB-3)
# Restore audit_logs to pre-leak state; lose post-leak writes (acceptable trade-off)

# Option B: Forward-only redaction
# Apply audit_detail_redactor.redact() to all leaked rows; preserve audit trail
PGPASSWORD=$PW psql ... -c \
  "UPDATE audit_logs SET details = '<REDACTED>' WHERE id IN (<list>);"
# Audit emit 'phI_leak_remediated' to acknowledge the action

# 5. Post-mortem
# Within 48h: file PHI_LEAK_POSTMORTEM.md with timeline + root cause + 5-whys + prevention
```

## §3 P0: Tenant isolation violation

### 3.1 Symptoms
- audit_logs row with action='tenant_isolation.violation_denied' count > 0
- OR (worse): user reports seeing another tenant's data
- Sentry alert on cross-tenant 200 response

### 3.2 Immediate response

```bash
# 1. CONFIRM the violation
# If audit_logs has violation_denied entries, the SYSTEM WORKED (deny path).
# Investigate the ATTACKER: which user_id, which api_client, which IP?
PGPASSWORD=$PW psql ... -c \
  "SELECT actor_user_id, ip_address, action, details->>'target_org_id', created_at \
   FROM audit_logs WHERE action = 'tenant_isolation.violation_denied' \
   ORDER BY created_at DESC LIMIT 20;"

# 2. If violation SUCCEEDED (200 returned cross-tenant):
# THIS IS P0-CRITICAL — page CTO immediately

# 3. Freeze the affected endpoint
# Add emergency allowlist block in nginx:
sudo tee -a /etc/nginx/conf.d/icoder.conf <<'EOF'
location /api/v1/encounters {
  return 503;
}
EOF
sudo systemctl reload nginx

# 4. Patch tenant_read_policy
# Hotfix: verify every query passes through visibility filter
grep -rn "select(Encounter|PatientContext|Document|RunHistory)" backend/app/api/
```

### 3.3 Recovery
- Identify all affected tenants
- Audit every query in the affected window
- Patch + redeploy
- Notify affected hospitals per Pilot contract

## §4 P1: DeepSeek outage

### 4.1 Symptoms
- 5xx from api.deepseek.com > 50% over 5 min
- agent_run latency p99 > 60s
- Tenacity retry budget exhausted

### 4.2 Response

```bash
# 1. Confirm DeepSeek outage
curl -fsS -o /dev/null -w "%{http_code}" https://api.deepseek.com/v1/models
# If 5xx: outage confirmed

# 2. Check DeepSeek status page
curl -fsS https://status.deepseek.com/api/v2/status.json | jq .

# 3. Decision: switch to fallback provider?
# Currently NO fallback implemented (A1C-B-007)
# DECISION: wait for DeepSeek recovery OR degrade to AI-Disabled mode

# 4. If degrading:
sed -i 's|ICODER_AI_ENABLED=true|ICODER_AI_ENABLED=false|' /etc/icoder/cloud.env
docker restart icoder-backend-blue

# 5. Verify AI-Disabled mode (per A1C.5)
curl -fsS -X POST https://api.cn.icoder.cloud/api/v1/agent-run \
  -H "Authorization: Bearer $JWT" -d @payload.json | jq .
# Expected: 503 with details.ai_disabled=true

# 6. When DeepSeek recovers:
sed -i 's|ICODER_AI_ENABLED=false|ICODER_AI_ENABLED=true|' /etc/icoder/cloud.env
docker restart icoder-backend-blue

# 7. Post-incident
# File DEEPSEEK_OUTAGE_POSTMORTEM.md if outage > 15 min
```

## §5 P1: DB saturation

### 5.1 Symptoms
- DB connection pool > 90% sustained
- p99 query latency > 1s
- uvicorn workers queueing

### 5.2 Response

```bash
# 1. Identify slow queries
PGPASSWORD=$PW psql ... -c \
  "SELECT pid, now() - pg_stat_activity.query_start AS duration, query \
   FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC LIMIT 10;"

# 2. Terminate worst offender (carefully!)
PGPASSWORD=$PW psql ... -c "SELECT pg_terminate_backend(<pid>);"

# 3. Scale uvicorn workers
docker stop icoder-backend-blue
docker run -d --name icoder-backend-blue \
  ... (same as Runbook 01 §2.3 but with --workers 8 instead of 4)

# 4. Investigate root cause
# Common: missing index / N+1 query / lock contention
EXPLAIN ANALYZE <suspect-query>
```

## §6 P2: Cron failure

### 6.1 Symptoms
- audit_logs row with action='cron.<name>.failed'
- Job-specific symptom (e.g. orphan runs accumulating)

### 6.2 Response

```bash
# 1. Inspect failure
docker logs icoder-backend-blue --since 1h | grep "cron.<name>"

# 2. Manual rerun if safe
docker exec icoder-backend-blue python -m app.cron.<name>

# 3. If persists: file P2 ticket
# 4. Post-fix: deploy via RB-1
```

## §7 P2: Webhook dead-letter growth

### 7.1 Symptoms
- dead_letter_queue row count > 10 in 1 hour

### 7.2 Response

```bash
# 1. Identify failing webhooks
PGPASSWORD=$PW psql ... -c \
  "SELECT delivery_id, last_error, created_at FROM dead_letter_queue \
   WHERE created_at > now() - interval '1 hour' ORDER BY created_at DESC;"

# 2. Check hospital HIS endpoint health
curl -I https://his.hospital-a.cn/icoder/callback

# 3. If HIS down: pause deliveries
# (DESIGN — pause mechanism not implemented; manual stop via app flag)

# 4. If HIS healthy: investigate payload — may contain invalid signature
# Manual replay after fix:
PGPASSWORD=$PW psql ... -c \
  "SELECT retry_delivery('<delivery_id>');"
```

## §8 Communication templates

### 8.1 P0 customer notification (encrypted channel)

```
SUBJECT: [URGENT] iCoDer Pilot — Security Incident requiring your attention

Dear Hospital Compliance Officer,

We identified a security incident at <timestamp> affecting <scope>.
Our team responded within <X> minutes and contained the incident.

What we know:
- <brief description>
- <affected scope>
- <no/yes patient data involved>

What we did:
- <containment actions>
- <evidence preserved>

What we ask of you:
- <action items for hospital>

We will provide a detailed post-mortem within 48 hours.

Sincerely,
iCoDer Security Oncall
```

### 8.2 P1 internal incident channel

```
@oncall — P1 incident started <timestamp>
- Symptom: <one-line description>
- Severity: P1
- Suspected cause: <guess>
- Runbook: <link>
- Status: INVESTIGATING
- Next update: <15 min>
```

## §9 Charter §22 forbidden verdicts honoured

- ❌ Not emitted: `INCIDENT_RESPONSE_VERIFIED` / `SECURITY_VERIFIED`
- ❌ Not emitted: `PRODUCTION_READY`

This runbook DOES emit (only):
- `PARTIAL_A1C_9_RUNBOOK_03_INCIDENT_RESPONSE_AUTHORED_LIVE_DRILL_REQUIRES_PILOT_ENV`
