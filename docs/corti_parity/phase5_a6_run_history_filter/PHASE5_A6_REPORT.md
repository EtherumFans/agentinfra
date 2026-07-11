# Phase 5 A6 — RunHistory Date Filter + Daily Cost Chart (GAP-12-02/03)

**Date:** 2026-07-10
**Gaps closed:** GAP-12-02 (RunHistory Date filter) + GAP-12-03 (Usage daily chart)
**Status:** PASS

## The gaps

Phase 4-H §12 audit found two related gaps on `/usage`:

- **GAP-12-02**: Corti Usage has `Last 7 days` date filter + `All API clients` filter; iCoDer had neither.
- **GAP-12-03**: Corti Usage has a `Daily`/`Monthly` chart toggle with a bar chart; iCoDer had no chart.

## The fixes

### Fix 1 — RunHistory `days` query param (backend)

`backend/app/api/run_trace.py` `list_run_history()`:

```python
async def list_run_history(
    request: Request,
    agent_id: str = Query("", description="Filter by agent_id (exact match)"),
    days: int = Query(0, ge=0, le=365, description="Filter to last N days (0 = no date filter)"),  # NEW
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
) -> dict[str, Any]:
    ...
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(RunHistoryModel.created_at >= cutoff)
```

`frontend/src/services/runtimeApi.ts`:

```typescript
// Phase 5 A6: optional `days` param filters by created_at >= now - days.
getRunHistory: (agentId = '', limit = 50, days = 0) =>
  api.get<{ items: any[]; total: number }>(
    '/runs/history',
    { params: { agent_id: agentId, limit, ...(days > 0 ? { days } : {}) } },
  ).then(r => r.data),
```

### Fix 2 — AgentChatPage segmented control (frontend)

`frontend/src/pages/AgentChatPage.tsx` RunHistory dropdown gets a 3-button segmented control:

- `All` (days=0) — default
- `7d` (days=7)
- `30d` (days=30)

State held in `historyDays`. `refreshRunHistory()` re-fires when `historyDays` changes (useCallback dependency).

### Fix 3 — Usage page daily cost chart (frontend)

`frontend/src/pages/UsagePage.tsx` — new `DailyCostChart` component:

```tsx
function DailyCostChart({ data }: { data: { date: string; cost: number }[] }) {
  const maxCost = Math.max(...data.map(d => d.cost), 0.0001);
  const total = data.reduce((sum, d) => sum + d.cost, 0);

  return (
    <div>
      <div className="flex items-end gap-[2px] h-32 mb-2" role="img" aria-label="Daily cost chart">
        {data.map(d => {
          const heightPct = Math.max((d.cost / maxCost) * 100, 2);
          const isToday = d.date === new Date().toISOString().slice(0, 10);
          return (
            <div key={d.date} className="flex-1 group relative flex flex-col justify-end"
                 title={`${d.date}: ¥${d.cost.toFixed(6)}`}>
              <div className="absolute -top-9 left-1/2 -translate-x-1/2 hidden group-hover:block ...">
                {d.date.slice(5)}: ¥{d.cost.toFixed(6)}
              </div>
              <div className={`w-full rounded-t-sm transition-all duration-200 ${
                  isToday ? 'bg-primary' : 'bg-primary/40 group-hover:bg-primary/70'}`}
                   style={{ height: `${heightPct}%` }} />
            </div>
          );
        })}
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
        <span>{data[0]?.date.slice(5)}</span>
        {data.length > 2 && <span>{data[Math.floor(data.length / 2)]?.date.slice(5)}</span>}
        <span>{data[data.length - 1]?.date.slice(5)}</span>
      </div>
      <p className="text-[11px] text-muted-foreground mt-2">
        累计: ¥{total.toFixed(6)} · 日均: ¥{(total / data.length).toFixed(6)} · 最高: ¥{maxCost.toFixed(6)}
      </p>
    </div>
  );
}
```

Features:
- CSS-grid bars (no chart library — 0 added bundle weight)
- Hover tooltip with exact date + cost
- Today's bar highlighted in `bg-primary`
- X-axis: first + middle + last date labels
- Stats line: 累计 (total) / 日均 (average) / 最高 (max)

Data flows from A3's `daily_breakdown` field on the `/usage/summary` response.

## Tests

`backend/tests/test_api/test_phase5_a6_run_history_days_filter.py` — 2 tests:

1. `test_a6_runs_history_days_filter` — inserts two rows (today + 60 days ago), then queries with `days=0/30/7`:
   - days=0: both visible
   - days=30: only today visible
   - days=7: only today visible
2. `test_a6_runs_history_days_default_is_zero` — when `days` omitted, behavior matches `days=0`.

```
$ python -m pytest tests/test_api/test_phase5_a6_run_history_days_filter.py -v
tests/test_api/test_phase5_a6_run_history_days_filter.py::test_a6_runs_history_days_filter PASSED
tests/test_api/test_phase5_a6_run_history_days_filter.py::test_a6_runs_history_days_default_is_zero PASSED
```

Frontend chart rendering verified by browser walkthrough (`phase5_a6_usage_daily_chart.png`).

## Files changed

- `backend/app/api/run_trace.py` — +7 lines (`days` query param + cutoff filter)
- `frontend/src/services/runtimeApi.ts` — +7 lines (days param threading)
- `frontend/src/pages/AgentChatPage.tsx` — +21 lines (segmented control)
- `frontend/src/pages/UsagePage.tsx` — +78 lines (`DailyCostChart` component + `dailyCostChart` i18n key)
- `frontend/src/i18n/locales.ts` — +2 lines (`dailyCostChart` zh-CN + en-US)

## Corti cross-reference

Corti `/usage` (verified 2026-07-10):
- `Last 7 days` button — opens dropdown with 7d/30d/etc. iCoDer has segmented control All/7d/30d. **Functionally equivalent.**
- `Daily` button toggles Daily/Monthly chart view. iCoDer renders daily chart default-on (no Monthly). **Phase 5 Track C candidate** to add Monthly toggle.
- Date axis: `04-Jul 06-Jul 08-Jul 10-Jul`. iCoDer shows `MM-DD` format. **Format difference only.**
- Amount axis: `$0 $0.09 $0.18 $0.27 $0.36`. iCoDer shows totals in stats line instead of Y-axis. **Design choice — equally valid.**

iCoDer post-A6 is functionally at parity with Corti on date filtering + daily chart. Two minor gaps deferred to Track C: Monthly toggle + All-API-Clients filter.

## What's NOT in A6 (deferred)

- `All API clients` filter (Corti has it, iCoDer shows org-wide totals) — Track C
- `Compare period` checkbox (Corti has it, iCoDer has `compareSummary` data but no UI toggle) — Track C
- `Monthly` chart toggle — Track C
