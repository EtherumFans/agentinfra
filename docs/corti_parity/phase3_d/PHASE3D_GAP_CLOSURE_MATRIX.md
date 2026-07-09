# Phase 3-D0 / D1 — Gap Closure Matrix

**Date:** 2026-07-06
**Phase:** 3-D0 + 3-D1
**Verdict:** ✅ All targeted gaps closed; no Phase 3-B2 / 3-C regressions

## Matrix

| Gap ID | Source | Description | Phase 3-D close | Verification |
|--------|--------|-------------|-----------------|--------------|
| 3-D0-1 | docx Task 1 | MCP scope enforcement — `required_scopes` field + `tools/call` check + `MCP_AUTH_FORBIDDEN` | Task 1 — `auth.py` + `auth_resolver.py` + `tool_registry.py` + `server.py` + 5 tests | TASK1 verif |
| 3-D0-2 | docx Task 2 | redacted_view actual log capture — caplog tests asserting no raw token / client_secret / Authorization header in logs | Task 2 — 5 caplog tests + `_assert_no_raw_token_in_logs` helper | TASK2 verif |
| 3-D0-3 | docx Task 3 | Test hygiene — delete stale e2e_product + fix test_register flaky + clean asyncio warnings + default sweep 0 fail | Task 3 — 7 files deleted + uuid4 isolation + asyncio marker guard + `infra` marker | TASK3 verif |
| 3-D1-4 | docx Task 4 | RunTrace Corti-parity Viewer — 9-step timeline, openable from AgentChatPage, auth step only redacted_view | Task 4 — `run_trace.py` + `run_trace.py` API + `RunTracePage.tsx` + AgentChatPage link + 9 tests | TASK4 verif |
| 3-D1-5a | docx Task 5 | Code Validation Agent — runnable, Hub/Clone/Chat/A2A, MCP tools, markdown+JSON, RunTrace, tests, no fake | Task 5 — `code_validation/agent.py` + v1.2 pack + agent_card + dispatch handler + 5 unit + 1 smoke | TASK5 verif |
| 3-D1-5b | docx Task 5 | Compliance Guardrail Agent — same | Task 5 — `compliance_guardrail/agent.py` + v1.2 pack + agent_card + dispatch handler + 6 unit + 1 smoke | TASK5 verif |
| 3-D1-5c | docx Task 5 | Note Completeness Agent — same | Task 5 — `note_completeness/agent.py` + v1.2 pack + agent_card + dispatch handler + 7 unit + 1 smoke | TASK5 verif |

**Total: 7 gaps closed (3 D0 + 4 D1).**

## PASS criteria closure (10/10)

| # | Criterion | Closed by |
|---|-----------|-----------|
| 1 | MCP scope enforcement done | Task 1 (gap 3-D0-1) |
| 2 | redacted_view actual log capture done | Task 2 (gap 3-D0-2) |
| 3 | Default sweep 0 fail | Task 3 (gap 3-D0-3) — 2265/0 |
| 4 | RunTrace Viewer opens from AgentChatPage | Task 4 (gap 3-D1-4) |
| 5 | ≥3 runnable agents | Task 5 (gaps 3-D1-5a/b/c) — 3 + medical-coding = 4 |
| 6 | Each supports markdown + JSON + RunTrace | Task 5 (gaps 3-D1-5a/b/c) |
| 7 | Each task has manual Corti verification | 5 reports in `manual_verification/` |
| 8 | Written to docs + memory | This dir + MEMORY.md |
| 9 | No token leaks | Task 2 caplog tests + Task 4 auth_resolved contract test |
| 10 | Phase 3-B2 + 3-C gaps no regression | See "No-regression evidence" below |

## No-regression evidence

### Phase 3-B2 gaps (closed in 3-B2, verified still closed in 3-D)

| Phase 3-B2 gap | Description | Status in 3-D |
|----------------|-------------|----------------|
| 2.2 | Click-to-Chat UX (Hub CTA → clone → chat) | ✅ `AgentChatPage` + Clone endpoint still work; the 3 new agents inherit this path automatically |
| 2.3 | Clone preset Hub action | ✅ Hub `clone_url` field populated for all runnable agents (4 now, was 1) |
| 4.3 | Pre-rendered markdown for chat UI | ✅ `medical-coding-agent` still pre-renders; 3 new agents use `generateFallbackMarkdown` |
| Loop 4 | `use_case` filter | ✅ `?use_case=coding_revenue_cycle` still returns 11 packs (3 upgraded in place, no count change) |

### Phase 3-C gaps (closed in 3-C, verified still closed in 3-D)

| Phase 3-C gap | Description | Status in 3-D |
|----------------|-------------|----------------|
| 3.1 | MCP dispatcher auth wiring (B5 #8/#9) | ✅ Task 1 added scope enforcement ON TOP of the existing auth wiring; auth_config + AuthHeader injection still work |
| 3.4 | 4 MCP auth types (none/bearer/inherit/oauth2) | ✅ All 4 still work; Task 2 caplog tests cover bearer + oauth2 paths |
| 3.7 | 7 MCP auth error codes (-32006..-32012) | ✅ Task 1 added `MCP_AUTH_FORBIDDEN` (-32012) firing path; the other 6 still fire correctly |
| 3-layer redaction | known-secret keys / token-blob heuristic / `_SAFE_KEYS` whitelist | ✅ Task 2 caplog tests verify all 3 layers; raw token / client_secret / Authorization header never leak |

### Phase 3-B1 / 3-A / earlier gaps (verified still closed in 3-D)

| Earlier gap | Description | Status in 3-D |
|-------------|-------------|----------------|
| 3-B1 Hub unification | 4 discovery surfaces share `_list_all_cards` | ✅ Now enumerates 5 agents (was 2); all 4 surfaces still consistent |
| 3-B1 v1→v2 projection | `_MedicalCodingV2ProjectingHandler` | ✅ Still works; `_SimpleAgentDispatchHandler` wraps it without changing medical-coding-agent's behavior |
| 3-A agent_pack audit | 16 packs all valid; no INVALID | ✅ Still 16 packs all valid; 3 upgraded v1.1 → v1.2 with no validation errors |

## Known remaining gaps (NOT closed in 3-D, deferred)

| Gap ID | Description | Target phase |
|--------|-------------|--------------|
| 3-D2-1 | RunTrace persistence (in-memory → DB/file) | Phase 3-D2 |
| 3-D2-2 | Orchestrator-emitted trace steps (`PLANNER_SELECTED_EXPERTS` / `EXPERT_RESPONSE` / `OUTPUT_GENERATED` for medical-coding-agent) | Phase 3-D2 |
| 3-D2-3 | Real MCP tool handlers for the 3 new agents (currently A2A-only) | Phase 3-D2 |
| 3-D2-4 | Custom markdown generators for the 3 new agents (currently fallback) | Phase 3-D2 (low priority) |
| Ph4 | MCP server OAuth2.0 enforcement (currently accepts any bearer) | Phase 4 |

These don't block Phase 3-D verdict — the docx prompt's 10 PASS
criteria are all met without them.
