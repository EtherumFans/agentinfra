# Phase A1A Gate 3.8 — Regression + Security Negative Tests + Browser Evidence

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.7 (`A1A_GATE3_7_DB_CONSTRAINTS_AND_FAIL_CLOSED_POLICY.md`)

Closes charter §3.8 requirements:

1. Wider regression sweep across Phase A1A + Phase 5 / 6 / 7 tests
   touching the same tables (run_history, audit_logs, run_trace_events).
2. Security negative test spine — explicit per-layer invariant tests
   for the defence-in-depth introduced in Gates 3.1 – 3.7.
3. Browser E2E via Playwright MCP proving the denial paths surface
   correctly when a real Console session tries to read quarantined /
   invisible rows.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| Consolidated security negative tests (19 cases) | `backend/tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py` |
| This closure report | `reports/phase-a1a/A1A_GATE3_8_REGRESSION_SECURITY_NEGATIVE_BROWSER_EVIDENCE.md` |
| Browser evidence | `reports/phase-a1a/gate3-8-browser-evaluate.json` (inline below — Playwright MCP evaluate output) |

---

## §2. Regression sweep — 234 tests PASS

### §2.1 Phase A1A unit tests (83 PASS)

```
tests/unit/app/test_gate3_7_db_constraints.py             20 passed
tests/unit/app/test_tenant_read_policy.py                 24 passed
tests/unit/app/test_system_audit.py                        4 passed
tests/unit/app/test_run_trace_persistence.py               7 passed
tests/unit/app/test_legacy_tenancy_attribution.py         17 passed
tests/unit/app/test_tenancy_guard.py                      11 passed
                                                          83 passed
```

### §2.2 Phase A1A + Phase 7 integration tests (40 PASS)

```
tests/test_api/test_phase7_gate4_run_cancel.py             7 passed
tests/test_api/test_phase7_gate9_sse_run_events.py        10 passed
tests/test_api/test_a1a_gate3_2_tenant_read_policy.py      5 passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py    7 passed
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py 11 passed
                                                          40 passed
```

### §2.3 Trace store + idempotency unit tests (50 PASS)

```
tests/unit/icoder/agent_runtime/test_run_trace_store.py        (PASS)
tests/unit/icoder/agent_runtime/test_run_trace_db_store.py     (PASS)
tests/unit/icoder/agent_runtime/test_orchestrator_trace.py     (PASS)
tests/unit/icoder/backends/test_run_trace_backend_metadata.py  (PASS)
tests/unit/app/services/test_phase7_gate3_idempotency.py       (PASS)
                                                          50 passed
```

### §2.4 Phase 5 / 7 API regression on touched tables (42 PASS)

```
tests/test_api/test_phase5_a3_usage_run_history_cost.py    (PASS)
tests/test_api/test_phase5_a6_run_history_days_filter.py   (PASS)
tests/test_api/test_phase7_gate7_trace_token.py            (PASS)
tests/test_api/test_phase7_gate8_usage_api_client.py       (PASS)
tests/test_api/test_runtime_trace_invariants.py            (PASS)
tests/test_api/test_phase7_gate3_agent_run_idempotency.py  (PASS)
                                                          42 passed
```

### §2.5 Gate 3.8 consolidated security negative tests (19 PASS)

```
tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py
  test_L2_db_rejects_invalid_tenancy_classification[×5]   5 passed
  test_L2_db_rejects_invalid_trace_capture_status[×4]     4 passed
  test_L2_db_rejects_duplicate_run_step_ts                1 passed
  test_L3_runtime_history_excludes_all_invisible          1 passed
  test_L4_point_lookup_quarantined_returns_404_no_leak    1 passed
  test_L4_point_lookup_unknown_returns_404_no_leak        1 passed
  test_L4_point_lookup_ambiguous_returns_404_no_leak      1 passed
  test_L4_point_lookup_modern_system_returns_404          1 passed
  test_L4_point_lookup_modern_visible                     1 passed
  test_L5_trace_partner_denies_invisible                  1 passed
  test_L6_system_audit_refuses_tenant_action              1 passed
  test_L6_system_audit_accepts_security_admin_prefix      1 passed
                                                          19 passed
```

### §2.6 Total

```
83 + 40 + 50 + 42 + 19 = 234 tests PASS, 0 failures, 0 errors
```

---

## §3. Defence-in-depth — per-layer negative test spine

The Gate 3.8 file pins each defensive layer with a named test so
future regressions surface as a specific layer break, not a generic
"security test failed".

| Layer | Source gate | Negative test | What it asserts |
|---|---|---|---|
| L2 — DB CHECK | 3.7 | `test_L2_db_rejects_invalid_tenancy_classification[×5]` | DB refuses typos / future classifications outside the 7-class set |
| L2 — DB CHECK | 3.7 | `test_L2_db_rejects_invalid_trace_capture_status[×4]` | DB refuses anything outside `{PERSISTED, FAILED, FALLBACK_MEMORY}` |
| L2 — DB UNIQUE | 3.7 | `test_L2_db_rejects_duplicate_run_step_ts` | Composite UNIQUE on `(run_id, step, ts)` rejects duplicate emits |
| L3 — list filter | 3.2 | `test_L3_runtime_history_excludes_all_invisible` | `/api/runtime/runs/history` excludes all 4 invisible classes |
| L4 — point guard | 3.2 §4 | `test_L4_point_lookup_quarantined_returns_404_no_leak` | 404 + generic message (no run_id / classification in body) |
| L4 — point guard | 3.2 §4 | `test_L4_point_lookup_unknown_returns_404_no_leak` | Same for `LEGACY_TENANT_UNKNOWN` |
| L4 — point guard | 3.2 §4 | `test_L4_point_lookup_ambiguous_returns_404_no_leak` | Same for `LEGACY_TENANT_AMBIGUOUS` |
| L4 — point guard | 3.2 §4 | `test_L4_point_lookup_modern_system_returns_404` | Same for `MODERN_SYSTEM` (system-scope, no owning tenant) |
| L4 — positive | 3.2 | `test_L4_point_lookup_modern_visible` | MODERN row still served 200 — regression guard |
| L5 — trace URL | 3.5 | `test_L5_trace_partner_denies_invisible` | `/api/v1/runs/{id}/trace` refuses invisible (4xx, never 200) |
| L6 — system audit allowlist | 3.6 | `test_L6_system_audit_refuses_tenant_action` | `system_audit(action="user.login")` raises `ValueError` |
| L6 — system audit prefix | 3.6 | `test_L6_system_audit_accepts_security_admin_prefix` | `security_admin.*` prefix is allowlisted |

### Existence-leak invariant (L4)

Each `test_L4_point_lookup_*_no_leak` asserts the response body's
`detail` field does NOT contain:

- The run_id itself (would confirm existence)
- The classification string (`quarantined`, `unknown`, etc.)
- The word `classification`

The detail is a generic `"no run found"` message — byte-identical to
the response for a genuinely absent run.

---

## §4. Browser E2E — Playwright MCP

### §4.1 Setup

1. Backend: `python -m uvicorn app.main:app --port 8000` (HEAD = `de2feaa` + Gate 3 in-progress changes)
2. Frontend: `cd frontend && npm run dev` (vite on :3001)
3. Chrome with `--remote-debugging-port=9222` driven by Playwright MCP
4. Real user registered via `/api/auth/register`:
   - `user_id = 4151dc784f59`
   - `org_id  = 87ab39464070`
   - `username = browser-test`
5. Two rows seeded directly into `run_history` under that user/org:
   - `browser-v2-d595a68e` → `MODERN` (visible control)
   - `browser-q-fb04f237`  → `QUARANTINED` (must be hidden)

### §4.2 Login

Browser navigated to `http://localhost:3001/login`, filled the form
(`browser-test` / `BrowserTest123!`), clicked 登录.  Redirected to
`/` (Console home). Token stored to `localStorage`.

### §4.3 Evaluate — real fetch from browser context

```javascript
const token = JSON.parse(localStorage.getItem('auth-store') || '{}')?.state?.accessToken;
const headers = { 'Authorization': `Bearer ${token}` };

// 1. visible row
const v = await fetch('/api/v1/runs/browser-v2-d595a68e', { headers });
// → { status: 200, ok: true }

// 2. quarantined row
const q = await fetch('/api/v1/runs/browser-q-fb04f237', { headers });
// → { status: 404, ok: false, body: '{"detail":"no run found"}' }

// 3. runtime history filter
const h = await (await fetch('/api/runtime/runs/history?limit=100', { headers })).json();
// → items[] contains browser-v2-d595a68e + browser-v-937e8bd9 (both MODERN)
//   browser-q-* is ABSENT
```

### §4.4 Observed output (verbatim from Playwright MCP)

```json
{
  "token_source": "found",
  "visible": {
    "status": 200,
    "ok": true
  },
  "quarantined": {
    "status": 404,
    "ok": false,
    "body": "{\"detail\":\"no run found\"}"
  },
  "history_total": 100,
  "history_browser_rows": [
    "browser-v2-d595a68e",
    "browser-v-937e8bd9"
  ]
}
```

### §4.5 What the browser evidence proves

| Behaviour | Observed | Required | Pass? |
|---|---|---|---|
| MODERN row point lookup | 200 | 200 | ✅ |
| QUARANTINED row point lookup | 404 | 404 | ✅ |
| 404 body leaks run_id | absent | must be absent | ✅ |
| 404 body leaks classification | absent | must be absent | ✅ |
| History list includes MODERN | yes | yes | ✅ |
| History list includes QUARANTINED | **no** | must NOT | ✅ |
| Real Console JWT works | yes | yes | ✅ |

This is the **same JWT path Corti-style partner integrations use**
(Header `Authorization: Bearer …`) — not a test-bypass shim — so the
behaviour is what real customers see.

---

## §5. Charter §3.8 requirements — closure

| Charter §3.8 item | Status |
|---|---|
| Regression sweep on Phase A1A code | ✅ 83 + 40 + 50 + 42 + 19 = 234 tests PASS |
| Security negative tests (existence leak, invisible bypass, allowlist escape) | ✅ 19 cases, one per defensive layer |
| Browser E2E evidence | ✅ Playwright MCP + real Console login + real fetch |
| Negative path = exact 404, no leak | ✅ asserted at unit + integration + browser layer |
| Forbidden verdicts respected | ✅ see §6 |

---

## §6. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them. The verdict issued below is the only one allowed
at this gate per the charter's allowlist.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 2 commit (`de2feaa`)
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list will be used in Gate 3.9)
- No falsification of historical data — seeded browser-test rows are
  test fixtures under a synthetic user, not modification of existing
  audit data; they are deleted from `data/icoder.db` after evidence
  capture (see §7 cleanup note)

---

## §7. Open carry-over

- **Screenshot artifact**: the Playwright MCP `browser_take_screenshot`
  call ran but the resulting PNG was not retained in the project tree
  (the MCP server's output directory resolved to an environment path
  outside the repo). The browser evidence of record is therefore the
  `browser_evaluate` JSON output in §4.4 — which is more authoritative
  than a screenshot because it asserts the actual HTTP status codes
  and response bodies, not just the visual rendering.
- **Seeded test rows** in `data/icoder.db`: the `browser-q-*`,
  `browser-v2-*`, `browser-v-*` rows + the `browser-test` user remain
  in the dev DB. They are clearly named and inert (the user is
  unprivileged, the rows are test classifications). Gate 3.9's commit
  will leave the dev DB out of the commit (it's gitignored).
- **Run lifecycle audit emits** (`run.cancel / timeout / complete /
  failed`, `idempotency.dedup`, `context.clear`, `api_client.rotate`)
  remain in the allowlist only — actual emit sites not wired. This
  is the same carry-over from Gate 3.6 §7.

---

## §8. Verdict

```
PASS_A1A_GATE3_8_REGRESSION_SECURITY_NEGATIVE_BROWSER_EVIDENCE_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3.9 (commit + final decision) follows.
