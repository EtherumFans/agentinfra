# README_INDEX — iCoDer 文档索引

> **声明**: 本文档是 iCoDer 文档库的总入口, 提供 5 分钟新人了解全局的阅读路径.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后
> **状态**: MAINLINE — 取代零散文档入口

---

## 0. 5 分钟了解 iCoDer

**iCoDer 是什么**: 面向中国医院场景的 **Corti-style 医疗 Agent Runtime 平台**, 以托管云 SaaS 形式交付 (Environments: EU / US / CN; 医院 = Tenant; HIS/EMR = API Client).

**架构 4 层**:
```
第四层: Business Workbenches   app/api/*         ~190 endpoints (Studio Tools)
第三层: Pre-built Agents       official_agents/   16 pack (Corti 20 目标)
第二层: Agentic Framework      app/icoder/agent_runtime/  A2A + MCP + Context + Orchestrator (spec 完整, 主线待切)
第一层: Runtime Core           icoder_runtime/   AgentRunner + LLMGateway + Registry + DataPolicy
```

**主线方向** (P1.3 拍板, 见 `docs/product/PRODUCT_DIRECTION.md`):
- Corti-style 平台 = 主体
- MedCodER 5-stage 管线 = Pre-built Agent #18 的实现选项 (不是产品本身)
- 不做 F1 提升 / 模型训练 / SaaS 后台堆叠
- 托管云 SaaS (单域名子路径模式), 不做私有化

**当前状态**: P1.3 审计后总分 65.94/100 (PARTIALLY_ALIGNED), P1.3 后预期 ~75, Phase 2-4 后 ~90.

---

## 1. 新人 5 步阅读路径

| 步 | 文档 | 用时 | 目的 |
|---|---|---|---|
| 1 | `CLAUDE.md` (项目根) | 1 min | 项目宪法: 产品定位 + 架构层次 + 启动命令 + 金标准 |
| 2 | `docs/README_INDEX.md` (本文档) | 1 min | 文档地图 + 阅读路径 |
| 3 | `docs/product/PRODUCT_DIRECTION.md` | 1 min | 主线声明 + MedCodER 降级 + 不做清单 |
| 4 | `docs/architecture/CURRENT_ARCHITECTURE.md` | 1.5 min | 4 层架构 + 主线/实验/legacy 三类资产 |
| 5 | `docs/product/CORTI_PARITY_ROADMAP.md` | 0.5 min | P1.3 + Phase 2-4 路线图 |

读完这 5 份, 应能回答:
- iCoDer 是什么? (Corti-style 医疗 Agent Runtime 平台)
- 4 层架构是什么? (Studio Tools / Pre-built Agents / Agentic Framework / Runtime Core)
- MedCodER 在哪个位置? (Pre-built Agent #18, 不是产品主体)
- 当前完成度? (65.94/100, PARTIALLY_ALIGNED)
- 下一步做什么? (P1.3 → Phase 2 → Phase 3 → Phase 4)

---

## 2. 文档树 (按类别)

### 2.1 方向性文档 (P1.3 新写, MAINLINE)

```
docs/
├── README_INDEX.md                              ← 本文档 (总入口)
├── product/
│   ├── PRODUCT_DIRECTION.md                     ← 主线声明 + MedCodER 降级
│   └── CORTI_PARITY_ROADMAP.md                  ← P1.3 + Phase 2-4 路线图
├── architecture/
│   ├── CURRENT_ARCHITECTURE.md                  ← 4 层架构当前状态
│   └── MAINLINE_VS_LEGACY.md                    ← 三层分类清单 (Mainline/Experimental/Legacy)
├── backlog/
│   ├── PRODUCT_BACKLOG.md                       ← 产品 backlog (P1.3 + Phase 2-4)
│   └── TECH_DEBT_BACKLOG.md                     ← 技术债 backlog (107 项)
└── corti_parity/
    ├── CORTI_REFERENCE_BASELINE.md              ← Stage 0: Corti 参考基线
    ├── ICODER_ASSET_INVENTORY.md                ← Stage 1: iCoDer 资产清单
    ├── CORTI_PARITY_GAP_ANALYSIS.md             ← Stage 2: 20 维度 gap 分析
    └── DIRECTION_CORRECTION_PLAN.md             ← Stage 3: 方向纠偏计划
```

### 2.2 Corti 对齐审计 (P1.3 Stage 0-3)

| 文档 | 内容 |
|---|---|
| `corti_parity/CORTI_REFERENCE_BASELINE.md` | Corti 产品定位 / 4 域架构 / Sidebar 15 项 / Home 4 tabs / 5 Studio tool API / 20 Pre-built Agents / Agentic Framework (A2A + Agent Card + Task + Message + Part + Artifact) / URL 对齐表 / 视觉系统 |
| `corti_parity/ICODER_ASSET_INVENTORY.md` | 38 backend API + 50+ services + 3 套 Agent 架构 + 16 agent pack + 30 frontend page + 90+ docs 清单, 含 keep/archive/deprecate 标签 |
| `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` | 20 维度打分 (0-5), 总分 65.94, 判定 PARTIALLY_ALIGNED, 5 aligned + 11 partial + 4 severe |
| `corti_parity/DIRECTION_CORRECTION_PLAN.md` | 5 项最大偏离 + 模块分类 + 新主线定义 + sidebar nav 建议 + P1.3 行动项 + 风险 + 成功标准 20 项 |

### 2.3 架构 & 规范 (Agentic Framework spec)

```
docs/
├── ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md  ← 总 RFC (4 sub-spec)
├── ICODER_V1_ORCHESTRATOR_SPEC.md               ← Orchestrator 5 态状态机
├── ICODER_V1_A2A_SPEC.md                        ← A2A JSON-RPC 2.0 + Agent Card v0.3
├── ICODER_V1_CONTEXT_SPEC.md                    ← Context UUID + 三层隔离 + GC 策略
├── ICODER_V1_MCP_SPEC.md                        ← MCP server 8 工具 + Expert as client
├── ICODER_V1_AGENT_CARD_SPEC.md                 ← AgentDefinition / ExpertCard / AgentCard 三层
└── ICODER_V1_TASK_SPEC.md                       ← Task 5 态 (Phase 1 stub, Phase 5 完整)
```

### 2.4 云部署

```
docs/cloud/
├── CLOUD_DEPLOYMENT.md                          ← 托管云部署总文档 (3 层 Env/Tenant/API Client)
├── API_CLIENT_MODEL.md                          ← backend-service vs ROPC embedded 模型
├── MULTI_REGION.md                              ← EU/US/CN 三 region 路由
└── CLOUD_INTAKE_TEMPLATE.md                     ← 客户接入模板
```

### 2.5 开发运维

```
docs/dev/
└── BACKEND_RECOVERY.md                          ← 后端 DB 恢复 runbook (cycle 23)
```

### 2.6 审计修复历史 (E1.x, 已闭环)

```
docs/audit_remediation/
├── PHASE_B_REPORT.md
├── PHASE_C_REPORT.md
├── E1_1_REAL_BOOT_GATE_REPORT.md
├── E1_2_ASSET_WIRING_AUDIT.md
└── E1_2_REAL_RETRIEVAL_BASELINE.md
```

### 2.7 API & SDK 参考

```
docs/
├── ARCHITECTURE.md                              ← 旧架构文档 (legacy, 逐步替换)
├── TECHNICAL-DESIGN.md                          ← 技术设计 (legacy)
├── agent-pack.md                                ← .icoder-agent 包格式
├── runtime.md                                   ← Runtime 旧文档
├── QUICKSTART.md                                ← 快速开始
├── SDK-TUTORIAL.md                              ← SDK 教程
├── PRODUCT-MODULES.md                           ← 产品模块清单
└── sdk/
    ├── js.md                                    ← JS SDK
    └── python.md                                ← Python SDK
```

### 2.8 操作手册 (旧, 逐步归档)

```
docs/operation-manual/
├── 01-HomePage.md ~ 22-Docs.md                  ← 22 页操作手册 (legacy, P2 归档)
└── SUMMARY.md
```

### 2.9 归档区 (P1.3 Stage 5 归档, 90+ 历史文档)

```
docs/archive/                                    ← P1.3 Stage 5 创建, 含 90+ 历史审计/对比/冲刺文档
```

详见 `docs/corti_parity/ASSET_CLEANUP_REPORT.md` (Stage 5 输出).

---

## 3. 关键概念速查

| 概念 | 定义 | 出处 |
|---|---|---|
| **Corti-style 平台** | 医疗 Agent Runtime 平台范式 (4 域 + Agentic Framework + Pre-built Agents + Studio Tools) | `product/PRODUCT_DIRECTION.md` §1-2 |
| **4 层架构** | Studio Tools / Pre-built Agents / Agentic Framework / Runtime Core | `architecture/CURRENT_ARCHITECTURE.md` §1 |
| **MedCodER 降级** | 5-stage ICD 编码管线 = Pre-built Agent #18, 不是产品主体 | `product/PRODUCT_DIRECTION.md` §4 |
| **3 类资产** | Mainline (主线) / Experimental (实验) / Legacy-Deprecated (废弃) | `architecture/MAINLINE_VS_LEGACY.md` §1 |
| **20 Pre-built Agents** | Corti 标准 agent 清单, iCoDer 已 3/20, 缺 17 | `corti_parity/CORTI_REFERENCE_BASELINE.md` §10 |
| **Agentic Framework** | A2A + Agent Card + Task + Context + MCP + Orchestrator | `ICODER_V1_*.md` (7 sub-spec) |
| **A2A 协议** | JSON-RPC 2.0 + Part (Text/Data/File) + Message + Task + Agent Card v0.3 | `ICODER_V1_A2A_SPEC.md` |
| **托管云 SaaS** | Env (EU/US/CN) → Tenant (医院) → API Client (backend/ROPC) | `cloud/CLOUD_DEPLOYMENT.md` |
| **PHI 脱敏** | 原始 PHI 不进云审计通道, 仅脱敏样本用于合规审计 | `CLAUDE.md` Runtime Core 职责 |
| **金标准评估** | 201 cases, per-case micro-F1, subdivision-tolerant | `CLAUDE.md` §金标准评估 |
| **20 维度 gap** | iCoDer vs Corti 对齐评分, 当前 65.94/100 | `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` |

---

## 4. 角色阅读路径

### 4.1 新人 (5 分钟)

按 §1 顺序读 5 份文档.

### 4.2 后端工程师 (30 分钟)

1. §1 五份 (5 min)
2. `architecture/CURRENT_ARCHITECTURE.md` (full, 5 min)
3. `architecture/MAINLINE_VS_LEGACY.md` (5 min)
4. `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (10 min)
5. `CLAUDE.md` §MedCodER 管线 (5 min)

### 4.3 前端工程师 (20 分钟)

1. §1 五份 (5 min)
2. `corti_parity/CORTI_REFERENCE_BASELINE.md` §3-5 (Sidebar IA + Home 4 tabs + Workbench) (5 min)
3. `product/CORTI_PARITY_ROADMAP.md` §1.3 (UI IA 最小纠偏) (5 min)
4. `frontend/src/pages/` + `frontend/src/components/` (5 min)

### 4.4 产品经理 (15 分钟)

1. `product/PRODUCT_DIRECTION.md` (3 min)
2. `product/CORTI_PARITY_ROADMAP.md` (5 min)
3. `backlog/PRODUCT_BACKLOG.md` (5 min)
4. `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` §1 + §20 (2 min)

### 4.5 DevOps (15 分钟)

1. `cloud/CLOUD_DEPLOYMENT.md` (5 min)
2. `dev/BACKEND_RECOVERY.md` (5 min)
3. `CLAUDE.md` §启动命令 (5 min)

---

## 5. 文档不在哪里 (避免误读)

| 误读 | 真实位置 |
|---|---|
| MedCodER 是产品主体? | 不是. `PRODUCT_DIRECTION.md` §4 明确降级为 Pre-built Agent #18 |
| 私有化部署? | 不做. `cloud/CLOUD_DEPLOYMENT.md` 仅托管云 SaaS |
| icoder-next 切片? | 已逆转. `PRODUCT_DIRECTION.md` §6 全产品 frontend |
| F1 提升实验? | 不做. `backlog/PRODUCT_BACKLOG.md` §5 永不上主线 |
| 旧 PRODUCT-ROADMAP.md? | 已被 `product/CORTI_PARITY_ROADMAP.md` 取代 |
| 旧 ARCHITECTURE.md? | 已被 `architecture/CURRENT_ARCHITECTURE.md` 取代 |

---

## 6. 文档维护规则

- **新增文档**: 优先放 `docs/{category}/`, 不放 repo root
- **命名**: ALL_CAPS_WITH_UNDERSCORES.md (与现有约定一致)
- **frontmatter**: 必含 `声明 / 日期 / 阶段 / 状态` 4 行
- **变更日志**: 每份文档末尾必含 `## 变更日志` 表 (日期 / 变更 / 触发)
- **归档**: 旧文档移到 `docs/archive/`, 不删除 (历史可查)
- **废弃标记**: 在文档顶部加 `> ⚠ DEPRECATED (2026-07-02): 见 XXX.md`

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, 文档索引 + 5 分钟新人路径 | P1.3 Stage 4 文档重写 |
