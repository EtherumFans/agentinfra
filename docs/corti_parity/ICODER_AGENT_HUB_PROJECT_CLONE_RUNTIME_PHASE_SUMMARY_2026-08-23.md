# iCoDer Agent Hub 项目克隆运行闭环阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床有效性、生产就绪、医院验收或监管批准。
>
> 阶段：Hub Clone → Customize → Run/A2A → Trace/Audit
>
> 结论：项目克隆的 Provider-backed 执行闭环已通过开发门禁；26 个可见 Agent 仍没有当前真实 LLM 语义 E2E 和生产验证证据。

## 阶段结论

上一阶段遗留的 P0 断链已经关闭：克隆后的项目 Agent 不再绕回源 Agent 的公开身份，也不再合成一个丢失源合同的通用 Pack。运行时现在以 `project_agent_id` 作为租户、响应、Run、Trace 和审计身份，以不可变 `source_runtime_agent_id` 选择源 Pack 的真实 Provider 或专用运行路径。

Provider-backed 克隆可以在安全覆盖范围内修改 system prompt、绑定已发布的租户 Expert，并配置受治理 Connector Graph。Medical Coding/CDI 专用运行时也已采用“固定源 Expert 图 + 项目附加策略”语义：源临床安全边界不可删除，项目 prompt 和租户 Expert 以带摘要校验的附加策略进入真实 HTTP/A2A/LLM 链路，外部 A2A JSON 不能伪造该策略。新增端到端测试从 Hub Clone API 开始，经 Connector 创建和 Graph 配置 API，使用克隆响应中的 A2A 地址执行，最终证明 Connector、Provider、A2A 响应、Trace、RunHistory 和 ConnectorExecutionAudit 共用同一个项目运行链。

这不是“Corti 已完整复刻”的结论。当前矩阵中 26/26 是开发环境 launch candidate，但 `semantic_live_e2e_verified=0` 且 `production_ready_verified=0`；这两个数字是阶段判断的硬边界。

## 本阶段关闭的开发缺口

- Clone 返回并强制区分 `project_agent_id`、`runtime_agent_id` 和 `source_runtime_agent_id`；项目身份不能被 SDK 响应绕过。
- 源 Pack 的版本、Provider、输出合同、工具、权限、示例、关系和完整性证明保持不可变；项目覆盖不会改写 provenance。
- system prompt 与已发布租户 Expert 的组合真实进入 Provider 请求；Expert 内容不从 Agent Card 泄漏。
- 并发 Clone 请求原子收敛到同一项目 ID，只有一次创建，重复请求幂等返回。
- Run 和 A2A 均以项目 ID 对外执行，Provider context 同时携带项目 ID 与源运行 ID。
- Medical Coding/CDI dedicated clone 能路由到源专用处理器并保留项目归因；项目 prompt 与租户 Expert 作为带 SHA-256 完整性校验的附加策略进入专用 LLM，源 Expert 图保持固定，删除安全图或摘要不匹配均失败关闭。
- Agent 详情和配置界面明确区分锁定的源 Expert 与可增删的项目 Expert；Trace 只保存策略摘要、ID 和布尔标志，不保存 prompt 或 Expert 正文。
- A2A 服务端只接受由租户克隆分发器构造的内存策略对象，忽略客户端 JSON 中同名字典，防止跨边界策略注入。
- A2A v1 Agent Card 可从租户克隆解析，端点属于项目 Agent，且不泄漏项目 prompt 或 Expert policy。
- Connector Graph 可通过项目管理 API 配置，并在项目 A2A 前执行；仅选定结构化字段和脱敏文本可出站，Connector 结果按不可信数据注入 Provider。
- A2A 响应、Trace、RunHistory 与 Connector audit 共用一个 `run_id`，并保持组织隔离。
- OpenAPI CloneResponse 与 JavaScript、Python、.NET 三套 SDK 已加入项目运行身份合同；JavaScript/Python 已执行，.NET 因本机无 SDK 保留 CI 门禁。
- Windows 启动早期原生导入守卫在已知精确危险组合上失败关闭，避免应用初始化阶段载入 PyArrow 24.0.0 或 Torch 2.11.0 + sentence-transformers 3.2.1。

## 当前验证证据

| 门禁 | 结果 | 说明 |
|---|---:|---|
| Clone→Customize→Run/A2A 聚焦 E2E | 13/13 | 含 Connector Graph 单链、Medical Coding/CDI 专用策略、项目签名 Trace 与外部 JSON 防伪造 |
| 专用运行/Trace/offline 组合回归 | 214/214 | 必须从 `backend` 工作目录运行，避免相对测试库指向错误 |
| 默认安全后端全量 | 5224 passed、0 failed、1 teardown error | 20 skipped、11 deselected；业务断言执行至 100%，最终 SQLite `drop_all` 因 E 盘约 73 MB 空闲报 `database or disk is full`；用时 35:54 |
| 失败用例隔离复验 | 1/1 | 同一测试及 teardown 随后单独运行通过，支持“瞬时磁盘空间环境错误”判断；全量门禁仍应在释放空间后重跑 |
| 原生导入守卫 + 部署预检合同 | 5/5 | 精确危险版本失败关闭与预检回归 |
| OpenAPI 漂移 | 通过 | `docs/openapi/openapi.json` 与当前应用一致 |
| Python SDK | 55/55 | Clone 类型、URL 编码、项目身份失败关闭均覆盖 |
| TypeScript SDK | 54/54 | `tsc` 构建通过，Clone 身份合同覆盖 |
| .NET SDK | 未执行 | 源码和合同测试已实现；本机没有 `dotnet`，必须由 CI/匹配主机验证 |
| 前端全量 | 142/142 | 23 个测试文件；生产构建通过，仅有既有 chunk 提示 |
| Agent 运行矩阵 | 26/26 | visible、executable、Provider-resolvable、launch-candidate-ready；后续 Surgical Registry 本地化后外部 LLM 必需数由 20 降至 19，本地基线由 6 增至 7 |
| 输出合同完整性 | 26/26 | 类型、嵌套 schema、示例、字段/跨 Agent 关系、allowlist 均通过 |
| 静态部署预检 | 81/81 | `static_without_docker_cli`，失败项 0 |
| 当前语义级真实 E2E | 0/26 | 未使用真实 LLM，不得推导质量对等 |
| 当前生产验证 | 0/26 | 未完成生产基础设施与外部上线门禁 |

机器证据：

- `reports/agent_hub/project_clone_runtime_phase_20260823/phase_evidence.json`
- `reports/agent_hub/project_clone_runtime_phase_20260823/runtime-matrix/agent_hub_runtime_matrix.json`
- `reports/agent_hub/project_clone_runtime_phase_20260823/preflight/deployment_preflight.json`
- `reports/agent_hub/governed_surgical_registry_phase_20260823/phase_evidence.json`
- `reports/agent_hub/governed_surgical_registry_phase_20260823/runtime_matrix/agent_hub_runtime_matrix.json`

## 与 Corti 当前公开能力的逐项差距

Corti 当前公开 Agent Library 表述为预置 Agent 可直接部署或按场景配置，并明确列出 system prompt、Experts、自定义逻辑、工具和集成，同时保留治理、验证与审计保证。[Corti Agent Library](https://corti.ai/agents)

Corti 当前 Quickstart 展示的是 Project 中创建持久 Agent、附加 Registry Connector，并通过 A2A HTTP+JSON 发送消息的完整路径；创建合同还公开了 system prompt、Experts 和 MCP servers。[Corti Agentic Quickstart](https://docs.corti.ai/agentic/quickstart)、[Create Agent](https://docs.corti.ai/agentic/agents/create-agent)

Corti 还公开声称 replayable traces、structured logs、governed memory、稳定 thread state，以及 A2A/MCP 兼容；官方交付 SDK 包括 JavaScript/TypeScript 与 C#/.NET。[Agentic Framework overview](https://docs.corti.ai/agentic/overview)、[Corti Agentic Framework](https://corti.ai/agentic-framework)、[SDKs and integrations](https://docs.corti.ai/agentic/sdks-integrations)

| 能力 | iCoDer 当前证据 | 差距判断 |
|---|---|---|
| 20+ 预置 Agent 目录 | 26 个用户可见 Pack，全部可执行并有严格合同 | 数量/结构开发门禁已超过公开目录下限；不代表语义质量对等 |
| 预置 Agent 项目化 | Clone 幂等、并发安全、组织隔离、源 provenance 固定 | Provider-backed 项目化开发闭环已关闭 |
| system prompt 定制 | Provider-backed 及 Medical Coding/CDI dedicated clone 均真实进入请求；Agent Card/Trace 不泄漏正文 | 开发路径已闭合；尚缺真实模型语义质量与生产规模验证 |
| Expert 组合 | 已发布租户 Expert 进入 Provider policy；dedicated runtime 保持源 Expert 图并附加项目 Expert 策略 | 安全附加语义已闭合；尚未证明 Corti 式完整自定义 Expert/MCP 生命周期 |
| 工具与集成 | 五类 Connector、受治理 Graph、A2A/MCP transport、审计链已有 | 新增 E2E 证明 Provider clone；任意 custom logic/低代码工作流 UX 仍不足 |
| A2A/Agent Card | v0.3 兼容路径、v1 资源、动态 Card、Task/Context/Artifact/stream 已有 | 协议面较完整；仍缺跨云/异构真实对端互操作与负载证据 |
| 审计与可观测性 | Run/Trace、Connector audit、OpenInference、反馈与保留策略已有 | 开发证据充分；未完成生产回放规模、SLA 和独立合规审阅 |
| Memory/thread state | 受治理 Memory、Context、Task 状态已有 | 未证明与 Corti 托管能力在并发、持久性、灾备和生产隔离上对等 |
| JavaScript/.NET SDK | JS 54/54；.NET 合同源码已实现 | 本机缺 .NET 运行验证；包发布、消费者矩阵和版本兼容仍未闭合 |
| 中国医疗场景适配 | 当前 7 个 Agent 有本地基线；除 ICD-10-CN、ICD-9-CM-3、DRG/DIP、CDI 等既有能力外，Surgical Registry 已增加中文手术/麻醉/阴性并发症的保守逐字提取 | 缺真实医院数据、国家/省级/医院规则与登记字典权威校验、编码员/临床/质控专家盲评和结算/登记回放 |
| 语义质量 | 当前矩阵 0/26 semantic live E2E | **核心开放差距**：不能声称达到 Corti 输出质量 |
| 生产可用性 | 静态预检 81/81 | **核心开放差距**：当前矩阵 0/26 production verified |

## Windows 崩溃与 Uvicorn `-1` 结论

本阶段能复现并定位的两次原生崩溃不是 Agent 运行本身造成，而是把 Unix 的 `\` 续行写法用于 PowerShell。pytest 因而把 `\` 解析为 `E:\` 收集路径，递归收集其他项目并导入 Transformers → sklearn → pandas → PyArrow，最终在已知危险原生组合上崩溃。后续命令统一使用 PowerShell 数组与 splatting，并启用精确版本的早期原生导入守卫；本轮 5224 个业务测试执行至 100%，没有再次发生原生崩溃。

用户 2026-08-21 日志中的独立 Uvicorn `-1` 仍不能归因为“内存不可读/不可写”：退出前 Trace 请求为 200，SQLAlchemy `ROLLBACK` 是只读事务收尾。Windows 事件日志在 2026-08-23 的另一时刻确有 `python.exe` 在 `pyarrow\arrow.dll` 中以 `0xC0000005` 崩溃的记录，但时间不匹配，只能证明本机存在独立的 PyArrow 原生访问冲突风险，不能证明它导致 8 月 21 日这次 Uvicorn 退出。

本轮全量测试末尾另出现 SQLite `database or disk is full`：当时 E 盘仅约 73 MB 可用，错误发生在 fixture 的 `drop_all` teardown，不是测试断言。相同测试随后 1/1 独立复验通过。该环境风险与内存访问冲突是两类问题；在释放足够磁盘空间并重跑全量前，不将最新全量门禁标记为完全绿色。

## 安全基线

- 本阶段没有读取或使用用户曾暴露的 DeepSeek Key；供应商侧仍应注销该旧 Key。
- `ICODER_CREDENTIAL_LLM` 与 `DEEPSEEK_API_KEY` 在测试进程中长度均为 0，Provider 为 mock，外部 LLM 被禁止。
- 保护数据库 `backend/data/icoder.db` 的 SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 测试结束后未保留 8000/18022 监听或 Uvicorn 服务。
- 没有使用 Corti 登录控制台或应用内浏览器；本阶段对标依据为官方公开页面。

## 仍需继续完成

开发环境下一优先级是：先释放至少 1–2 GB 的 E 盘空间并重跑默认安全后端全量，消除环境性 teardown 门禁；随后建立 26-Agent 真实模型合成输入语义评测、差异基准和失败分类，并补 .NET CI、PostgreSQL 多 worker、Docker/云部署与异构 A2A 对端测试。真实 LLM 测试必须使用已轮换的新密钥，且不得写入仓库、日志或持久化测试证据。

真实医院数据、编码与临床专家盲评、医保/DRG/DIP 权威规则确认、法务数据授权、等保/个保/数安、渗透测试、云容量/SLA、灾备和医院验收只能作为外部上线门禁保留，不能由本地测试替代。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 关闭项目 Clone 双身份运行、Provider Expert、Agent Card、Connector Graph A2A、三 SDK Clone 合同和 Windows 原生导入早期守卫；更新 26-Agent/81 项门禁与 Corti 差距 | 上一阶段项目副本定制执行 P0 与本机原生崩溃风险 |
| 2026-08-23 | 关闭 Medical Coding/CDI dedicated clone 的可审计附加 prompt/Expert 策略、A2A 防伪造、项目签名 Trace 和管理面锁定语义；更新 13 项项目 E2E 与全量磁盘空间例外 | Corti 项目 Agent 定制对标与最新回归证据 |
