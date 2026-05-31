# iCoDer 收敛审计报告

**日期**: 2026-05-16
**版本**: V0.5-dev
**上版审计**: 2026-05-15 (`iCoDer_Convergence_Audit_2026-05-15.md`)

---

## 变更摘要：5月15日→5月16日

4 个新提交:

| Commit | 说明 | 影响 |
|--------|------|------|
| `0ed2851` | LLM-based primary diagnosis selection (Corti-style) | Homepage expert 从纯规则排序改为 LLM + 规则双路径 |
| `f20a911` | 多码表管理系统 | CodeTable/CodeMapping 模型 + CRUD API + 跨表映射 |
| `e72c811` | CodeTablePage UI 对齐 Figma | 搜索按钮改为 Corti 圆形图标, 列表→垂直列表 |
| `537873e` | Figma V5 设计对齐 | 看板式卡片网格 + 紧凑布局, 侧边栏 224px |

---

## 一、Corti vs iCoDer 40 项差距闭合进度

### 总览

| 优先级 | 总数 | 已修复 | 部分 | 未解决 | 闭合率 |
|--------|------|--------|------|--------|--------|
| P0 | 14 | 11 | 3 | 0 | 78.6% |
| P1 | 15 | 11 | 3 | 1 | 73.3% |
| P2 | 11 | 9 | 1 | 1 | 81.8% |
| **总计** | **40** | **31** | **7** | **2** | **77.5%** |

### 自上版审计以来的变化 (5月15日→5月16日)

5月15日审计时, 大部分 P0/P1/P2 修复已存在于工作区代码中但未提交。经过 `375a77d` (P0 14项)、`36a887a` (P1 15项)、`a476ead` (P2 11项) 等提交, 工作区修复已全部落地。

**本次新合入的闭合项:**

| Gap | 描述 | 合入 Commit |
|-----|------|-------------|
| P0-1~3 | Medical Coding 三视图+证据+替代建议 | `375a77d` (P0 bundle) |
| P0-5~14 | Agent路由/模板/Prompt/Cost/Inspector/Code/SDK | `375a77d` |
| P1-1,3,4,6~10,13~15 | 主题/多类型输入/引导按钮/搜索/计费等 | `36a887a` (P1 bundle) |
| P2-1~4,6~9,11 | AI Studio概览/教程/历史记录/Expand/Save/模板搜索等 | `a476ead` (P2 bundle) |

---

## 二、5月15日审计问题最新状态

| # | 问题 | 5月15日状态 | 5月16日状态 |
|---|------|------------|------------|
| P1-1 (WebSocket STT) | 部分修复, 待验证 | 代码存在但未端到端验证 |
| P1-2 (Runtime safety gaps) | 工作区已修复 | **已提交** (P0 bundle) |
| P1-3 (AgentRunner bypass Runtime) | 工作区已修复 | **已提交** (P0 bundle) |
| P1-4 (Orchestrator skip 5 states) | 工作区已修复 | **已提交** (P0 bundle) |
| P1-5 (Memory data corruption) | 已修复 | 保持不变 |
| P1-6 (Route conflict /api-clients) | 待确认 | 待验证 (APIClientsPage 功能完整) |
| N1 (SSE Manager heartbeat leak) | 有 bug | **已修复** (P2 bundle) |
| N2 (ReviewResponse null) | 已修复 | 保持不变 |
| N3 (GoldCase missing PUT) | 已修复 | 保持不变 |
| N4 (10 models no schema) | 未修复 | 未修复 |
| N5 (evaluation batch stub) | 已修复 | 保持不变 |
| N6 (usage hardcoded) | 已修复 | 保持不变 |
| N8 (frontend mock data) | 多处 mock | 部分改善 (MedicalCoding/Billing/Settings 已接入真实后端) |
| N9 (stt_service global state) | 未修复 | 未修复 |
| N10 (DRG only surgery-based) | 未修复 | 未修复 |
| P2-8 (backend tests unstable) | 待验证 | 待运行 |
| P2-9 (no Alembic migrations) | 未修复 | 未修复 |
| P2-10 (no LLM token monitoring) | 未修复 | 未修复 |

---

## 三、新能力: 超越 Corti 的差异化功能

### 3.1 多码表管理系统 (新增)

**文件**: `backend/app/api/code_tables.py`, `backend/app/models/code_table.py`, `frontend/src/pages/CodeTablePage.tsx`

- 4 个预置码表: ICD-10-CN 国标版(2025)、ICD-10-CN 医保版(2025)、ICD-10-CN 医院本地版、ICD-9-CM-3 国标版(2025)
- CRUD API: GET/POST/DELETE `/api/code-tables`
- 跨表映射: POST `/api/code-tables/map` (一个code → 所有表)
- 编码审核集成: review response 含 `cross_table_view`, 显示主诊断在每个码表中的表达 + 有效性标记

**Corti 对比**: Corti 有 9 种编码系统选择但无"跨表映射"功能。iCoDer 的多码表管理解决中国医疗场景的实际需求(不同医院/医保/卫健委使用不同版本编码字典)。

### 3.2 LLM 主诊断选择 (新增)

**文件**: `backend/app/agents/experts/homepage_expert.py`

从纯规则排序改为 LLM + 规则双路径:
- LLM 接收 `admission_reason` + `candidates` + `clinical_context`
- Corti 风格 prompt: "急性入院原因优先于稳定的慢性病"、".9 未特指码在证据充分时应降权"
- LLM 失败时回退到规则排序

**实测效果**: 肺炎病例主诊断从 I10(高血压) 修正为 J18.9(肺炎), LLM 推理: "Pneumonia is the main reason for admission, requiring acute care"

---

## 四、仍存在的已知问题

### 未解决 (代码层面)

| # | 问题 | 影响 |
|---|------|------|
| P1-5 | Expert Library 缺 "Read more" 文档链接 | 用户无法查看专家详细文档 |
| P2-10 | SupportPage 无 Intercom 实时聊天 | 仅静态链接, 无 AI 优先客服 |
| N4 | 10/18 数据模型无 Pydantic Schema | API 响应未经验证 |
| N8 | FactExtractionPage/HomePage 仍有部分 mock | 用户体验不连贯 |
| N9 | stt_service 全局可变状态非线程安全 | 并发 STT 可能冲突 |
| N10 | DRG grouper 仅基于手术代码 | 内科 DRG 分组不准确 |
| P2-8 | 后端测试不稳定 | CI 不可用 |
| P2-9 | 无 Alembic 迁移 | 生产部署障碍 |
| P2-10 | LLM token 消耗无监控 | 成本控制盲区 |

### 部分解决

| # | 问题 | 当前状态 |
|---|------|---------|
| P0-4 | 编码系统 5 种 vs Corti 9 种 | 复选框 UI, 非 combobox |
| P0-6 | Agent 16 模板 vs Corti 20 | 4 个模板待补充 |
| P0-12 | Embedded Assistant 7 toggle vs Corti 5 | 超出 Corti 但文档不一致 |
| P1-2 | Guided Tour 不完整 | 仅 EmbeddedAssistant 完整 |
| P1-11 | STT CommandVariable enum 有限 | 结构存在 |
| P1-12 | STT 录音 UI 风格差异 | 功能 OK |
| P2-5 | STT Code tab 4 格式 vs 5 | HTML web component 代码未作为 tab |

---

## 五、执行路径图 (当前状态)

```
                       ┌─────────────────────────────────┐
                       │         Frontend Entry           │
                       └──────────────┬──────────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
 POST /api/reviews         POST /api/agents/:id/run    POST /api/agents/:id/stream
 (编码审核)                 (Agent 聊天)                (Agent 流式聊天)
                 │                    │                    │
                 ▼                    ▼                    ▼
      ┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
      │ AgentOrchestrator │  │    AgentRunner        │  │    AgentRunner        │
      │ run_pipeline()    │  │    .run()              │  │    .stream()          │
      └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
               │                       │                          │
      ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
      │ ✅ Runtime 创建   │  │ ✅ Runtime 创建        │  │ ✅ Runtime 创建        │
      │ ✅ 9 状态全流转   │  │ ✅ INGESTED→ARCHIVED  │  │ ✅ INGESTED→ARCHIVED  │
      │ ✅ guard() 3处    │  │ ✅ guard() 门控       │  │ ✅ guard() 门控       │
      │ ✅ guard_post 5处  │  │ ✅ guard_post() 输出  │  │ ✅ guard_post() 输出  │
      │ ✅ check_timeout 5处│ │ ✅ check_timeout()   │  │ ✅ check_timeout()   │
      └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
               │                       │                          │
      ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
      │ 固定 Pipeline     │  │ LLM 规划 →           │  │ LLM 规划 →           │
      │ (13 步全部有      │  │ expert_runner.run()  │  │ expert_runner.stream │
      │  Runtime 门控)    │  │   (逐个调用 expert)  │  │   (逐个调用 expert)  │
      │                   │  │                       │  │                       │
      │ 1. Guardrails     │  │ Routing:              │  │ Routing:              │
      │ 2. Evidence       │  │ - single_expert       │  │ - single_expert       │
      │ 3. Timeline       │  │ - fixed_order         │  │ - fixed_order         │
      │ 4. ClinicalTriage │  │ - llm_plan (default)  │  │ - llm_plan (default)  │
      │ 5. Diagnosis (LLM)│  └───────────────────────┘  └───────────────────────┘
      │ 6. Procedure      │
      │ 7. Homepage(LLM)  │    ┌──────────────────────────┐
      │ 8. Evidence Verify│    │ run_intelligent_pipeline  │
      │ 9. Ranking/Disag. │    │ ❌ 仍无 Runtime           │
      │ 10. Confidence    │    │ ❌ 仍无 Guardrails        │
      │ 11. DRG + DocGap  │    └──────────────────────────┘
      │ 12. Report+Reason │
      │ 13. Guardrails out│
      └────────────────────┘

图例: ✅ = 已集成  ⚠️ = 部分集成  ❌ = 完全缺失
```

---

## 六、推荐下一步 (优先级排序)

### 立即 (本周)

1. **端到端验证 P1-1 (WebSocket STT)** — 启动前后端, 确认 `/ws/speech-to-text` 可用
2. **端到端验证 P1-6 (路由冲突)** — 确认 APIClientsPage 前端正常访问
3. **关闭剩余 2 项未解决 gap** — P1-5 (Read more 链接) + P2-10 (Intercom widget)

### 短期 (1-2 周)

4. **补齐部分解决项** — P0-4 (编码系统扩展到 9 种) / P0-6 (模板补齐到 20) / P1-2 (全局 Tour 系统)
5. **修复 N9 (STT 线程安全)** — 为 `_stt_model` 添加锁保护
6. **修复 N10 (DRG 分组器)** — 纳入诊断代码

### 中期

7. **N4 (Pydantic Schema 补齐)** — 至少覆盖 Agent/Expert/ApiKey
8. **N8 (消除 mock 数据)** — FactExtractionPage/HomePage
9. **前端测试初始化** — 核心页面组件测试

---

## 附录: 全栈收敛度量 (更新)

| 层面 | 指标 | 5月15日 | 5月16日 |
|------|------|---------|---------|
| Corti gap P0 | 闭合率 | 21% (3/14) | **78.6% (11/14)** |
| Corti gap P1 | 闭合率 | 7% (1/15) | **73.3% (11/15)** |
| Corti gap P2 | 闭合率 | 0% (0/11) | **81.8% (9/11)** |
| Corti gap 总闭合率 | — | 10% (4/40) | **77.5% (31/40)** |
| 前端页面 | 功能完整 | 21/24 (88%) | 23/24 (96%) |
| 后端端点 | 完全实现 | ~96/102 (94%) | ~98/102 (96%) |
| iCoDer 独有功能 | — | 10 项 | **13 项** (+ 多码表管理, LLM主诊断, cross_table_view) |
