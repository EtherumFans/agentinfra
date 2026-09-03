# Phase 4-F1 Remaining Backlog

**Date:** 2026-07-10
**Phase:** 4-F1 (AgentChatPage Unified Run Path Repair)
**Status:** F1 PASS — this is the residual backlog after closing the G001 chat UI blocker

## P0 — High priority

### P0-1. Dedicated RunTrace viewer wiring for unified-endpoint runs

**Symptom:** When the user clicks "View RunTrace" in the chat result bubble, the dedicated
`/runs/{run_id}/trace` page returns "未找到 RunTrace — no trace events for run_id '...'".

**Root cause:** The unified endpoint `POST /api/v1/agents/{id}/run` returns `trace_events`
inline in the response body, but doesn't persist them to the runtime runs storage table
that `/api/runtime/runs/{id}/trace` reads from. The unified facade is a thin wrapper around
`CodingRuntimeDispatcher` / `ProviderRegistry` — it doesn't call
`RuntimeRunRegistry.persist()` or whatever the equivalent is.

**Workaround in F1:** Inline `📋 Trace Events (N)` expander in `MessageBubble` shows the
7 trace events with step/status/latency. Copy JSON includes `trace_events` in the
clipboard payload. So the user CAN inspect trace_events — just not via the dedicated
9-step timeline page.

**Fix options:**
- (a) Unified endpoint writes trace_events to runtime runs storage on completion (small
  backend change in `app/api/agents.py` or `agent_run.py` — call the persistence layer
  after computing the response)
- (b) RunTrace viewer falls back to fetching from the unified endpoint by run_id (frontend
  change in `RunTracePage.tsx` — if runtime runs storage returns 404, try calling a new
  unified endpoint like `GET /api/v1/agents/{agent_id}/runs/{run_id}`)
- (c) Both (defense in depth)

**Estimated effort:** 4-6 hours (option a) / 2-3 hours (option b) / 6-9 hours (option c)

### P0-2. Live cost wiring from LLMGateway to AgentRunResponse.cost

**Symptom:** `AgentRunResponse.cost` is `{"amount": 0.0, "currency": "internal_credit"}`
on every run — no actual token cost computed.

**Root cause:** The unified endpoint facade doesn't query `LLMGateway` for token usage on
the response path. The LLM call happens inside `CodingRuntimeDispatcher` /
`ProviderRegistry`, which doesn't surface token counts back to the facade.

**Fix:**
- Add a `cost` field to the dispatcher return shape (from `LLMGateway.usage` /
  `LLMGatewayAdapter.last_token_usage`)
- Multiply by the per-token rate (DeepSeek pricing table)
- Wire into `AgentRunResponse.cost = { amount: <float>, currency: "CNY" or "internal_credit", token_usage: { input, output } }`

**Estimated effort:** 4-6 hours

### P0-3. iCoDer built tab rendering on `/ai-studio/agents`

**Symptom:** Clicking the "iCoDer built" tab button on `/ai-studio/agents` does not render
the 14 hub agents. The content panel still shows the "My Agents" empty state ("还没有AI
智能体").

**Root cause:** Pre-existing — the tab button click handler in `AgentsPage.tsx` isn't
calling `agentHubApi.list()` or isn't switching the content panel source. The hub endpoint
returns 14 agents verified via curl:
```
medical-coding-agent | corti_like_fast
principal-diagnosis-review | a2a_pure_llm
drg-analyzer | a2a_pure_llm
... (14 total)
```

**Fix:** Read `AgentsPage.tsx`, find the tab state wiring, ensure "iCoDer built" tab
triggers `agentHubApi.list()` and renders hub cards. Likely a 1-2 line fix once located.

**Estimated effort:** 1-2 hours

## P1 — Medium priority

### P1-1. Wire other 3 P0 agents (Coding Evidence, Principal Dx Review, DRG/DIP Risk) to unified endpoint

**Current state:** F1 only wires Medical Coding Agent to `runtimeAgentApi.runAgentUnified()`.
Other agents fall through to the A2A `runAgentViaA2A()` fallback. This works for the
non-MedCodER agents (they don't have a 5-stage pipeline that 60s-timeouts), but they don't
benefit from the unified envelope (13-field response, trace_events, summary, etc.).

**Fix:** Extend the `isMedicalCoding` check in `AgentChatPage.onSubmit` to cover all 4 P0
agents, or simpler — always use the unified endpoint and remove the A2A fallback.

**Risk:** Removing A2A fallback entirely is a bigger change — some agents may have A2A-
specific features (Add context JSON files as DataParts) that the unified endpoint doesn't
support. The unified endpoint takes `extra` as a single object, not A2A parts.

**Estimated effort:** 2-3 hours (extend detection list) / 4-6 hours (full migration with
`extra` shape design)

### P1-2. AgentConfigSidebar Code tab — curl instead of C#

**Symptom:** Per Phase 4-F plan §F3, the right sidebar Code tab in AgentChatPage should
show JS / Python / curl (matching Corti). Current implementation has C# (from the original
iCoDer AgentDetailPage extraction).

**Fix:** In `frontend/src/components/agents/AgentConfigSidebar.tsx` (or the shared
`SettingsCodeTabs.tsx` if it exists), replace C# code block with curl equivalent. Use the
existing `CodeSnippet.tsx` component which supports JS/Python/curl/JSON.

**Estimated effort:** 2-3 hours (per Corti §7.4 spec)

### P1-3. Add context wiring for unified endpoint

**Current state:** F1 passes attached JSON files through the `extra` field on the
unified endpoint:
```ts
const extra: Record<string, unknown> = {};
if (filesForRun.length === 1) {
  extra.context_file = filesForRun[0];
} else if (filesForRun.length > 1) {
  extra.context_files = filesForRun;
}
```

But the backend unified endpoint doesn't yet document/parse this `extra.context_file` /
`extra.context_files` shape. It's a placeholder.

**Fix:** Define and document the `extra` schema on the backend (e.g., `extra.context_files:
Array<{ filename, content }>`), and have `CodingRuntimeDispatcher` /
`ProviderRegistry` consume them as additional context for the LLM prompt.

**Estimated effort:** 3-4 hours (backend schema + dispatcher integration + frontend shape
alignment)

## P2 — Lower priority

### P2-1. RunTrace viewer 9-step timeline page wiring

(See P0-1 above — this is the same gap from the user-facing timeline page perspective.)

### P2-2. Settings tab system prompt editor — save changes

**Symptom:** The Settings tab in `AgentConfigSidebar` shows the system prompt in a
textarea, but changes aren't persisted back to the agent config. User can edit the prompt
visually but the change is lost on refresh.

**Fix:** Wire the save button to `agentsApi.update()` (already exists for project-scoped
agents).

**Estimated effort:** 1-2 hours

### P2-3. Code tab — real per-agent code snippet

**Symptom:** The Code tab in `AgentConfigSidebar` should show agent-specific code (e.g.,
for Medical Coding Agent, a curl example hitting `/api/v1/agents/medical-coding-agent/run`
with the T12 case). Currently it likely shows a generic template.

**Fix:** Generate code snippets per-agent using the agent's `agent_id`, default
`runtime_mode`, and an example input from `example_inputs` (v1.3 spec field added in F1b).

**Estimated effort:** 2-3 hours

## P3 — Future / strategic

### P3-1. Phase 4-F2 — wire all 14 hub agents through unified endpoint + verify smoke runs

**Scope:** Per the Phase 4-F plan, 8 iCoDer built agents were spec'd (medical-coding,
coding-evidence, principal-dx-review, drg-dip-risk, procedure-coding, medical-record-
quality, discharge-summary-structuring, compliance-explanation). Hub currently returns 14
agents. F2 should:
- Verify all 14 agents have v1.3 spec fields (`default_runtime_mode`, `available_runtime_modes`,
  `example_inputs`, `built_by`)
- Wire all 14 to dispatch through the unified endpoint
- Run 14 smoke tests (extend `test_phase4f_smoke.py`)
- For non-medical-coding agents, verify the A2A fallback path also works (since they
  don't have the 60s-timeout issue)

**Estimated effort:** 6-8 hours

### P3-2. Agent run history page

**Symptom:** User can't see a list of past agent runs. The RunTrace viewer requires
knowing the run_id (typically from a chat result bubble link).

**Fix:** Add `/ai-studio/agents/:agentId/runs` page that lists recent runs for that agent
with filters (date range, runtime_mode, status). Calls `/api/runtime/runs?agent_ref=...`
(existing endpoint) but only returns A2A-persisted runs; need to also surface unified-
endpoint runs (depends on P0-1 persistence wiring).

**Estimated effort:** 6-8 hours

### P3-3. Agent fork (Corti "Fork" CTA)

**Scope:** Corti allows forking an agent to create a new project-scoped agent with the
same config. iCoDer has the clone endpoint but no "fork" UX.

**Estimated effort:** 4-6 hours

## Summary

| Priority | Count | Estimated effort |
|---|---|---|
| P0 | 3 | 9-14 hours |
| P1 | 3 | 7-13 hours |
| P2 | 3 | 5-8 hours |
| P3 | 3 | 16-22 hours |
| **Total** | **12** | **37-57 hours** |

The P0 items (RunTrace viewer wiring, live cost, iCoDer built tab rendering) are the most
visible to users and should be addressed in Phase 4-F2. P1-P3 can be addressed in
parallel or deferred based on user feedback.
