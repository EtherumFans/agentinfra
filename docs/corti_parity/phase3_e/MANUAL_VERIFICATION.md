# Phase 3-E — Manual Verification Checklist

**Status:** Deferred (自动化验证已 PASS, 浏览器走查待用户执行)
**Date:** 2026-07-07

---

## 1. 启动 dev servers

```bash
# Terminal 1 — backend
cd backend && python -m uvicorn app.main:app --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

预期:
- backend 启动日志末尾出现 `boot ok` (来自 Phase 3-E T5 验证)
- frontend Vite dev server 启动, 默认 http://localhost:5173 或 3000

---

## 2. 验证 Agent 中文名 (T1)

打开 `http://localhost:5173/ai-studio/agents` (或 `/agents`)。

**预期:** Hub 列出的 16 个 Agent 全部显示中文名 + 智能体后缀:

| agent_id (URL/API) | 显示名 |
|--------------------|--------|
| medical-coding-agent | 医学编码智能体 |
| code-validation-agent | 编码校验智能体 |
| compliance-guardrail-agent | 合规护栏智能体 |
| note-completeness-agent | 病历完整性智能体 |
| cdi-review-agent | CDI 审核智能体 |
| code-reconciler-agent | 编码核对智能体 |
| denial-appeals-agent | 拒付申诉智能体 |
| diagnosis-extractor-agent | 诊断提取智能体 |
| documentation-gap-agent | 病历缺口智能体 |
| drg-analyzer-agent | DRG 分析智能体 |
| evidence-ranker-agent | 证据排序智能体 |
| evidence-extractor-agent | 证据提取智能体 |
| index-navigator-agent | 索引导航智能体 |
| medcoder-coding-review-agent | MedCodER 编码审核智能体 |
| procedure-extractor-agent | 手术提取智能体 |
| tabular-validator-agent | 表格校验智能体 |

切 locale 到 en-US (右上角 globe icon) → Agent 名仍为中文 (因为来自 API, 是已知行为)。

---

## 3. 验证页面 i18n (T3)

逐页打开, 检查 chrome 文案随 locale 切换:

| 页面 | URL | zh-CN 关键文案 | en-US 关键文案 |
|------|-----|----------------|-----------------|
| AI Studio Overview | `/ai-studio` | "AI 智能体" / "管理、创建和市场发现 Agent" | "AI Agents" / "Manage, create, and discover Agents in the marketplace" |
| API Clients | `/api-clients` | "API 客户端" / "创建 OAuth 客户端" | "API Clients" / "Create OAuth client" |
| Release Notes | `/release-notes` | "Release Notes" / "iCoDer 医疗 AI 智能体平台版本变更记录。" | "Release Notes" / "iCoDer medical AI agent platform version change log." |
| Reset Password | `/reset-password?token=xxx` | "重置密码" / "新密码" | "Reset Password" / "New password" |
| Agent Chat | `/agents/{id}/chat?preset=icoder/medical-coding-agent@2.0.0` | "输入" / "运行" / "运行结果" | "Input" / "Run" / "Run result" |
| RunTrace | `/runs/{run_id}/trace` | "1. 用户消息接收" / "统一工具调度器 / Dispatcher" | "1. User message received" / "Unified Tool Dispatcher" |

---

## 4. 验证组件 i18n (T4)

逐组件触发, 检查 chrome 文案随 locale 切换:

| 组件 | 触发位置 | zh-CN | en-US |
|------|----------|-------|-------|
| WorkbenchLayout | AI Studio 工具页 (Transcribe / Document / Chat / Code) | "Input" / "Output" / "Settings" / "Event Inspector" | (相同, 都是英文字符串 zh=en) |
| OrgSwitcher | 顶栏 org 切换器 (无 org 时) | "No Organization" / "Select Org" | (相同) |
| EditSystemPromptModal | Agent 详情页 → Settings → Edit system prompt | "Edit system prompt" / "Save" / "Cancel" | (相同) |
| ToolSelector | Agent 详情页 → Tools tab | "Available Tools" / "Search tools..." / 分类名 "安全护栏" 等 | "Available Tools" / "Search tools..." / "Safety" 等 |
| EventInspector | AI Studio 工具页底部 | "Event Inspector" / "Credits consumed" | (相同) |
| ErrorBoundary | 故意触发组件异常 (e.g. 删一个 prop) | "加载失败" / "重试" | "Load failed" / "Retry" |
| SettingsCodeTab | AI Studio 工具页右栏 | "Settings" / "Code" / "Tools" | (相同) |
| CodeSnippet | Developer Quickstart 页 | "JavaScript (SDK)" / "Python (SDK)" / "JSON Config" | (相同) |
| TopKChips | Medical Coding 工作台 → 无候选时 | "No candidates" | (相同) |
| A2ACollaboration | Agent 详情页右下 | "A2A Agent 协作" / "个可用" | "A2A Agent Collaboration" / "available" |

---

## 5. 验证 Dispatcher Detail 增强 (T6)

### 5.1 跑 medical-coding-agent

在 Medical Coding 工作台 (`/ai-studio/medical-coding`) 输入病历文本 → 点击运行。

### 5.2 进入 RunTrace

运行完成后, 在 Agent Chat 页或运行结果区点击 "View RunTrace" 链接, 跳到 `/runs/{run_id}/trace`。

### 5.3 检查时间线分段

预期时间线分 3 段:

1. **pre-dispatcher** — 灰色边框, 含 `1. 用户消息接收` / `2. Planner 选定 Expert`
2. **dispatcher** — 蓝色 group header "统一工具调度器 / Dispatcher" + 蓝色边框 4 步:
   - `3. 工具列表` (Search 图标)
   - `4. 鉴权完成` (Key 图标)
   - `5. Scope 校验` (Shield 图标)
   - `6. 工具调用` (Wrench 图标)
3. **post-dispatcher** — 灰色边框, 含 `7. Expert 响应` / `8. 输出生成` / `9. 完成`

### 5.4 检查 dispatcher 详情展开

点击 `4. 鉴权完成` 行 → 展开后应显示:

- **dispatcher detail** 区 (蓝色 "DISPATCHER DETAIL" 标签):
  - `tool_name:` (字体 + 蓝色高亮) — 例如 `medical_coding_run` 或 `coding_validate`
  - `auth_type:` — `bearer` 或 `in-process` (后者带 "⚠ in-process bypass" 黄色提示)
  - `redacted_view:` — PHI 脱敏后的 view 名
  - `granted_scopes:` — 绿色 chips, 例如 `api:read` / `api:write`
  - 可选 `note:` — 黄色斜体说明
- **raw safe_metadata** 区 (灰色 "RAW SAFE_METADATA" 标签):
  - JSON 视图, 但只包含 `tool_name / auth_type / redacted_view / granted_scopes / note / mcp_error_code` 字段 (纵深防御)

点击 `6. 工具调用` 行 → 展开后应显示:

- `tool_name:` (蓝色高亮)
- `handler_ref:` (代码片段样式, 例如 `medcoder_runtime.medical_coding.coding_engine.CodingEngineAdapter.infer_async`)
- 可选 `stage:` chip
- `arguments (N keys, M chars, validated ✓):` + key 列表 chips

点击 `9. 完成` 行 → 展开后应显示:

- 成功路径: `result: <ResultType>` (绿色) + `(N keys: key1, key2, ...)` + `M chars`
- 失败路径: `error: <msg>` (红色) + `mcp_error_code: -32007` (红色)
- `total_dispatch: 123.4ms (auth+scope+resolve+handler)` — 整个 dispatch_tool 调用周期

### 5.5 切 locale 到 en-US

预期:
- 9 个 step labels 切英文 (e.g. "1. User message received")
- "DISPATCHER DETAIL" / "RAW SAFE_METADATA" 标签保持英文 (本来就是英文)
- group header 切 "Unified Tool Dispatcher"
- 字段名 (tool_name / auth_type / ...) 保持原样 (技术术语)
- intro 段切英文

---

## 6. 验证 backend boot assertion

```bash
cd backend && python -c "from app.main import app; print('boot ok')"
```

预期末行: `boot ok`。中间日志应包含:
- `MCP context_id middleware installed at module load time`
- `TenantHeaderMiddleware installed at module load time`
- `Loaded 33304 ICD-10-CN codes from knowledge base`
- `Loaded 23165 ICD-9-CM-3 codes from knowledge base`
- `STT ffmpeg configured via imageio-ffmpeg: ...`

不应出现 `assert_tool_registry_matches_agent_pack` 失败 (medcoder-coding-review pack 的 subset-match 应通过)。

---

## 7. 自动化测试 (Phase 3-E T5 已 PASS)

```bash
# Frontend
cd frontend && npx tsc --noEmit                              # 0 errors
cd frontend && npx vitest run src/i18n/locales.test.ts       # 9/9 pass

# Backend
cd backend && python -c "from app.main import app; print('boot ok')"   # boot ok
cd backend && python -m pytest tests/integration/icoder/test_phase3b1_agent_hub.py tests/integration/icoder/test_phase3b0_agent_inventory.py tests/unit/icoder/test_markdown_generator.py -v   # 37/37 pass
```

---

## 8. 截图清单 (可选)

如需归档:

- `docs/corti_parity/phase3_e/screenshots/agents_hub_zh.png` — Agent Hub 16 中文名
- `docs/corti_parity/phase3_e/screenshots/agents_hub_en.png` — en-US locale (Agent 名仍中文)
- `docs/corti_parity/phase3_e/screenshots/runtrace_dispatcher_zh.png` — RunTrace dispatcher 4 步 + 蓝色 group header
- `docs/corti_parity/phase3_e/screenshots/runtrace_auth_resolved_detail_zh.png` — auth_resolved 展开 (dispatcher detail + raw safe_metadata)
- `docs/corti_parity/phase3_e/screenshots/runtrace_tools_call_detail_zh.png` — tools_call 展开 (arguments summary)
- `docs/corti_parity/phase3_e/screenshots/runtrace_completion_detail_zh.png` — completion 展开 (result summary + total_dispatch)
- `docs/corti_parity/phase3_e/screenshots/runtrace_dispatcher_en.png` — en-US locale 切换
