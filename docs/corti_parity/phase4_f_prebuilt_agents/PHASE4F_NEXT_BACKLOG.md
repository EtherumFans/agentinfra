# Phase 4-F — Next Backlog

**Date:** 2026-07-10
**Scope:** Follow-up items discovered during Phase 4-F execution, prioritized
P0 → P3.

---

## P0 — Must close next

### P0-1 — G001 chat UI wiring (CRITICAL blocker)

**Symptom:** Medical Coding Agent run from `/ai-studio/agents/:id/chat`
shows "运行中…" for 60s, then "运行失败 / timeout of 60000ms exceeded".

**Root cause:** AgentChatPage calls A2A endpoint
`/api/icoder/agents/medical-coding-agent/v1/message:send` (via
`runtimeApi.ts` `sendMessage()`), which routes through `InboundHandler` →
full MedCodER 5-stage pipeline. Real DeepSeek + BGE-M3 + FAISS = 60s+.

**Why F4 smoke tests pass:** They use the unified endpoint
`POST /api/v1/agents/{id}/run` (Phase 4-F F1b) which routes medical-coding
fast path to `CodingRuntimeDispatcher` (G001 fast path, ~9-10s).

**Fix:** Wire AgentChatPage to call `runtimeAgentApi.agentRun()` instead
of A2A `sendMessage()` for medical-coding fast path. AgentDetailPage
already does this (Phase 4-F F3).

**Files to modify:**
- `frontend/src/pages/AgentChatPage.tsx` — change handleSend to call
  `runtimeAgentApi.agentRun()` when agent_id is medical-coding-agent
- Add fallback to A2A for non-medical-coding agents (they don't have
  G001 fast path)

**Estimated effort:** 2-3 hours (mirror AgentDetailPage wiring + test on
T12 case with real DeepSeek)

**Unblocks:** F5 steps 10, 13, 14, 15 + all future chat UI demos

---

## P1 — High priority

### P1-1 — Live DeepSeek latency test (T12 < 15s)

**Prerequisite:** P0-1 complete (chat UI uses unified endpoint)

**Action:** With chat UI wired to unified endpoint, run T12 case on real
DeepSeek (LLM_PROVIDER unset). Verify latency_ms < 15000.

**Files:**
- `backend/tests/test_api/test_phase4f_smoke.py` — add `test_t12_real_llm_latency`
  (skipped if `LLM_PROVIDER=mock`)

**Estimated effort:** 1-2 hours

### P1-2 — Python SDK tab in sidebar

**Symptom:** CodeSnippet.tsx supports `python?: string` prop and includes
a Python tab in the tabs config, but AgentConfigSidebar's SdkCodeBlock
doesn't pass a Python example string. Python tab is missing from the Code
tab in the right sidebar.

**Fix:** Add Python SDK example string to SdkCodeBlock:
```python
from icoder import CortiClient
client = CortiClient(api_key=os.environ["ICODER_API_KEY"])
response = client.agents.run(
    agent_id="icoder/medical-coding-agent@2.0.0",
    input={"text": "Your input here"},
    include_trace=True,
)
print(response.result.parts[0].data)
```

**Files:**
- `frontend/src/components/agents/AgentConfigSidebar.tsx` — add `python`
  prop to CodeSnippet

**Estimated effort:** ~5 lines + test, 30 minutes

### P1-3 — Update pre-existing test assertions

**Symptom:** 3 pre-existing test failures:
- `test_phase3d1_three_simple_agents_visible_and_runnable` expects
  `code-validation-agent@1.0.0`, actually `@2.0.0` (Phase 4-C rename)
- `agentHubContract.test.ts:63` regex about agentHubApi.list() in AgentsPage
- `agentNavigationSmoke.test.tsx` RunTracePage assertion

**Fix:** Update test expectations to match current code state.

**Estimated effort:** 1-2 hours

---

## P2 — Medium priority

### P2-1 — Agent run history

**Description:** Persist runs to DB + add "Run history" tab in Agent Detail
showing past runs with timestamp, latency, status, summary.

**Files:**
- `backend/app/models/agent_run_history.py` (new)
- `backend/app/api/agent_run.py` — add `GET /api/v1/agents/{agent_id}/runs`
- `frontend/src/pages/AgentDetailPage.tsx` — add "Run history" tab
- `frontend/src/services/agentHubApi.ts` — add `listRuns()` method

**Estimated effort:** 4-6 hours

### P2-2 — Agent fork ("Save as my agent")

**Description:** From Hub card, "Save as my agent" creates a new
project_agent_id with the pack as starting point. Different from Clone
(which is idempotent) — Fork always creates a new copy.

**Files:**
- `backend/app/api/icoder_agents_hub.py` — add `POST /api/icoder/agents/{id}/fork`
- `frontend/src/pages/AgentsPage.tsx` — add "Fork" button to card

**Estimated effort:** 3-4 hours

### P2-3 — API Client dropdown real binding

**Description:** Replace placeholder data in API Client dropdown with
real API Client list from `GET /api/v1/api-clients`.

**Files:**
- `frontend/src/pages/AgentDetailPage.tsx` — fetch real API Clients
- `frontend/src/services/api.ts` — add `listApiClients()` method

**Estimated effort:** 2-3 hours

### P2-4 — Live cost calculation

**Description:** Wire token usage → USD conversion. Update header
"$50.00" placeholder with real accumulated cost from `cost.usd` in
agent run responses.

**Files:**
- `backend/app/api/billing.py` — add `GET /api/v1/billing/current-cost`
- `frontend/src/components/layout/Header.tsx` — fetch current cost on
  agent run completion

**Estimated effort:** 3-4 hours

---

## P3 — Long-term

### P3-1 — Web Component SDK

**Description:** Export agent run as embeddable Web Component for
ROPC embedded integration (per CLAUDE.md `backend-service` vs
`ROPC embedded` distinction).

**Files:**
- `frontend/src/web-components/icoder-agent-runner.ts` (new)
- Build pipeline to compile as standalone Web Component

**Estimated effort:** 8-12 hours

### P3-2 — Deep Evidence full wiring

**Description:** Complete the per-code evidence span extraction pipeline
for Coding Evidence Agent. Currently the LLM produces structured
`coded_evidence[]` but doesn't use the BGE-M3 + FAISS retriever for
evidence span localization.

**Files:**
- `backend/icoder_runtime/backends/pure_llm_provider.py` — add evidence
  span retrieval stage
- `backend/official_agents/evidence_extractor/agent_pack.json` — declare
  `available_runtime_modes: ["a2a_pure_llm", "deep_evidence"]`

**Estimated effort:** 6-8 hours

### P3-3 — 大规模编码质量评估

**Description:** Run Medical Coding Agent on full `icoder_201.json` fixture
set (201 cases) and compute per-case micro-F1 + aggregate micro-pooled F1.
Compare against Phase 2 baseline + MedCodER `full` variant.

**Files:**
- `scripts/e2e_phase4f_eval.py` (new)
- `docs/corti_parity/phase4_f_prebuilt_agents/PHASE4F_EVAL_RESULTS.md` (new)

**Estimated effort:** 4-6 hours (script + run + report)

### P3-4 — DRG/DIP 规则引擎

**Description:** Implement `DrgDipRuleSet` (parallel to
`MedicalCodingRuleSet`) with CN-DRG + DIP 规则. Currently DRG/DIP Risk
Review Agent uses LLM explainer only — no deterministic rule primary path.

**Files:**
- `backend/compliance_services/drg_dip_rule_set.py` (new)
- `backend/compliance_services/rule_engine.py` — register new rule_set

**Estimated effort:** 8-12 hours (rules authoring + integration)

### P3-5 — 医保合规知识库

**Description:** Build knowledge base of medical insurance compliance
rules (拒付场景 + 编码争议案例). Used by Denial Appeals + Compliance
Guardrail agents.

**Files:**
- `data/medical_insurance_kb/` (new data directory)
- `backend/compliance_services/insurance_audit_rule_set.py` (new)

**Estimated effort:** 12-16 hours (KB authoring + rule encoding)

---

## Backlog summary

| Priority | Count | Total estimated effort |
|---|---|---|
| P0 | 1 | 2-3 hours |
| P1 | 3 | 4-6 hours |
| P2 | 4 | 12-17 hours |
| P3 | 5 | 38-54 hours |
| **Total** | **13** | **56-80 hours** |

**Recommended next session:** P0-1 (G001 chat UI wiring) + P1-1 (live
DeepSeek latency test). These two together unblock live demos through
the chat UI — the last critical path for Corti parity on the agent pages.

---

**Backlog end.**
