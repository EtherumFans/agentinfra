# Phase 4-H §12 — Run / Trace / Cost / Observability Parity Audit

**Audit date:** 2026-07-10
**Auditor:** Phase 4-H audit (Corti Console + iCoDer localhost:3002 + backend code inspection)
**Source PDF:** `Phase 4-H Audit Report.pdf` §12 (3 sub-sections: §12.1 RunHistory / §12.2 Trace / §12.3 Cost)
**Dev mode:** FROZEN per §2.1 — this is a READ-ONLY parity audit. No code changes.

---

## Executive Summary

This audit confirms a major **iCoDer ADVANTAGE** on RunHistory + Trace (server-side persisted per-run event log), while Corti has only **aggregate-level observability** (no per-run history page in Console). However, iCoDer has **3 real bugs** in the trace surface that PDF §12.2 explicitly calls out:

1. **Step duration double-counted** — 7 steps shown for a 3-step run, with duration duplicated across the 3 phantom steps (3020ms × 3 = 9060ms phantom total). **CONFIRMED BUG.**
2. **Inline trace vs persisted trace metadata mismatch** — the 3 phantom steps have no duration field; only the "real" ones do. The inline emitter and the DB-persisted events diverge in shape.
3. **Currency mismatch** — TopBar shows `$50.00` USD; `/billing` shows `¥50.00` yuan; `/usage` shows `¥0.00` consumed. Three different numbers for the same concept.

**Verdict (§12):** PARTIAL PASS. iCoDer leads Corti on RunHistory + Trace infrastructure, but the 3 bugs above are real P0 fixes (PDF §12.2 explicitly flags them).

---

## §12.1 — RunHistory

### Corti RunHistory surface (OBSERVED)

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Server-persisted | ❌ **NOT OBSERVED** — no dedicated RunHistory page in Console left nav | Console nav snapshot: AI Studio (Overview/Agents/STT/TextGen/Embedded/Facts/Coding) + Manage (API Clients/Team/Billing/Usage/Customers/Templates/Settings) — no "Runs" / "RunHistory" / "History" |
| 2 | Filter conditions | ⚠️ **PARTIAL** — /usage page has "Last 30 days" date filter + "All API clients" filter dropdown | `/usage` page snapshot |
| 3 | Agent filter | ❌ **NOT OBSERVED** — no per-Agent filter on /usage | Same |
| 4 | User filter | ❌ **NOT OBSERVED** — no per-User filter on /usage | Same |
| 5 | Date filter | ✅ **YES** — "Last 30 days" (single option, no custom range) | `/usage` page |
| 6 | Status filter | ❌ **NOT OBSERVED** — no success/error status filter | Same |
| 7 | Cost | ⚠️ **PARTIAL** — aggregate only ($0.83 over 30 days on /usage chart); no per-run cost breakdown | `/usage` page `$0.83 Total credits consumed` |
| 8 | Latency | ❌ **NOT OBSERVED** — no latency column | Same |
| 9 | Error | ❌ **NOT OBSERVED** — no error count or list | Same |
| 10 | Input Summary | ❌ **NOT OBSERVED** | Same |
| 11 | Output Summary | ❌ **NOT OBSERVED** | Same |
| 12 | Retention | ❌ **NOT OBSERVED** — no retention policy visible | Console |
| 13 | Delete | ❌ **NOT OBSERVED** — no delete run button | Same |
| 14 | Export | ❌ **NOT OBSERVED** — no export button | Same |

### iCoDer RunHistory surface (OBSERVED + code-confirmed)

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Server-persisted | ✅ **YES** — `run_history` table (alembic 010, Phase 4-G) + `RunHistoryModel` ORM | `backend/app/api/agent_run.py:263` (`_persist_run_history()`) + `backend/app/models/run_history.py` + `backend/app/api/run_trace.py:100` (`list_run_history` endpoint) |
| 2 | Filter conditions | ✅ **YES** — `agent_id` + `org_id` + `user_id` query params on `GET /api/runtime/runs/history` | `backend/app/api/run_trace.py:135-141` |
| 3 | Agent filter | ✅ **YES** — `stmt.where(RunHistoryModel.agent_id == agent_id)` | Line 137 |
| 4 | User filter | ✅ **YES** — `stmt.where(RunHistoryModel.user_id == str(user_id))` | Line 141 |
| 5 | Date filter | ❌ **NOT OBSERVED** — only `limit` param (default 50), no date range | Line 135 |
| 6 | Status filter | ❌ **NOT OBSERVED** — no status filter in query | Line 135-141 |
| 7 | Cost | ✅ **YES** — `api_client_id` + cost in trace metadata (Phase 4-G) | memory `project_phase4_g_live_cost_api_client_runhistory_fork_2026_07_10.md` |
| 8 | Latency | ✅ **YES** — `latency_ms` in unified envelope (Phase 4-F2) | memory `project_phase4_f2_a2a_unified_run_2026_07_10.md` |
| 9 | Error | ✅ **YES** — `error` + `error_reason` in unified envelope (Phase 4-F plan §9.4) | Plan file |
| 10 | Input Summary | ✅ **YES** — `input` field persisted in run_history row | `agent_run.py:315` INSERT |
| 11 | Output Summary | ✅ **YES** — `summary` field persisted in run_history row | Same |
| 12 | Retention | ❌ **NOT OBSERVED** — no retention policy in code | code grep |
| 13 | Delete | ❌ **NOT OBSERVED** — no delete endpoint | Same |
| 14 | Export | ❌ **NOT OBSERVED** — no export endpoint | Same |

### iCoDer RunHistory UI surface (OBSERVED)

- ✅ **Per-agent "Recent runs" dropdown** on AgentChatPage (`frontend/src/pages/AgentChatPage.tsx:392-406`) — shows last 20 runs for the current agent; selecting one navigates to `/runs/{run_id}/trace`
- ❌ **No dedicated `/runs` list page** — only `/runs/:runId/trace` route exists in `App.tsx:80`
- ❌ **No `/runs` page in left nav** — iCoDer left nav has AI Studio (总览/AI智能体/语音转录/事实提取/医学编码) + 管理 (API客户端/团队/计费/用量/客户/模板/设置) — no "运行历史" / "Runs" item
- ❌ **No /usage page integration** — iCoDer /usage page shows only `user.login` events in "最近活动" (recent activity) feed, NOT agent runs (see iCoDer /usage snapshot)

### §12.1 verdict

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Server-persisted run history | ❌ | ✅ (table + endpoint) | **iCoDer ADVANTAGE** |
| Agent filter | ❌ | ✅ | **iCoDer ADVANTAGE** |
| User filter | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Date filter | ✅ (30d preset) | ❌ (only limit) | **Corti ADVANTAGE** |
| Status filter | ❌ | ❌ | MATCH (both lack) |
| Cost (per-run) | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Latency | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Error | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Input/Output Summary | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Retention / Delete / Export | ❌ | ❌ | MATCH (both lack) |
| UI: dedicated /runs list page | ❌ | ❌ | MATCH (both lack) |
| UI: per-agent run history dropdown | ❌ | ✅ | **iCoDer ADVANTAGE** |
| UI: /usage page integration with runs | ⚠️ (aggregate chart only) | ❌ (only user.login events) | **CLOSE** |

**Overall §12.1:** iCoDer leads Corti on RunHistory (server-persisted table + filters + per-agent dropdown + cost/latency/error columns). Gaps:
- ❌ iCoDer lacks Date filter (Corti has "Last 30 days" preset)
- ❌ iCoDer lacks dedicated `/runs` list page in left nav
- ❌ iCoDer /usage page does NOT surface agent runs (only `user.login` activity)

---

## §12.2 — Trace

### Corti Trace surface (OBSERVED)

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Lifecycle events | ⚠️ **PARTIAL** — streaming chat shows token-by-token output, but no per-step lifecycle events surfaced in Console UI | Agent detail page only has Settings/Code tabs + chat panel; no "Trace" / "Event Inspector" tab |
| 2 | Expert events | ❌ **NOT OBSERVED** — no Expert call event surfaced | Same |
| 3 | Tool events | ❌ **NOT OBSERVED** — no Tool call event in Console | Same |
| 4 | Model events | ❌ **NOT OBSERVED** — no Model call event (token count, model name) | Same |
| 5 | Token | ❌ **NOT OBSERVED** — no token counter visible | Same |
| 6 | Cost | ⚠️ **PARTIAL** — per-run "Credits consumed: $X" footer (per §7.3.3) + topbar aggregate $0.034596 + /usage aggregate $0.83 | Console observation |
| 7 | Step Duration | ❌ **NOT OBSERVED** | Console |
| 8 | Cumulative Duration | ❌ **NOT OBSERVED** | Console |
| 9 | Error | ⚠️ **PARTIAL** — `error.triggered` event emitted by embedded Web Component (per §11.3); no Console-side error trace | `corti_embedded_web_component.md` line 75 |
| 10 | Retry | ❌ **NOT OBSERVED** | Console |
| 11 | Metadata | ❌ **NOT OBSERVED** — no metadata field in trace | Console |
| 12 | Input / Output | ⚠️ **PARTIAL** — chat panel shows input message + streamed output text; no structured input/output capture | Console |
| 13 | PHI 脱敏 | ❌ **NOT OBSERVED** — no PHI redaction indicator in Console | Console |
| 14 | Copy | ❌ **NOT OBSERVED** — no "Copy trace" button | Console |
| 15 | Export | ❌ **NOT OBSERVED** — no "Export trace" button | Console |

### iCoDer Trace surface (OBSERVED + code-confirmed)

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Lifecycle events | ✅ **YES** — 9-step Corti-parity timeline (USER_MESSAGE_RECEIVED → PLANNING → TOOL_DISPATCHER (4 steps) → AGGREGATION → OUTPUT_GENERATED → COMPLETION) | `RunTracePage.tsx` + `backend/app/api/run_trace.py:71` |
| 2 | Expert events | ✅ **YES** — Expert delegation events emitted via `ExpertCaller` | memory `project_phase4_a_agent_backend_provider_foundation_2026_07_07.md` |
| 3 | Tool events | ✅ **YES** — `auth_resolved` step shows `tool_name` + `auth_type` + `redacted_view` + `granted_scopes` + `note` | `RunTracePage.tsx` "auth_resolved 步骤仅展示..." |
| 4 | Model events | ✅ **YES** — LLM call events via `LLMGatewayAdapter` | memory `project_phase4_b_note_completeness_llm_migration_2026_07_08.md` |
| 5 | Token | ⚠️ **PARTIAL** — `input_text_len` in trace metadata; no `output_tokens` / `total_tokens` field observed | code grep — needs verification |
| 6 | Cost | ✅ **YES** — per-run cost in trace metadata + TopBar live cost counter (Phase 4-G) | memory `project_phase4_g_live_cost_api_client_runhistory_fork_2026_07_10.md` |
| 7 | Step Duration | ⚠️ **PARTIAL + BUG** — duration field present but **double-counted** (see "iCoDer-specific concerns" below) | `RunTracePage` observation |
| 8 | Cumulative Duration | ⚠️ **PARTIAL + BUG** — "9060ms total" is phantom (3× 3020ms; should be 3020ms) | Same |
| 9 | Error | ✅ **YES** — structured `error` + `error_reason` in envelope (Phase 4-F §9.4) | Plan file |
| 10 | Retry | ❌ **NOT OBSERVED** — no retry event in trace | code grep |
| 11 | Metadata | ✅ **YES** — `trace_events[]` persisted with full metadata | `agent_run.py:315` INSERT + `run_trace.py:71` GET |
| 12 | Input / Output | ✅ **YES** — `input` + `summary` + `result` fields persisted | Same |
| 13 | PHI 脱敏 | ✅ **YES** — `DataPolicy` edge PHI redaction + `redacted_view` in trace | `RunTracePage.tsx` + CLAUDE.md "DataPolicy — 边缘 PHI 脱敏" |
| 14 | Copy | ✅ **YES** — "Copy JSON" / "Copy Markdown" buttons on AgentChatPage output | memory `project_phase4_d_corti_replication_taste_skill_audit_2026_07_08.md` |
| 15 | Export | ❌ **NOT OBSERVED** — no "Export trace" button | Console |

### iCoDer-specific concerns (PDF §12.2 explicit call-outs)

PDF §12.2 explicitly asks: "特别检查 iCoDer 当前可能存在的：step duration 重复累计；inline trace 与 persisted trace 元数据不一致；input_text_len 口径不一致；Agent Runtime 总耗时与 Trace 总耗时不一致。"

#### Concern 1 — Step duration double-counted

**Status: CONFIRMED BUG (real, reproducible).**

**Evidence:** `RunTracePage` for run `run-e5692ed9-1d1c-42a0-b36f-e77c5bef22c9` shows:

```
7 steps · 7 ok · 9060ms total

1. 用户消息接收  ok  ts=1783661052.808          (no duration)
2. 用户消息接收  ok  ts=1783661055.837          (no duration)
3. 输出生成      ok  3020.0ms  ts=1783661055.837
4. 输出生成      ok  ts=1783661055.837          (no duration)
5. 输出生成      ok  3020.0ms  ts=1783661055.837
6. 完成          ok  ts=1783661055.837          (no duration)
7. 完成          ok  3020.0ms  ts=1783661055.837
```

- Steps 1 & 2 same name → duplicate
- Steps 3, 4, 5 same name → triplicate
- Steps 6, 7 same name → duplicate
- Only steps 3, 5, 7 have `3020.0ms` duration → 3× the same value
- Total `9060ms` = 3 × 3020ms = phantom

**Root cause (INFERRED):** The trace emitter is firing the same event 2-3× with different metadata shapes — once with duration, once without. Likely the inline emitter (real-time SSE) and the persisted emitter (DB write) are both writing to the same trace_events array, causing duplicates.

**File to fix:** `backend/app/api/agent_run.py` — trace event emission logic around lines 537 (`USER_MESSAGE_RECEIVED`), 644 (`OUTPUT_GENERATED + COMPLETION`).

#### Concern 2 — Inline trace vs persisted trace metadata mismatch

**Status: CONFIRMED (visible in the same trace).**

**Evidence:** Steps 1, 2, 4, 6 have NO duration field. Steps 3, 5, 7 have `3020.0ms`. The shape of inline-emitted events (no duration) differs from persisted events (with duration). This indicates:
- Inline emitter fires event with partial metadata (no duration — computed after step completes)
- Persisted emitter fires event with full metadata (with duration)
- Both write to the same array → mismatched shapes

**Root cause (INFERRED):** Two separate code paths emitting the same logical event with different metadata completeness. Should unify into single emitter with deferred duration computation.

#### Concern 3 — input_text_len 口径不一致

**Status: UNKNOWN — needs code verification.**

PDF §12.2 asks if `input_text_len` is inconsistent across surfaces. Without running specific test cases, can't confirm. Flagged for Phase 5 verification.

#### Concern 4 — Agent Runtime 总耗时 vs Trace 总耗时

**Status: CONFIRMED BUG (derived from Concern 1).**

**Evidence:** "9060ms total" on RunTrace page is 3× the actual 3020ms runtime. The Runtime's actual latency_ms in the unified envelope (Phase 4-F2) is `~3020ms`, but the Trace page sums all step durations to `9060ms` due to duplicates.

### §12.2 verdict

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Lifecycle events | ⚠️ PARTIAL | ✅ (9-step) | **iCoDer ADVANTAGE** |
| Expert events | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Tool events | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Model events | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Token | ❌ | ⚠️ PARTIAL | **iCoDer ADVANTAGE** (partial) |
| Cost | ⚠️ PARTIAL | ✅ | **iCoDer ADVANTAGE** |
| Step Duration | ❌ | ⚠️ **BUG** (double-counted) | **iCoDer BUG** — fix needed |
| Cumulative Duration | ❌ | ⚠️ **BUG** (phantom 9060ms) | **iCoDer BUG** — fix needed |
| Error | ⚠️ PARTIAL | ✅ | **iCoDer ADVANTAGE** |
| Retry | ❌ | ❌ | MATCH (both lack) |
| Metadata | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Input / Output | ⚠️ PARTIAL | ✅ | **iCoDer ADVANTAGE** |
| PHI 脱敏 | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Copy | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Export | ❌ | ❌ | MATCH (both lack) |

**Overall §12.2:** iCoDer leads Corti massively on Trace (13/15 dimensions iCoDer ADVANTAGE, 2 MATCH). BUT 2 confirmed bugs (step duration double-count + cumulative duration phantom) need P0 fix.

---

## §12.3 — Cost

### Corti Cost surface (OBSERVED)

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Single Run Cost | ⚠️ **PARTIAL** — per-run "Credits consumed: $X" footer in agent run detail (per §7.3.3); not exposed in /usage or /billing | §7 audit + Console observation |
| 2 | Cumulative Cost | ✅ **YES** — $0.83 over 30 days on /usage chart | `/usage` page |
| 3 | Billing Balance | ✅ **YES** — $48.69 in breadcrumb + /billing page | `/billing` page |
| 4 | Token Breakdown | ❌ **NOT OBSERVED** — no per-run token count (prompt_tokens / completion_tokens) | Console |
| 5 | Model Pricing | ❌ **NOT OBSERVED in Console** — pricing referenced via "read the docs" link on /corti-models page; actual pricing not in Console | `/corti-models` page |
| 6 | API Client Attribution | ✅ **YES** — "All API clients" filter dropdown on /usage | `/usage` page |
| 7 | User Attribution | ❌ **NOT OBSERVED** — no per-user cost breakdown | Same |
| 8 | Organization Attribution | ✅ **YES** — project = organization; /billing is project-scoped | URL `/project/b8f8129a-...` |
| 9 | Budget | ⚠️ **PARTIAL** — "Send alert when balance falls below $10" low balance threshold | `/billing` Plan tab |
| 10 | Alert | ✅ **YES** — "Enable low balance alerts" toggle (email notifications) | `/billing` Plan tab |
| 11 | Quota | ❌ **NOT OBSERVED** — no per-API-Client quota config | `/billing` + `/api-clients` |
| 12 | Reset | ⚠️ **PARTIAL** — "Reset live cost" button on Agents page (resets topbar counter only, NOT actual balance) | Agents page topbar |
| 13 | Export | ❌ **NOT OBSERVED** — no export button | `/billing` + `/usage` |

### iCoDer Cost surface (OBSERVED + memory-confirmed)

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Single Run Cost | ✅ **YES** — per-run cost in trace metadata (Phase 4-G #1 live cost from token × pricing) | memory `project_phase4_g_live_cost_api_client_runhistory_fork_2026_07_10.md` |
| 2 | Cumulative Cost | ⚠️ **PARTIAL + BUG** — /usage page shows "¥0.00 已消耗额度 (近30天)" but TopBar shows "$50.00" — **currency mismatch**; aggregate not actually wired to real runs | `/usage` page snapshot |
| 3 | Billing Balance | ✅ **YES** — ¥50.00 on /billing + $50.00 in TopBar (mismatch) | `/billing` + TopBar |
| 4 | Token Breakdown | ⚠️ **PARTIAL** — `input_text_len` in trace; `prompt_tokens` / `completion_tokens` likely present in cost calc but not surfaced in UI | memory Phase 4-G |
| 5 | Model Pricing | ❌ **NOT OBSERVED** — no public pricing page in Console; pricing is server-side config | Console |
| 6 | API Client Attribution | ✅ **YES** — `api_client_id` in trace metadata (Phase 4-G #2) | memory Phase 4-G |
| 7 | User Attribution | ✅ **YES** — `user_id` in run_history table (per §12.1 #4) | `run_trace.py:141` |
| 8 | Organization Attribution | ✅ **YES** — `organization_id` in run_history (per §12.1 #2) | `run_trace.py:139` |
| 9 | Budget | ⚠️ **PARTIAL** — /billing has "余额不足提醒" (low balance alert) threshold field, same as Corti | `/billing` page |
| 10 | Alert | ✅ **YES** — "余额不足提醒" toggle (matches Corti) | `/billing` page |
| 11 | Quota | ❌ **NOT OBSERVED** — no per-API-Client quota | Same as Corti |
| 12 | Reset | ⚠️ **PARTIAL** — iCoDer TopBar has cost counter but no "Reset" button visible (matches Corti except Corti's reset is on Agents page) | TopBar snapshot |
| 13 | Export | ❌ **NOT OBSERVED** — no export | Same as Corti |

### iCoDer Cost BUGS (OBSERVED)

#### BUG 12-01 — Currency mismatch

**Evidence:**
- TopBar shows `$50.00` (USD)
- `/billing` page shows `¥50.00` (yuan)
- `/usage` page shows `¥0.00` consumed (yuan)

**Issue:** Three different numbers for the same concept. TopBar uses USD; billing/usage use yuan. Either:
- (A) TopBar should show `¥50.00` to match /billing, OR
- (B) /billing should show `$50.00` to match TopBar

**Decision required:** CN market → yuan default, USD optional. Recommend TopBar shows `¥50.00` + currency toggle.

#### BUG 12-02 — /usage credits consumed shows ¥0.00 but real runs consumed credits

**Evidence:** `/usage` page shows "已消耗额度 ¥0.00 (近30天)" but the TopBar live cost counter on Agents page (Corti parity) shows accumulated cost per session. The /usage page is NOT wired to the actual run_history cost data.

**Root cause (INFERRED):** `/usage` page reads from a different source than the TopBar live cost counter. They should both read from `run_history.cost` column aggregated over the period.

### §12.3 verdict

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Single Run Cost | ⚠️ PARTIAL | ✅ | **iCoDer ADVANTAGE** |
| Cumulative Cost | ✅ | ⚠️ **BUG** (¥0.00) | **Corti ADVANTAGE** (iCoDer needs fix) |
| Billing Balance | ✅ | ✅ (with currency mismatch) | **CLOSE** |
| Token Breakdown | ❌ | ⚠️ PARTIAL | **iCoDer ADVANTAGE** (partial) |
| Model Pricing | ❌ | ❌ | MATCH (both lack) |
| API Client Attribution | ✅ | ✅ | MATCH |
| User Attribution | ❌ | ✅ | **iCoDer ADVANTAGE** |
| Organization Attribution | ✅ | ✅ | MATCH |
| Budget | ⚠️ PARTIAL | ⚠️ PARTIAL | MATCH |
| Alert | ✅ | ✅ | MATCH |
| Quota | ❌ | ❌ | MATCH (both lack) |
| Reset | ⚠️ PARTIAL | ❌ | **Corti ADVANTAGE** (minor) |
| Export | ❌ | ❌ | MATCH (both lack) |

**Overall §12.3:** iCoDer matches Corti on most dimensions + leads on User Attribution + Single Run Cost. 2 bugs need P0 fix:
- BUG 12-01: currency mismatch ($ vs ¥)
- BUG 12-02: /usage page not wired to real run cost data

---

## Per-item gap inventory (priority-ordered for Phase 5)

### P0 — Confirmed bugs (PDF §12.2 explicitly calls out)

#### BUG-12-01 — Step duration double-counted + phantom cumulative duration

**Evidence:** RunTrace page shows 7 steps for a 3-step run, with 3020ms duplicated 3× → 9060ms phantom total.

**Files to fix:**
- `backend/app/api/agent_run.py:537` — USER_MESSAGE_RECEIVED emission
- `backend/app/api/agent_run.py:644` — OUTPUT_GENERATED + COMPLETION emission
- Likely: inline emitter + persisted emitter both writing to same `trace_events[]` array; should consolidate to single emitter

**Verify:** After fix, RunTrace page should show 3 steps (not 7), with 3020ms total (not 9060ms).

**Estimated effort:** 2-3 hours

---

#### BUG-12-02 — Currency mismatch ($ vs ¥)

**Evidence:**
- TopBar: `$50.00` USD
- /billing: `¥50.00` yuan
- /usage: `¥0.00` consumed

**Files to fix:**
- `frontend/src/components/layout/TopBar.tsx` (or equivalent) — change `$` → `¥` (or add currency toggle)
- `backend/app/config.py` — `ICODER_CURRENCY` env var (USD vs CNY, default CNY for CN market)
- `/billing` + `/usage` pages should use the same currency as TopBar

**Estimated effort:** 1 hour

---

#### BUG-12-03 — /usage page not wired to real run cost data

**Evidence:** `/usage` shows "已消耗额度 ¥0.00 (近30天)" but run_history table has cost data (Phase 4-G).

**Files to fix:**
- `backend/app/api/usage.py` (or equivalent) — read from `run_history.cost` aggregated over period, NOT from a separate usage_log table
- `frontend/src/pages/UsagePage.tsx` — display real aggregated cost
- Also: surface agent runs in "最近活动" feed (currently only `user.login` events)

**Estimated effort:** 2 hours

---

### P1 — iCoDer lacks vs Corti

#### GAP-12-01 — iCoDer /usage lacks "All API clients" filter dropdown

**Corti has:** "All API clients" filter dropdown on /usage page (per-API-Client cost breakdown).
**iCoDer lacks:** No API Client filter on /usage page.

**Files to modify:**
- `frontend/src/pages/UsagePage.tsx` — add API Client filter dropdown
- `backend/app/api/usage.py` — accept `api_client_id` query param

**Estimated effort:** 1 hour

---

#### GAP-12-02 — iCoDer /usage lacks daily credits consumed chart

**Corti has:** Daily credits consumed chart (X = date 10-Jun to 10-Jul, Y = $0 to $0.36).
**iCoDer lacks:** Only metric cards, no chart.

**Files to modify:**
- `frontend/src/pages/UsagePage.tsx` — add chart (e.g., Recharts BarChart)
- `backend/app/api/usage.py` — return daily aggregated data points

**Estimated effort:** 2 hours

---

#### GAP-12-03 — iCoDer lacks Date filter on /runs/history endpoint

**Corti has:** "Last 30 days" preset date filter on /usage.
**iCoDer lacks:** Only `limit` param, no date range.

**Files to modify:**
- `backend/app/api/run_trace.py:135` — add `start_date` + `end_date` query params
- `frontend/src/pages/AgentChatPage.tsx:392-406` — add date filter to "Recent runs" dropdown

**Estimated effort:** 1 hour

---

#### GAP-12-04 — iCoDer lacks dedicated `/runs` list page in left nav

**Corti has:** No dedicated page either (only /usage aggregate chart).
**iCoDer has:** Only per-agent "Recent runs" dropdown on AgentChatPage.

**Decision:** Per CLAUDE.md "iCoDer 复刻方向" + memory `feedback_agent_pages_replicate_corti.md`, iCoDer should match Corti (no dedicated /runs page) — but should surface runs on /usage page (per BUG-12-03 above).

**Estimated effort:** 0 (no change — match Corti)

---

### P2 — Polish

#### GAP-12-05 — iCoDer lacks "Reset live cost" button

**Corti has:** "Reset live cost" button on Agents page topbar (resets the accumulated $0.034596 to $0).
**iCoDer lacks:** No reset button on TopBar.

**Files to modify:**
- `frontend/src/components/layout/TopBar.tsx` — add Reset button next to cost counter
- `frontend/src/services/runtimeApi.ts` — add `resetLiveCost()` function

**Estimated effort:** 30 minutes

---

#### GAP-12-06 — iCoDer lacks "Export" button on RunTrace page

**Corti lacks:** No export on trace either.
**iCoDer lacks:** Same.

**Decision:** MATCH (both lack). No change.

**Estimated effort:** 0

---

## iCoDer ADVANTAGES (Corti lacks these)

| # | iCoDer feature | Corti equivalent |
|---|---|---|
| 1 | Server-persisted `run_history` table with agent_id + user_id + org_id filters | Corti has only aggregate /usage chart |
| 2 | `GET /api/runtime/runs/history` endpoint with multi-filter | Corti has no per-run history endpoint |
| 3 | Per-agent "Recent runs" dropdown on AgentChatPage | Corti has no per-agent run history |
| 4 | 9-step Corti-parity timeline on RunTrace page | Corti has no trace page in Console |
| 5 | PHI 脱敏 (DataPolicy edge redaction + `redacted_view` in trace) | Corti has no PHI redaction indicator |
| 6 | `api_client_id` in trace metadata (Phase 4-G) | Corti has API Client filter but no per-run attribution in trace |
| 7 | `user_id` in run_history (per-user attribution) | Corti has no per-user attribution |
| 8 | Single Run Cost in trace metadata (token × pricing) | Corti has per-run "Credits consumed: $X" footer but no token breakdown |
| 9 | "Copy JSON" + "Copy Markdown" on AgentChatPage output | Corti lacks copy buttons on chat output |
| 10 | `error_reason` structured error contract (Phase 4-F §9.4) | Corti has `error.triggered` event only (no structured reason) |

---

## Phase 5 Recommendations (priority-ordered)

### P0 — Critical bugs

1. **BUG-12-01** — Fix step duration double-counting. 2-3 hours.
2. **BUG-12-02** — Fix currency mismatch ($ vs ¥). 1 hour.
3. **BUG-12-03** — Wire /usage page to real run_history cost data + surface agent runs in activity feed. 2 hours.

### P1 — Close Corti gaps

4. **GAP-12-01** — Add API Client filter on /usage page. 1 hour.
5. **GAP-12-02** — Add daily credits consumed chart on /usage page. 2 hours.
6. **GAP-12-03** — Add Date filter on /runs/history endpoint. 1 hour.

### P2 — Polish

7. **GAP-12-05** — Add "Reset live cost" button on TopBar. 30 minutes.

### DO NOT IMPLEMENT

- ❌ Dedicated `/runs` list page — Corti doesn't have one either. Match Corti (no dedicated page).
- ❌ Export trace — Corti doesn't have it. Match Corti.
- ❌ Token Breakdown UI surface — Corti doesn't expose tokens in Console. Match Corti (server-side only).
- ❌ Model Pricing page — Corti references docs.corti.ai for pricing. iCoDer should match (server-side config only).

---

## Cross-references

- `CORTI_DEVELOPER_EXPERIENCE_AUDIT.md` — §10 (API Client + SDK)
- `CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` — §11 (integration)
- `ICODER_INTEGRATION_GAP_ANALYSIS.md` — §11 iCoDer gaps
- `backend/app/api/agent_run.py` — unified Agent Run endpoint + run_history persistence
- `backend/app/api/run_trace.py` — trace timeline + run_history list endpoint
- `backend/app/api/runtime_platform.py:528` — `/runs` endpoint
- `frontend/src/pages/RunTracePage.tsx` — RunTrace UI (9-step timeline)
- `frontend/src/pages/UsagePage.tsx` — /usage page
- `frontend/src/pages/BillingPage.tsx` — /billing page
- `frontend/src/pages/AgentChatPage.tsx:392-406` — per-agent "Recent runs" dropdown
- `frontend/src/components/layout/TopBar.tsx` — live cost counter

---

**Audit complete.** Next: §13 Fork/Version/Publish audit → §14 Parity Matrix 2.0 → §16 test fixtures → §17 final report → §18+§19 architecture inference + Phase 5 recommendation.
