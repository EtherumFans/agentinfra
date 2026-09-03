# Phase 4-H Baseline

**Audit start:** 2026-07-10 14:13:52 local (06:13:52 UTC)
**Auditor:** Claude (Sonnet 4.5)
**Timezone:** Asia/Shanghai (UTC+8)

---

## 1. Code baseline

| Field | Value |
|-------|-------|
| Current HEAD commit | `e292420` `docs(phase4g): walkthrough report + 4 screenshots` |
| Working tree state | CLEAN — no uncommitted changes (Phase 4-G all committed) |
| Audit-prior commit | `e9a4cc9` `feat(phase4g): live cost + API Client binding + RunHistory + Agent fork (PASS)` |
| Repository | `E:\Corti4C` (git, branch `master`) |
| Last 5 commits | `e292420`, `e9a4cc9`, `b7db84f` (phase4f-f3), `c9c1f52` (phase4f-f1f2), `5f8f611` (phase4f redesign) |

## 2. Backend

| Field | Value |
|-------|-------|
| Startup command | `python -m uvicorn app.main:app --port 8000 --host 127.0.0.1` |
| Process status | Running (PID 16340, port 8000 LISTENING) |
| Base URL | `http://localhost:8000` |
| Health endpoint | `GET /api/health` → `{"status":"healthy","app":"iCoDer Medical Coding Agent","version":"1.0.0","environment":"development","medcoder_index_ready":true,"llm_provider":"deepseek","llm_model":"deepseek-chat"}` |
| Runtime status | `GET /api/runtime/status` → started: true, execution_mode: legacy, agents_installed: 14, default_provider: deepseek |
| Endpoint count | 174 paths in OpenAPI |
| LLM provider | DeepSeek (`LLM_PROVIDER=deepseek`) |
| LLM model | `deepseek-chat` (DeepSeek V4 flash) |
| LLM base URL | `https://api.deepseek.com/v1` |
| LLM pricing | $0.14/1M input, $0.28/1M output (`LLM_PRICE_INPUT_PER_1M=0.14`, `LLM_PRICE_OUTPUT_PER_1M=0.28`) |
| MedCodER index | Ready (BGE-M3 + FAISS loaded) |

## 3. Frontend

| Field | Value |
|-------|-------|
| Startup command | `npm run dev` (Vite v5.4.21) |
| Process status | Running (PID 26940, port 3002 LISTENING) |
| Base URL | `http://localhost:3002` |
| HTTP status | 200 OK |
| Tech stack | React 18 + TypeScript 5 + Vite 5 + Tailwind CSS |
| tsc status | 0 errors (verified prior to audit) |

## 4. Database

| Field | Value |
|-------|-------|
| Database | SQLite at `E:\Corti4C\backend\data\icoder.db` |
| Alembic revision | `010` (latest — creates `run_history` table) |
| Table count | 35 tables |
| Notable tables | `agents`, `experts`, `oauth_clients`, `oauth_tokens`, `run_history`, `run_trace_events`, `audit_logs`, `transactions`, `users`, `organizations`, `encounters`, `documents`, `clinical_evidences`, `code_candidates`, `code_mappings`, `mcp_servers`, `templates`, `tickets`, `customers` |

## 5. Test account

| Field | Value |
|-------|-------|
| Username | `admin` |
| Email | `admin@icoder.ai` |
| Role | system administrator |
| Organization | default org (`ff4d047cb533`) |
| User ID | `f237e192bbd5` |
| Auth method | JWT Bearer token (HS256, in `localStorage.access_token`) |
| Token expiry | ~32h (`exp` 1783679900, `iat` 1783651100) |
| Billing balance | $50.00 (baseline) |
| Live cost accumulator | $0.000000 (reset at audit start) |

## 6. Browser + environment

| Field | Value |
|-------|-------|
| Browser | Chrome via Playwright MCP (chromium) |
| Screen resolution | (to be captured per page; defaulting to viewport) |
| OS | Windows 10 Home China 10.0.19045 |
| Playwright MCP version | (latest) |
| Screenshot path | `E:\Corti4C\screenshots\phase4h\` (created, empty) |

## 7. Corti console access

| Field | Value (to be filled in §3.3) |
|-------|------------------------------|
| Corti home URL | TBD |
| Console entry | TBD |
| Current org | TBD |
| Current role | TBD |
| Accessible modules | TBD |
| Language | TBD |
| API domain | TBD |
| Auth/storage method | TBD |

## 8. Phase 4-G audit-prior state (carried forward)

| Capability | State |
|------------|-------|
| Agent Hub (My + iCoDer built tabs) | ✅ working (13 iCoDer built agents visible) |
| Agent Detail Page | ✅ working |
| Agent Chat Page | ✅ working |
| Settings / Code tabs | ✅ working |
| JS / Python / curl / JSON Config | ✅ working |
| Unified Agent Run API (`POST /api/v1/agents/{id}/run`) | ✅ working |
| A2A-compatible envelope | ✅ working |
| ProviderRegistry + PureLLMProvider | ✅ wired |
| DeepSeek real calls | ✅ working (T12 case ~7s, $0.000206) |
| RunTrace (9-step timeline) | ✅ working |
| Per-run cost (token × pricing) | ✅ working |
| RunHistory (server-side persistence) | ✅ working (alembic 010) |
| API Client ID Trace attribution | ✅ working (inline + persisted safe_metadata) |
| Agent clone / fork | ✅ working (Forked-from badge renders) |
| 4 P0 non-Medical-Coding Agents (smoke run) | ✅ working |
| Medical Coding Agent | ✅ working (corti_like_fast default) |
| Compliance Guardrail + 7 other prebuilt | ✅ visible |

## 9. Known limitations carried into audit

(From PHASE4G_LIVE_COST_API_CLIENT_RUNHISTORY_FORK_REPORT.md §9):

- AgentsPage "自定义" card button (AgentsPage.tsx:576) navigates to `/ai-studio/agents/${card.agent_ref}` but agent_ref contains a slash → router falls back to `/`. Pre-existing, not Phase 4-G regression.
- API Client dropdown UI not yet rendered on AgentChatPage — only the stateful plumbing works. P1 follow-up.

## 10. Audit scope reminder

Per the PDF prompt §2.1 — development is FROZEN during this audit. Allowed code modifications only when:
1. iCoDer cannot start
2. Login or core routes block audit
3. Agent cannot run
4. Browser walkthrough blocked by clear P0 bug
5. Audit evidence cannot be saved

Any code modification must be:
- A separate commit
- Tagged `AUDIT_BLOCKER_FIX`
- Recorded with before/after evidence
- Not opportunistic refactoring
- Not Corti implementation copying

All non-blocking issues go to the diff backlog, not immediate development.
