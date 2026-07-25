# A1C.8 — Per-Journey 9-Piece Evidence Template

**Phase**: A1C.8
**Date**: 2026-07-25
**Scope**: PDF §十六 mandatory 9-piece evidence bundle for each Pilot journey.

---

## §1 The 9 mandatory evidence pieces (PDF §十六)

For every journey, the Pilot runner MUST capture and store these 9 artifacts:

| # | Artifact | Format | Tool | Storage path template |
|---|----------|--------|------|----------------------|
| 1 | **step_log** | JSON | Playwright MCP step recorder | `evidence/journeys/<jid>/run-<ts>/step_log.json` |
| 2 | **network_manifest** | JSON | Playwright MCP + request interception | `evidence/journeys/<jid>/run-<ts>/network_manifest.json` |
| 3 | **console** | plain text | Playwright MCP console capture | `evidence/journeys/<jid>/run-<ts>/console.log` |
| 4 | **screenshots** | PNG (before + after + key steps) | Playwright MCP screenshot | `evidence/journeys/<jid>/run-<ts>/screenshot-{step}.png` |
| 5 | **trace.zip** | ZIP (Playwright trace) | Playwright MCP `--tracing=on` | `evidence/journeys/<jid>/run-<ts>/trace.zip` |
| 6 | **video.webm** | WebM | Playwright MCP `--video=on` | `evidence/journeys/<jid>/run-<ts>/video.webm` |
| 7 | **secret_leak_count** | plain text (integer) | regex scanner over (1)+(2)+(3) | `evidence/journeys/<jid>/run-<ts>/secret_leak_count.txt` |
| 8 | **backend_trace** | JSON | run_trace table export | `evidence/journeys/<jid>/run-<ts>/backend_trace.json` |
| 9 | **audit_events** | JSON | audit_logs table query | `evidence/journeys/<jid>/run-<ts>/audit_events.json` |

## §2 Evidence schema

### 2.1 step_log.json

```json
{
  "journey_id": "J-08",
  "journey_name": "Context Delete",
  "run_timestamp": "2026-07-25T09:14:00Z",
  "actor": {
    "user_id": "u-clinician-001",
    "organization_id": "org-hospital-a",
    "rbac_role": "clinician"
  },
  "environment": {
    "base_url": "https://api.cn.icoder.cloud",
    "browser": "chromium-headed",
    "viewport": "1440x900"
  },
  "steps": [
    {
      "step_id": 1,
      "action": "navigate",
      "target": "/login",
      "started_at": "2026-07-25T09:14:00.100Z",
      "completed_at": "2026-07-25T09:14:00.842Z",
      "duration_ms": 742,
      "result": "success"
    },
    {
      "step_id": 2,
      "action": "fill",
      "target": "input[name=username]",
      "value": "u-clinician-001",
      ...
    },
    ...
  ],
  "total_duration_ms": 8421,
  "outcome": "success|failure|partial",
  "blockers": []
}
```

### 2.2 network_manifest.json

```json
{
  "run_timestamp": "2026-07-25T09:14:00Z",
  "total_requests": 47,
  "by_method": {"GET": 28, "POST": 15, "DELETE": 1, "PUT": 3},
  "by_status": {"200": 38, "201": 6, "401": 1, "403": 0, "404": 1, "5xx": 0},
  "by_path_template": {
    "/api/v1/patient-context": {"POST": 1, "GET": 1, "DELETE": 1},
    "/api/v1/agent-run": {"POST": 1},
    ...
  },
  "phI_leak_scan": {
    "patterns_checked": ["patient_id", "patient_name_chinese", "phone_cn", "id_card_cn", "email", "icd10_with_evidence", "medical_record_text"],
    "matches_found": 0,
    "matches_redacted": 0,
    "verdict": "PASS_NO_LEAK"
  },
  "secret_leak_scan": {
    "patterns_checked": ["sk-", "gAAAAAB", "BEGIN PRIVATE KEY", "Bearer eyJ", "password="],
    "matches_found": 0,
    "verdict": "PASS_NO_LEAK"
  }
}
```

### 2.3 console.log

```
[09:14:00.142] INFO User authenticated: u-clinician-001 (org-hospital-a)
[09:14:01.420] INFO POST /api/v1/patient-context 201 281ms
[09:14:02.011] INFO patient_context.created audit emitted (event_id=ev-8f7b3c2a)
...
```

### 2.4 screenshots

- `screenshot-01-login.png` — after login form filled
- `screenshot-02-context-create.png` — after POST /patient-context
- `screenshot-03-context-confirm.png` — after DELETE confirm
- `screenshot-04-context-404.png` — after GET (proves 404)
- `screenshot-05-logout.png` — after logout

### 2.5 trace.zip

Playwright trace file (open with `npx playwright show-trace trace.zip`). Contains:
- Every action with selector
- DOM snapshot before/after each action
- Network requests with timing waterfall
- Console messages inline

### 2.6 video.webm

WebM video of entire journey (1440x900 @ 30fps). Useful for:
- Auditor replay
- Training material
- Bug repro context

### 2.7 secret_leak_count.txt

```
0
```

Single integer — count of secret patterns found across step_log + network_manifest + console. MUST be 0 for journey PASS.

### 2.8 backend_trace.json

```json
{
  "trace_id": "tr_8f7b3c2a-9e4d-4c1f-bb25-7c1f3a9d6e44",
  "run_id": "run-2026-07-25-8842",
  "events": [
    {"seq": 1, "type": "StepEvent", "step": "agent_run.start", "status": "captured_pending", "ts": "..."},
    {"seq": 2, "type": "TokenUsageEvent", "model": "deepseek-v4-flash", "input_tokens": 8421, "output_tokens": 384, "cost_cny": 0.0142, "ts": "..."},
    {"seq": 3, "type": "StepEvent", "step": "agent_run.complete", "status": "captured_committed", "ts": "..."}
  ],
  "capture_status_final": "CAPTURED_COMMITTED"
}
```

### 2.9 audit_events.json

```json
{
  "audit_log_rows": [
    {
      "audit_id": "...",
      "actor": {"user_id": "u-clinician-001", "username": "dr_wang", "user_type": "human"},
      "organization": {"organization_id": "org-hospital-a", "tenancy_classification": "MODERN"},
      "patient_context": {"patient_context_id": "pc-...", "patient_id_redacted": "<REDACTED>"},
      "action": "patient_context.create",
      "purpose": "treatment",
      "resource": {"resource_type": "patient_context", "resource_id": "pc-..."},
      "result": {"status": "success", "http_status_code": 201},
      "timestamp": "2026-07-25T09:14:22.482Z",
      "trace_id": null,
      "source_ip": "10.0.1.42",
      "client": {"client_kind": "browser_spa", "user_agent": "Mozilla/5.0 ..."},
      "policy_decision": {"decision": "allow", "rbac_role": "clinician", "tenant_match": true}
    },
    ...
  ],
  "row_count": 5,
  "phI_in_audit_details": false,
  "verdict": "PASS_NO_PHI_LEAK"
}
```

## §3 Charter §22 forbidden verdicts honoured

This template does NOT emit:
- ❌ `JOURNEY_EVIDENCE_VERIFIED` — live re-run deferred to Pilot
- ❌ `BROWSER_E2E_COMPLETE` — Charter §22 forbids

This template DOES emit (only):
- `PARTIAL_A1C_8_EVIDENCE_TEMPLATE_AUTHORED_LIVE_RE_RUN_DEFERRED_TO_PILOT`
