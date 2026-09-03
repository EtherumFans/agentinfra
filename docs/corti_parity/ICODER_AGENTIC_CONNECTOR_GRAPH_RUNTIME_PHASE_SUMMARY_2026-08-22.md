# Agentic v2 Connector Graph 运行时阶段总结（2026-08-22）

本阶段把已持久化的五类 Connector 和失败关闭执行器接入通用 Agent Run，形成
“管理员配置受控图 → 运行时最小化参数 → Connector 审计 → 输出二次安全门 → Provider →
结果发布”的本地闭环。没有调用真实 LLM、Corti 或外部 Connector，也没有启动 Windows
原生 MedCodER/FAISS 栈。

当前结论是：**通用 Provider Agent 的顺序型 Connector graph 已达到开发环境上线候选；
不能扩大为 Corti 动态 Planner、生产 MCP/A2A transport 或全部 Agent 入口等价。**

## 已完成

- 新增严格 `ConnectorGraphNode/Spec/PutRequest/Response`：最多 16 节点、唯一节点 id、
  依赖存在性、DAG 环路检查、固定 `sequential` 执行模式、操作/输入键格式、数据分类和
  purpose-of-use；`include_text` 不允许伪装成 `non_phi`。
- 新增 `/api/v2/agentic/agents/{agent_id}/connector-graph` 的 GET/PUT/DELETE；owner/admin
  变更、租户过滤、`SELECT FOR UPDATE` 和单调 revision 乐观锁；删除保留 revision tombstone，
  避免无审计的配置复活。
- Graph 写入时验证 Connector 同组织、同源 Agent、未删除、启用状态和 operation allowlist；
  活跃图引用的 Connector 不可被禁用，更新后的 capability/tool/schema operation 不能破坏图。
- 修正自定义 Agent DB fallback 只按 `agent_id` 查询的问题；现在必须同时匹配当前
  `organization_id`，跨租户回退返回 `unknown_agent`。
- Graph 在 Provider 之前按拓扑顺序执行；只发送管理员选择的 `input_keys`、可选去标识文本
  和 server-owned dependency channel，模型不能选择 URL、凭据、Connector 或自由参数。
- 每个 Connector 输出在进入后续节点或 Provider 前再次做递归 PHI redaction、确定性 prompt
  injection 检测、JSON 形状及累计 256 KiB 限制。
- 必需节点失败、安全门失败或配置损坏时返回 `connector_graph_failed`，Provider 调用次数为 0，
  `result` 为空；可选节点失败以稳定错误码进入不可信数据块，不伪装成功调用。
- Provider 只在 user-data 区收到 `SERVER_GOVERNED_CONNECTOR_RESULTS_JSON`，system prompt 同时
  加入静态“不把 Connector 数据当指令/授权”约束；原始输出不进入 Run Trace 或审计表。
- Run Trace 增加有界的 graph revision、node/connector id、attempts、error code；
  `connector_execution_audit` 继续只保存最小必要元数据。
- JavaScript/TypeScript 与 Python SDK 已支持 Connector CRUD、外部 credential reference、
  graph GET/PUT/DELETE；没有增加绕过 Agent Run 的公开执行方法。
- 修复重复应用 lifespan 的 Coding Dispatcher/gateway 状态泄漏；mock/无 Provider 环境下旧
  `deepseek` alias 立即走失败关闭 mock，不再重试未注册 Provider 或随测试顺序改变错误合同。

## 验证

- Graph schema + HTTP/runtime E2E：10/10；覆盖 DAG、环路/未知依赖、分类、revision、跨租户、
  binding、字段最小化、输出去标识、trace、必需/可选失败、prompt injection 和 Provider 阻断。
- Connector resource/executor/graph 专项：48/48。
- A2A v0.3/v1 + Connector + graph + SSRF + OpenAPI + 通用 Agent Run 联合：214/214；
  53 个警告均为 Starlette/httpx 或 `datetime.utcnow()` 弃用提示。
- JavaScript SDK：32/32；Python SDK：39/39。
- OpenAPI：252 paths；graph 路径公开 GET/PUT/DELETE 严格 schema；导出漂移检查通过。
- Python compile 通过；新增范围暴露密钥形状扫描 0 命中。

主要复现命令（执行前显式清空真实凭据并关闭外部 LLM）：

```powershell
$env:ICODER_CREDENTIAL_LLM=''
$env:LLM_PROVIDER='mock'
$env:ICODER_ALLOW_EXTERNAL_LLM='false'
python -m pytest tests/unit/icoder/a2a/test_envelope.py tests/unit/icoder/a2a/test_v1_protocol.py tests/integration/icoder/a2a/test_endpoints.py tests/unit/corti_parity/test_a2a_openapi_runtime_parity.py tests/unit/app/schemas/test_connector_graph.py tests/unit/app/services/test_agent_connectors.py tests/integration/icoder/a2a/test_agent_connectors.py tests/integration/icoder/a2a/test_connector_executor.py tests/integration/icoder/a2a/test_connector_graph_runtime.py tests/unit/corti_parity/test_agent_connector_openapi_contract.py tests/test_api/test_a1b_ae_r_3_public_expert_ssrf.py tests/test_api/test_phase4f_agent_run.py -q
python scripts/export_openapi.py --check
```

```powershell
Set-Location packages/icoder-sdk
npm test
Set-Location ../icoder-python
python -m pytest tests -q
```

## 尚未完成/不得宣称

- 当前图是管理员固定的顺序预处理 DAG，不是 LLM Planner 的条件选择、分支、循环或并行 tool
  orchestration；`execution_mode` 仅支持 `sequential`。
- 当前只接入通用 Provider Agent Run；Medical Coding/CDI 专用分支、A2A v0.3/v1 直接入口、
  stream/async Task continuation 尚未共享此 graph。
- 没有 Console graph 编辑器、运行中节点 UI 或端到端浏览器旅程。
- 没有生产 MCP handshake、A2A transport、DNS-to-socket IP pinning、redirect 逐跳复验、
  Vault/KMS/Secret Manager resolver、OAuth2 token exchange/rotation。
- 熔断和并发限制仍是进程内；没有 Redis/PostgreSQL 多 worker、Docker Linux 或受控外网证据。
- .NET SDK 尚未加入 Connector graph 资源；三 SDK 全覆盖仍未完成。
- Corti 托管 Connector、医院真实系统、真实患者数据、跨境/等保/法务/认证和独立临床 reviewer
  门禁均未通过。

机器可读证据：[`phase_evidence.json`](../../reports/agent_hub/connector_graph_runtime_phase_20260822/phase_evidence.json)。
