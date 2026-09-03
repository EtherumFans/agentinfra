# Phase 4-C — Next Optimization Plan (Phase 4-D Scope)

**Phase**: 4-C (Code Validation Agent LLMWithToolsProvider Migration)
**Report**: 6 of 6
**Date**: 2026-07-08
**Purpose**: Short/mid/long-term optimization roadmap; Phase 4-D concrete task list

---

## 1. Phase 4-D Scope (Short-term, ~1-2 weeks)

Per user's 2026-07-08 explicit directive ("智能体的页面，无论是预置智能体还是我的智能体跟corti还有很大的差距，无论从UI/IA或者使用流程上都应该复刻corti，现在差距还很大"), **Phase 4-D = Corti agent page UI/IA replication FIRST**, before any further agent migration.

### 1.1 Task D-1: Corti agent detail page UI/IA replication (12-item gap)

**Priority order** (from memory `project_phase4c_corti_vs_icoder_agent_page_gap_2026_07_08.md`):

| # | Item | Files to modify | Acceptance criteria |
|---|------|-----------------|---------------------|
| 1 | Top bar **live cost counter** + Reset button | `frontend/src/pages/AgentChatPage.tsx`; new `LiveCostCounter` component; SSE cost events from backend | Counter accumulates in real-time during LLM loop; Reset button zero-outs; matches Corti `$0.091304` format |
| 2 | Top bar **API Client selector** (combobox) | `AgentChatPage.tsx`; new `ApiClientSelector` component; backend `/api/v1/api-clients` endpoint (may need new) | Combobox lists available API Clients for current tenant; switching updates subsequent A2A calls' `X-API-Client-Id` header |
| 3 | Top bar **Available credits** link | `AgentChatPage.tsx`; new `AvailableCredits` component; backend `/api/v1/billing/credits` endpoint (may need new) | Link shows `$XX.XX` → navigates to `/billing`; refreshes after each run |
| 4 | Left chat **Add context** button | `AgentChatPage.tsx`; new `AddContextMenu` component | Button opens menu to attach file/text/context; attaches to A2A `parts[]` as `DataPart` or `FilePart` |
| 5 | Right **Settings / Code dual panel** (radio) | `AgentChatPage.tsx`; new `AgentConfigSidebar` component (right slide-out); radio toggle between Settings + Code | Radio switches panel content; Settings shows system prompt + experts + pinned parts; Code shows SDK tabs |
| 6 | **System prompt textarea** (user-editable) | `AgentConfigSidebar.tsx`; backend `/api/v1/agents/{id}/config` PATCH endpoint (may need new) | Textarea shows current system prompt; user can edit + save; saved prompt overrides pack default for tenant |
| 7 | **Browse Expert Library** + **Add expert** buttons | `AgentConfigSidebar.tsx`; new `ExpertLibraryModal` component; backend `/api/v1/experts` list endpoint | Modal lists available experts; click Add appends to agent's experts[]; persists to tenant agent config |
| 8 | **Pinned message parts** region | `AgentConfigSidebar.tsx`; new `PinnedParts` component | Region lists pinned parts; user can pin/unpin message parts from chat; pinned parts injected into every subsequent LLM call |
| 9 | **SDK / Code tabs** (JavaScript / .NET / JSON Config) | `AgentConfigSidebar.tsx`; new `SdkCodeBlock` component; code templates for 3 tabs | 3 tabs render code blocks; copy button; JSON Config tab reads from `agent_pack.json` |
| 10 | **Ctrl+Enter submit** (no standalone Send button) | `AgentChatPage.tsx` textarea; remove Run button; add keyboard handler | Ctrl+Enter submits; plain Enter inserts newline; matches Corti |
| 11 | **Breadcrumb** showing current agent name | `AgentChatPage.tsx`; new `AgentBreadcrumb` component | Shows "Agents > {agent_name}"; clickable segments navigate |
| 12 | Detail page **URL contains agent id** | `frontend/src/router.tsx`; route `/ai-studio/agents/:agentId` instead of `?agent_id=` | URL pattern matches Corti `/agents/{id}`; deep-link works |

**List page additions** (lower priority, same phase):
- Card shows **created time + creator** ("07-Jul-2026 • Luhua Song")
- **Created by** filter (in addition to existing use_case filter)

**i18n + component library + RunTrace integration**:
- All new strings in `frontend/src/i18n/locales.ts` (zh + en)
- Use existing Tailwind + shadcn/ui components; no new dependency
- Live cost counter reads from new SSE cost event (emit during `_real_llm_pipeline` loop)

**Tests**:
- `frontend/src/pages/__tests__/AgentChatPage.test.tsx` — 12 tests (one per item, render + interaction)
- `frontend/src/utils/__tests__/medicalCodingMarkdown.test.tsx` — extend (already 2 v2 tests, add more edge cases)
- `npx tsc --noEmit` 0 error
- `npx vitest run` all pass

### 1.2 Task D-2: v2 A2A dispatch wiring

**Problem**: `_handle_simple` routes to `validate_codes` MCP tool → `agent_legacy` (v1 shape); v2 path not browser-reachable (Report 3 §2.3).

**Solution options** (pick one in Phase 4-D planning):

| Option | Implementation | Pros | Cons |
|--------|----------------|------|------|
| A: New `validate_codes_v2` MCP tool | New MCP tool wraps `agent_v2.run()`; A2A dispatch routes by `agent_ref` version | Clean separation; v1 preserved for backwards compat | Two MCP tools for same agent; version negotiation complexity |
| B: Route `_handle_simple` to `agent_v2.run()` for code-validation-agent | Special-case in `inbound_handler.py`; if `agent_ref` is `icoder/code-validation-agent@2.0.0`, call v2 directly | Simpler; one path | BREAKING — v1 consumers of `validate_codes` MCP tool break (per plan decision #6) |
| C: Make `validate_codes` MCP tool dispatch by `agent_ref` version | `validate_codes` internally checks `agent_ref`; if `@2.0.0`, call v2; if `@1.0.0`, call legacy | Backwards compatible; one MCP tool | Conditional logic in MCP tool; test matrix doubles |

**Recommendation**: Option C — single MCP tool, conditional dispatch, backwards compatible.

**Files to modify**:
- `backend/app/icoder/mcp/handlers/validate_codes.py` — add `agent_ref` parameter; dispatch to v2 or legacy
- `backend/app/icoder/agent_runtime/orchestrator/inbound_handler.py` — pass `agent_ref` to `validate_codes` call
- `backend/tests/unit/icoder/mcp/test_validate_codes.py` — add v2 dispatch tests

**Acceptance criteria**:
- A2A call to `code-validation-agent` returns v2 shape (`validated_codes` + `cross_code_issues` + `markdown`)
- Existing v1 consumers (other agents calling `validate_codes` MCP tool) still get v1 shape
- RunTrace shows `backend_provider=icoder.llm-with-tools.v1`, `tool_rounds>0`, `round_index` populated

### 1.3 Task D-3: Playwright screenshot tooling fix

**Problem**: `browser_take_screenshot` times out at 5000ms "waiting for fonts to load" (Report 3 §2.2).

**Investigation steps**:
1. Check `frontend/index.html` for `@font-face` rules referencing fonts not in dev
2. Check `frontend/src/main.tsx` for font imports
3. Try `browser_take_screenshot` with `type: 'jpeg'` (no font loading)
4. Try `browser_evaluate` with `await document.fonts.ready` before screenshot
5. Try `browser_run_code_unsafe` with explicit `page.waitForLoadState('domcontentloaded')` before screenshot

**Files to investigate**:
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/tailwind.config.js` (font family config)

**Acceptance criteria**:
- `browser_take_screenshot` completes < 3000ms
- 4-input walkthrough on iCoDer captures 16+ screenshots
- 4-input walkthrough on Corti captures 16+ screenshots

### 1.4 Task D-4: 4-input re-walk on iCoDer + Corti (Phase 4-C closeout)

**After D-1 + D-2 + D-3 are complete**, re-run the 4-input walkthrough:

**iCoDer walkthrough**:
1. Start dev servers
2. Open `/ai-studio/agents/code-validation-agent` (new URL pattern from D-1 #12)
3. For each of 4 inputs: submit via Ctrl+Enter (D-1 #10) → screenshot chat response → grab `run_id` → navigate `/runs/{run_id}/trace` → screenshot ToolDispatchDetail → screenshot BackendProviderSummary
4. Save 16+ screenshots to `docs/architecture/agent_backend/phase4d_browser_walkthrough/`

**Corti walkthrough**:
1. Open `console.corti.app/ai-studio/agents/{id}` (Corti account)
2. For each of 4 inputs: submit via Ctrl+Enter → screenshot response → `browser_network_requests` for SSE events → record latency/cost
3. Save 16+ screenshots + network captures to `docs/architecture/agent_backend/phase4d_corti_comparison/`

**Acceptance criteria**:
- 4 iCoDer inputs return v2 shape (`validated_codes` + `cross_code_issues` + `markdown`)
- 4 Corti inputs return Corti's standard shape
- RunTrace for iCoDer shows `tool_rounds>0`, `round_index` populated, `caller="llm"`
- Visual comparison shows iCoDer UI 1:1 with Corti (per 12-item gap closure)

---

## 2. Phase 4-E Scope (Mid-term, ~2-4 weeks)

After Phase 4-D closeout:

### 2.1 Compliance Guardrail migration (RuleEngine → LLMWithToolsProvider)

**Why now**: LLMWithToolsProvider infrastructure is proven (Phase 4-C); Compliance Guardrail is the next RuleEngine-heavy agent to benefit from LLM + tools.

**Scope**:
- New `backend/official_agents/compliance-guardrail/agent_v2.py`
- New `output_schema_v2.py` (ComplianceGuardrailOutputV2)
- New `system_prompt_v2.py` (Corti-style, Chinese, compliance context)
- Reuse 4 MCP tools (`verify_code`/`get_guidelines`/`explore_code`/`search_codes`)
- `agent_pack.json` bump to v2.0.0; `backend_provider="icoder.llm-with-tools.v1"`
- Legacy fallback to current RuleEngine-based agent

**Tests**: Same 5 categories as code-validation v2 (happy path / legacy fallback / schema validation / empty input / prompt injection refusal)

### 2.2 Streaming LLM responses (SSE)

**Why**: Corti streams `final_text` chunk-by-chunk; iCoDer currently blocks until full response. UX gap.

**Scope**:
- Backend: `_real_llm_pipeline` yields chunks instead of returning full response
- A2A: `message/stream` endpoint (SSE) streams chunks to frontend
- Frontend: `AgentChatPage` renders chunks as they arrive (markdown incremental render)
- RunTrace: `BACKEND_METADATA` step gets `streaming: true` field; per-chunk timing not stored (too noisy)

### 2.3 Tool result caching

**Why**: `verify_code` for same code+context returns same result; re-running wastes latency. Corti likely caches internally.

**Scope**:
- New `backend/icoder_runtime/backends/tool_cache.py` — LRU cache keyed by `(tool_name, arguments_hash)`, TTL 5min, max 1000 entries
- `ToolMCPCompatLayer.call` checks cache before dispatching
- Cache hit recorded in `dispatch_detail` as `cache_hit: true`
- RunTrace shows `cache_hit` field

### 2.4 Live cost counter UX (real-time accumulating)

**Why**: Phase 4-D #1 will wire the counter, but it needs per-chunk cost events from backend.

**Scope**:
- Backend: `_real_llm_pipeline` emits `cost_event` after each LLM call + each tool dispatch
- Frontend: `LiveCostCounter` subscribes to SSE cost events; accumulates + displays
- Reset button clears counter + sends `POST /api/v1/runs/{run_id}/reset-cost`

---

## 3. Phase 5+ Scope (Long-term, ~1-3 months)

### 3.1 Unified agent hub

**Why**: Corti has single `/ai-studio/agents`; iCoDer splits between "prebuilt" + "my-agents". IA simplification.

**Scope**:
- Merge `prebuilt-agents` + `my-agents` pages into single `/ai-studio/agents`
- Filter by "Created by" (Corti pattern) + "Use case" (existing iCoDer pattern)
- Clone action creates "my-agent" copy from prebuilt template

### 3.2 Expert library browsing

**Why**: Corti "Browse Expert Library" modal; iCoDer has experts internally but no browse UI.

**Scope**:
- New `/ai-studio/experts` page (list + detail)
- New `ExpertLibraryModal` component (modal from agent config sidebar)
- Backend `/api/v1/experts` list + detail endpoints

### 3.3 SDK code generation tabs

**Why**: Corti JS/.NET/JSON Config tabs; iCoDer has none.

**Scope**:
- New `SdkCodeBlock` component (Phase 4-D #9 stub; Phase 5 full impl)
- Code templates for JavaScript (SDK), .NET (SDK), JSON Config (from agent_pack.json)
- Copy button + syntax highlight

### 3.4 Pinned message parts

**Why**: Corti fixed-message-part reuse; iCoDer has no concept.

**Scope**:
- New `PinnedParts` data model (per tenant + per agent)
- Backend `/api/v1/agents/{id}/pinned-parts` CRUD endpoints
- Frontend `PinnedParts` component in config sidebar
- LLM call injection: pinned parts prepended to `messages[]` in `_real_llm_pipeline`

### 3.5 API Client identity switching

**Why**: Corti top bar combobox; iCoDer has tenant header but no per-call identity switcher.

**Scope**:
- New `ApiClientSelector` component (Phase 4-D #2 stub; Phase 5 full impl)
- Backend `/api/v1/api-clients` list endpoint
- Per-call `X-API-Client-Id` header injection

---

## 4. Summary Table

| Phase | Scope | Duration | Priority |
|-------|-------|----------|----------|
| 4-D | Corti UI/IA replication (12-item) + v2 dispatch wiring + Playwright fix + 4-input re-walk | ~1-2 weeks | **#1 (user directive)** |
| 4-E | Compliance Guardrail migration + streaming + caching + live cost UX | ~2-4 weeks | High |
| 5+ | Unified hub + expert library + SDK tabs + pinned parts + API Client switcher | ~1-3 months | Medium |

---

## 5. Risk Assessment for Phase 4-D

| Risk | Mitigation |
|------|------------|
| 12-item UI replication is large; might not fit in 1-2 weeks | Prioritize top bar (1-3) + right panel (5-9) first; defer list card metadata + breadcrumb + URL pattern to Phase 4-D.5 |
| v2 A2A dispatch wiring (Option C) doubles test matrix | Use feature flag `ICODER_CODEVAL_V2_DISPATCH` to roll out gradually |
| Playwright screenshot fix might be unblockable | Fallback: use `browser_evaluate` for DOM assertions + save network captures; visual evidence secondary |
| 4-input re-walk depends on D-1 + D-2 + D-3 all complete | If any blocked, document partial closeout + defer to Phase 4-E |
| Corti UI might change between 2026-07-08 walkthrough and Phase 4-D implementation | Re-walk Corti at start of Phase 4-D; update 12-item gap list if needed |

---

## 6. PASS Criteria for Phase 4-D

1. 12-item UI/IA gap closed (all 12 items have visual screenshot evidence)
2. v2 A2A dispatch returns v2 shape from browser
3. Playwright screenshot tool completes < 3000ms
4. 4-input re-walk on iCoDer: 16+ screenshots + v2 shape responses
5. 4-input re-walk on Corti: 16+ screenshots + SSE event captures
6. Visual comparison: iCoDer agent detail page 1:1 with Corti (per 12-item gap)
7. `tsc --noEmit` 0 error
8. `vitest run` all pass
9. `pytest tests/unit/icoder/` all pass (no regression)
10. RunTrace for code-validation-agent shows `tool_rounds>0`, `round_index` populated, `caller="llm"`
11. User confirms UI/IA parity ("现在差距还很大" → "差距已闭合")
12. 6 Phase 4-D output reports (mirror Phase 4-C structure)

---

## 7. Hand-off

This report concludes Phase 4-C. Next conversation should:
1. Re-read this report + Reports 1-5
2. Re-walk Corti agent detail page (update 12-item gap list if Corti UI changed)
3. Start Phase 4-D Task D-1 (Corti UI/IA replication, prioritized top bar + right panel)
4. Use `EnterPlanMode` to plan Task D-1 implementation before coding
5. After D-1, proceed to D-2 (v2 dispatch wiring), D-3 (Playwright fix), D-4 (4-input re-walk)

---

## 8. Phase 4-C Final Verdict

**Phase 4-C status: COMPLETE**

- Backend: PASS (LLMWithToolsProvider + 4 MCP tools + v2 schema + RunTrace fields + frontend v2 rendering)
- Tests: PASS (15 categories, 1053 tests, 0 regressions)
- Walkthrough: PARTIAL PASS (backend verified via API + unit tests; visual capture blocked by tooling; deferred to Phase 4-D)
- Reports: 6 of 6 complete (this is the final report)

**Next phase: Phase 4-D — Corti Agent Page UI/IA Replication** (per user's 2026-07-08 explicit directive)
