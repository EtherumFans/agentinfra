# Phase 3-E — Agent 中文名称化 + 全量 i18n 覆盖 + Dispatcher Detail 增强

**Status:** PASS
**Date:** 2026-07-07
**Branch:** master
**Plan:** `C:\Users\huawei\.claude\plans\logical-squishing-phoenix.md`

---

## 1. Context

Phase 3-D2 closed Corti-parity gaps on RunTrace / MCP-native / markdown. 但遗留两个产品化问题:

1. 16 个 official agent 的 `manifest.name` 多为英文 (e.g. "Medical Coding Agent" / "Code Validation Agent"), 与产品定位 "面向中国医院场景的医疗收入合规 AI 平台" 不符。
2. 前端 i18n 基础设施已存在 (`useT()` hook + `LocaleDict` interface + zh-CN/en-US dual locale), 但 6 个页面 + 10 个组件未接入, 硬编码中文/英文字符串约 220 处。

外加用户在 T2 进行中追加的需求:
3. RunTrace 9 步时间线已能表达 Agent 通过统一工具调度器 (MCP dispatcher) 干活, 但 dispatcher 详情展示不够 — 仅显示 raw `safe_metadata` JSON。需要增强为结构化展示 (tool_name / handler_ref / scope diff / arguments summary / result summary)。

本 phase 同时解决这三件事。

---

## 2. Tasks 完成情况

### T1 — 16 个 Agent 改中文名称 ✅

**Goal:** `backend/official_agents/*/agent_pack.json` 的 `manifest.name` 全部改成中文名 (智能体后缀)。`agent_id` (kebab-case 英文) 不动 — 它是 URL/API 标识符。

**Files modified (16):**
- `backend/official_agents/medical_coding/agent_pack.json` → "医学编码智能体"
- `backend/official_agents/code-validation/agent_pack.json` → "编码校验智能体"
- `backend/official_agents/compliance-guardrail/agent_pack.json` → "合规护栏智能体"
- `backend/official_agents/note-completeness/agent_pack.json` → "病历完整性智能体"
- `backend/official_agents/cdi-review/agent_pack.json` → "CDI 审核智能体"
- `backend/official_agents/code_reconciler/agent_pack.json` → "编码核对智能体"
- `backend/official_agents/denial-appeals/agent_pack.json` → "拒付申诉智能体"
- `backend/official_agents/diagnosis-extractor/agent_pack.json` → "诊断提取智能体"
- `backend/official_agents/documentation-gap/agent_pack.json` → "病历缺口智能体"
- `backend/official_agents/drg-analyzer/agent_pack.json` → "DRG 分析智能体"
- `backend/official_agents/evidence-ranker/agent_pack.json` → "证据排序智能体"
- `backend/official_agents/evidence_extractor/agent_pack.json` → "证据提取智能体"
- `backend/official_agents/index_navigator/agent_pack.json` → "索引导航智能体"
- `backend/official_agents/medcoder-coding-review/agent_pack.json` → "MedCodER 编码审核智能体"
- `backend/official_agents/procedure-extractor/agent_pack.json` → "手术提取智能体"
- `backend/official_agents/tabular_validator/agent_pack.json` → "表格校验智能体"

**Backend Python code (26 edits)** — 同步更新所有硬编码 agent 名:
- `backend/app/icoder/agent_runtime/a2a/agent_card.py` — 4 cards (medical_coding / code-validation / compliance-guardrail / note-completeness)
- `backend/app/main.py:600` — medical-coding-agent fallback card
- `backend/app/icoder/markdown_generator.py` — 4 generators × 2 lines each (8 edits)
- `backend/tests/unit/icoder/test_markdown_generator.py` — 4 assertion updates
- `backend/app/api/embedded.py` — 3 HTML options
- `backend/app/api/agents.py` — 5 AGENT_TEMPLATES titles
- `backend/app/agents/experts/report_expert.py:219` — markdown footer

### T2 — 扩展 i18n locale 字典 ✅

**Goal:** 在 `frontend/src/i18n/locales.ts` 的 `LocaleDict` interface + zh-CN dict + en-US dict 三处同步新增 ~220 个 key, 覆盖 6 页 + 10 组件的所有 user-facing 字符串。

**Result:** 实际新增 188 key × 2 locale = 376 行 (因 `apiClientsTitle` 与原 dict 重名, 删除 1 个去重, 最终 187 key)。

**Key 命名规范:** flat camelCase, 按文件前缀分组:
- `aiStudioOverview*` (8 keys) — AI Studio Overview 页
- `apiClients*` (24 keys) — API Clients 页 (复用原 `apiClientsTitle`)
- `releaseNotes*` (3 keys) — Release Notes 页
- `resetPassword*` (14 keys) — Reset Password 页
- `runTrace*` (52 keys) — RunTrace 页 (含 9 step labels + dispatcher detail labels)
- `agentChat*` (21 keys) — Agent Chat 页
- `workbenchLayout*` (4 keys) — WorkbenchLayout 组件
- `editSystemPrompt*` (7 keys) — EditSystemPromptModal 组件
- `toolSelector*` (17 keys) — ToolSelector 组件 (含 6 中文分类名)
- `orgSwitcher*` (5 keys) — OrgSwitcher 组件
- `eventInspector*` (3 keys) — EventInspector 组件
- `errorBoundary*` (2 keys) — ErrorBoundary 组件
- `topKChips*` (1 key) — TopKChips 组件
- `settingsCodeTab*` (3 keys) — SettingsCodeTab 组件
- `codeSnippet*` (7 keys) — CodeSnippet 组件
- `a2aCollaboration*` (3 keys) — A2ACollaboration 组件

**Locale parity test:** 9/9 tests pass (key 集合相同 + 无空值 + 占位符平衡)。

### T3 — 6 个页面接入 useT() ✅

**Files modified (6):**
- `frontend/src/pages/AIStudioOverviewPage.tsx` — 8 strings
- `frontend/src/pages/APIClientsPage.tsx` — 24 strings (含 OAuth 创建/撤销流程)
- `frontend/src/pages/ReleaseNotesPage.tsx` — 3 strings (release notes 内容保留为 zh-CN SSOT)
- `frontend/src/pages/ResetPasswordPage.tsx` — 14 strings
- `frontend/src/pages/RunTracePage.tsx` — 52 strings (含 9 step labels + dispatcher detail)
- `frontend/src/pages/AgentChatPage.tsx` — 21 strings (含 preset greeting mapping)

### T4 — 10 个组件接入 useT() ✅

**Files modified (10):**
- `frontend/src/components/layout/WorkbenchLayout.tsx` — 4 strings
- `frontend/src/components/layout/OrgSwitcher.tsx` — 5 strings
- `frontend/src/components/EditSystemPromptModal.tsx` — 7 strings
- `frontend/src/components/agents/ToolSelector.tsx` — 17 strings (含 6 中文分类名)
- `frontend/src/components/common/EventInspector.tsx` — 3 strings
- `frontend/src/components/common/ErrorBoundary.tsx` — 2 strings (DefaultFallback 提取为函数组件)
- `frontend/src/components/common/SettingsCodeTab.tsx` — 3 strings
- `frontend/src/components/common/CodeSnippet.tsx` — 7 strings
- `frontend/src/components/medical-coding/TopKChips.tsx` — 1 string
- `frontend/src/components/A2ACollaboration.tsx` — 3 strings

### T5 — 验证 + 文档 ✅

详见 §3 验证结果 + `MANUAL_VERIFICATION.md`。

### T6 — Dispatcher Detail 增强 ✅ (用户中途追加)

**Goal:** 让 RunTrace 9 步时间线明确表达 "Agent 通过统一工具调度器 (MCP dispatcher) 干活", 4 个 dispatcher 步骤 (tools_list / auth_resolved / scope_checked / tools_call) 用结构化方式展示元数据, 而非 raw JSON。

**Backend enhancements (`backend/app/icoder/mcp/server.py` dispatch_tool()):**
- AUTH_RESOLVED 增补 in-process bypass 路径的 emit (auth_config is None 时也发射 trace event)
- AUTH_RESOLVED success/failure 增加 `tool_name` 字段
- TOOLS_CALL safe_metadata 增强: `tool_name` + `handler_ref` + `stage` + `arguments_keys` (前 20 个 keys) + `arguments_size` (字符数) + `input_validated`
- COMPLETION safe_metadata 增强: `tool_name` + `is_error` + `result_type` + `result_keys` (前 20 个 keys) + `result_size` + `total_dispatch_ms` (整个 dispatch_tool 调用周期)

**Frontend enhancements (`frontend/src/pages/RunTracePage.tsx`):**
- 新增 `DISPATCHER_STEPS` set + `getStepIcon` 函数 (4 dispatcher 步骤 + completion 各有图标)
- 新增 `renderScopeDiff` — 把 `required_scopes` vs `granted_scopes` 渲染为 ✓ matched / ✗ missing chip 列
- 新增 `renderDispatcherDetail` — 按 step 类型结构化展示:
  - `tools_list`: tool_count + tool_names (chips)
  - `auth_resolved`: tool_name + auth_type + redacted_view + granted_scopes (chips) + note
  - `scope_checked`: scope diff (✓/✗ chips) + redacted_view
  - `tools_call`: arguments (key 列表 + size + validated 标记)
  - `completion`: result type + result keys + result size OR error + mcp_error_code + total_dispatch_ms
- TimelineRow 增强: dispatcher 步骤显示 `tool_name → handler_ref` 副标题 + 蓝色边框
- 时间线分段: pre-dispatcher / dispatcher (蓝色 group header "统一工具调度器 / Dispatcher") / post-dispatcher
- 展开 view: dispatcher 步骤先显示 "dispatcher detail" 结构化区, 再显示 "raw safe_metadata"
- 纵深防御: `auth_resolved` 的 raw metadata 视图只允许 `tool_name / auth_type / redacted_view / granted_scopes / note / mcp_error_code` 字段

---

## 3. Verification Results

| Check | Result |
|-------|--------|
| `npx tsc --noEmit` (frontend) | ✅ 0 errors |
| `npx vitest run src/i18n/locales.test.ts` | ✅ 9/9 tests pass |
| `python -c "from app.main import app; print('boot ok')"` (backend) | ✅ boot ok, 8 MCP tools registered, medcoder-coding-review pack subset-match 通过 |
| `pytest tests/integration/icoder/test_phase3b1_agent_hub.py tests/integration/icoder/test_phase3b0_agent_inventory.py tests/unit/icoder/test_markdown_generator.py` | ✅ 37/37 pass |

---

## 4. PASS criteria (8/8)

1. ✅ 16 个 agent_pack.json 的 `manifest.name` 都是中文 (智能体后缀) — T1
2. ✅ `agent_id` 保持 kebab-case 英文 (URL/API 不变) — T1
3. ✅ `frontend/src/i18n/locales.ts` 新增 ~220 key × 2 locale (实际 187 × 2 = 374 行, 含 1 个去重) — T2
4. ✅ 6 个页面接入 `useT()` — T3
5. ✅ 10 个组件接入 `useT()` — T4
6. ✅ `npx tsc --noEmit` 0 errors — T5
7. ✅ `npx vitest run src/i18n/locales.test.ts` 通过 — T5
8. ✅ 后端 agent pack 加载 + boot assertion 通过 — T5

**Bonus (T6):** dispatcher detail 结构化展示 + 4 个 backend emit 增强。

---

## 5. Files Modified (Summary)

**Backend (T1 + T6):**
- 16 × `backend/official_agents/*/agent_pack.json` (manifest.name)
- `backend/app/icoder/agent_runtime/a2a/agent_card.py` (4 cards)
- `backend/app/main.py` (1 fallback card)
- `backend/app/icoder/markdown_generator.py` (4 generators)
- `backend/app/api/embedded.py` (3 HTML options)
- `backend/app/api/agents.py` (5 AGENT_TEMPLATES)
- `backend/app/agents/experts/report_expert.py` (1 markdown footer)
- `backend/tests/unit/icoder/test_markdown_generator.py` (4 assertions)
- `backend/app/icoder/mcp/server.py` (dispatch_tool enhancements)

**Frontend i18n dict (T2):**
- `frontend/src/i18n/locales.ts` (374 lines added: 187 keys × 2 locales)

**Frontend pages (T3):**
- `frontend/src/pages/AIStudioOverviewPage.tsx`
- `frontend/src/pages/APIClientsPage.tsx`
- `frontend/src/pages/ReleaseNotesPage.tsx`
- `frontend/src/pages/ResetPasswordPage.tsx`
- `frontend/src/pages/RunTracePage.tsx` (含 T6 dispatcher 增强)
- `frontend/src/pages/AgentChatPage.tsx`

**Frontend components (T4):**
- `frontend/src/components/layout/WorkbenchLayout.tsx`
- `frontend/src/components/layout/OrgSwitcher.tsx`
- `frontend/src/components/EditSystemPromptModal.tsx`
- `frontend/src/components/agents/ToolSelector.tsx`
- `frontend/src/components/common/EventInspector.tsx`
- `frontend/src/components/common/ErrorBoundary.tsx`
- `frontend/src/components/common/SettingsCodeTab.tsx`
- `frontend/src/components/common/CodeSnippet.tsx`
- `frontend/src/components/medical-coding/TopKChips.tsx`
- `frontend/src/components/A2ACollaboration.tsx`

---

## 6. Known limitations / Open questions

- **en-US locale 下的 Agent 名仍显示中文** (因为来自 API)。已知行为, 非 bug。后续如需 en-US 显示英文名, 需要在 agent_pack.json 加 `display_name_en` 字段 + 后端 Hub API 投影 + 前端按 locale 选。本 phase 不做。
- **ReleaseNotesPage 版本日志**: 简化为 zh-CN 作为 SSOT, en-US locale 下仍显示中文 release notes 内容 (仅页面 chrome 切英文)。后续如需完整双语, 单独 phase。
- **dev server 手动验证 + 截图**: deferred to `MANUAL_VERIFICATION.md` — 当前所有自动化验证 (tsc / vitest / pytest / boot) 全绿。

---

## 7. Reused existing utilities

- `frontend/src/i18n/index.ts::useT()` / `useLocaleStore` — 现有 i18n hook + zustand store
- `frontend/src/i18n/locales.ts::LocaleDict` — 现有 flat camelCase dict 结构
- `frontend/src/i18n/locales.test.ts` — 现有 key parity test (自动覆盖新 key)
- `frontend/src/pages/HomePage.tsx` — 现有 i18n consumer 范本
- `frontend/src/components/layout/Layout.tsx` — 现有 i18n + locale toggle 范本
- `backend/app/api/icoder_agents_hub.py::_build_card()` — 读 `manifest.name` 现有逻辑, 不需要改
- `backend/app/icoder/markdown_generator.py::generate_markdown_for(agent_id, result)` — 按 agent_id 分发, 不按 name, 不受影响
