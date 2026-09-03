# Agentic v2 Connector Graph A2A 阶段总结（2026-08-22）

本阶段把管理员受控的顺序型 Connector graph 从统一 HTTP Agent Run 扩展到通用
Provider A2A 运行链。A2A v0.3、v1 JSON-RPC 和 v1 HTTP+JSON 继续共享同一个
`ProviderA2AHandler`、同一个 graph runner 和同一组安全门。测试显式清空 LLM 密钥，
使用进程内 mock Connector/Provider；没有调用真实 LLM、Corti、外部 Connector 或
Windows 原生 MedCodER/FAISS。

当前结论是：**租户自定义、已启用 A2A 的通用 Provider Agent，已经可以通过同步
A2A v0.3/v1 执行 Connector graph，并具备失败关闭、Task 终态、Run/Trace 与 Connector
审计证据；这仍不是完整异步 A2A、动态 Agent Card、专用医疗 Agent graph 或 Corti
托管 Connector 等价。**

## 已完成

- 抽出 HTTP Run/A2A 共用的租户 Agent 查询和 DB Pack 合成服务；自定义 Agent 必须同时
  匹配 `agent_id`、当前 `organization_id`，且 A2A 入口额外要求 `a2a_enabled=true`。
- 通用 A2A dispatcher 只把非专用候选交给 Provider adapter；Medical Coding、CDI、
  Code Validation、Compliance 和 Note Completeness 的专用执行链不会被动态 DB fallback
  抢占。
- v0.3、v1 JSON-RPC 和 v1 HTTP+JSON 最终调用同一个 graph runner；节点输入仍只包含
  管理员选择的 `input_keys`、可选去标识文本和 server-owned dependency channel。
- Connector 输出继续执行递归 PHI redaction、prompt-injection 检测、对象/大小门禁；只以
  `SERVER_GOVERNED_CONNECTOR_RESULTS_JSON` 不可信数据块进入 Provider。
- 必需节点失败时 Provider 调用次数为 0；A2A 返回稳定 `CONNECTOR_GRAPH_FAILED`（v0.3）
  或 v1 `INTERNAL` 投影，且不会产生 Agent Message/Artifact。
- 修复 v1 已有 `taskId` 只校验、不落终态的问题：成功进入 `completed`，任何 legacy
  dispatch 错误进入 `failed`；状态更新使用条件更新和既有状态机，避免覆盖并发终态。
- v1 Task id 通过 server-owned bridge metadata 进入 `ConnectorExecutionAudit.task_id`；
  客户端同名 metadata 会被覆盖，不能伪造审计关联。
- 通用 Provider A2A 在首次 Trace 前提交租户归属 `RunHistory`，状态从 `PENDING`→`RUNNING`
  →`COMPLETED/FAILED`；Trace API 不再把 A2A graph 运行视为无归属 orphan run。
- A2A Trace 现在包含有界的 `user_message_received`、graph `tools_call` 和 `completion`；
  Connector 原始参数、输出、PHI 和凭据不进入 Trace/RunHistory。
- 统一 HTTP Agent Run 继续使用相同 DB Agent Pack 合成逻辑；没有新增公开的任意
  Connector 执行端点。

## 验证

- Connector graph HTTP Run + A2A 集成文件：10/10；其中新增 4 条覆盖 v0.3 成功、v1
  JSON-RPC 成功、v1 HTTP 必需节点失败、Task=`failed`、Artifact=[]、Run/Trace、Connector
  audit task correlation 和跨租户 404。
- A2A 协议/官方 Provider 兼容回归：232/232。
- A2A + Connector CRUD/executor/graph + SSRF + OpenAPI + 通用 Agent Run 联合：364/364；
  62 个警告均为 Starlette/httpx 或 `datetime.utcnow()` 弃用提示。
- 导出 OpenAPI 漂移检查通过；导出文件仍为 252 paths。
- Python compile 通过；本阶段文件暴露密钥形状扫描 0 命中。

主要复现命令（执行前清空真实凭据并关闭外部 LLM）：

```powershell
$env:ICODER_CREDENTIAL_LLM=''
$env:LLM_PROVIDER='mock'
$env:ICODER_ALLOW_EXTERNAL_LLM='false'
$env:ICODER_DISABLE_NATIVE_MEDCODER='true'
$env:ICODER_MODEL_LIVE_CANARY_ENABLED='false'
$env:ICODER_RUNTRACE_STORE='memory'
python -m pytest -q tests/integration/icoder/a2a tests/unit/app/schemas/test_connector_graph.py tests/unit/app/services/test_agent_connectors.py tests/unit/corti_parity/test_a2a_openapi_runtime_parity.py tests/unit/corti_parity/test_agent_connector_openapi_contract.py tests/unit/icoder/a2a tests/unit/icoder/test_provider_a2a_streaming.py tests/test_api/test_a1b_ae_r_3_public_expert_ssrf.py tests/test_api/test_phase4f_agent_run.py
python scripts/export_openapi.py --check
```

## 尚未完成/不得宣称

- v1 只支持同步 Send/Stream 和对已有 Task 的 continuation；`returnImmediately` 异步 Task
  创建、Subscribe、持久事件恢复、重连和跨 worker 投递尚未实现。
- 自定义 DB Agent 可以直接运行 A2A，但标准/租户动态 Agent Card discovery 尚未接入；
  当前 discovery provider 仍以进程内官方 Pack 为主。
- Medical Coding、CDI、Code Validation、Compliance 和 Note Completeness 等专用执行链
  尚未共享 graph；不能用通用 Provider 证据外推全部 Agent 入口。
- graph 仍是管理员固定的 `sequential` DAG，不支持条件、并行、循环、模型 Planner 动态
  选 Connector 或长任务恢复。
- 没有 Console graph 编辑器、节点运行 UI 或浏览器 E2E。
- 没有生产 MCP handshake/A2A transport、DNS-to-socket IP pinning、redirect 逐跳复验、
  Vault/KMS/Secret Manager resolver、OAuth2 exchange/rotation。
- 熔断/并发状态仍是进程内；没有 PostgreSQL/Redis/Docker Linux 多 worker 证据。
- .NET SDK 尚未加入 Connector graph；OpenInference export、task/message feedback 仍缺失。
- Corti 托管行为、医院系统、真实患者数据、合法规则/许可、等保/法务/认证、云容量灾备和
  独立临床 reviewer 门禁均未通过。

机器可读证据：[`phase_evidence.json`](../../reports/agent_hub/connector_graph_a2a_phase_20260822/phase_evidence.json)。
