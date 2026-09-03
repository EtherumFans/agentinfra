# Phase 5 A3 — /usage Page Wired to run_history.cost (GAP-12-01)

**Date:** 2026-07-10
**Gap closed:** GAP-12-01 (Phase 4-H §12 audit, P1)
**Status:** PASS

## The gap

`GET /api/usage/summary` aggregated `Transaction.amount` (billing-side debits) as `credits_used`. Most agent runs don't create debit transactions — only manual top-ups + signup bonus do. So the page always showed `¥0.00 consumed` even when `run_history` had rows with non-zero `cost_usd`.

Phase 4-H audit found:
- iCoDer `/usage` page: `¥0.00 consumed` (broken)
- Corti `/usage` page: `$0.56 Total credits consumed` (working)

## The fix

`backend/app/api/usage.py` `get_usage_summary()`:

**Before:**
```python
tx_result = await db.execute(
    select(func.coalesce(func.sum(Transaction.amount), 0))
    .where(Transaction.user_id == user.id)
    .where(Transaction.type == "debit")
    .where(Transaction.created_at >= since)
)
credits_used = round(tx_result.scalar() or 0, 2)
```

**After:**
```python
# Aggregate real LLM cost from run_history.cost_usd (legacy column name;
# the value is CNY per Phase 5 A2 currency unification).
run_cost_result = await db.execute(
    select(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0))
    .where(RunHistoryModel.user_id == str(user.id))
    .where(RunHistoryModel.created_at >= since)
)
credits_used = round(float(run_cost_result.scalar() or 0.0), 6)

# Daily breakdown for A6's 30-day bar chart.
daily_result = await db.execute(
    select(
        func.date(RunHistoryModel.created_at).label("day"),
        func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
    )
    .where(RunHistoryModel.user_id == str(user.id))
    .where(RunHistoryModel.created_at >= since)
    .group_by(func.date(RunHistoryModel.created_at))
    .order_by(func.date(RunHistoryModel.created_at).asc())
)
daily_breakdown = [
    {"date": str(row.day), "cost": round(float(row.cost or 0.0), 6)}
    for row in daily_result
]
```

Plus the response now includes `"currency": "CNY"` explicitly (Phase 5 A2).

## Why this works

`RunHistoryModel` is the server-persisted record of every agent run (Phase 4-G alembic 010). Every run with a non-mock LLM call has a non-zero `cost_usd` value computed from `usage.input_tokens × LLM_PRICE_INPUT_PER_1M + usage.output_tokens × LLM_PRICE_OUTPUT_PER_1M`. Aggregating this column surfaces the real LLM cost.

Precision bump from 2 → 6 decimal places because typical per-run cost is `~¥0.001-0.05` — 2 dp would round most runs to `0.00`.

## Test

`backend/tests/test_api/test_phase5_a3_usage_run_history_cost.py` — 2 tests:

1. `test_a3_usage_summary_includes_run_history_cost` — inserts a row with `cost_usd=0.042185` directly into `run_history`, calls `GET /api/usage/summary?days=7`, asserts `credits_used >= 0.042185 - 1e-6` and `currency == "CNY"`.
2. `test_a3_usage_summary_returns_daily_breakdown` — inserts a row dated today, asserts `daily_breakdown` is a list and contains today's entry with `cost >= 0.031`.

```
$ python -m pytest tests/test_api/test_phase5_a3_usage_run_history_cost.py -v
tests/test_api/test_phase5_a3_usage_run_history_cost.py::test_a3_usage_summary_includes_run_history_cost PASSED
tests/test_api/test_phase5_a3_usage_run_history_cost.py::test_a3_usage_summary_returns_daily_breakdown PASSED
```

## Files changed

- `backend/app/api/usage.py` — +50 / -10 lines (Transaction → RunHistoryModel; precision 2→6; +`daily_breakdown`; +`currency=CNY` field)

## What this enables

A6 (Phase 5 daily cost chart) consumes the new `daily_breakdown` field to render a Corti-style bar chart on `/usage`. See A6 report.

## Migration note

If `Transaction.amount` was used elsewhere as the source of truth for "credits consumed," those callers will now diverge. A quick audit shows `Transaction` is still used by `BillingPage` for the transaction list (top-ups + manual debits), which is correct — that's a different concept (billing ledger vs. consumption). The two concepts are now properly separated.

## Corti cross-reference

Corti `/usage` page (verified via authorized Corti account, 2026-07-10):
- Shows `$48.69 Available credits` and `$0.56 Total credits consumed`
- The `$0.56` reflects actual API usage, equivalent to iCoDer's `run_history.cost_usd` sum post-A3.

iCoDer post-A3 matches Corti's behavior on this dimension.
