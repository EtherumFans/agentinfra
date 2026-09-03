# A1C.8 — Real Browser End-to-End Pilot Journeys (≥15 journeys) Replay Plan

**Phase**: A1C.8
**Date**: 2026-07-25
**Scope**: PDF §十六 ≥15 journeys × 9 evidence pieces each.

---

## §1 Honest scope statement

This subgate **cannot** capture live evidence because:
1. There is no live Pilot stack (cloud account not provisioned — A1C.7 carry-forward)
2. There is no Pilot domain (`api.cn.icoder.cloud` DNS CNAME not registered)
3. There is no Pilot KMS (cloud KMS provider not selected)
4. There is no Pilot DeepSeek key (`LLM_API_KEY` not injected)

**Therefore**: this subgate is `BLOCKED_BY_PILOT_ENVIRONMENT` and is **closed under honest PARTIAL** per Charter §16 (PDF §十六 approved pattern).

This subgate DOES:
- Author the 20-journey Pilot matrix (PDF §十六 asks ≥15)
- Author the per-journey 9-piece evidence template
- Cross-reference RV.5 prior PASS evidence (30/30 journeys) as design provenance
- Cross-reference A1C.3 patient_context API closure (was BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT in RV.5)

## §2 20-Journey Pilot matrix (≥15 required)

| Journey | RV.5 prior | A1C.8 status | Pilot action |
|---------|-----------|--------------|--------------|
| J-01 Expert Registry | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-02 Create Research Agent | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-03 Run Research Agent (DeepSeek live) | PASS | DESIGN_VERIFIED | Replay with real LLM_API_KEY |
| J-04 Calculator Tool | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-05 Interviewing Tool | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-06 External Expert Disabled | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-07 Clone Preset | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| **J-08 Context Delete (patient_context)** | PRIOR_BLOCKED | **A1C.3_FIXED** | Replay on Pilot env with new A1C.3 endpoint |
| J-09 Cross-Tenant Attack | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-10 Logout Storage Cleanup | PASS (3/3) | DESIGN_VERIFIED | Replay on Pilot env |
| **J-11 Patient Context Lifecycle** | NEW | **A1C.3_NEW** | Replay on Pilot env |
| J-12 Webhook Delivery | DESIGN | DESIGN_ONLY | Replay after queue wired |
| J-13 AI-Disabled Mode | PASS (6/6) | DESIGN_VERIFIED | Replay on Pilot env |
| **J-14 PHI Redaction Live** | DESIGN | DESIGN_ONLY | Replay with HAR + Sentry regex |
| J-15 DeepSeek Failure Recovery | PRIOR_PASS (Gate 12) | DESIGN_VERIFIED | Replay with toxiproxy |
| J-16 Multi-tenant Concurrent | PASS (234 tests) | DESIGN_VERIFIED | Replay on Pilot env |
| J-17 SSO Re-login | PASS | DESIGN_VERIFIED | Replay on Pilot env |
| J-18 Webhook Dead-Letter | DESIGN | DESIGN_ONLY | Replay after Redis wired |
| J-19 KMS Key Rotation | DESIGN | DESIGN_ONLY | Replay after cloud KMS wired |
| J-20 Coding Review Approve/Reject | PASS | DESIGN_VERIFIED | Replay on Pilot env |

**Aggregate**: 20/20 journeys authored; 14/20 prior-PASS or DESIGN_VERIFIED; 6/20 require Pilot infra before replay (Redis queue / HAR / KMS provider / toxiproxy).

## §3 RV.5 prior evidence (provenance)

RV.5 (Phase A1B-AE-RV) closed PASS with **30/30 journeys** at commit `0f107d0` on `phase-a1b/agent-expert-terminal-reverification`. Evidence base:

```
reports/phase-a1b/agent-expert-reverification/evidence/journeys/
├── journey-01-expert-registry/
├── journey-02-create-research-agent/
├── journey-03-run-research-agent/
├── journey-04-calculator/
├── journey-05-interviewing/
├── journey-06-external-expert-disabled/
├── journey-07-clone-preset/
├── journey-08-context-delete/
├── journey-09-cross-tenant/
└── journey-10-logout-storage-cleanup/
```

Each journey folder has 10 runs × 6 evidence pieces (step_log + network_manifest + screenshots + secret_leak_count + finding). PDF §十六 requires 9 pieces — 3 additional pieces per run are A1C.8 add:
- `console.log` (Playwright MCP `console_messages()`)
- `trace.zip` (Playwright `--tracing=on`)
- `video.webm` (Playwright `--video=on`)
- `backend_trace.json` (run_trace table export)
- `audit_events.json` (audit_logs table query)

## §4 J-08 Context Delete — A1C.3 closure

**Prior status**: RV.5 marked J-08 as `BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT`.

**A1C.3 closure**: Patient context API implemented in this phase:
- Migration 029 `patient_contexts` table
- `POST /api/v1/patient-context` (create with 24h TTL)
- `GET /api/v1/patient-context/{id}` (read)
- `DELETE /api/v1/patient-context/{id}` (delete + audit emit)
- `POST /api/v1/patient-context/{id}/extend` (extend TTL)

**Evidence**: `reports/phase-a1c/A1C.3/HIS_EMR_INTEGRATION_CONTRACT.md` §4 + 16 HIS/EMR simulator scenarios PASS.

**A1C.8 status**: J-08 unblocked; ready for Pilot replay.

## §5 J-11 Patient Context Lifecycle (NEW journey)

This is a **new** A1C.8 journey that RV.5 did not exercise (RV.5 predated the A1C.3 endpoint):

```
Step 1: Login as clinician (POST /api/v1/auth/login)
Step 2: POST /api/v1/patient-context {patient_id, encounter_id, documents[...]}
        → expect 201 + patient_context_id
Step 3: GET /api/v1/patient-context/{id}
        → expect 200 + documents[]
Step 4: POST /api/v1/patient-context/{id}/extend {ttl_seconds=3600}
        → expect 200 + new expires_at
Step 5: DELETE /api/v1/patient-context/{id}
        → expect 204
Step 6: GET /api/v1/patient-context/{id} (post-delete)
        → expect 404 (not 403 — no leak)
Step 7: Query audit_logs WHERE action LIKE 'patient_context.%'
        → expect 3 rows (create / extend / delete)
```

**9-piece evidence**: per template (`JOURNEY_EVIDENCE_TEMPLATE.md`).

## §6 Pilot replay script (skeleton)

```python
# scripts/a1c8_pilot_journey_runner.py (DESIGN — Pilot env only)
import asyncio
from playwright.async_api import async_playwright

JOURNEYS = [
    "j01_expert_registry",
    "j02_create_research_agent",
    ...,
    "j20_coding_review",
]

async def run_journey(p, journey_id: str):
    browser = await p.chromium.launch(headed=True, slow_mo=100)
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=f"evidence/journeys/{journey_id}/run-{ts}/",
    }
    page = await context.new_page()

    # Start tracing
    await context.tracing.start(screenshots=True, snapshots=True)

    # Run journey steps (per JOURNEY_MATRIX.csv)
    await eval(f"{journey_id}_steps")(page)

    # Stop tracing
    await context.tracing.stop(path=f"evidence/journeys/{journey_id}/run-{ts}/trace.zip")

    # Capture evidence
    await save_console_log(page, ...)
    await save_network_manifest(page, ...)
    await save_screenshots(...)
    await save_backend_trace(run_id, ...)
    await save_audit_events(org_id, ts, ...)
    await save_secret_leak_count(...)
    await save_step_log(...)

    await browser.close()

async def main():
    async with async_playwright() as p:
        for journey_id in JOURNEYS:
            await run_journey(p, journey_id)
```

**Pilot execution**: `python scripts/a1c8_pilot_journey_runner.py --base-url https://api.cn.icoder.cloud`

## §7 Charter §22 forbidden verdicts honoured

- ❌ Not emitted: `BROWSER_E2E_VERIFIED` / `JOURNEYS_ALL_PASS`
- ❌ Not emitted: `LIVE_E2E_DEMONSTRATED`
- ❌ Not emitted: PRODUCTION_READY / HOSPITAL_PILOT_DEPLOYED

This subgate DOES emit (only):
- `PARTIAL_A1C_8_PILOT_JOURNEY_MATRIX_AND_EVIDENCE_TEMPLATE_AUTHORED_LIVE_REPLAY_BLOCKED_BY_PILOT_ENVIRONMENT`

## §8 Carry-forward to A1C.9 + Pilot

The following Pilot actions are tracked in this subgate and consolidated in A1C.9:

1. Provision Pilot env (A1C.7 dependency)
2. Wire Redis queue + cloud KMS + Sentry CN relay
3. Inject `LLM_API_KEY` + `FERNET_KEY` via KMS
4. Run `scripts/a1c8_pilot_journey_runner.py` on Pilot env
5. Capture 9-piece evidence for all 20 journeys
6. Verify `secret_leak_count = 0` across all runs
7. Verify `phi_in_audit_details = false` across all runs
8. Verify `policy_decision.decision = allow` for happy-path journeys
9. Verify `policy_decision.decision = deny` for J-09 cross-tenant attack
10. Generate `PILOT_JOURNEY_EVIDENCE_INDEX.json` with SHA-256 fingerprints
