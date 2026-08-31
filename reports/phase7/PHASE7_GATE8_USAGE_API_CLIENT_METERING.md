# Phase 7 Gate 8 — Usage × API Client Real Metering Closed Loop

**Date**: 2026-07-14
**Status**: PASS_GATE8_USAGE_API_CLIENT_METERING_VERIFIED
**Soft gate** (not on Checkpoint A/B/C/D hard path)

---

## §13 — Acceptance criteria

Per Phase 7 Gate 0 §R5 (audit findings 5 + 16):
- `run_history.api_client_id` column was missing → **FIXED in Gate 5**
- Usage endpoints could not filter by partner → **FIXED in this gate**
- Partners / admins could not answer "which partner spent what?" → **FIXED in this gate**

The Phase 7 brief positions Gate 8 as the metering closure: every credit-consuming run is attributable to a `(user, api_client)` pair, and Usage endpoints can slice cost by that attribution.

---

## Deliverables

| # | Item | File | Status |
|---|------|------|--------|
| 1 | `/api/usage/summary` accepts `api_client_id` filter | `app/api/usage.py` | ✅ |
| 2 | `/api/usage/by-agent` accepts `api_client_id` filter | same | ✅ |
| 3 | NEW `/api/usage/by-client` per-partner breakdown endpoint | same | ✅ |
| 4 | `"console"` sentinel for `api_client_id IS NULL` runs | all three endpoints | ✅ |
| 5 | `filters` echo in response (frontend can display active filters) | all three endpoints | ✅ |
| 6 | 13 tests covering §13.1-§13.3 | `tests/test_api/test_phase7_gate8_usage_api_client.py` | ✅ 13/13 |

---

## §13.1 `/summary` filter behavior

```
GET /api/usage/summary?days=30                                       → all runs
GET /api/usage/summary?days=30&api_client_id=partner-a               → only partner-a's runs
GET /api/usage/summary?days=30&api_client_id=console                 → only Console-initiated runs
GET /api/usage/summary?days=30&api_client_id=partner-a&agent_id=X    → composed filter
```

The `"console"` sentinel is **case-insensitive** (`CONSOLE`, `Console`, `console` all map to the same IS NULL filter). This lets the UI render a single dropdown that includes "Console" alongside partner names without needing special-case logic.

The `filters` echo in the response shows what was applied — the frontend can display "Filtered by: partner-a × cdi-agent" instead of inferring from the URL.

---

## §13.2 `/by-agent` filter behavior

```
GET /api/usage/by-agent?days=30                          → per-agent totals across all clients
GET /api/usage/by-agent?days=30&api_client_id=partner-a  → per-agent breakdown for partner-a only
GET /api/usage/by-agent?days=30&api_client_id=console    → Console-only per-agent breakdown
```

Use case: "Partner A is using which agents the most?" — typical question during pricing tier negotiation or partner onboarding review.

---

## §13.3 NEW `/by-client` endpoint

`GET /api/usage/by-client?days=30`

Returns one row per `api_client_id`, sorted by cost descending:

```json
{
  "items": [
    {"api_client_id": "partner-b", "cost": 0.50, "run_count": 1,  "avg_latency_ms": 2500},
    {"api_client_id": "partner-a", "cost": 0.35, "run_count": 3,  "avg_latency_ms": 4000},
    {"api_client_id": "console",   "cost": 0.03, "run_count": 2,  "avg_latency_ms": 1650}
  ],
  "total_cost": 0.88,
  "currency": "CNY",
  "period_days": 30
}
```

Design notes:
- The `"console"` row is **synthetic** — it aggregates all runs with `api_client_id IS NULL`. It's only included if there are Console runs in the window (otherwise the row is omitted, not zero-filled, to keep the chart clean).
- Sorted by cost descending by default — admins see the most expensive partner first.
- `total_cost` is the sum of all returned items, which equals the unfiltered `/summary` `credits_used` for the same window.

---

## Test coverage (13/13 PASS)

**§13.1 /summary filter (7 tests):**
1. `test_summary_unfiltered_aggregates_all_clients` — 0.88 total
2. `test_summary_filtered_by_partner_a_returns_only_partner_a_runs` — 0.35
3. `test_summary_filtered_by_partner_b_returns_only_partner_b_runs` — 0.50
4. `test_summary_console_sentinel_returns_only_console_runs` — 0.03
5. `test_summary_console_sentinel_case_insensitive` — `CONSOLE`/`Console`/`console`
6. `test_summary_combines_api_client_id_with_agent_id` — partner-a × cdi-agent = 0.05
7. `test_summary_unknown_api_client_returns_zero` — empty result, not error

**§13.2 /by-agent filter (3 tests):**
8. `test_by_agent_unfiltered_lists_all_agents`
9. `test_by_agent_filtered_by_partner_a`
10. `test_by_agent_console_sentinel`

**§13.3 /by-client endpoint (3 tests):**
11. `test_by_client_returns_per_partner_plus_console_bucket` — full breakdown shape
12. `test_by_client_empty_when_no_runs` — empty items list
13. `test_by_client_omits_console_bucket_when_no_console_runs` — synthetic bucket skipped when zero

Seed fixture uses `user_id="u-test-bypass"` (the conftest auth-bypass user) and deterministic cost values per run, so assertions are exact (not ranges).

---

## Regression

```
Gate 3 (idempotency)            4 PASS
Gate 4 (run cancel)             7 PASS
Gate 5 (API clients)           15 PASS
Gate 6 (CORS)                   8 PASS
Gate 7 (trace token)           13 PASS
Gate 8 (Usage × API client)    13 PASS  ← new
                              -------
Total                          60 PASS / 0 FAIL
```

---

## Frontend followups (not blocking)

The endpoints are wired; the Usage page UI doesn't yet surface the new breakdown. The followups (P2, deferred):

1. Add "API Client" dropdown next to existing Agent / Runtime mode filters
2. Add "By Client" bar chart alongside the existing "By Agent" chart
3. Make the partner name clickable → drill into `/by-agent?api_client_id=X`

These don't block the Phase 7 verdict — the contract is "Usage can be filtered by API client", which the backend now supports. UI surfacing is polish.

---

## Next: Gate 9 (SSE / Run state event realism)

Gate 8 was a soft gate. The hard checkpoint path remains:
- A (Gates 2+3 ✅)
- B (Gates 5+6+7 ✅)
- C (Gate 10) — next hard checkpoint
- D (Gate 12)

Soft gates 9 and 11 remain between now and Gate 10. Gate 9 covers SSE / Run state event realism — verifying that `run.started`, `run.progress`, `run.completed`, `run.failed` events actually fire with real payloads.
