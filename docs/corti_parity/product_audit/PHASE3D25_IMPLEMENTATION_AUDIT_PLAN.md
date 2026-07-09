# Phase 3-D2.5 Implementation + Audit Plan

**Phase:** 3-D2.5 — Corti Parity Product Audit + Tool Dispatch Detail
**Date:** 2026-07-07
**Lead:** Claude (glm-5.2) + SONG Luhua
**Predecessor:** Phase 3-D2 (2026-07-07) — 4 gaps closed (RunTrace DB / 9-step trace / MCP-native / custom markdown); browser walkthrough deferred
**Source prompt:** `C:\Users\huawei\Downloads\Corti Parity Product Audit.docx`

---

## 0. Goal

Answer two open questions from Phase 3-D2:

1. **Product-grade Corti parity audit** — Is iCoDer still just *engineering-feature* Corti replication, or has it formed a Corti-style medical Agent Runtime *product prototype*? What's missing for demo / pilot / commercialization?
2. **Tool Dispatch Detail** — RunTrace shows `tools_list / auth_resolved / scope_checked / tools_call` but lacks a dispatch-level detail expansion showing `dispatch_tool()` internal stages (schema validation / phi_redaction / scope / handler / duration / result_shape / error_stage).

Phase 3-D2 closed 4 gaps at code level but **deferred the browser-level Playwright walkthrough**. This phase delivers that walkthrough + the missing dispatch detail + a 12-dimension product audit + 6 audit reports.

---

## 1. Scope (5 parts)

| Part | What | Deliverable |
|------|------|-------------|
| A | Tool Dispatch Detail (backend metadata + frontend expandable + 7 tests) | Code + tests |
| B | 12-dimension Corti Parity Product Audit | Audit notes feeding into reports |
| C | Browser/Playwright real verification (4 runnable agents × full path + 13 screenshots + DevTools safety) | Screenshots + verification report |
| D | 6 audit reports | 6 markdown files in `docs/corti_parity/product_audit/` |
| E | 12-dimension scorecard (0-5 each) + final verdict (A/B/C/D) | Scorecard report |

---

## 2. Part A — Tool Dispatch Detail Implementation

### A1. Backend: `dispatch_tool()` emits `dispatch_detail`

**Location:** `backend/app/icoder/mcp/server.py::dispatch_tool()` (lines 287-566)

**Current state:** Trace emits at 4 points (AUTH_RESOLVED / SCOPE_CHECKED / TOOLS_CALL / COMPLETION), each carrying partial metadata. The dispatch lifecycle isn't co-located.

**Target:** Co-locate a 15-field `dispatch_detail` dict under `TOOLS_CALL` step's `safe_metadata.dispatch_detail`. Keep AUTH_RESOLVED/SCOPE_CHECKED/COMPLETION emits as-is (they remain the cross-stage timeline); the new detail is a *concentrated* view of one tool dispatch.

**15 fields** (per docx spec):

```
tool_name                     # already in current TOOLS_CALL emit
dispatch_mode                 # NEW — "http" | "in_process"
handler_ref                   # already in current TOOLS_CALL emit
input_schema_validation       # NEW — "passed" | "failed" | "skipped"
phi_redaction                 # NEW — "passed" | "failed" | "skipped"
auth_type                     # NEW — from descriptor.auth_config.type or "in-process"
auth_resolved                 # NEW — true | false (false when auth resolution raised)
required_scopes               # NEW — from descriptor
granted_scopes                # NEW — from auth_header
scope_check                   # NEW — "passed" | "failed"
handler_status                # NEW — "ok" | "failed" (failed covers resolve + invoke)
duration_ms                   # NEW — end-to-end dispatch_tool duration
result_shape                  # NEW — type + top-level keys (dict only) + size
error_code                    # NEW — MCPErrorCode int when failed, else null
error_stage                   # NEW — "schema" | "phi" | "auth" | "scope" | "handler_resolve" | "handler_invoke" | null
```

**Implementation strategy** (minimal blast radius):

1. Introduce a local `dispatch_detail: dict[str, Any] = {}` accumulator at the top of `dispatch_tool()`.
2. Populate fields incrementally as each stage runs:
   - After descriptor lookup: `tool_name`, `dispatch_mode` (detect via `isinstance(request, SimpleNamespace)` or a `request.state.dispatch_mode` marker set by in-process caller)
   - After PHI redaction: `phi_redaction` ("passed" / "skipped" when redactor is None)
   - After input validation: `input_schema_validation` ("passed" / "failed" / "skipped" when no schema)
   - After auth resolution: `auth_type`, `auth_resolved`, `required_scopes`, `granted_scopes`
   - After scope check: `scope_check`
   - After handler resolve + invoke: `handler_ref`, `handler_status`, `duration_ms`, `result_shape`, `error_code`, `error_stage`
3. **Emit point:** Move the current `TOOLS_CALL` OK emit (line 480-492) from *before handler invoke* to *after handler invoke*, and embed `dispatch_detail` in `safe_metadata["dispatch_detail"]`. Failed paths (handler resolve fail / handler invoke fail) also emit `TOOLS_CALL=FAILED` with `dispatch_detail` (handler_status=failed, error_stage set).
4. Keep `COMPLETION` emit unchanged — it remains the run-level summary (covers the whole `dispatch_tool` call as one of the 9 timeline steps).
5. **Redaction:** `dispatch_detail` carries only display-safe fields. `error_code` is an int (MCPErrorCode), `error_stage` is an enum-string. No raw token / Authorization / client_secret / secret_ref / PHI ever enters `dispatch_detail`. The existing `_redact_safe_metadata` defensive scan still runs before DB insert.

**Safety requirements (docx §A1 "安全要求"):**

- ✅ No raw token (we only carry `auth_type` + `redacted_view` already on AUTH_RESOLVED step)
- ✅ No Authorization header (we carry `auth_resolved: bool` only)
- ✅ No client_secret / secret_ref (we carry `auth_type` only)
- ✅ No PHI原文 (PHI is redacted before handler; `result_shape` is type+keys+size, never content)
- ✅ Redaction-before-write (existing `_redact_safe_metadata` runs on the whole `safe_metadata` dict including `dispatch_detail`)
- ✅ error_message sanitization: `error_code` is an int; we do NOT put `error.message` in dispatch_detail (the existing COMPLETION emit carries `error` string but is already filtered by `_redact_safe_metadata` if it contains "token"/"secret"/"authorization")

**`dispatch_mode` detection:**

- HTTP path: `tools/call` route → `request` is a real `starlette.requests.Request`
- In-process path: `_SimpleAgentDispatchHandler` → `request` is a `SimpleNamespace` (per Phase 3-D2 Task 3)

Detection: `isinstance(request, Request)` → "http"; else "in_process". Alternatively, set `request.state.dispatch_mode = "in_process"` in `_SimpleAgentDispatchHandler`. I'll go with the `isinstance` check (no caller change needed).

### A2. Frontend: RunTracePage Tool Dispatch Detail expandable

**Location:** `frontend/src/pages/RunTracePage.tsx`

**Target:** When a step is `tools_call` OR `safe_metadata.dispatch_detail` exists, render a collapsible "Tool Dispatch Detail" panel under that step.

**Layout (docx §A2):**

```
▼ Tool Dispatch Detail
  Tool              : search_icd
  Dispatch Mode     : http
  Handler           : app.icoder.mcp.handlers.coding:search_icd
  Schema Validation : passed
  PHI Redaction     : passed
  Auth Type         : bearer
  Required Scopes   : [coding:search]
  Granted Scopes    : [coding:search, coding:validate]
  Scope Check       : passed
  Handler Status    : ok
  Duration          : 142 ms
  Result Shape      : dict{codes, total, has_more} (size: 1284 B)
  Error Stage       : —
  Error Code        : —
```

**Behavior:**

- Default collapsed (chevron icon)
- Failed `tools_call` auto-expands (so user sees failure stage immediately)
- Only safe metadata is rendered (the backend already redacts; frontend is defense-in-depth — never render keys named `token` / `secret` / `authorization` / `client_secret` / `secret_ref` / `password` even if they appear)
- TypeScript 0 errors (gate: `npx tsc --noEmit`)

**Component shape:**

```tsx
function ToolDispatchDetail({ detail }: { detail: DispatchDetail }) {
  const [open, setOpen] = useState(detail.handler_status === "failed");
  // ... render rows
}
```

Embedded inside the existing `RunTraceStep` component's metadata render path.

### A3. Tests (7 new)

**File:** `backend/tests/unit/icoder/mcp/test_dispatch_detail.py` (new) + 1 frontend test

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_dispatch_tool_success_emits_dispatch_detail` | TOOLS_CALL step carries `dispatch_detail` with all 15 fields; `handler_status="ok"`, `error_stage=null` |
| 2 | `test_dispatch_tool_schema_validation_failure_emits_dispatch_detail` | Invalid args → `dispatch_detail.input_schema_validation="failed"`, `error_stage="schema"`, `error_code=-32602` |
| 3 | `test_dispatch_tool_scope_failure_emits_dispatch_detail` | Missing scope → `dispatch_detail.scope_check="failed"`, `error_stage="scope"`, `error_code=-32012` |
| 4 | `test_dispatch_tool_handler_failure_emits_dispatch_detail` | Handler raises → `dispatch_detail.handler_status="failed"`, `error_stage="handler_invoke"` |
| 5 | `test_dispatch_detail_contains_no_token_secret_authorization_phi` | Sweep `dispatch_detail` recursively; assert no key matches `token|secret|authorization|client_secret|secret_ref|password` and no value matches `_is_token_blob` |
| 6 | `test_run_trace_api_returns_dispatch_detail` | `GET /api/runtime/runs/{run_id}/trace` response includes `dispatch_detail` under `tools_call` step |
| 7 | `test_run_trace_page_renders_tool_dispatch_detail` | (frontend vitest) Render `RunTraceStep` with `dispatch_detail`; assert "Tool Dispatch Detail" label + collapsed chevron; click → rows visible |

Backend tests 1-6 go in `test_dispatch_detail.py` (uses the existing `dispatch_tool` test fixtures from `test_mcp_agent_tools_lifecycle.py`). Frontend test 7 goes in `frontend/src/pages/__tests__/RunTracePage.dispatch_detail.test.tsx` (new).

---

## 3. Part B — 12-Dimension Corti Parity Product Audit

For each dimension: read code + (where needed) run dev server + verify against the docx questions. Output feeds the audit report (Part D).

| # | Dimension | Key evidence source | What I'll verify |
|---|-----------|--------------------|----|
| B1 | Product main path | Browser walkthrough (Part C) + code | Hub → Clone → Chat → Run → Rendered → JSON → RunTrace → Dispatch Detail → return. 4 agents all pass. Error path understandable. |
| B2 | Agent Hub / IA | `official_agents/**/agent_pack.json` + Hub endpoint | Card clarity, runnable/Coming Soon, use_case filter, inputs/outputs/permissions/non-goals, no fake runnable, China differentiation. |
| B3 | 4 runnable agents | Run each in browser | medical-coding / code-validation / compliance-guardrail / note-completeness. Check Hub可见/Clone/Chat/A2A mainline/真实业务逻辑/MCP dispatcher/markdown+JSON/RunTrace/Dispatch Detail/失败路径/无 fake. |
| B4 | MCP / Tool Runtime | `tool_registry.py` + `dispatch_tool` | 8 tools / unified dispatch_tool / 3 new tools required_scopes / -32012 on scope fail / dispatch_detail / handler_ref resolvable / inputSchema valid / error envelope uniform. |
| B5 | Security / Redaction | `run_trace.py::_redact_safe_metadata` + tests | No token/client_secret/Authorization/secret_ref in logs or RunTrace; DB write redaction; cross-org 404; DevTools network clean; auth_resolved frontend defense-in-depth. |
| B6 | RunTrace / Audit trail | `RunTracePage` + InboundHandler trace emits | Opens from AgentChatPage; medical-coding 9-step; simple agents PLANNER=SKIPPED; tools_list/auth_resolved/scope_checked/tools_call visible; Dispatch Detail expandable; failed path COMPLETION=FAILED; persisted; org/project scoped. |
| B7 | Output quality | 3 markdown generators + medical-coding markdown | Rendered defaults to markdown; JSON canonical; 3 simple agents have 5-section markdown; conclusion/table/risk/advice; suitable for 病案科/医保办; no over-automation promise; manual review reminder; DRG/DIP impact explained. |
| B8 | A2A / State machine / Error UX | `inbound_handler.py` + A2A envelope | message:send envelope; success/failed/input-required consistent; unknown agent 404; scope forbidden understandable; planning_failed/tool_failed/aggregation_failed in RunTrace; frontend shows understandable error. |
| B9 | China medical / revenue compliance differentiation | `MedicalCodingRuleSet` + 3 simple agents | ICD-10-CN/ICD-9-CM-3 clear; DRG/DIP sensitive items; 医保合规 risk; 病历完整性; 人工复核 boundary; no auto-writeback to HIS. |
| B10 | Frontend UX / Visual parity | Browser walkthrough (Part C) | Hub like Agent Library; card professional; Chat clear; Rendered/JSON easy; RunTrace readable; Dispatch Detail non-intrusive; empty/error/loading natural; 中文文案 professional. |
| B11 | Engineering quality / Test credibility | `pytest.ini` + targeted sweeps | Targeted sweeps cover core paths; default sweep MemoryError sharded plan; TS 0 errors; migration rollback; Phase 3-B2/C/D/D2 no regression; heavy/retrieval/infra markers reasonable. |
| B12 | Production readiness | `app/config.py` + cloud docs | RunTrace DB write failure policy; A2A bearer-token resolution (currently in-process bypass); multi-worker; tenant/org/project permissions; dev server stability; hospital pilot minimum. |

---

## 4. Part C — Browser / Playwright Real Verification

### C1. Service startup

```bash
cd backend && python -m uvicorn app.main:app --port 8000 &
cd frontend && npm run dev &   # port 3000 or 3002
```

### C2. 4 runnable agents × full path

For each agent (`medical-coding-agent` / `code-validation-agent` / `compliance-guardrail-agent` / `note-completeness-agent`):

1. Hub: open `/ai-studio/agents`, locate card
2. Clone / Use Agent: click card → chat page
3. Chat: input sample text
4. Run: click send → wait for completion
5. Rendered Output: verify markdown displayed
6. JSON Output: toggle to JSON tab
7. View RunTrace: click "View RunTrace" link
8. Expand Tool Dispatch Detail: click chevron on `tools_call` step

### C3. Screenshots (13) → `docs/corti_parity/product_audit/screenshots/`

| File | What |
|------|------|
| `hub.png` | Agent Hub page |
| `agent_card_runnable.png` | One runnable agent's card (medical-coding) |
| `chat_medical_coding.png` | Chat page with sample input |
| `chat_code_validation.png` | Chat page for code-validation |
| `chat_compliance_guardrail.png` | Chat page for compliance-guardrail |
| `chat_note_completeness.png` | Chat page for note-completeness |
| `output_rendered_each_agent.png` | Rendered markdown tab (one per agent, or 4-in-one) |
| `output_json_each_agent.png` | JSON tab (one per agent, or 4-in-one) |
| `runtrace_medical_coding.png` | 9-step RunTrace timeline |
| `runtrace_simple_agent.png` | 4-step RunTrace (PLANNER=SKIPPED) |
| `tool_dispatch_detail_success.png` | Dispatch Detail expanded on success |
| `tool_dispatch_detail_forbidden.png` | Dispatch Detail expanded on -32012 scope forbidden |
| `error_state.png` | Any error state (e.g. unknown agent 404) |

### C4. DevTools / Network safety

Inspect 4 responses:

1. `GET /api/runtime/runs/{run_id}/trace` response body
2. `POST /mcp/v1/tools/list` response body
3. `POST /a2a/v1/message:send` response body
4. `POST /mcp/v1/tools/call` (forbidden case) response body

Assert none contain: raw token / `Authorization: Bearer ...` / `client_secret` / `secret_ref` / PHI原文.

---

## 5. Part D — 6 Audit Reports

All written to `docs/corti_parity/product_audit/`:

| File | Content |
|------|---------|
| `ICODER_CORTI_PARITY_PRODUCT_AUDIT_REPORT.md` | Full 12-dimension audit findings (B1-B12) |
| `ICODER_CORTI_PARITY_SCORECARD.md` | 12-dimension scorecard (0-5 each) + total + verdict |
| `ICODER_PHASE4_READINESS_REPORT.md` | Is Phase 4 ready to start? What's blocking? |
| `ICODER_BROWSER_MANUAL_VERIFICATION_REPORT.md` | Part C walkthrough log + screenshot index + DevTools findings |
| `ICODER_TOOL_DISPATCH_DETAIL_IMPLEMENTATION_REPORT.md` | Part A implementation: code changes + 7 tests + redaction proof |
| `ICODER_AUDIT_GAP_MATRIX.md` | All gaps found during audit (new + carry-over from Phase 3-D2) with severity + owner + Phase |

---

## 6. Part E — Scorecard + Verdict

### 12 dimensions (0-5 each)

For each: `score | evidence | remaining gaps | next action`.

| # | Dimension |
|---|-----------|
| 1 | 产品主路径 |
| 2 | Agent Hub 信息架构 |
| 3 | Agent 可运行性 |
| 4 | MCP / Tool Runtime |
| 5 | 权限 / 安全 / 脱敏 |
| 6 | RunTrace / 审计留痕 |
| 7 | 输出质量 |
| 8 | A2A / 状态机 / 错误体验 |
| 9 | 中国医疗编码 / 收入合规差异化 |
| 10 | 前端 UX / 视觉复刻 |
| 11 | 工程质量 / 测试可信度 |
| 12 | 生产化 readiness |

### Final verdict (one of)

- **A. 工程功能复刻阶段** — still feature-replication, not yet a product
- **B. Corti-style 医疗 Agent Runtime 产品雏形** — product prototype, demo-ready
- **C. 可演示 / 可试点** — pilot-ready with selected hospitals
- **D. 可商业化** — commercial-ready

### PASS criteria (10, from docx)

1. ✅ Tool Dispatch Detail 展开层完成
2. ✅ Tool Dispatch Detail 不泄露 token/secret/Authorization/PHI
3. ✅ 4 runnable agents 浏览器主路径全部走通
4. ✅ RunTrace 可以打开并展示 Tool Dispatch Detail
5. ✅ DevTools/Network 安全检查完成
6. ✅ 输出 6 份审计报告
7. ✅ Scorecard 12 维度全部打分
8. ✅ Phase 3-B2/3-C/3-D/3-D2 已关闭 gap 无回归
9. ✅ TypeScript 0 error
10. ✅ 明确给出 Phase 4 是否可启动的裁决

---

## 7. Execution order

1. **Part A1** (backend dispatch_detail) — write code, no tests yet
2. **Part A2** (frontend RunTracePage expandable) — write component
3. **Part A3** (7 tests) — write tests, run them, fix until green
4. **Part C1** (start dev server) — uvicorn + vite
5. **Part C2-C4** (browser walkthrough + screenshots + DevTools) — Playwright MCP
6. **Part B** (12-dimension audit) — combine code reading + browser evidence
7. **Part D** (6 reports) — write all 6 markdown files
8. **Part E** (scorecard + verdict) — finalize in scorecard report

---

## 8. Risk / known limits

- **Default sweep MemoryError** — pre-existing on Windows; targeted sweeps are the workaround. Will run targeted sweeps for new tests only.
- **Bearer-token resolution from A2A envelope** — Phase 3-D2 left this as Phase 4 task; the simple-agent path uses in-process auth bypass. Audit will flag this in B12 (production readiness) and B5 (security).
- **Corti live account** — not available this session; audit uses iCoDer-side evidence + the Corti reverse-engineering reports (Section B observation log + Section F gap matrix) as the Corti reference baseline.
- **Chrome / Playwright MCP** — Playwright MCP is available; will use `mcp__playwright__browser_*` tools. If a browser action fails (e.g. element not found), will fall back to direct API calls + code-level evidence and flag the gap in the verification report.

---

## 9. Acceptance

This plan is ready to execute. No open questions. Proceeding to Part A1.
