> **DEPRECATED (Phase 2-F / 2026-07-02 — TD-101)**: 本文档为旧版模块描述, 已被新版替代.
> 当前主线参考: [docs/product/PRODUCT_DIRECTION.md](product/PRODUCT_DIRECTION.md) + [docs/architecture/CURRENT_ARCHITECTURE.md](architecture/CURRENT_ARCHITECTURE.md)
> 不再定位为 "Corti-competitive"; 当前定位 = Corti-style 医疗 Agent Runtime 平台 (近 1:1 复刻).
> 保留仅作历史参考 — 勿据此文档做模块决策.

# iCoDer — Clinical AI Platform (DEPRECATED)

## 产品定位

iCoDer 是**Corti-competitive 临床 AI 平台**。预置编码审核、语音转录、文书生成、事实提取、嵌入助手等即开即用的临床 AI 能力，同时提供 Agent Runtime（多租户、Marketplace、合同强制工具系统、Deny-First 安全模型）、SDK/API、Web Components 供 HIS 厂商和第三方开发者深度集成与二次开发。

**核心差异**：每步决策**可审计**——编码溯源到病历原文，决策链 SHA-256 哈希可重放，满足医保纠纷举证和合规要求。这不是定位边界，而是保证 AI 安全性的基础设施。

---

## 一、Agent Runtime 引擎

### 1.1 合同强制型工具系统

双层工具架构，每个工具携带机器可验证的 Hoare 式 `{前置条件} 工具 {后置条件}` 合同。

| 层级 | 数量 | 说明 |
|------|------|------|
| Tier 1 确定性核心 | 7 | 零LLM参与——ICD索引导航、证据排名、置信度校准、分歧分析、安全护栏 |
| Tier 2 LLM推理 | 10 | LLM辅助——证据提取、编码分配、DRG分析、文档缺口检查、报告生成 |

**合同执行流程**：LLM提议工具调用 → Harness验证前置条件 → 执行工具 → Harness验证后置条件 → 通过则写入符号状态，拒绝则反馈LLM修正。

### 1.2 工具注册表 (ToolRegistry)

17个工具在6个分类下注册，每个工具包含完整元数据：

- 前置条件表达式 (`requires`)：声明调用前必须满足的条件
- 后置条件表达式 (`guarantees`)：声明工具产出的保证
- 准确度标签 (`accuracy_tags`)：用于自动注入保障步骤
- 可注入标记 (`is_injectable`)：Tier 1工具可被Harness自动注入

| 分类 | 工具 |
|------|------|
| 安全护栏 | guard_input, guard_output |
| 信息提取 | extract_evidence, reconstruct_timeline |
| 编码 | search_icd10_index, search_icd9_index, assign_diagnosis_code, assign_procedure_code |
| 验证 | rank_evidence, calibrate_confidence, verify_evidence, analyze_disagreements |
| 分析 | analyze_drg_impact, check_documentation_gaps, cdi_review |
| 报告 | format_report, generate_cdi_query |

### 1.3 执行模式

| 模式 | 说明 |
|------|------|
| `tool_native` | LLM自主选择工具，Harness合同强制验证（新增） |
| `llm_plan` | LLM动态规划Expert调用序列 |
| `fixed_order` | 按列表顺序串行调用Expert |
| `single_expert` | 仅调用默认Expert |

### 1.4 符号状态引擎 (SymbolicState)

类型化的受信世界状态。只有通过合同后置条件验证的工具输出才能写入。LLM不能直接修改状态，防止幻觉数据污染。

### 1.5 Tier1 自动注入

Harness根据已启用工具的 `accuracy_tags` 自动注入必要的Tier1保障步骤：
- 编码工具 → 自动注入 `search_icd10_index` + `rank_evidence` + `calibrate_confidence`
- 所有工具 → 自动注入 `guard_input` + `guard_output`

---

## 二、Deny-First 权限模型

### 2.1 权限策略

每个工具默认 `allowed: false`。Agent创建时必须选择权限策略，显式授权工具。

| 预置策略 | 工具数 | 适用场景 |
|---------|--------|---------|
| medical_coding | 15 | 标准医学编码管道 |
| cdi_audit | 9 | 临床文档审核（只读分析，不允许编码分配） |
| drg_analysis | 11 | DRG/DIP支付影响分析 |
| restrictive | 6 | 严格模式（仅确定性工具） |
| full_access | 17 | 全部工具可用（仅开发/管理） |

### 2.2 权限检查流程

每个工具调用前：检查是否 `allowed` → 检查是否超 `max_per_session` → 检查是否需要 `requires_human` 审批。全部通过才允许执行。

### 2.3 人机协同门 (DUC)

高风险操作标记为 `requires_human: true`，需人工审批后才能执行。如：主诊断最终确认（影响DRG分组和医保支付）。

---

## 三、安全体系

### 3.1 凭据隔离 (CredentialVault)

- 凭据从环境变量读取，永不出现在代码、日志、审计记录中
- `ICODER_CREDENTIAL_LLM` 提供LLM API密钥
- 支持按服务名解析（`llm`, `pubmed`, `drugbank`, `posos` 等）
- 健康检查可列出所有已配置/未配置的服务

### 3.2 审计链 (AuditChain)

- Append-only事件日志，不可删除、不可修改
- 每个事件带 SHA-256 哈希
- `verify_integrity()` 验证链完整性
- `replay()` 重放完整决策链，用于合规审计和医保纠纷

### 3.3 安全护栏 (Guardrails)

| 规则 | 级别 | 说明 |
|------|------|------|
| 处方拦截 | 错误 | 阻止AI输出药物处方建议 |
| 诊断免责声明 | 警告 | 编码建议自动添加免责声明 |
| 急诊分诊拦截 | 错误 | 防止AI执行急诊分诊建议 |
| 可疑编码格式 | 警告 | 检测异常精确编码（可能是幻觉） |
| PHI检测 | 警告 | 扫描身份证/手机号/邮箱 |
| 屏蔽词检测 | 错误 | 检测安全攻击关键词 |

### 3.4 登录安全

- 登录限流：5次/5分钟/IP，超限返回429
- Token吊销：密码修改或登出时批量吊销
- 密码重置Token：1小时有效期，一次性使用
- 防用户枚举：forgot-password始终返回202

---

## 四、账号体系

### 4.1 认证方式

| 方式 | 端点 | 说明 |
|------|------|------|
| 用户名密码登录 | `POST /api/auth/login` | JWT access + refresh token |
| 注册 | `POST /api/auth/register` | 自动创建组织，注册者成为Owner |
| OAuth 2.0 M2M | `POST /api/oauth/token` | Client Credentials Grant |
| API Key | `POST /api/keys` | sk-前缀密钥，SHA-256哈希存储 |
| Token刷新 | `POST /api/auth/refresh` | 使用refresh_token获取新access_token |

### 4.2 账户管理

| 功能 | 端点 |
|------|------|
| 修改密码 | `POST /api/auth/change-password` |
| 忘记密码 | `POST /api/auth/forgot-password` |
| 重置密码 | `POST /api/auth/reset-password` |
| 吊销Token | `POST /api/auth/revoke-tokens` |
| 个人信息 | `GET /api/auth/me` |
| 切换组织 | `POST /api/auth/switch-org` |

### 4.3 角色体系

| 角色 | 权限 |
|------|------|
| admin | 系统管理 |
| coder | 编码员 |
| dept_head | 科室负责人 |
| insurance | 医保办 |
| qc | 质控科 |
| clinician | 临床医生 |
| it | 信息科 |

### 4.4 多租户

- Organization + OrganizationMember 模型
- 注册时自动创建组织
- 支持多组织切换（switch-org）
- 组织角色：owner / admin / member / viewer

---

## 五、编码审核管道

### 5.1 管道流程

```
Encounter创建 → 9步编码审核管道 → Review → 人工审核 → ARCHIVED
```

| 步骤 | 说明 |
|------|------|
| 1. 证据提取 | 从病历文档提取结构化临床事实 |
| 2. 时间线重建 | 重建临床事件时间线 |
| 3. 临床分诊 | 事实分类：可编码/病史/已排除/偶发性 |
| 4. ICD诊断编码 | ICD-10-CN索引导航 + 编码分配 |
| 5. 手术编码 | ICD-9-CM-3手术编码分配 |
| 6. 首页编码+规则校验 | 主诊断/主手术确定 |
| 7. 证据验证+排名 | 证据强度评分 + 冲突检测 |
| 8. DRG/DIP分析+文档缺口 | 支付影响分析 + 文档完整性检查 |
| 9. 报告生成 | Markdown/HTML审核报告 |

### 5.2 管道API

| 端点 | 说明 |
|------|------|
| `POST /api/encounters` | 创建病历 |
| `POST /api/encounters/text` | 从自由文本创建病历 |
| `POST /api/reviews` | 运行编码审核管道（支持async模式） |
| `GET /api/reviews` | 审核列表 |
| `GET /api/reviews/{id}` | 审核详情（含报告） |
| `GET /api/reviews/tasks/{id}` | 轮询异步任务状态 |
| `PUT /api/reviews/{id}/complete` | 标记人工审核完成 |

---

## 六、AI Studio 模块

### 6.1 语音转录 (Speech to Text)

- 引擎：Medvoice / Web内置
- 听写语言：简体中文 / English (US)
- 语音指令：跳转段落、撤销录入、插入模板、新建段落、句号
- 标点：语音标点、自动标点

### 6.2 文书生成 (Text Generation)

- 输入类型：自由文本 / 对话转录 / 结构化事实JSON
- 文书模板选择
- 质控模式：标准 / 严格 / 草稿
- 输出语言：简体中文 / English (US)

### 6.3 事实提取 (Fact Extraction)

- 从病历文本提取结构化临床事实
- 支持使用样例
- 输出语言选择

### 6.4 医学编码 (Medical Coding)

- 编码系统选择（ICD-10-CN国标版/医保版、ICD-9-CM-3国标版）
- 包含/排除编码过滤
- 置信度阈值可调
- Event Inspector 实时事件监控

### 6.5 嵌入助手 (Embedded Assistant)

- iframe预览
- 会话设置：语言/模式/UI选项
- 外观配置：主题/语言/听写语言
- 首次使用引导

### 6.6 Agent 管理

| 功能 | 说明 |
|------|------|
| Agent 创建 | 名称 + 系统提示词 + 工具选择 + 权限策略 + 路由策略 |
| Agent 模板 | 20个预置模板 |
| Agent 测试 | 内置聊天界面，实时测试 |
| Agent 发布 | draft → published |
| Agent 市场 | 社区分享 |

---

## 七、管理功能

### 7.1 API 客户端管理

- OAuth 2.0 客户端创建和管理
- API Key 创建/列表/吊销
- Client Credentials 认证

### 7.2 团队管理

- 团队成员列表
- 邀请成员（按角色）
- 移除成员

### 7.3 计费与用量

- 额度余额查看
- 充值入口
- 累计消耗统计
- API请求数监控
- 时间范围筛选（7天/30天/90天）
- 对比周期

### 7.4 设置

- 账户信息（用户名/姓名/角色/科室/国家）
- 修改密码
- 安全护栏配置（6条规则+状态查看）
- 编码体系设置（默认编码系统/置信度阈值）
- API限流配置（100 req/min滑动窗口）
- 通知偏好（每日摘要/异常告警/浏览器通知）
- 30个A2A Agent注册表
- 组织管理（成员/邀请/角色）

### 7.5 数据管理

| 功能 | 说明 |
|------|------|
| 金标准病例 | CSV导入/列表/难度/准确率 |
| AI智能体评估 | 执行评估/A/B对比/历史 |
| 专家库 | 30个注册Expert的浏览和管理 |

---

## 八、技术架构

### 8.1 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy async + SQLite |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS |
| LLM | DeepSeek (deepseek-chat) via OpenAI-compatible API |
| 认证 | JWT (HS256) + OAuth 2.0 Client Credentials |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |

### 8.2 API 设计

- RESTful API + WebSocket 实时推送
- SSE 流式响应
- Swagger/OpenAPI 文档
- 版本化端点 (`/v1/`)
- 统一错误格式

### 8.3 安全设计

- Deny-First权限模型
- 凭据隔离（无明文密钥）
- Append-only审计链
- 登录限流
- 6条安全护栏规则
- 人机协同门（高风险操作）
- 合同强制型工具验证

### 8.4 SDK 支持

- JavaScript/TypeScript SDK
- C# .NET SDK
- Python SDK
- Postman Collection

---

## 九、测试覆盖

| 层级 | 数量 | 说明 |
|------|------|------|
| 单元测试 | 577 passed | 服务/模型/API |
| 跳过 | 1 skipped | 条件跳过 |
| 预期失败 | 10 xfailed | LLM响应波动（非代码缺陷） |
| 集成测试 | 4 passed | 完整业务流程 |

---

## 十、部署

### 环境变量

| 变量 | 必须 | 说明 |
|------|------|------|
| `ICODER_CREDENTIAL_LLM` | 是 | LLM API密钥 |
| `ICODER_SECRET_KEY` | 是 | JWT签名密钥（自动生成48位随机值） |
| `VITE_API_TARGET` | 否 | 前端API代理目标（默认localhost:8000） |

### 默认账号

部署后运行 `python -c "from app.seed import seed; import asyncio; asyncio.run(seed())"` 创建演示数据。

---

## 附录：功能清单

### Agent Runtime 引擎

| # | 功能 | 状态 |
|----|------|------|
| 1 | ToolRegistry — 17个工具在6个分类下注册 | ✅ |
| 2 | Tier1确定性工具 — 零LLM (ICD索引/证据排名/置信度校准/护栏) | ✅ |
| 3 | Tier2 LLM推理工具 — LLM辅助 (证据提取/编码分配/报告) | ✅ |
| 4 | 合同强制 — 每个工具的前置/后置条件由Harness以确定性代码验证 | ✅ |
| 5 | 前置条件拒绝 → LLM接收反馈 → 自动修正 → 重试 | ✅ |
| 6 | 后置条件拒绝 → 结果不写入SymbolicState → LLM必须重试 | ✅ |
| 7 | SymbolicState — 类型化受信状态，只能通过已验证工具调用写入 | ✅ |
| 8 | Tier1自动注入 — 根据accuracy_tags自动注入保障步骤 | ✅ |
| 9 | tool_native路由 — LLM自主选择工具顺序 | ✅ |
| 10 | llm_plan路由 — LLM动态规划Expert序列 | ✅ |
| 11 | fixed_order路由 — 固定顺序串行Expert | ✅ |
| 12 | single_expert路由 — 单Expert直连 | ✅ |
| 13 | SSE流式tool_native执行 — 实时步骤进度推送 | ✅ |
| 14 | 工具依赖解析 — resolve_dependencies()自动排序 | ✅ |
| 15 | API: GET /api/tools — 工具目录（含合同元数据） | ✅ |
| 16 | API: GET /api/tools/categories — 分类统计 | ✅ |

### 权限系统

| # | 功能 | 状态 |
|----|------|------|
| 17 | Deny-First权限模型 — 所有工具默认allowed:false | ✅ |
| 18 | PermissionPolicy — 5个预置策略 | ✅ |
| 19 | medical_coding预置 — 15个工具 | ✅ |
| 20 | cdi_audit预置 — 9个工具（只读分析） | ✅ |
| 21 | drg_analysis预置 — 11个工具 | ✅ |
| 22 | restrictive预置 — 6个工具（仅确定性） | ✅ |
| 23 | full_access预置 — 17个工具（开发/管理） | ✅ |
| 24 | 每工具速率限制 — max_per_session | ✅ |
| 25 | 人机协同门 — requires_human标记 | ✅ |
| 26 | 权限策略序列化/反序列化 — to_config()/from_config() | ✅ |
| 27 | API: GET /api/tools/permission-presets — 预置策略列表 | ✅ |
| 28 | UI: 权限策略下拉选择器（Agent详情页→设置） | ✅ |

### 安全体系

| # | 功能 | 状态 |
|----|------|------|
| 29 | CredentialVault — 凭据从环境变量读取 | ✅ |
| 30 | 无明文API Key — config.py和.env中无硬编码密钥 | ✅ |
| 31 | 按服务名解析凭据 (llm/pubmed/drugbank/posos等) | ✅ |
| 32 | 健康检查 — health_check()列出已配置服务 | ✅ |
| 33 | AuditChain — Append-only事件日志 | ✅ |
| 34 | verify_integrity() — 哈希链完整性验证 | ✅ |
| 35 | replay() — 审计链重放 | ✅ |
| 36 | 护栏: 处方拦截 (错误级) | ✅ |
| 37 | 护栏: 诊断免责声明 (警告级) | ✅ |
| 38 | 护栏: 急诊分诊拦截 (错误级) | ✅ |
| 39 | 护栏: 可疑编码格式检测 (警告级) | ✅ |
| 40 | 护栏: PHI检测 (警告级) | ✅ |
| 41 | 护栏: 屏蔽词检测 (错误级) | ✅ |
| 42 | 登录限流 — 5次/5分钟/IP | ✅ |
| 43 | Token吊销 — 批量吊销（密码修改/登出时） | ✅ |
| 44 | 密码重置Token — 1小时有效期/一次性 | ✅ |
| 45 | 防用户枚举 — forgot-password始终202 | ✅ |
| 46 | DeterministicRuntime — 14状态机+状态超时+动作门控 | ✅ |
| 47 | SECRET_KEY自动生成 — 默认48位随机值 | ✅ |
| 48 | DEBUG/APP_ENV可配置 | ✅ |

### 账号体系

| # | 功能 | 状态 |
|----|------|------|
| 49 | 用户名密码登录 — JWT access+refresh token | ✅ |
| 50 | 注册 — 自动创建组织，注册者为Owner | ✅ |
| 51 | 忘记密码 — 邮箱发送重置链接 | ✅ |
| 52 | 重置密码 — Token验证+密码更新+旧Token吊销 | ✅ |
| 53 | 修改密码 — 需当前密码验证 | ✅ |
| 54 | Token刷新 — refresh_token换新access_token | ✅ |
| 55 | Token吊销 — 登出所有设备 | ✅ |
| 56 | OAuth 2.0 M2M — Client Credentials Grant | ✅ |
| 57 | API Key — 创建/列表/吊销 | ✅ |
| 58 | 7种用户角色 (admin/coder/dept_head/insurance/qc/clinician/it) | ✅ |
| 59 | 多租户 — Organization + OrganizationMember | ✅ |
| 60 | 组织切换 — switch-org | ✅ |
| 61 | 组织角色 — owner/admin/member/viewer | ✅ |
| 62 | 审计日志 — login/logout/register事件记录 | ✅ |
| 63 | UI: 登录页 (登录/注册/忘记密码三模式) | ✅ |
| 64 | UI: 修改密码卡片 (Settings页) | ✅ |
| 65 | UI: API Key管理页 | ✅ |

### 编码审核管道

| # | 功能 | 状态 |
|----|------|------|
| 66 | Encounter创建 — 结构化+自由文本两种方式 | ✅ |
| 67 | 9步编码审核管道 — 证据提取→编码→验证→DRG→报告 | ✅ |
| 68 | async模式 — 后台执行+WebSocket进度推送 | ✅ |
| 69 | 任务轮询 — GET /api/reviews/tasks/{id} | ✅ |
| 70 | 审核报告 — Markdown+HTML双格式 | ✅ |
| 71 | 人工审核流程 — pending→in_review→completed→archived | ✅ |
| 72 | 主诊断推理 (primary_diagnosis_reasoning) | ✅ |
| 73 | 证据排名+冲突检测 (rank_all_evidence) | ✅ |
| 74 | 置信度校准 (calibrate_all) — AUTO/REVIEW/ESCALATE | ✅ |
| 75 | 分歧分析 (analyze_disagreements) — AI vs 金标准 | ✅ |
| 76 | 文档缺口分析 (DocumentationGapExpert) | ✅ |
| 77 | DRG/DIP支付影响分析 | ✅ |
| 78 | CDI临床文档改进审查 | ✅ |
| 79 | 批量审核 — POST /api/reviews/batch | ✅ |
| 80 | 33,304 ICD-10-CN + 23,165 ICD-9-CM-3编码字典 | ✅ |
| 81 | 模糊匹配编码搜索 (rapidfuzz) | ✅ |

### AI Studio

| # | 功能 | 状态 |
|----|------|------|
| 82 | 语音转录 — Medvoice引擎/中英双语/语音指令 | ✅ |
| 83 | 文书生成 — 3种输入类型/模板选择/质控模式 | ✅ |
| 84 | 事实提取 — 结构化事实输出 | ✅ |
| 85 | 医学编码 — 编码系统选择/过滤/置信度阈值/Event Inspector | ✅ |
| 86 | 嵌入助手 — iframe预览/外观配置/会话设置 | ✅ |
| 87 | Agent管理 — 创建/编辑/删除/测试/发布 | ✅ |
| 88 | Agent模板 — 20个预置模板 | ✅ |
| 89 | Agent测试 — 内置聊天界面（支持tool_native执行） | ✅ |
| 90 | 工具选择器 — ToolSelector组件（分类浏览/T1T2标记/合同详情） | ✅ |
| 91 | 路由策略选择器 — 5种模式可选 | ✅ |
| 92 | Expert绑定 — 浏览/添加/拖拽排序 | ✅ |
| 93 | Agent市场 — 社区分享入口 | ✅ |
| 94 | A2A Agent协作 — 30个注册Agent/链式调用 | ✅ |
| 95 | 多语言SDK代码片段生成 (JS/.NET/Python/cURL) | ✅ |

### 管理功能

| # | 功能 | 状态 |
|----|------|------|
| 96 | 首页仪表板 — 用量图表/快速入口/API统计 | ✅ |
| 97 | API客户端管理 — OAuth客户端创建/列表 | ✅ |
| 98 | 团队管理 — 成员列表/邀请/移除 | ✅ |
| 99 | 计费 — 额度余额/充值/消耗统计 | ✅ |
| 100 | 用量监控 — API请求数/响应时间/时间筛选 | ✅ |
| 101 | 设置 — 账户/密码/护栏/编码体系/限流/通知/组织 | ✅ |
| 102 | 金标准病例 — CSV导入/列表/难度标记 | ✅ |
| 103 | AI智能体评估 — 执行评估/A/B对比/历史 | ✅ |
| 104 | 专家库 — 30个Expert注册表 | ✅ |
| 105 | 开发者快速入门 — SDK文档链接 | ✅ |
| 106 | 支持 — 在线咨询/提交工单 | ✅ |

### 技术基础设施

| # | 功能 | 状态 |
|----|------|------|
| 107 | 577单元测试 + 10xfail(LLM flaky) — 零真实失败 | ✅ |
| 108 | 4个E2E集成测试 — 完整业务流程 | ✅ |
| 109 | JavaScript/TypeScript SDK | ✅ |
| 110 | C# .NET SDK | ✅ |
| 111 | Python SDK | ✅ |
| 112 | Postman Collection | ✅ |
| 113 | Swagger/OpenAPI文档 | ✅ |
| 114 | Vite前端代理 — 可配置API目标 | ✅ |
| 115 | .env + .gitignore — 配置不入库 | ✅ |
| 116 | SSE流式响应 | ✅ |
| 117 | WebSocket实时推送 | ✅ |
| 118 | 多语言i18n (中文/English) | ✅ |
| 119 | 暗色模式 | ✅ |
| 120 | 响应式布局 | ✅ |

**总计：120项功能，全部完成。**
