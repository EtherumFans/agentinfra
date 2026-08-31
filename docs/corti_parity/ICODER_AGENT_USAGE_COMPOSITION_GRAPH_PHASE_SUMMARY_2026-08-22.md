# Agent Usage、SDK Composition 与全入口 Connector Graph 阶段总结（2026-08-22）

本阶段按 Corti 当前公开 Agentic v2 合同，完成三项此前仍可在开发环境关闭的缺口：
按 Agent usage、TypeScript/Python Agent SDK composition，以及专用 Agent/直接 A2A 入口对
Connector graph 的统一执行。结论是这些能力已达到本地可审计候选；这不代表 Corti 托管
运行时、临床质量、生产 Connector 网络或医院上线等价。

公开对照包括 Corti Agent SDK 的
[Composition](https://docs.corti.ai/agentic/agent-sdk/composition.md)，以及官方 usage 合同中的
`GET /v2/agentic/agents/{AGENT_ID}/usage`。

## 已完成

- 新增 `GET /api/v2/agentic/agents/{agent_id}/usage`。查询先校验租户内官方/自定义 Agent
  可见性，跨租户和未知 Agent 均统一 404；`from` inclusive、`to` exclusive，接受
  `minute|hour|day|week`，但按官方当前行为固定返回 `day`。
- usage 返回 `invocations`、`uniqueContexts` totals 和逐日 buckets；没有事件的日期也返回零值。
  为本地/院内部署增加单次最长 366 天的资源上限，避免无界聚合。
- `automatedEvaluation` 不再是普通 feedback 写权限的别名：仅 OAuth/runtime 机器凭据且明确
  含 `feedback:evaluate` 才可提交；用户 JWT 和只有 `feedback:write` 的 API Client 失败关闭。
  该来源标记不产生训练授权，审计固定记录 `training_authorized=false`。
- 统一 Run API 的 Medical Coding/CDI 专用分支在运行专用适配器前执行同一租户 Connector
  graph；所有直接 A2A v0.3/v1 handler 由传输外层 gate 统一覆盖，Provider 路径识别
  `connector_graph_preexecuted`，避免重复执行。
- `_connector_results` 和相关 revision 为服务端拥有字段；客户端伪造以下划线开头的数据键会
  被拒绝。TextPart 与显式 `input_keys` 的结构化 DataPart 分离，未选字段不会经序列化文本泄漏。
- 必需节点失败和 graph 内部异常均在进入 Agent 前失败关闭；保留 tenant/run/trace/context
  归属、失败 RunHistory、TOOL/COMPLETION trace 和最小错误原因。
- TypeScript/Python SDK 增加与 Corti 私有预览公开形状对齐的组合原语：
  `workflow` 支持 `when`、`transform`、重试和延迟；`parallel` 用 settled 结果隔离分支失败并
  支持分支输入；`stateGraph` 浅合并状态、有界循环并报告终止原因；`agentNode/agent_node`
  负责 Agent 输入/状态映射。
- JavaScript、Python、.NET 同步到 `1.0.0-beta.20`（Python PEP 440 为 `1.0.0b20`）；
  .NET 加入 per-Agent usage 源码合同，Corti 当前公开 composition 仅覆盖 TypeScript/Python。

## 验证结果

所有测试均显式清空 `ICODER_CREDENTIAL_LLM`、使用 mock provider、关闭外部服务并禁用原生
MedCodER。未使用用户 DeepSeek 密钥、未调用 Corti 写接口、未启动端口 8000。

| 验证 | 结果 |
|---|---:|
| Connector graph 全入口与失败审计 | 13/13 |
| usage/feedback 权限与租户隔离 | 6/6 |
| A2A v1 异步运行时 | 3/3 |
| 真实 FastAPI lifespan 启动 | 3/3 |
| 统一 Agent Run/26-Agent 失败关闭合同 | 46/46 |
| A2A/OpenAPI 现行路径合同 | 3/3 |
| 本阶段后端独立进程汇总 | 74/74 |
| JavaScript SDK + TypeScript build | 40/40 |
| Python SDK | 47/47 |
| 前端 OpenAPI 路径合同 | 60/60 |
| 三 SDK 版本/发布门 | 5/5；统一 `1.0.0-beta.20` |
| OpenAPI | 256 paths、788,396 bytes、usage GET 存在、快照无漂移 |
| 本地候选制品 | JS tgz + Python wheel/sdist；SHA-256 清单；未发布 |
| compileall / 新增范围密钥形状扫描 | 通过 / 0 个文件命中 |
| 收尾进程 | 8000 listener 0；Uvicorn 进程 0 |

后端集成套件共用同一个临时 SQLite，不能以多个 pytest 进程并行运行。并行尝试会产生
`database is locked` 或某套件 teardown 删除另一套件表的假失败；改为独立进程串行后所有
74 项通过。该约束应保留在本地测试编排和 CI job 切分中。

候选清单：
[`LOCAL_RELEASE_MANIFEST_BETA20.json`](../../reports/release-candidate/LOCAL_RELEASE_MANIFEST_BETA20.json)。
清单明确记录 dirty 工作树和 `publication.performed=false`。

## 尚存差距

- Connector graph 服务端仍是有界顺序执行；SDK composition 是客户端/应用层原语，不能冒充
  分布式服务端条件/并行 Planner。
- 动态/标准 well-known Agent Card、生产 OAuth/credential transport、socket IP 钉住、逐跳
  redirect 复验、分布式熔断/并发和多副本队列仍未完成。
- usage 是运行次数/唯一 Context 的运行时统计，不是 Corti 或 Provider 的权威账单；生产成本
  对账、项目级财务账户、发票和退款仍不存在。
- 自动评估入口具备最小机器 scope，但训练用途仍未授权；临床纠错、case review 和自动评估
  均不得自动进入训练集。
- .NET 本机没有 `dotnet/csc/msbuild`，usage 源码与测试未记为编译通过。
- 真实 LLM 证据仍仅限历史受控最小链路；26-Agent 临床质量、受治理 ICD 检索、Corti 同病例
  盲评、医院互操作、合法编码资产、法务/等保/认证和独立 reviewer 仍是外部门禁。

机器可读证据：
[`phase_evidence.json`](../../reports/agent_hub/agent_usage_composition_graph_phase_20260822/phase_evidence.json)。
