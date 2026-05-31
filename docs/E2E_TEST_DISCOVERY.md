# E2E Test Discovery — iCoDer Medical Coding Agent

> 项目侦察报告：完整盘点所有页面、API、业务对象、Auth 体系、错误处理模式。
> 生成日期：2026-05-10

---

## 1. 系统架构概览

```
浏览器 (React SPA, port 3000)
  │
  ├─ /api/* ──→ Vite proxy ──→ FastAPI (port 8001)
  │                              ├─ JWT auth (access + refresh token)
  │                              ├─ Rate limit: 100 req/min/IP
  │                              ├─ SQLite (aiosqlite, async)
  │                              └─ DeepSeek LLM
  ├─ /ws/*  ──→ WebSocket (STT, Agent streaming)
  └─ 状态管理: Zustand + localStorage persist
```

---

## 2. 路由与页面清单 (24 pages)

### 2.1 公开页面 (无需登录)

| 路由 | 页面 | 功能 |
|------|------|------|
| `/login` | LoginPage | 用户名+密码登录；错误提示；隐私/服务条款链接 |

### 2.2 受保护页面 (ProtectedRoute 包裹)

所有以下页面需要 `isAuthenticated === true`。通过 `<Navigate to="/login" replace />` 拦截未认证访问。

| # | 路由 | 页面 | 核心业务对象 | CRUD |
|---|------|------|-------------|------|
| 1 | `/` | HomePage | — | — |
| 2 | `/developer-quickstart` | DeveloperQuickstartPage | OAuth Client | R |
| 3 | `/ai-studio` | AIStudioOverviewPage | — | — |
| 4 | `/ai-studio/agents` | AgentsPage | Agent, Expert | R (通过API) |
| 5 | `/ai-studio/speech-to-text` | SpeechToTextPage | — | — |
| 6 | `/ai-studio/text-generation` | TextGenerationPage | 文书模板 | CRUD (localStorage) |
| 7 | `/ai-studio/embedded-assistant` | EmbeddedAssistantPage | — | — |
| 8 | `/ai-studio/fact-extraction` | FactExtractionPage | 临床事实 | R |
| 9 | `/ai-studio/medical-coding` | MedicalCodingPage | Encounter | CRUD |
| 10 | `/workbench/:encounterId?` | CodingWorkbenchPage | Encounter, Review | R, Create Review |
| 11 | `/review/:reviewId` | CaseReviewPage | Review, CodeCandidate | R, U (审核) |
| 12 | `/api-clients` | APIClientsPage | OAuth Client | CRUD |
| 13 | `/team` | TeamPage | TeamMember | R, U, D |
| 14 | `/billing` | BillingPage | Transaction | R |
| 15 | `/usage` | UsagePage | Usage stats | R |
| 16 | `/settings` | SettingsPage | Config, Agent | R |
| 17 | `/code-dictionaries` | CodeDictionariesPage | ICD code | R (搜索) |
| 18 | `/rule-libraries` | RuleLibrariesPage | Coding Rule | R |
| 19 | `/gold-cases` | GoldCasesPage | GoldCase | CRUD, CSV import/export |
| 20 | `/evaluation` | EvaluationPage | Evaluation | R (运行) |
| 21 | `/expert-library` | ExpertLibraryPage | Expert | CRUD |
| 22 | `/support` | SupportPage | — | — |
| 23 | `/tickets` | TicketsPage | — | — |

### 2.3 路由冲突警告

- **`/api-clients`** 路径前缀 `/api` 与 Vite proxy 的 `/api` → backend 规则冲突。
  当用户直接访问 `http://localhost:3000/api-clients` 时，Vite 将其代理到后端，
  React Router 无法加载，ProtectedRoute 重定向失效。
  **影响**: 未认证用户直接访问该 URL 不会被重定向到 `/login`（获得后端 404 而非前端重定向）。

---

## 3. 核心业务对象

### 3.1 Encounter (就诊/病历)

```
Model: backend/app/models/encounter.py
API:   /api/encounters (CRUD + text import)
Pages: CodingWorkbenchPage, MedicalCodingPage
```

| 操作 | 端点 | Auth |
|------|------|------|
| 列表 | GET /api/encounters?page=&page_size=&status= | get_current_user |
| 详情 | GET /api/encounters/{id} | get_current_user |
| 创建 | POST /api/encounters | get_current_user |
| 文本创建 | POST /api/encounters/text | get_current_user |
| 删除 | DELETE /api/encounters/{id} | get_current_user |

### 3.2 Review (编码审核)

```
Model: backend/app/models/review.py
API:   /api/reviews (create, list, get, review, complete, report)
Pages: CodingWorkbenchPage, CaseReviewPage
```

| 操作 | 端点 | 说明 |
|------|------|------|
| 创建审核 | POST /api/reviews | 触发完整编码管线 (9步) |
| 审核编码 | PUT /api/reviews/{id}/candidates/{cid}/review | 人工确认/拒绝/修改 |
| 完成审核 | PUT /api/reviews/{id}/complete | 标记审核完成 |
| 报告 | GET /api/reviews/{id}/report/markdown | 审核报告 |

### 3.3 GoldCase (金标准病例)

```
Model: backend/app/models/gold_case.py
API:   /api/gold-cases (CRUD)
Pages: GoldCasesPage, EvaluationPage
```

| 字段 | 类型 |
|------|------|
| case_id | 自动生成 (GOLD-xxxxxx) |
| department | 科室 |
| diagnosis_group | 诊断分组 |
| original_primary_diagnosis / gold_primary_diagnosis | 原始 vs 金标准编码 |
| difficulty | easy / medium / hard |
| agent_accuracy | 评估后填充 |
| full_case_data | JSON (完整 encounter 数据) |

### 3.4 Agent (智能体)

```
Model: backend/app/models/agent.py
API:   /api/agents (CRUD + stream + stats)
Pages: AgentsPage
```

| 特性 | 说明 |
|------|------|
| expert_ids | JSON array — Agent 可绑定多个 Expert |
| routing_strategy | single_expert / fixed_order / llm_plan |
| a2a_enabled | 是否注册为 A2A discoverable agent |
| usage_count | 调用计数器 |
| 执行 | POST /api/agents/{id}/run (同步) |
| 流式执行 | POST /api/agents/{id}/stream (SSE) |

### 3.5 Expert (专家)

```
Model: backend/app/models/expert.py
API:   /api/experts (CRUD + run + MCP servers + BYO)
Pages: ExpertLibraryPage
```

30 个预置 Expert，11 个类别：编码、医保、质控、文书、急诊、护理、药学、文献、计算、沟通。

### 3.6 其他业务对象

| 对象 | 端点 | CRUD |
|------|------|------|
| OAuth Client | /api/oauth/clients | CRUD (client_secret 仅创建时返回) |
| API Key | /api/keys | CRUD |
| Team Member | /api/team/members | R, U (role), D |
| Transaction | /api/billing/transactions | R |
| Coding Rule | /api/rules | R (检索 + 验证) |
| ICD Code | /api/codes | R (搜索 + 浏览 + 验证) |

---

## 4. 认证与授权体系

### 4.1 Auth 架构

```
JWT (access_token 15min + refresh_token 7d)
  ├─ 前端: localStorage 存储 token
  ├─ 前端: Zustand persist (icoder-auth key) 存储 user + isAuthenticated
  ├─ 前端: axios interceptor 自动附加 Bearer token
  ├─ 前端: 401 → 自动 refresh → 失败则清空 state 重定向 /login
  └─ 后端: HTTPBearer → get_current_user → get_admin_user (角色门控)
```

### 4.2 用户角色 (7 种)

| 角色 | 枚举值 | 说明 |
|------|--------|------|
| admin | ADMIN | 系统管理员 |
| coder | CODER | 编码员 (默认) |
| dept_head | DEPT_HEAD | 科室负责人 |
| insurance | INSURANCE | 医保办 |
| qc | QC | 质控科 |
| clinician | CLINICIAN | 临床医生 |
| it | IT | 信息科 |

### 4.3 权限控制现状

- **认证层面**: 几乎所有非公开端点需要 `get_current_user`
- **角色门控**: `get_admin_user` 用于管理员专属操作
- **前端门控**: `ProtectedRoute` 组件检查 `isAuthenticated`
- **已知缺陷**: 前端无角色级 UI 控制 (所有角色看到相同界面)

### 4.4 Auth 相关端点

| 端点 | 方法 | Auth | 说明 |
|------|------|------|------|
| /api/auth/login | POST | Public | 返回 access_token + refresh_token |
| /api/auth/register | POST | Public | 注册新用户 |
| /api/auth/refresh | POST | Public | 刷新 access_token |
| /api/auth/me | GET | Protected | 当前用户信息 |

---

## 5. 错误处理模式

### 5.1 前端错误处理

| 层级 | 机制 | 位置 |
|------|------|------|
| 全局 | axios response interceptor | api.ts:23-46 |
| 401 | 自动 refresh → 失败则清空 + redirect | api.ts:26-42 |
| 页面级 | try/catch → setError() → UI red banner | CodingWorkbenchPage:49-56 |
| 页面级 | .catch(() => {}) 吞没 | 多处 (fire-and-forget) |
| 网络失败 | 无全局处理 (浏览器默认) | — |
| Error Boundary | 不存在 | — |

### 5.2 后端错误处理

| 机制 | 位置 |
|------|------|
| Global exception handler → 500 JSON | main.py:70-76 |
| HTTPException (401/403/404/422) | 各 API 端点 |
| Rate limit → 429 | rate_limit.py:32 |
| 调试模式错误详情 | main.py:75 (DEBUG flag) |

### 5.3 错误 UI 模式

- **LoginPage**: 红色 banner (`.bg-red-50`) 显示错误文本
- **CodingWorkbenchPage**: 红色 badge (`.badge-error`) 显示 `error` state
- **CaseReviewPage**: `console.error` 仅日志（无用户提示）
- **多处**: `.catch(() => {})` 静默吞没

---

## 6. 表单与输入校验

| 页面 | 校验方式 | 校验内容 |
|------|---------|---------|
| LoginPage | HTML5 `required` + 状态 error | 非空用户名/密码；API 返回错误 |
| GoldCasesPage (create) | 无前端校验 | 依赖 API 返回错误 (但表单可能提交空白数据) |
| CodingWorkbenchPage | URL param + 条件渲染 | encounterId 存在性 |
| CaseReviewPage | 手动 check `reason.trim()` | 审核原因非空 |
| TeamPage (invite) | 无前端校验 | 邮箱格式 |
| APIClientsPage (create) | URLSearchParams | name, scopes, token_expires_seconds |
| ExpertLibraryPage (create) | 无前端校验 | name, description, system_prompt |
| TextGenerationPage (templates) | 无前端校验 | 依赖 localStorage |

---

## 7. 数据导出 / 下载

| 页面 | 功能 | 实现 |
|------|------|------|
| GoldCasesPage | CSV 导入 | FileReader + 手动解析 CSV → API create |
| GoldCasesPage | CSV 模板 | `navigator.clipboard.writeText()` + `alert()` |
| GoldCasesPage | CSV 导出 | **不存在** (仅有模板复制) |
| CodingWorkbenchPage | Export 按钮 | **无 onClick** (装饰性) |
| CaseReviewPage | Report Markdown | GET /api/reviews/{id}/report/markdown |

---

## 8. WebSocket 端点

| 路径 | 用途 |
|------|------|
| /ws/speech-to-text | 实时语音转文本 (FunASR Paraformer) |
| /ws/agents/{agent_id}/stream | Agent 流式执行 (SSE 替代) |

---

## 9. 状态持久化

| Key | 存储 | 内容 |
|-----|------|------|
| `icoder-auth` | localStorage (Zustand persist) | user, accessToken, refreshToken, isAuthenticated |
| `access_token` | localStorage | JWT access token (axios interceptor 读取) |
| `refresh_token` | localStorage | JWT refresh token |
| 文书模板 | localStorage | TextGenerationPage 自定义模板 |

---

## 10. 已知问题 (对 E2E 测试的影响)

| # | 问题 | 影响测试 |
|---|------|---------|
| 1 | `/api-clients` 路由与 Vite proxy `/api` 冲突 | 直接 URL 导航测试失效 |
| 2 | 无 Error Boundary | 未捕获异常导致白屏 |
| 3 | GoldCasesPage 无前端表单校验 | 空白提交会被 API 拒绝 |
| 4 | CaseReviewPage 仅 console.error | 审核失败无用户提示 |
| 5 | Export 按钮无 onClick (装饰性) | 无法测试导出 |
| 6 | 前端无角色级 UI 门控 | 所有角色看到相同按钮 |
| 7 | GoldCasesPage 无真正的 CSV 导出 | 仅有模板复制 |
| 8 | 多处 .catch(() => {}) 吞没错误 | 错误不可观测 |
