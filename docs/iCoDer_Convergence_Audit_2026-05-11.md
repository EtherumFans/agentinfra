# iCoDer 收敛审计报告

**日期**: 2026-05-11
**版本**: V0.4-dev
**审计范围**: 全栈 (backend / frontend / sdk / web-components / tests)

---

## 一、P1 问题（阻塞上线，必须修复）

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| P1-1 | **WebSocket STT 不可用** — `/ws` 端点返回 426 Upgrade Required，语音转文字功能完全失效 | SpeechToTextPage、EmbeddedAssistantPage 的实时语音功能不可用 | Vite dev server 未正确代理 WebSocket 升级请求到 FastAPI |
| P1-2 | **Runtime 安全框架大面积空洞** — 12 个状态仅 TRANSITION 4 个被调用；`guard()` 仅在 orchestrator 第 208 行调用 1 次；`guard_post()` 调用 0 次；DUC 的 10 个高危操作仅 `finalize_principal_diagnosis` 有门控 | AI 编码建议可能未经安全验证直接输出，违反 "所有安全决定由确定性规则执行" 的设计原则 | Runtime 框架后置于业务代码开发，集成不完整 |
| P1-3 | **AgentRunner 完全绕过 Runtime** — `POST /api/agents/{id}/run` 和 `/stream` 直接调用 `expert_runner.run()`，不创建任何 `DeterministicRuntime` 实例，不经过状态机、tool gate、DUC、audit chain 中的任何一个 | Agent 聊天界面产生的编码建议绕过了全部 5 层安全框架 | AgentRunner 是独立执行通道，从未集成 Runtime |
| P1-4 | **Orchestrator 跳过 5 个中间状态** — `run_pipeline()` 状态转换: `INGESTED → FACTS_EXTRACTED → RULES_VALIDATED → ARCHIVED`，跳过了 `CONTEXT_READY`、`CANDIDATES_READY`、`RISK_IDENTIFIED`、`REVIEW_REQUIRED`、`DECISION_CONFIRMED` | 状态机形同虚设，高风险操作（写回 EMR、提交支付）无状态保护 | 开发便利优先，跳过了需要人工交互的中间状态 |
| P1-5 | **语义记忆数据损坏** — `memory_expert.py` save() 第 88-112 行：先写 `key_facts` 为 JSON 数组，再覆写为 `{"facts": [...], "_embedding": [...]}`；recall() 第 166-171 行期望 `dict` 格式但第 178-184 行 keyword fallback 按 `list` 遍历，导致 `isinstance(kf, dict)` 为 True 时走到 dict 分支，为 False (list) 时走到 `for f in facts` 分支。两段代码假设不一致 | 语义搜索召回率大幅下降，记忆功能不可靠 | save 和 recall 在不同时间修改，数据格式契约断裂 |
| P1-6 | **路由冲突** — `/api-clients` 前端路由被 Vite 的 `/api` 代理规则拦截，APIClientsPage 无法直接访问 | OAuth 客户端管理页面不可用 | Vite proxy 配置 `'^/api'` 太宽泛 |

---

## 二、P2 问题（影响功能完整性，应在 V1.0 前修复）

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| P2-1 | **4/11 Expert 未连线** — CDIExpert、DenialManagementExpert、AuditTrailExpert、HCCRiskAdjustmentExpert 已在 orchestrator 中实例化，但其 `_execute_step` 分支仅被 `run_intelligent_pipeline()` 调用；固定 pipeline `run_pipeline()` 完全不经过它们 | CDI 审核、拒付管理、审计追踪、HCC 风险调整功能不可用 | 固定 pipeline 步骤中未包含这 4 个专家 |
| P2-2 | **A2A 协议未启用** — `register_agent()` 调用 0 次；`.well-known/agent.json` 为空；`coordinate()` 创建任务但从不执行 | 多 Agent 协作不可用 | A2A 注册逻辑写了但从未在启动时触发 |
| P2-3 | **Orchestrator 与 AgentRunner 双轨执行** — 两条独立的执行路径，Orchestrator 用固定 9 步 pipeline + Runtime，AgentRunner 用 LLM 规划 + 直接调用 `expert_runner`，输出格式完全不同 | 同一系统内编码审核结果不一致；维护两套代码 | 开发时未统一抽象 |
| P2-4 | **intelligent_pipeline 无 Runtime** — `run_intelligent_pipeline()` 调用 `_execute_step()`，其中无任何 `rt.transition()` 或 `rt.guard()` 调用 | LLM 动态规划的 pipeline 完全无安全护栏 | 实现时遗漏 |
| P2-5 | **前端分页/搜索/计算器等 UI 装饰性元素** — 多处按钮无 onClick（或在近期才修复），属于视觉占位 | 用户点击无响应，体验差 | 快速原型阶段的遗留 |
| P2-6 | **CodingWorkbench 导出按钮无功能** — 点击无效 | 工作台核心操作缺失 | 未实现 |
| P2-7 | **TicketPage 为纯占位页** — 无任何后端集成 | 工单系统不可用 | 设计为外部系统 |
| P2-8 | **后端 test_oauth.py 可能因 POST body vs JSON 格式问题失败**；test_code_dictionary.py 可能因空数据返回异常 | CI 不可靠 | 测试未随业务代码同步维护 |
| P2-9 | **无数据库迁移脚本** — Alembic 目录已初始化但 `versions/` 为空 | 数据库 schema 变更无法追踪和回滚 | 开发阶段直接操作 SQLite |
| P2-10 | **LLM token 消耗无监控** — Agent 聊天无 token 计数、无成本追踪 | 运营成本不可控 | 未实现 |

---

## 三、执行路径图

```
                          ┌─────────────────────────────────┐
                          │         Frontend Entry           │
                          └──────────────┬──────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
    POST /api/reviews         POST /api/agents/:id/run    POST /api/agents/:id/stream
    (编码审核同步/异步)        (Agent 聊天)                (Agent 流式聊天)
                    │                    │                    │
                    ▼                    ▼                    ▼
         ┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
         │ AgentOrchestrator │  │    AgentRunner        │  │    AgentRunner        │
         │ run_pipeline()    │  │    .run()              │  │    .stream()          │
         └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
                  │                       │                          │
         ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
         │ ✅ Runtime 创建   │  │ ❌ 无 Runtime         │  │ ❌ 无 Runtime         │
         │ ✅ Guardrails in  │  │ ❌ 无 Guardrails      │  │ ❌ 无 Guardrails      │
         │ ✅ Guardrails out │  │ ❌ 无 Tool Gate       │  │ ❌ 无 Tool Gate       │
         │ ⚠️ 仅 4/12 状态   │  │ ❌ 无 DUC             │  │ ❌ 无 DUC             │
         │ ⚠️ guard()仅1处   │  │ ❌ 无 Audit Chain     │  │ ❌ 无 Audit Chain     │
         │ ❌ guard_post() 0  │  │                       │  │                       │
         └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
                  │                       │                          │
         ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
         │ 9 步固定 Pipeline │  │ LLM 规划 →           │  │ LLM 规划 →           │
         │ (run_pipeline)    │  │ expert_runner.run()  │  │ expert_runner.stream │
         │                   │  │   (逐个调用 expert)  │  │   (逐个调用 expert)  │
         │ Steps:            │  │                       │  │                       │
         │ 1. Evidence       │  │ Routing:              │  │ Routing:              │
         │ 2a.Diagnosis      │  │ - single_expert       │  │ - single_expert       │
         │ 2b.Procedure      │  │ - fixed_order         │  │ - fixed_order         │
         │ 3. Homepage       │  │ - llm_plan (default)  │  │ - llm_plan (default)  │
         │ 4. Code Dict      │  │                       │  │                       │
         │ 5. Rule Engine    │  └───────────────────────┘  └───────────────────────┘
         │ 6. Verification   │
         │ 7a.DRG            │     ┌──────────────────────────┐
         │ 7b.Doc Gap        │     │ run_intelligent_pipeline  │
         │ 8. Report         │     │ (Orchestrator)            │
         │ 9. Human Review   │     │ ❌ 无 Runtime             │
         └───────────────────┘     │ ❌ 无 Guardrails          │
                                   └──────────────────────────┘

图例: ✅ = 已集成  ⚠️ = 部分集成  ❌ = 完全缺失
```

### 关键观察

1. **三条独立的执行通道**，安全防护水平不一致
2. **Orchestrator 的 run_pipeline()** 是唯一有 Runtime 的通道，但也只用了 4/12 状态
3. **AgentRunner (run + stream)** 是两个高频使用的通道（AI Studio 聊天界面），却完全没有安全护栏
4. **intelligent_pipeline** 代码已写但在生产路径上未被调用，且没有 Runtime

---

## 四、Runtime 绕行点详细清单

### 4.1 AgentRunner — 完全绕行

**文件**: `backend/app/services/agent_runner.py`
**影响端点**: `POST /api/agents/{id}/run`, `POST /api/agents/{id}/stream`
**前端入口**: AgentsPage (AI Studio 聊天界面)

AgentRunner 执行流程中完全不涉及以下任何一个安全层：

```
AgentRunner.run() / .stream()
  → _resolve_experts()         # 从 DB 加载 Agent 绑定的 Expert
  → routing_strategy 分支:
      single_expert: → _run_single_expert() → expert_runner.run()
      fixed_order:   → _run_fixed_order()   → expert_runner.run() × N
      llm_plan:      → _run_llm_planned()   → llm_service + expert_runner.run()
```

缺失项：
- 不创建 `DeterministicRuntime` 实例
- 不调用 `rt.transition()`
- 不调用 `rt.guard()` / `rt.guard_post()`
- 不调用 `guardrails.validate_input()` / `guardrails.validate_output()`
- 不记录 AuditChain
- 不触发 DUC 人工确认

### 4.2 run_intelligent_pipeline — 完全绕行

**文件**: `backend/app/agents/orchestrator.py` 第 293-375 行

```python
async def run_intelligent_pipeline(self, encounter_data):
    # ...
    for planned_step in planned_steps:
        await self._execute_step(step_name, context)  # ← 直接调 expert，无任何 Runtime
```

对比 `run_pipeline()` 中存在的 Runtime 调用：
- `rt = runtime_registry.get_or_create(pipeline_id)` — ❌ 缺失
- `rt.transition(CaseState.INGESTED, ...)` — ❌ 缺失
- `rt.transition(CaseState.FACTS_EXTRACTED, ...)` — ❌ 缺失
- `rt.transition(CaseState.RULES_VALIDATED, ...)` — ❌ 缺失
- `rt.guard("finalize_principal_diagnosis", ...)` — ❌ 缺失
- `rt.transition(CaseState.ARCHIVED, ...)` — ❌ 缺失

### 4.3 run_pipeline — 部分绕行

**文件**: `backend/app/agents/orchestrator.py` 第 59-290 行

虽然 run_pipeline 使用了 Runtime，但以下调用全部缺失：

```
STATES USED:      INGESTED → FACTS_EXTRACTED → RULES_VALIDATED → ARCHIVED
STATES SKIPPED:   CONTEXT_READY, CANDIDATES_READY, RISK_IDENTIFIED,
                  REVIEW_REQUIRED, DECISION_CONFIRMED, DOC_FEEDBACK_READY,
                  WRITEBACK_PENDING, WRITTEN_BACK
                  (FAILED, ESCALATED — 仅在异常时可用)

GUARD CALLS:      guard("finalize_principal_diagnosis") — 仅 1 处 (第 208 行)
                  其余 9 个 DUC action 从未被 guard:
                  - confirm_high_dispute_comorbidity    ❌
                  - submit_payment_high_risk            ❌
                  - writeback_to_emr                    ❌
                  - writeback_to_his                    ❌
                  - writeback_to_insurance              ❌
                  - create_document_correction_task     ❌
                  - archive_case                        ❌
                  - confirm_decision                    ❌
                  - initiate_writeback                  ❌

GUARD_POST:       guard_post() — 调用 0 次 (第 324-330 行代码从未执行)

TIMEOUT_CHECK:    check_timeout() — 在 orchestrator 中调用 0 次
                  但 runtime.py 中有完整实现 (6 个状态有时限)
```

### 4.4 前端直连 API — 无中间防护

前端页面通过 Axios 直接调用 API，没有任何前端侧的输入校验或输出过滤。安全护栏完全依赖后端，但后端的三条执行通道中两条没有护栏。

---

## 五、前端伪功能清单

### 5.1 纯占位页面（无后端/无功能）

| 页面 | 状态 | 详情 |
|------|------|------|
| **TicketsPage** | 纯占位 | 仅显示 "外部工单系统" 链接到 `http://localhost:3000/tickets`（自引用死循环） |
| **RuleLibrariesPage** | 待确认 | 需要确认是否连接后端 rules API |

### 5.2 装饰性 UI（近期部分修复，但仍需确认）

| 位置 | 元素 | 原始状态 | 修复状态 (commit 83fc16c) |
|------|------|----------|---------------------------|
| CodingWorkbenchPage | 导出按钮 | 无 onClick | 待确认 |
| AIStudioOverviewPage | 计算器按钮 | 无 onClick | 已修复 |
| SupportPage | 在线客服 | `href="#"` | 已修复 → 跳转 EmbeddedAssistant |
| Layout footer | JS SDK / Postman 链接 | `href="#"` | 已修复 |
| Various pages | 搜索/分页 | 装饰性 | 部分修复 |

### 5.3 后端有 API 但前端无调用

| API 端点 | 前端使用情况 |
|----------|-------------|
| `POST /api/a2a/register` | 从未从前端调用 |
| `GET /.well-known/agent.json` | 从未调用 |
| `GET /api/reviews/{id}/report/markdown` | 待确认 |
| `GET /api/reviews/{id}/report/html` | 待确认 |

### 5.4 前端有页面但后端 API 存根

| 页面 | 调用的 API | 状态 |
|------|-----------|------|
| EvaluationPage | `evaluationApi.run()` | API 有实现但依赖 GoldCase 数据 |
| TicketsPage | 无 API 调用 | 纯外部链接 |

---

## 六、测试缺口清单

### 6.1 前端单元测试 — 零覆盖

```
已安装依赖:
  vitest 2.1.1          ✅ 已安装
  @testing-library/react 16.0.1  ✅ 已安装
  @testing-library/jest-dom 6.5.0 ✅ 已安装
  jsdom 25.0.1           ✅ 已安装

已编写测试文件:          0 个
Vitest 配置 (vite.config.ts):  ❌ 无 test 配置块
覆盖率工具:               ❌ 未安装 @vitest/coverage-*
```

需要的前端单元测试：
- 组件渲染测试 (至少 10 个核心组件)
- Zustand store 测试 (auth + app)
- API 拦截器测试 (401 刷新逻辑)
- i18n 切换测试
- 表单验证测试

### 6.2 后端测试缺口

| 缺失测试 | 优先级 | 说明 |
|----------|--------|------|
| AgentRunner 测试 | P0 | 3 种路由策略无一有测试 |
| Orchestrator 集成测试 | P0 | run_pipeline 和 intelligent_pipeline 无测试 |
| Runtime 单元测试 | P0 | 12 状态转换、tool gate、DUC、audit chain 均无测试 |
| WebSocket STT 测试 | P1 | websocket.py 无测试 |
| Memory Expert 测试 | P1 | save/recall 数据损坏可能未被检测 |
| Guardrails 集成测试 | P1 | 仅有单元测试，无端到端验证 |
| Expert 逐个测试 | P2 | 每个 Expert 的 run() 无独立测试 |
| A2A 协议测试 | P2 | register/coordinate 无测试 |

### 6.3 E2E 测试缺口

| 缺失场景 | 优先级 | 说明 |
|----------|--------|------|
| WebSocket STT 流程 | P0 | 需先修复 P1-1 才能测试 |
| Agent 聊天流式响应 | P1 | 当前 E2E 未覆盖 SSE 流 |
| Agent 创建/编辑/删除 | P1 | 未覆盖 Agent CRUD |
| Expert 运行 | P1 | 未覆盖 Expert 调用 |
| 护栏阻断场景 | P1 | 未测试恶意输入 |
| OAuth 客户端流程 | P2 | 未覆盖 |
| 多角色权限 | P2 | 未测试 6 种角色的访问控制 |
| 移动端响应式 | P2 | 未覆盖 |

### 6.4 CI/CD 缺口

| 项目 | 状态 |
|------|------|
| GitHub Actions | ❌ 不存在 |
| Git pre-commit hooks | ❌ 不存在 |
| Git pre-push hooks | ❌ 不存在 |
| 自动化测试触发 | ❌ 不存在 |
| 代码覆盖率门禁 | ❌ 不存在 |
| Lint 门禁 | ❌ 不存在（ESLint 配置存在但未强制执行） |

---

## 七、推荐的 4 周收敛计划

### Week 1: 安全框架加固 (最优先)

| 天 | 工作项 | 类别 | 预计改动文件 |
|----|--------|------|-------------|
| 1-2 | **AgentRunner 集成 Runtime** — 在 `run()` 和 `stream()` 中创建 `DeterministicRuntime` 实例，调用 `rt.transition()` + `rt.guard()`，记录 AuditChain | P1-3 | `agent_runner.py` |
| 3 | **补齐 run_pipeline 的 5 个中间状态** — `CONTEXT_READY`(context build 后)、`CANDIDATES_READY`(step2b 后)、`RISK_IDENTIFIED`(DRG 后)、`REVIEW_REQUIRED`(有风险时)、`DECISION_CONFIRMED`(report 前) | P1-4 | `orchestrator.py` |
| 4 | **添加 guard_post() 调用** — 每个 Expert 输出后调用 `rt.guard_post(output)` 验证关键字段；**添加 timeout check** — pipeline 关键节点前调用 `rt.check_timeout()` | P1-2 | `orchestrator.py` |
| 5 | **修复记忆数据格式契约** — 统一 save() 和 recall() 的数据结构，添加单元测试验证 | P1-5 | `memory_expert.py` + `test_memory.py` |

**Week 1 验证标准**: AgentRunner 和 Orchestrator 的所有执行路径都有 Runtime 实例；memory save/recall 循环测试通过。

### Week 2: 功能连接 + 前端清理

| 天 | 工作项 | 类别 | 预计改动文件 |
|----|--------|------|-------------|
| 1 | **修复 WebSocket STT** — 配置 Vite proxy 正确升级 `ws://` 请求或前端直连后端端口 | P1-1 | `vite.config.ts` |
| 2 | **修复路由冲突** — 调整 Vite proxy 规则或重命名 API 路径 | P1-6 | `vite.config.ts` / `App.tsx` |
| 3-4 | **连通 4 个未连线 Expert** — 在 run_pipeline() 固定流程中加入 `cdi_review`(step7b 后)、`denial_analysis`(report 前)、`audit_trail`(全程)、`hcc_risk_adjustment`(diagnosis 后) | P2-1 | `orchestrator.py` |
| 5 | **前端伪功能清理** — 移除 TicketsPage 死循环链接、确认所有按钮有 onClick、CodingWorkbench 导出实现或标记为"即将推出" | P2-5/6/7 | 前端多个文件 |

**Week 2 验证标准**: STT 功能可用；APIClientsPage 可正常访问；所有 11 个 Expert 在 pipeline 中可被调用。

### Week 3: 测试补全

| 天 | 工作项 | 类别 | 预计改动文件 |
|----|--------|------|-------------|
| 1-2 | **Runtime 单元测试** — 12 状态全转换覆盖、所有 DUC action gate 测试、timeout 测试、audit chain 完整性测试、非法转换拒绝测试 | Test | `test_runtime.py` |
| 2-3 | **AgentRunner 测试** — 3 种路由策略测试(single/fixed/llm_plan)、无 Expert 降级测试、LLM 规划失败降级测试 | Test | `test_agent_runner.py` |
| 3-4 | **Memory Expert 测试** — save/recall 循环、embedding 存储和检索、session 隔离、agent 隔离 | Test | `test_memory_expert.py` |
| 4-5 | **前端组件测试** — 至少覆盖 AgentsPage(聊天输入)、MedicalCodingPage(编码提交)、LoginPage(表单验证)、SettingsPage(护栏切换)、Zustand stores | Test | `frontend/src/**/*.test.tsx` |
| 5 | **修复已知后端测试失败** — test_oauth.py、test_code_dictionary.py | Test | `test_oauth.py`, `test_code_dictionary.py` |

**Week 3 验证标准**: 后端测试覆盖率达到 60%+；前端组件测试从 0 → 10+ 个文件；所有已有测试通过。

### Week 4: CI/CD + 文档 + 收尾

| 天 | 工作项 | 类别 | 预计改动文件 |
|----|--------|------|-------------|
| 1-2 | **搭建 GitHub Actions** — 后端 pytest + 前端 vitest + E2E Playwright，PR 触发，覆盖率报告 | CI | `.github/workflows/ci.yml` |
| 3 | **配置 pre-commit hook** — ESLint + pytest (仅变更文件相关测试) | CI | `.husky/pre-commit` |
| 4 | **A2A 协议上线** — 启动时自动注册 Agent，`.well-known/agent.json` 动态生成，至少 1 个 multi-agent 协作场景端到端可用 | P2-2 | `a2a.py`, `main.py` |
| 5 | **收敛审计文档更新** + **PRD 同步** + **数据库迁移初始化** (生成初始 Alembic migration) | Doc/DB | 多个文件 |

**Week 4 验证标准**: GitHub Actions 绿灯；pre-commit hook 生效；A2A 至少 1 个场景可用；Alembic 有初始迁移。

---

## 附录：风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| AgentRunner 无护栏导致非法编码建议输出 | 中 | 严重 — 合规风险 | Week 1 优先修复 |
| 记忆数据损坏导致上下文丢失 | 高 | 中等 — 用户体验 | Week 1 修复 |
| STT 不可用阻断语音场景 | 确定 | 中等 | Week 2 修复 |
| 双轨执行导致审核结果不一致 | 高 | 中等 | 后续统一抽象 |
| CI 缺失导致回归未被发现 | 高 | 中等 | Week 4 搭建 |
| 无数据库迁移导致环境不一致 | 低 | 中等 | Week 4 初始化 |
