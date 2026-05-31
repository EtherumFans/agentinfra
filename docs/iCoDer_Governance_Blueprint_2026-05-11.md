# iCoDer 治理蓝图

**日期**: 2026-05-11
**版本**: V0.4-dev
**类型**: 治理文档 (不涉及代码修改)

---

## 一、清理清单

### 1.1 应立即删除的目录/文件

| 路径 | 大小 | 理由 |
|------|------|------|
| `screenshots/` | ~70 文件 | 竞品截图、开发调试截图，不应入仓库。含 Corti Console HTML/CSS 抓取文件 |
| `backend/screenshots/` | 1 文件 | 开发调试截图 |
| `Corti/` | 467KB | 竞品调研 PDF + 截图，敏感且与代码无关。应移至内部知识库 |
| `scripts/chrome-connect.skill.md` | - | Claude Code skill 配置，不应入项目仓库 |
| `scripts/connect-cdp.py` | - | 开发调试用 Chrome CDP 连接脚本 |
| `scripts/launch-chrome-debug.ps1` | - | 开发调试用 PowerShell 脚本 |
| `backend/.env` | - | 敏感配置已提交到 git（检查 `.gitignore`） |
| `frontend/dist/` | - | 构建产物已在 git 中追踪（应只保留在 CI artifact） |
| `frontend/node_modules/` | - | `package-lock.json` 变更显示 node_modules 被追踪（确认 `.gitignore`） |
| `frontend/playwright-report/` | - | 测试报告不应入仓库 |
| `frontend/test-results/` | - | 测试结果不应入仓库 |

### 1.2 .gitignore 应补充的规则

```gitignore
# 敏感配置
.env
.env.*
!.env.example

# 截图 & 调研
screenshots/
backend/screenshots/
Corti/

# 构建产物
frontend/dist/
*.log

# 测试产物
frontend/playwright-report/
frontend/test-results/
**/__pycache__/
*.pyc

# IDE
.vscode/
.idea/

# 调试脚本
scripts/chrome-connect.skill.md
scripts/connect-cdp.py
scripts/launch-chrome-debug.ps1

# OS
Thumbs.db
.DS_Store
```

### 1.3 代码级清理

| 文件 | 问题 | 操作建议 |
|------|------|----------|
| `frontend/src/pages/TicketsPage.tsx` | 自引用死循环 `href="http://localhost:3000/tickets"` | 要么连接后端，要么标记为 `// TODO: 集成外部工单系统` |
| `frontend/src/pages/CodingWorkbenchPage.tsx:149` | 导出按钮无 onClick | 实现导出功能或加 `disabled` + tooltip "即将推出" |
| `frontend/src/pages/CaseReviewPage.tsx:49,64` | `console.error` 而非用户可见的错误提示 | 替换为 toast/error state |
| `backend/app/services/memory_expert.py:88-112` | save/recall 数据格式不一致 | 统一为 `{"facts": [...], "_embedding": [...]}` 格式 |

### 1.4 硬编码清理

| 文件 | 硬编码值 | 应替换为 |
|------|----------|----------|
| `frontend/nginx.conf:13` | `http://backend:8000` | 引用环境变量或至少文档说明 |
| `backend/app/services/a2a_protocol.py:290` | `http://localhost:8000` | `settings.APP_URL` 配置项 |
| `frontend/src/pages/SupportPage.tsx:16` | `http://localhost:8000/docs` | 相对路径 `/api/docs` 或配置 |
| `frontend/src/pages/TicketsPage.tsx:19` | `http://localhost:3000/tickets` | 应指向真实外部系统 |

---

## 二、Docker 治理

### 2.1 当前 Docker 架构

```
docker-compose.yml
├── backend (python:3.11-slim)
│   └── Dockerfile: pip install → uvicorn :8000
└── frontend (node:20-alpine → nginx:alpine)
    └── Dockerfile: npm build → nginx serve :80
        └── nginx.conf: SPA + /api/ → proxy_pass backend:8000
```

### 2.2 Docker 问题清单

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| D-1 | **nginx.conf 缺少 WebSocket 代理** | P0 | `/ws/` 路径无 `proxy_http_version 1.1` + `Upgrade` / `Connection` 头，STT 语音流在 Docker 环境完全不可用 |
| D-2 | **无 .dockerignore 文件** | P1 | `node_modules/`、`__pycache__/`、`.env`、`screenshots/` 等会被 COPY 进镜像，镜像膨胀 + 敏感信息泄漏风险 |
| D-3 | **后端 Dockerfile 无多阶段构建** | P2 | `build-essential` 安装后未清理，最终镜像包含编译工具链 |
| D-4 | **前端 Dockerfile 使用 `npm ci --legacy-peer-deps`** | P1 | 存在 peer dependency 冲突未解决，用 flag 绕过而非修复 |
| D-5 | **docker-compose 挂载 .env 为只读文件** | P2 | `./backend/.env:/app/.env:ro` — 但 .env 文件在 git 中被追踪，应改用环境变量注入 |
| D-6 | **SQLite 在生产容器中使用** | P1 | `sqlite+aiosqlite:///./data/icoder.db` — 容器重启时数据可能丢失，应挂载 volume 或切换到 PostgreSQL |
| D-7 | **healthcheck 用 Python urllib 内联** | P2 | 后端 healthcheck 启动 Python 解释器进程开销大，建议改用 `curl` 或 `wget`；前端 healthcheck 用 `wget -qO-` 但 alpine nginx 镜像不含 wget |
| D-8 | **data volume 定义但未挂载到 backend** | P1 | `docker-compose.yml:33` 定义了 `volumes: data:` 但 backend 服务的 volumes 写的是 `./data:/app/data`（bind mount 而非 named volume） |
| D-9 | **backend 无 depends_on 数据库** | P2 | 虽然当前用 SQLite 无需外部 DB，但设计上预留了 PostgreSQL 切换空间，缺少 DB 服务定义 |
| D-10 | **前端 300s proxy_read_timeout 过长** | P3 | 编码审核 pipeline 可能需要长超时，但 5 分钟对所有 `/api/` 请求都适用会导致连接堆积 |

### 2.3 Docker 修复方案（推荐但不执行）

**nginx.conf 增加 WebSocket 支持**:
```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
```

**.dockerignore** (frontend):
```
node_modules
dist
.git
.env
*.log
screenshots
playwright-report
test-results
```

**.dockerignore** (backend):
```
__pycache__
*.pyc
.env
.git
tests
screenshots
.pytest_cache
```

---

## 三、Coding Review Workflow 端到端分析

### 3.1 完整数据流

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           CODING REVIEW WORKFLOW                              │
│                                                                              │
│  FRONTEND                        BACKEND                         EXTERNAL     │
│  ────────                        ───────                         ────────     │
│                                                                              │
│  ┌──────────────┐    POST /api/reviews    ┌────────────────────┐             │
│  │ Workbench    │ ──────────────────────→ │ reviews.py         │             │
│  │ encounter    │    {encounter_id}       │ create_review()    │             │
│  │ selected     │                         └─────────┬──────────┘             │
│  └──────────────┘                                   │                        │
│                                                     ▼                        │
│  ┌──────────────┐    (sync mode)         ┌────────────────────┐             │
│  │ Progress     │ ←───────────────────── │ AgentOrchestrator  │             │
│  │ (none in UI) │    ReviewResponse      │ .run_pipeline()    │             │
│  └──────────────┘                        └─────────┬──────────┘             │
│                                                     │                        │
│  ┌──────────────┐    (async mode)        ┌─────────┴──────────┐             │
│  │ WebSocket    │ ←── WS /ws/reviews/    │ TaskManager        │             │
│  │ progress     │     {task_id}          │ background task    │             │
│  └──────────────┘                        └────────────────────┘             │
│                                                     │                        │
│  ┌──────────────┐    GET /api/reviews/   Pipeline Steps:                     │
│  │ CaseReview   │ ←── {review_id}        1. Evidence Extraction              │
│  │ human review │                        2a. ICD Diagnosis                   │
│  └──────┬───────┘                        2b. Procedure Coding                │
│         │ PUT /api/reviews/              3. Homepage + Rules                 │
│         │ {id}/candidates/{id}/review    4. Code Dictionary                  │
│         │                                5. Rule Engine                     │
│  ┌──────┴───────┐    PUT /api/reviews/   6. Evidence Verification   ┌──────┐ │
│  │ Complete     │ ── {id}/complete       7a. DRG/DIP Analysis       │LLM   │ │
│  │ Review       │                        7b. Doc Gap                │(Deep-│ │
│  └──────────────┘                        8. Report Generation       │Seek) │ │
│                                          9. Human Review            └──────┘ │
│                                                                              │
│  ┌──────────────┐    POST /api/agents/   ┌────────────────────┐             │
│  │ AI Studio    │ ── {id}/run 或 /stream │ AgentRunner         │             │
│  │ Chat         │                        │ (NO Runtime!)       │             │
│  └──────────────┘                        └────────────────────┘             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 工作流断点分析

| 步骤 | 前端 | 后端 API | Runtime | Guardrails | 状态 |
|------|------|----------|---------|------------|------|
| 1. 选择病历 | Workbench 搜索框 | `GET /api/encounters` | - | - | ✅ 已通 |
| 2. 运行审核 | 点击"运行审核" | `POST /api/reviews` | ⚠️ 仅 4/12 状态 | ✅ input+output | ⚠️ 部分 |
| 3. 进度展示 | 无进度条 (同步模式卡住) | sync 模式阻塞 | - | - | ❌ 无进度UI |
| 4. 查看结果 | 四面板展示 evidence/candidates/report/DRG | response 包含全部数据 | - | - | ✅ 已通 |
| 5. 人工复核 | CaseReviewPage 逐个审核 | `PUT .../candidates/{id}/review` | ❌ 不经过 Runtime | ❌ 无护栏 | ❌ 绕过 |
| 6. 完成审核 | 点击"完成审核" | `PUT .../{id}/complete` | ❌ 不经过 Runtime | ❌ 无护栏 | ❌ 绕过 |
| 7. 导出报告 | 导出按钮 | 无对应 API 调用 | - | - | ❌ 死按钮 |
| 8. AI Studio 聊天 | 聊天输入 | `POST /api/agents/{id}/stream` | ❌ 完全绕过 | ❌ 无护栏 | ❌ 绕过 |

### 3.3 关键断点

1. **同步模式无进度反馈** — `POST /api/reviews` 同步模式直接阻塞等待 pipeline 完成（可能 30-120 秒），前端无 spinner 以外的任何进度指示。async 模式有 WebSocket 进度但前端从未使用 async 模式。

2. **人工复核绕过 Runtime** — `review_candidate()` (reviews.py:367-404) 直接操作数据库 `CodeCandidate` 表，不经过 `DeterministicRuntime`，不触发 DUC，不记录 AuditChain。这违反了 "所有安全决定由 Runtime 执行" 的设计原则。

3. **完成审核绕过 Runtime** — `complete_review()` (reviews.py:407-441) 仅更新 `human_review_status` 字段，未经 `rt.guard("confirm_decision")` 验证。

4. **AI Studio 聊天是独立宇宙** — `POST /api/agents/{id}/run` 和 `/stream` 走 AgentRunner，与 Orchestrator 的 pipeline 完全无关。用户在 AI Studio 中获得的编码建议不受任何安全护栏保护。

### 3.4 理想工作流 vs 实际工作流

| 环节 | 理想 | 实际 |
|------|------|------|
| 编码审核触发 | 统一走 Runtime → Orchestrator | 3 条独立通道，安全覆盖不一致 |
| AI 建议输出 | 每步输出经 `guard_post()` 验证 | `guard_post()` 调用 0 次 |
| 高风险操作 | DUC 强制人工确认 | 仅 `finalize_principal_diagnosis` 有门控 |
| 人工复核 | 经 Runtime API `/api/runtime/review/{case_id}` | 直接写数据库，Runtime API 从未被前端调用 |
| 审核链路 | AuditChain 全程记录 | 仅 Orchestrator 有 AuditChain（且不完整） |
| 状态追踪 | 12 状态全流转 | 仅 4 状态被使用 |

---

## 四、Definition of Done

每个功能进入主分支前，必须满足以下 8 条。未经满足的功能只能存在于 feature branch。

### DoD-1: 经过 Runtime

- [ ] 所有编码审核执行路径（Orchestrator、AgentRunner、IntelligentPipeline）均创建 `DeterministicRuntime` 实例
- [ ] 关键步骤间调用 `rt.transition()` 完成状态转换
- [ ] 当前状态与操作匹配（通过 `STATE_ACTIONS` 验证）
- [ ] 非法状态转换被拒绝（返回 False 且记录审计）

**验证方式**: 检查代码中 `runtime_registry.get_or_create()` 调用存在且 `rt.transition()` 覆盖所有关键步骤

### DoD-2: 有 Audit

- [ ] 每个状态转换记录 `AuditEvent`（含 timestamp、actor、payload）
- [ ] 每个 tool gate 检查记录 guard_check 事件
- [ ] 每个人工确认记录 human_confirmation 事件
- [ ] `AuditChain` 可通过 API 查询（`GET /api/runtime/audit/{case_id}`）

**验证方式**: 调用 audit API 确认事件链完整；检查 `rt.audit.record()` 调用覆盖所有关键操作

### DoD-3: 有测试

- [ ] 每个新增 API 端点有至少 1 个集成测试
- [ ] 每个新增 Service 有单元测试覆盖核心逻辑
- [ ] 每个新增 Expert 有独立测试（mock LLM 调用）
- [ ] Runtime 状态转换有完整覆盖（12 状态 × 合法/非法转换）
- [ ] 前端组件有渲染测试（至少覆盖用户交互路径）

**验证方式**: `pytest --cov=app --cov-report=term` 覆盖率不降低；`npm test` 无失败

### DoD-4: 有状态转换

- [ ] 新功能涉及的状态变更通过 `STATE_TRANSITIONS` 定义
- [ ] 状态变更前调用 `rt.guard()` 检查操作许可
- [ ] 状态变更后调用 `rt.guard_post()` 验证输出
- [ ] 超时状态有对应的 `STATE_TIMEOUTS` 配置

**验证方式**: 检查 `STATE_TRANSITIONS` 表包含新状态；`rt.guard()` / `rt.guard_post()` 调用存在

### DoD-5: 有错误处理

- [ ] Expert 调用失败不导致 pipeline 崩溃（try/except + errors[] 收集）
- [ ] LLM 调用失败有 fallback 策略
- [ ] API 返回明确的错误码和消息（非 500 "Internal server error"）
- [ ] 前端错误状态有用户可见提示（非 `console.error`）
- [ ] 异步任务失败可通过 TaskManager 查询状态

**验证方式**: 故意触发错误场景（LLM 超时、DB 断开、无效输入）确认优雅降级

### DoD-6: 有 API 文档

- [ ] 新端点有完整的 FastAPI docstring（summary + description）
- [ ] Request/Response schema 有 Field description
- [ ] 错误响应在 docstring 中列出
- [ ] 可通过 `/docs` (Swagger UI) 交互测试

**验证方式**: 访问 `http://localhost:8000/docs` 确认端点可见、schema 完整、可执行

### DoD-7: 有前端真实调用

- [ ] 前端页面不是纯占位（TicketsPage 除外——需有明确 TODO 注释）
- [ ] 所有按钮有 onClick 且触发真实 API 调用或导航
- [ ] API 调用有 loading/error/success 三种状态处理
- [ ] 无 `href="#"` 或自引用死循环链接

**验证方式**: Playwright E2E 测试覆盖新页面；手工点击所有交互元素

### DoD-8: 无死按钮

- [ ] 页面中所有 `<button>` 有 `onClick`
- [ ] 所有 `<a>` 的 `href` 指向有效路由或外部 URL
- [ ] 导出/下载/分享等操作按钮要么已实现，要么明确标记 `disabled` + tooltip
- [ ] 无 `onClick={() => {}}` 或 `onClick={undefined}`

**验证方式**: `grep -r "onClick={" frontend/src/pages/` 确认所有 onClick 有实际逻辑；E2E 测试逐页点击

---

## 五、重构优先级矩阵

### P0 — 阻塞合并，立即修复（Week 1）

| # | 治理项 | 覆盖 DoD | 当前状态 | 修复目标 |
|---|--------|----------|----------|----------|
| P0-1 | **AgentRunner 集成 Runtime** | DoD-1, DoD-2, DoD-4 | AgentRunner.run() 和 .stream() 完全不涉及 Runtime | 创建 Runtime 实例 + transition + guard，3 条路由策略均覆盖 |
| P0-2 | **人工复核接入 Runtime** | DoD-1, DoD-2, DoD-4 | `review_candidate()` 和 `complete_review()` 直接写 DB | 调用 `rt.guard()` + `rt.human_confirm()` + `rt.transition()` |
| P0-3 | **nginx WebSocket 代理** | (Docker) | nginx.conf 无 `/ws/` 配置 | 添加 WebSocket proxy 配置块 |
| P0-4 | **.dockerignore 创建** | (Docker) | 不存在 | 创建 frontend + backend 的 .dockerignore |
| P0-5 | **.gitignore 清理** | (Cleanup) | `screenshots/`、`dist/`、`.env` 被追踪 | 更新 .gitignore + `git rm --cached` |
| P0-6 | **记忆数据格式统一** | DoD-5 | save/recall 数据格式不一致 | 统一为 `{"facts": [...], "_embedding": [...]}` |

### P1 — 阻塞 V1.0 发布（Week 2-3）

| # | 治理项 | 覆盖 DoD | 当前状态 | 修复目标 |
|---|--------|----------|----------|----------|
| P1-1 | **补齐 run_pipeline 中间状态** | DoD-4 | 仅 4/12 状态被使用 | 增加 CONTEXT_READY、CANDIDATES_READY、RISK_IDENTIFIED、REVIEW_REQUIRED、DECISION_CONFIRMED |
| P1-2 | **补齐 guard() 和 guard_post() 调用** | DoD-4, DoD-5 | guard 仅 1 处；guard_post 0 处 | 每个 Expert 输出后 guard_post；每个 DUC action 前 guard |
| P1-3 | **4 个未连线 Expert 接通** | DoD-7 | CDI/Denial/Audit/HCC Expert 未在固定 pipeline 中调用 | 在 run_pipeline 中添加对应步骤 |
| P1-4 | **前端 async 模式启用** | DoD-7 | 同步模式无进度反馈 | 默认 async + WebSocket 进度订阅 |
| P1-5 | **导出按钮实现** | DoD-8 | CodingWorkbench 导出按钮无功能 | 实现 report markdown/PDF 导出 |
| P1-6 | **SQLite → 至少 volume 持久化** | (Docker) | bind mount `./data` 但未验证 | 使用 named volume + 备份策略文档 |
| P1-7 | **硬编码 URL 清理** | DoD-8 | localhost 硬编码在 5 处 | 全部替换为配置变量或相对路径 |
| P1-8 | **TicketsPage 死循环修复** | DoD-7, DoD-8 | 自引用 `localhost:3000/tickets` | 连外部系统或加 TODO 标记 |

### P2 — V1.0 可延后但需跟踪（Week 4+）

| # | 治理项 | 覆盖 DoD | 当前状态 | 修复目标 |
|---|--------|----------|----------|----------|
| P2-1 | **A2A 协议端到端上线** | DoD-7 | register 在启动时调用但 coordinate 从未被真实 agent 使用 | 至少 1 个 multi-agent 协作场景可用 |
| P2-2 | **AgentRunner 与 Orchestrator 统一抽象** | DoD-1 | 双轨执行，输出格式不同 | 统一为 AgentRunner 调用 Orchestrator 或反之 |
| P2-3 | **intelligent_pipeline 集成 Runtime** | DoD-1, DoD-4 | 动态 pipeline 无 Runtime | 添加 Runtime 调用 |
| P2-4 | **Docker 多阶段构建优化** | (Docker) | 后端镜像含 build-essential | 分离 build 和 runtime 阶段 |
| P2-5 | **前端 peer dependency 冲突修复** | (CI) | `--legacy-peer-deps` 绕过 | 升级/调整依赖版本 |
| P2-6 | **healthcheck 优化** | (Docker) | Python 进程启动开销 + nginx 无 curl/wget | 后端用 curl，nginx 镜像换 nginx:alpine-slim + curl |
| P2-7 | **数据库迁移初始化** | (DB) | Alembic versions/ 为空 | 生成初始 migration |
| P2-8 | **前端单元测试从 0 到 10+** | DoD-3 | vitest 配置为 0 | 配置 vitest + 写 10 个组件测试 |
| P2-9 | **E2E 测试补全** | DoD-3 | 24 个用例，缺 STT/护栏/多角色 | 补全缺失场景 |
| P2-10 | **CI/CD 搭建** | DoD-3 | 无 CI | GitHub Actions: pytest + vitest + playwright |

---

## 附录 A：治理检查清单（合并前自检）

```
□ DoD-1  经过 Runtime         — rt.transition() 覆盖所有状态变更
□ DoD-2  有 Audit             — rt.audit.record() 覆盖所有关键操作
□ DoD-3  有测试               — pytest + vitest 均通过
□ DoD-4  有状态转换            — STATE_TRANSITIONS 定义完整
□ DoD-5  有错误处理            — try/except + 用户可见错误提示
□ DoD-6  有 API 文档           — /docs 可交互测试
□ DoD-7  有前端真实调用         — 非占位，有 loading/error/success
□ DoD-8  无死按钮              — grep onClick 无空函数
```

## 附录 B：Docker 部署检查清单

```
□ .dockerignore 存在且完整
□ nginx.conf 含 WebSocket 代理
□ 敏感配置通过环境变量注入（非 .env 文件挂载）
□ data 使用 named volume（非 bind mount）
□ healthcheck 可用（curl/wget 非 Python）
□ 镜像无构建工具链残留
□ npm ci 无 --legacy-peer-deps
□ 前端 proxy_read_timeout 合理（通用 60s + pipeline 专用更长）
```
