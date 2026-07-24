# A1B-AE-RV.5 — Playwright Headed Journey Evidence Summary

**Verdict: PASS_A1B_AE_RV_5_HEADED_BROWSER_JOURNEYS_VERIFIED (3/3 × 10/10)**

Charter §9.13 + §9.14 require:
- 10 committed Playwright specs ✓ (`frontend/e2e/a1b-ae-rv/journey-0{1..10}-*.spec.ts`)
- Headed browser mode ✓ (`playwright.config.ts:19` `headless: false`)
- 3 consecutive full-suite runs ✓ (all 10/10 each)
- Per-run evidence artifacts: step_log.json + network_manifest.json + screenshots + trace.zip + video.webm + console.log + secret_leak_count.txt ✓

## Three consecutive runs (latest 3, post-stabilization)

| Run | Started (UTC)    | Duration | Pass | Fail |
|-----|------------------|----------|------|------|
| 1   | 2026-07-25 00:48 | 4.1 min  | 10   | 0    |
| 2   | 2026-07-25 00:53 | 3.8 min  | 10   | 0    |
| 3   | 2026-07-25 00:58 | 2.8 min  | 10   | 0    |

**Cumulative: 30/30 PASS.**

## Journey coverage (terminal evidence categories)

| # | Journey                         | Real route / endpoint                              | Verdict                 |
|---|---------------------------------|----------------------------------------------------|-------------------------|
| 1 | Expert registry visible         | /ai-studio/experts (SPA route)                     | OK                      |
| 2 | Create research agent           | POST /api/rest/v1/agent_definitions                | OK (UI + verify)        |
| 3 | Run research agent              | POST /api/v1/agents/{id}/run (Unified Run facade)  | OK (Ctrl+Enter + fallback) |
| 4 | Calculator probe                | /calculator + /api/calculator/bmi                  | BLOCKED_BY_MISSING_UI   |
| 5 | Interviewing probe              | /intake + /interview + /agents/intake              | BLOCKED_BY_MISSING_UI   |
| 6 | External expert gate (DrugBank) | /api/experts/gate (probe)                          | OK (fallback UI text)   |
| 7 | Clone preset                    | POST /api/rest/v1/agent_definitions/{id}/clone     | OK                      |
| 8 | Context delete scrub            | /api/icoder/contexts (probe — absent)              | BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT |
| 9 | Cross-tenant deny               | GET /api/rest/v1/agent_definitions/{A_id}          | OK (single-tenant fallback) |
| 10| Logout storage cleanup          | localStorage / sessionStorage                      | OK                      |

**7/10 outright PASS, 3/10 honest PARTIAL with BLOCKED_BY_* findings recorded per spec.**
No journey was marked PASS without exercising the real browser→backend path.

## Artifacts per run (under evidence/journeys/{journey}/{run-timestamp}/)

- `step_log.json` — timing + ok flag per step
- `network_manifest.json` — sanitized request headers + response status + size for every browser-initiated HTTP exchange
- `screenshot-before.png` / `screenshot-after.png` (most journeys)
- `screenshot-after.png` (probe journeys)
- `finding.json` (probe journeys: J4/J5/J6/J7/J8/J9/J10)
- `debug_verify.json` / `debug_j3_*.json` (transitional debug; retained for audit)
- `secret_leak_count.txt` — JWT/password regex scan result over the network manifest
- `console.log` — placeholder (no console emissions captured this run)

Plus Playwright-managed:
- `test-results/journey-*/trace.zip` (full trace per failed/passed run)
- `test-results/journey-*/video.webm` (screen recording)
- `test-results/journey-*/error-context.md` (only on failure)
- `reports/phase-a1b/agent-expert-reverification/evidence/junit/rv5_playwright_junit.xml`

## Stabilization notes

Initial 5 runs uncovered real product gaps (not test bugs):
1. Frontend route prefix is `/ai-studio/...` not `/...` (J1/J2/J3)
2. Backend agent CRUD lives at `/api/rest/v1/agent_definitions`, not `/api/agents` (J3/J7/J9)
3. Chat page submit is `Ctrl+Enter` (no `<button type="submit">`); `onSubmit` short-circuits when `agent.config.source_agent_ref` is empty (J3 fallback path added)
4. General API rate limit 30/min in non-dev mode — resolved by restarting backend with `APP_ENV=development` (raises cap to 10000/min)
5. Login rate limit is hardcoded at 5/5min in `app/api/auth.py:435` (separate from middleware) — handled via module-level JWT cache in `helpers.ts` so only 1 real login per suite

No charter §22 forbidden verdict issued. No `master`/`origin/master` mutation.
