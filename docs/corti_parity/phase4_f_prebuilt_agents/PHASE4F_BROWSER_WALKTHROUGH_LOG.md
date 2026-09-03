# Phase 4-F — Browser Walkthrough Log

**Date:** 2026-07-10
**Per prompt §11.3 — 21 steps**
**Browser:** Chrome 149 (Win64) via Playwright MCP (remote debugging port 9222)
**Dev servers:** backend uvicorn :8000 + frontend vite :3000

---

## Environment setup

- Backend: `cd backend && python -m uvicorn app.main:app --port 8000` (running)
- Frontend: `cd frontend && npm run dev` (port 3000, NOT 3002 as plan stated)
- Chrome: launched with `--remote-debugging-port=9222 --user-data-dir=...`
- Playwright MCP: connected to http://localhost:9222

**Note:** User logged into iCoDer themselves after first attempt with
demo/demo1234 returned 401 "Invalid credentials".

---

## Walkthrough (21 steps)

### Step 1 — Open app ✅
- URL: `http://localhost:3000/`
- Page redirected to `/ai-studio/agents` (default landing for signed-in user)
- Page title: "iCoDer Medical Coding Agent"

### Step 2 — Login ✅
- User logged in themselves (demo/demo1234 returned 401)
- Confirmed by presence of "$50.00" billing link + user avatar in header

### Step 3 — Navigate to AI Studio / Agents ✅
- URL: `http://localhost:3000/ai-studio/agents`
- Page rendered with sidebar nav (AI Studio section: 总览/AI智能体/语音转录/事实提取/医学编码)

### Step 4 — Switch to iCoDer built tab ✅
- Clicked "iCoDer built" tab (second of 2 tabs)
- Tab became active; "我的AI智能体" became inactive

### Step 5 — Screenshot Agent list ✅
- **File:** `phase4_f_agents_list.png` (My Agents tab default)
- Then switched to iCoDer built tab
- **File:** `phase4_f_icoder_built_tab.png` (14 cards visible)

**Observed:** 14 cards in iCoDer built tab:
- 9 runnable/MVP: Medical Coding, Coding Evidence, Principal Dx Review,
  DRG/DIP Risk Review, Procedure Coding, Note Completeness, Discharge
  Summary Structuring, Compliance Guardrail, Code Validation
- 5 metadata-only: Denial Appeals, Evidence Ranker, Diagnosis Extractor,
  CDI Review, Documentation Gap

Each card shows:
- Name + version + maturity badge
- "09-Jul-2026 · iCoDer" timestamp (F2 created_at + creator fields)
- **Default runtime mode chip** (F2 spec field) — e.g. `corti_like_fast`,
  `a2a_pure_llm`, `rule_engine`
- Red lines chips (no_upcoding / evidence_required / no_writeback)
- Medical Coding card shows "Corti 7-step: Synthesize → Extract → Search →
  Assign → Validate → Identify Gaps → Review"

### Step 6 — Open Medical Coding Agent ✅
- Clicked "使用智能体" button on Medical Coding Agent card
- URL navigated to `/ai-studio/agents/aa02f049ae26/chat?preset=icoder%2Fmedical-coding-agent%402.0.0`
- (project_agent_id `aa02f049ae26` from Clone response)
- Page rendered AgentChatPage with breadcrumb "智能体 > Medical Coding Agent (Clone)"
- Right sidebar shows Settings/Code tabs (Settings active by default)

### Step 7 — Screenshot Agent Detail ✅
- **File:** `phase4_f_medical_coding_detail.png`
- Shows:
  - Breadcrumb with source attribution
  - Header: "Medical Coding Agent (Clone) v2.0.0" + description
  - Left: chat input area with system prompt pre-filled, "添加上下文"
    button, "0 字符 · ⌘+↵" hint
  - Right: Settings tab with Name field, System prompt editor (full Corti
    7-step prompt), Experts area (CO=coding-expert), Pinned parts area

### Step 8 — Input T12 demo case ✅
- Typed: `患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。`
- Character counter updated: "29 字符 · ⌘+↵"

### Step 9 — Run (Ctrl+Enter) ✅
- Pressed Ctrl+Enter (plain Enter didn't submit)
- Message sent to chat; user bubble appeared with T12 text
- Below user bubble: "运行中…" (running) status indicator
- Chat input disabled during run

### Step 10 — Confirm <15s ❌ FAILED (G001 blocker)
- After 60s: status changed to "运行失败 / timeout of 60000ms exceeded"
- **Files:** `phase4_f_medical_coding_run_failed.png` + `phase4_f_run_failed_state.png`

**Root cause:** Chat page calls A2A endpoint
`/api/icoder/agents/medical-coding-agent/v1/message:send` (via
`runtimeApi.ts` `sendMessage()`), which routes through `InboundHandler` →
full MedCodER 5-stage pipeline (Extraction → Retrieval → Merge →
Re-rank → Compliance). Real DeepSeek + BGE-M3 + FAISS = 60s+ on T12 case.

**Why F4 smoke tests pass:** F4 uses the unified endpoint
`POST /api/v1/agents/{id}/run` which routes medical-coding fast path
to `CodingRuntimeDispatcher` (G001 fast path, ~9-10s). The chat page UI
doesn't use the unified endpoint yet — that's the G001 chat UI wiring
follow-up.

**Verification that unified endpoint works:**
```bash
cd backend
python -m pytest tests/test_api/test_phase4f_smoke.py -v
# Result: 4/4 PASS in 15.07s (mock LLM gateway)
```

### Step 11 — Settings tab screenshot ✅
- **File:** `phase4_f_settings_tab.png`
- Shows:
  - Name field: "Medical Coding Agent (Clone)" (28/50)
  - System prompt editor: full Corti 7-step workflow prompt
  - Experts: "CO = coding-expert" avatar + Browse + Add buttons (disabled)
  - Pinned parts: "无固定消息片段" empty state

### Step 12 — Code tab screenshot ✅
- Clicked "Code" tab in right sidebar
- 3 tabs visible: **JavaScript (SDK)** / **curl** / **JSON 配置**
- Clicked curl tab
- Content: `curl -X POST "http://localhost:3000/api/v1/agents/aa02f049ae26/run" -H "Authorization: Bearer $ICODER_API_KEY" -H "Content-Type: application/json" -d '{ "input": {"text": "Your input here"}, "include_trace": true, "include_evidence": true }'`
- **File:** `phase4_f_code_tab.png`

**Verification:** JS + curl + JSON tabs present. C# absent (per prompt
§7.4). Python SDK tab missing — CodeSnippet.tsx supports it but
AgentConfigSidebar doesn't pass `python` prop.

### Step 13 — Event Inspector / RunTrace ⚠️ DEFERRED
- Could not verify live Event Inspector — requires successful run
- RunTrace component is wired in AgentDetailPage and renders `trace_events`
  from unified endpoint response
- G001 blocker prevented successful run through chat UI

### Step 14 — Copy JSON ⚠️ DEFERRED
- Copy JSON button is wired in AgentChatPage output header (Phase 4-F F3)
- Clipboard content verification requires successful run
- G001 blocker prevented verification

### Step 15 — Copy Markdown ⚠️ DEFERRED
- Copy Markdown button is wired in AgentChatPage output header (Phase 4-F F3)
- Same blocker as Step 14

### Step 16 — Coding Evidence Agent detail screenshot ✅
- Navigated back to `/ai-studio/agents`
- Switched to iCoDer built tab
- Clicked "使用智能体" on Coding Evidence Agent card
- URL: `/ai-studio/agents/92fdf1736186/chat?preset=icoder%2Fevidence-extractor%401.0.0`
- **File:** `phase4_f_coding_evidence_detail.png`
- (Live run skipped — same G001 A2A blocker would apply)

### Step 17 — Principal Diagnosis Review Agent detail screenshot ✅
- Navigated back to `/ai-studio/agents`
- Switched to iCoDer built tab
- Clicked "使用智能体" on Principal Dx Review card
- URL: `/ai-studio/agents/80f9cbb89eba/chat?preset=icoder%2Fprincipal-diagnosis-review%401.0.0`
- **File:** `phase4_f_principal_dx_detail.png`

### Step 18-21 — DRG/DIP Risk Review Agent detail screenshot ✅
- Navigated back to `/ai-studio/agents`
- Switched to iCoDer built tab
- Clicked "使用智能体" on DRG/DIP Risk Review card
- URL: `/ai-studio/agents/23b99e0e6bf1/chat?preset=icoder%2Fdrg-analyzer%401.0.0`
- **File:** `phase4_f_drg_dip_detail.png`

(Live runs for steps 16-21 skipped — all would hit the same G001 A2A
blocker. F4 smoke tests prove the unified endpoint works for all 4 P0
agents under mock gateway.)

---

## Issues found + midway fixes

### Issue 1 — Login 401
- **Symptom:** First login attempt with demo/demo1234 returned 401 "Invalid
  credentials"
- **Fix:** User logged in themselves (per their message "登录了")

### Issue 2 — Chrome debugging port ECONNREFUSED
- **Symptom:** Playwright MCP initially failed with ECONNREFUSED 127.0.0.1:9222
- **Fix:** Launched Chrome manually with `--remote-debugging-port=9222
  --user-data-dir=...`

### Issue 3 — Screenshot path "outside allowed roots"
- **Symptom:** Initial attempt with relative path failed
- **Fix:** Used absolute path `E:/Corti4C/docs/...`

### Issue 4 — Vite port mismatch
- **Symptom:** Plan said vite runs on port 3002; actual port was 3000
- **Fix:** Used http://localhost:3000 throughout

### Issue 5 — Enter key didn't submit
- **Symptom:** Plain Enter (from `browser_type` with `submit:true`) didn't
  submit chat message
- **Fix:** Pressed Ctrl+Enter (matches Corti pattern + the "⌘+↵" hint)

### Issue 6 — G001 chat page 60s timeout
- **Symptom:** Medical Coding Agent run from chat UI shows "运行中…"
  for 60s then "运行失败 / timeout of 60000ms exceeded"
- **Root cause:** Chat page routes through A2A endpoint → MedCodER 5-stage
- **Mitigation:** F4 smoke tests via unified endpoint prove G001 fast path
  works (~9-10s expected with real DeepSeek, 3s under mock)
- **Follow-up:** Wire AgentChatPage to call unified endpoint for
  medical-coding fast path (P0 backlog item)

---

## Final state

- **Screenshots captured:** 10 files in `docs/corti_parity/phase4_f_prebuilt_agents/screenshots/`
- **Successful runs:** 0 (G001 blocker prevented chat UI live runs)
- **Failed runs:** 1 (Medical Coding through chat UI, 60s timeout)
- **Unified endpoint tests:** 4/4 PASS (F4 smoke tests, 15.07s under mock)
- **Page state at walkthrough end:** Medical Coding Agent chat page with
  failure message; Settings/Code tabs verified functional

---

## Screenshot inventory

| File | Step | Content |
|---|---|---|
| `phase4_f_agents_list.png` | 5 | My Agents tab (default) |
| `phase4_f_icoder_built_tab.png` | 5 | iCoDer built tab (14 cards) |
| `phase4_f_medical_coding_detail.png` | 7 | Medical Coding chat page initial state |
| `phase4_f_medical_coding_run_failed.png` | 10 | Run failed state (60s timeout) |
| `phase4_f_run_failed_state.png` | 10 | Close-up of failure message |
| `phase4_f_settings_tab.png` | 11 | Settings tab (name + system prompt + experts) |
| `phase4_f_code_tab.png` | 12 | Code tab (curl selected, unified endpoint URL) |
| `phase4_f_coding_evidence_detail.png` | 16 | Coding Evidence Agent chat page |
| `phase4_f_principal_dx_detail.png` | 17 | Principal Dx Review chat page |
| `phase4_f_drg_dip_detail.png` | 18-21 | DRG/DIP Risk Review chat page |

---

**Walkthrough log end.**
