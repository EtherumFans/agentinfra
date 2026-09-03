# Phase 4-F3 — Remaining Backlog

**Date:** 2026-07-10
**Scope:** Items not closed by Phase 4-F3 (Core Agent Smoke Runs). Forward-looking tasks for Phase 4-G+ and Phase 5+.

---

## P0 — Must do in Phase 4-G

These are the next product-readiness blockers per Corti parity matrix `PHASE4F3_CORTI_PARITY_MATRIX.md` (6 PARTIAL dimensions).

| # | Item | Why | Files | Effort |
|---|---|---|---|---|
| 1 | Live cost backend wiring | Topbar shows `$50.00` flat credit. Need real-time cost from `cost_usd` field in `AgentRunResponse` — backend already returns `cost: {}` placeholder; need to populate from `LLMGatewayAdapter` usage metrics | `backend/app/api/agent_run.py`, `backend/app/icoder/agent_runtime/a2a_facade.py`, `frontend/src/components/layout/TopBar.tsx` | Medium |
| 2 | API Client selector — real binding | Dropdown exists in state but selection doesn't bind to runtime calls. Need to pass `api_client_id` field in unified run request and route the call through the selected client's credentials | `frontend/src/pages/AgentChatPage.tsx`, `backend/app/api/agent_run.py` | Medium |
| 3 | RunHistory tab — server-side persistence | Currently chat result is lost on page refresh. Need RunHistory table + GET endpoint + chat-page hydration on load | `backend/app/api/runtime_history.py` (new), `frontend/src/pages/AgentChatPage.tsx` | Large |
| 4 | Agent fork — clone iCoDer built agent to user-owned editable copy | Corti parity — "自定义" button should fork the agent into user's namespace (already half-implemented via `agentHubApi.clone()`, needs UI polish on AgentDetailPage) | `frontend/src/pages/AgentDetailPage.tsx` | Medium |

---

## P1 — Phase 4-F4 polish (UX quality)

| # | Item | Why | Effort |
|---|---|---|---|
| 5 | Settings tab — System prompt editor improvements | Currently autosaves on blur; Corti-style would autosave with cursor position retention + diff indicator | Small |
| 6 | Experts area — "浏览专家库" button enable | Currently disabled stub. Should open expert browser modal with search + filter + add/remove | Medium |
| 7 | Demo input — auto-fill button on agent card | `example_inputs` field exists in pack but no UI button. Add "Try demo" button on each card that auto-fills the chat textarea with the first `example_inputs[0].input_text` | Small |
| 8 | Pinned parts — add/edit pinned message parts | Currently shows "无固定消息片段" empty state. Should support add/edit/delete with content type (text/JSON/file) selector | Small |
| 9 | RunTrace page — expandable rows with raw metadata | Already implemented (Phase 3-D2) but rows could be more polished with copy-button per event | Small |
| 10 | AgentDetailPage — fix broken streaming (Phase 2.1-A leftover) | "Send" button on detail page's chat tab shows "Agent streaming endpoint removed" error. Should call new unified `POST /api/v1/agents/{id}/run` endpoint (F1b) — same as AgentChatPage | Medium |
| 11 | Code slot — add SDK tabs for additional languages | Currently JS/Python/curl/JSON. Corti has same 4; consider adding Go / Rust SDK examples | Small |

---

## P2 — Phase 4-G product features

| # | Item | Why | Effort |
|---|---|---|---|
| 12 | Web Component SDK (ROPC embedded) | HIS/EMR integration via `<icoder-agent>` custom element — Corti's flagship embed pattern | Large |
| 13 | Deep Evidence — full wiring for Coding Evidence agent | Currently Coding Evidence returns a single span per code; need full per-code evidence span extraction with multiple evidence_text per code (direct + indirect + negated) | Medium |
| 14 | DRG/DIP rule engine — real implementation | Currently `drg-analyzer` is LLM-only; need rule engine path for high-risk code detection (MDC catalog + CC/MCC list + age/sex edits) | Large |
| 15 | 医保合规知识库 — regional rule sets | Per-region (CN-Hangzhou, CN-Shanghai, etc.) compliance rule sets with regional DRG/DIP weights and local medical insurance policies | Large |
| 16 | Topbar notifications | Bell icon in topbar (already rendered) should open a notifications dropdown with recent agent runs / cost alerts / system messages | Small |

---

## P3 — Phase 4-H+ / Phase 5

| # | Item | Why | Effort |
|---|---|---|---|
| 17 | Large-scale quality evaluation | 201 gold-case run on Medical Coding Agent to measure F1 vs MedCodER baseline; CI integration with per-PR F1 regression check | Large |
| 18 | Agent Marketplace — publish/install flow | Corti-style marketplace for ISV-built agents (currently only iCoDer built agents visible) | Large |
| 19 | Multi-tenant RBAC | Currently single org (`icoder Default`); need per-tenant role management for SaaS | Large |
| 20 | Experts system — full Phase 5 wiring | Browse expert library / add custom expert / expert-as-LLM with own system prompt / pinned parts pinning across runs | Large |
| 21 | Agent versioning — semantic version migration | Currently packs are versioned (v1.0.0, v1.2.0) but no migration path; need automated v1→v2 upgrade with schema_diff and breaking-change detection | Medium |
| 22 | SSE streaming for long-running agents | Currently the unified endpoint returns when the run completes. For agents >10s, add SSE streaming so the user sees partial output (Corti has this for streaming experts) | Medium |

---

## Pre-existing UX issues (not blockers, but worth tracking)

| # | Issue | Workaround | Phase target |
|---|---|---|---|
| A | Chat history loss on browser back from RunTrace page | Right-click "View RunTrace" → "Open in new tab" | Phase 4-G #3 (RunHistory persistence) |
| B | iCoDer built tab — 5 metadata-only agents show "Coming Soon" with no "使用智能体" button | Expected — these are stubs pending future implementation | Phase 5+ |
| C | Dark mode toggle works but some color tokens may need verification | Phase 4-E2 already audited and fixed the tailwind config; no regression in F3 | (none — verified) |
| D | System prompt textarea autosaves on blur but doesn't show "saving..." indicator during save | Add `agentChatSaving` i18n key + visual indicator | Phase 4-F4 P1 #5 |
| E | Tab switching via Playwright `browser_click` doesn't always trigger React onClick | Use `browser_evaluate` with programmatic `.click()` | (testing tooling only) |
| F | Ctrl+Enter via Playwright `browser_press_key` doesn't trigger React onKeyDown | Use `browser_evaluate` with `dispatchEvent(new KeyboardEvent(...))` | (testing tooling only) |
| G | Login API rate-limited after 5+ logins in 10min | Use UI auth path (Playwright) or wait 60s+ between login API calls | (testing tooling only) |

---

## Deferred from F3 (not in scope)

Per F3 prompt §1, the F3 scope was narrowly:

1. ✅ 4 P0 non-Medical-Coding agents smoke run (DONE — 4/4 PASS via real DeepSeek)
2. ✅ Frontend polish — extract Settings/Code/Tools shared components (DONE — Phase 4-D already extracted; F3 verified)
3. ✅ Code tab — JS/Python/curl/JSON standardization (DONE — `AgentConfigSidebar.tsx` refactored to use shared `CodeSnippet`)
4. ✅ API Client dropdown rendering (DONE — `AgentChatPage.tsx` adds dropdown UI)
5. ✅ RunTrace expandable raw metadata (DONE — Phase 3-D2 already implemented)
6. ✅ 8 agent spec standardization — 5 new fields (DONE — all 8 packs already have v1.3 spec from F1/F2)
7. ✅ New backend test file `test_phase4f3_core_agent_smoke.py` (DONE — 9 cases / 18 actual tests)
8. ✅ Frontend tests (DONE — tsc 0 + 75/75 vitest)
9. ✅ Browser walkthrough 4 agents × 15 steps (DONE — 60/60 PASS)

The following items were considered but explicitly deferred:

- **Live cost backend wiring** — deferred to Phase 4-G #1
- **API Client selector binding** — deferred to Phase 4-G #2
- **RunHistory persistence** — deferred to Phase 4-G #3
- **Agent fork on AgentDetailPage** — deferred to Phase 4-G #4
- **Experts system (browse/add/pinned parts)** — deferred to Phase 5 #20
- **Demo input auto-fill button** — deferred to Phase 4-F4 P1 #7
- **AgentDetailPage streaming fix** — deferred to Phase 4-F4 P1 #10
- **Web Component SDK** — deferred to Phase 4-G #12
- **Deep Evidence full wiring** — deferred to Phase 4-G #13
- **DRG/DIP rule engine** — deferred to Phase 4-G #14
- **医保合规知识库** — deferred to Phase 4-G #15
- **Large-scale quality evaluation** — deferred to Phase 4-H+ #17
- **Agent Marketplace** — deferred to Phase 4-H+ #18
- **Multi-tenant RBAC** — deferred to Phase 4-H+ #19
- **SSE streaming** — deferred to Phase 4-H+ #22

---

## Summary

- **P0 (4 items):** Phase 4-G scope — must close for SaaS product readiness
- **P1 (7 items):** Phase 4-F4 polish — improve UX quality
- **P2 (5 items):** Phase 4-G — product features for SaaS readiness
- **P3 (6 items):** Phase 4-H+ / Phase 5 — long-term roadmap

**Next sub-phase to start:** Phase 4-G — P0 #1-4 (live cost + API Client binding + RunHistory + Agent fork). This continues the Corti parity closure from F3's 6 PARTIAL dimensions.

---

## Corti parity closure status (per `PHASE4F3_CORTI_PARITY_MATRIX.md`)

| Dimension | Status | Closing phase |
|---|---|---|
| 1. Agent list tabs | ✅ PARITY | (closed) |
| 2. Built-in badge | 🟢 CLOSE | (cosmetic, no urgent action) |
| 3. Use case classification | ✅ PARITY | (closed) |
| 4. Agent card | ✅ PARITY+ | (closed) |
| 5. Agent Detail Page | ⚠️ PARTIAL | Phase 4-F4 P1 #10 |
| 6. Settings slot | ⚠️ PARTIAL | Phase 5 #20 (Experts + Pinned parts) |
| 7. Code slot | ✅ PARITY | (closed) |
| 8. Experts area | ⚠️ PARTIAL | Phase 5 #20 |
| 9. Add context button | ✅ PARITY | (closed) |
| 10. API Client dropdown | ⚠️ PARTIAL | Phase 4-G #2 |
| 11. Live cost | ⚠️ PARTIAL | Phase 4-G #1 |
| 12. SDK tabs | ✅ PARITY | (closed) |
| 13. RunTrace | ✅ PARITY+ | (closed) |
| 14. Copy JSON/Markdown | ✅ PARITY | (closed) |
| 15. Demo input | ⚠️ PARTIAL | Phase 4-F4 P1 #7 |
| 16. Error handling | ✅ PARITY | (closed) |

**Corti parity closure:** 10/16 closed (62.5%); 6 PARTIAL remain — all addressed in the backlog above.
