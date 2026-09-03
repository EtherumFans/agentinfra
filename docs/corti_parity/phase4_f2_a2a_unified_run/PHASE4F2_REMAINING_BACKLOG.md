# Phase 4-F2 — Remaining Backlog

**Date:** 2026-07-10
**Scope:** Items not closed by Phase 4-F2 (A2A-Compatible Unified Agent Run Architecture). These are forward-looking tasks for Phase 4-F3+ and Phase 4-G+.

---

## P0 — Must do in Phase 4-F3

These items block the F3 verdict and are immediately actionable.

| # | Item | Why | Files |
|---|---|---|---|
| 1 | 4 P0 smoke runs on non-medical-coding agents | F2 only smoke-tested Medical Coding (T12). Need to verify Coding Evidence, Principal Diagnosis Review, DRG/DIP Risk Review, Discharge Summary Structuring all return 200 + structured output via `/api/v1/agents/{id}/run` | `backend/tests/api/test_phase4f_smoke.py` (new), `backend/tests/fixtures/phase4f_smoke/*.json` (8 fixtures) |
| 2 | Frontend polish — extract Settings/Code/Tools shared components | AgentDetailPage and AgentChatPage currently have duplicated Settings/Code panels. Extract to `frontend/src/components/agent/SettingsCodeTabs.tsx` for reuse | `frontend/src/components/agent/SettingsCodeTabs.tsx` (new), `frontend/src/pages/AgentDetailPage.tsx`, `frontend/src/pages/AgentChatPage.tsx` |
| 3 | Code tab — replace C# with curl/JS/Python | Prompt §7.4 requires JS/Python/curl tabs (not C#). Currently the Code tab has C# snippets | `frontend/src/pages/AgentChatPage.tsx` (AgentConfigSidebar .NET snippets) |
| 4 | AgentChatPage — Add API Client dropdown rendering | The state `selectedApiClient` already exists; only the UI is missing | `frontend/src/pages/AgentChatPage.tsx` |
| 5 | 8 agent spec standardization — add 5 new fields | Packs need `default_runtime_mode`, `available_runtime_modes`, `example_inputs`, `built_by`, `output_contract` fields on remaining packs (5 of 8 done in F2) | `backend/official_agents/*/agent_pack.json` |

---

## P1 — Important for Phase 4-F3 polish

| # | Item | Why | Effort |
|---|---|---|---|
| 6 | Settings tab — System prompt editor improvements | Currently read-only display; should support edit + save (Corti parity) | Medium |
| 7 | Experts area — "Browse expert library" button enable | Currently disabled; should open expert browser modal | Medium |
| 8 | Pinned parts — add/edit pinned message parts | Currently shows "无固定消息片段"; should support add/edit | Small |
| 9 | RunTrace page — expandable rows with raw metadata | Currently rows are clickable but don't expand | Small |
| 10 | AgentDetailPage — fix broken streaming (Phase 2.1-A leftover) | Currently the "Send" button on the detail page's chat tab shows "Agent streaming endpoint removed" error | Medium |

---

## P2 — Phase 4-G product features

| # | Item | Why | Effort |
|---|---|---|---|
| 11 | Live cost backend wiring | Topbar shows `$50.00` flat credit. Need real-time cost from `cost_usd` field in `AgentRunResponse` | Medium |
| 12 | API Client selector — real binding | Dropdown exists in state but not rendered. Need real list from `GET /api/clients` + selection | Medium |
| 13 | Run History tab — server-side persistence | Currently chat result is lost on page refresh. Need RunHistory table + GET endpoint | Large |
| 14 | Agent fork — clone iCoDer built agent to user-owned editable copy | Corti parity — "自定义" button should create a forked copy | Medium |
| 15 | Web Component SDK (ROPC embedded) | HIS/EMR integration via `<icoder-agent>` custom element | Large |
| 16 | Deep Evidence — full wiring for Coding Evidence agent | Currently Coding Evidence returns a stub response; need full per-code evidence span extraction | Medium |

---

## P3 — Phase 4-H+ / Phase 5

| # | Item | Why | Effort |
|---|---|---|---|
| 17 | Large-scale quality evaluation | 201 gold-case run on Medical Coding Agent to measure F1 vs MedCodER baseline | Large |
| 18 | DRG/DIP rule engine — real implementation | Currently `drg-analyzer` is LLM-only; need rule engine path for high-risk code detection | Large |
| 19 | 医保合规知识库 — regional rule sets | Per-region (CN-Hangzhou, CN-Shanghai, etc.) compliance rule sets | Large |
| 20 | Agent Marketplace — publish/install flow | Corti-style marketplace for ISV-built agents (currently only iCoDer built agents visible) | Large |
| 21 | Multi-tenant RBAC | Currently single org (`icoder Default`); need per-tenant role management for SaaS | Large |

---

## Pre-existing UX Issues (not blockers, but worth tracking)

| # | Issue | Workaround |
|---|---|---|
| A | Chat history loss on browser back from RunTrace page | Right-click "View RunTrace" → "Open in new tab" |
| B | iCoDer built tab — 5 metadata-only agents show "Coming Soon" with no "使用智能体" button | Expected — these are stubs pending Phase 4-F3+ implementation |
| C | Dark mode toggle works but some color tokens may need verification | Phase 4-E2 already audited and fixed the tailwind config; no regression in F2 |
| D | System prompt textarea is read-only | Expected — Phase 4-F3 will add edit + save |

---

## Deferred from F2 (not in scope)

Per F2 prompt §1, the F2 scope was narrowly:

1. ✅ Unified endpoint constructs A2A envelope (DONE — `construct_envelope()` in `a2a_facade.py`)
2. ✅ Medical Coding default = corti_like_fast on BOTH paths (DONE — `_MedicalCodingV2ProjectingHandler` intercept)
3. ✅ trace_events persisted to RunTraceStore (DONE — `persist_trace_events()` after every run)
4. ✅ iCoDer built tab renders 14 cards (DONE — vitest regex fix)

The following items were considered but explicitly deferred:

- **RunHistory table persistence** — chat result survives page refresh (deferred to Phase 4-G #13)
- **Real-time cost in topbar** — currently flat $50.00 credit (deferred to Phase 4-G #11)
- **API Client selector rendering** — placeholder only (deferred to Phase 4-G #12, but Phase 4-F3 #4 may render a non-functional dropdown)
- **Agent fork (自定义 button)** — Corti parity (deferred to Phase 4-G #14)
- **4 P0 smoke runs on non-medical-coding agents** — explicitly F3 scope (P0 #1 above)

---

## Summary

- **P0 (5 items):** Phase 4-F3 scope — must close for F3 verdict
- **P1 (5 items):** Phase 4-F3 polish — improve UX quality
- **P2 (6 items):** Phase 4-G — product features for SaaS readiness
- **P3 (5 items):** Phase 4-H+ — long-term roadmap

**Next sub-phase to start:** Phase 4-F3 — frontend polish + 4 P0 smoke runs.
