# Agentic v2 Connector 阶段总结（2026-08-21）

本阶段完成了五类 Connector 的持久资源与安全 CRUD；没有调用真实 LLM、Corti 或任何外部
Connector，也没有启动浏览器或本机原生 MedCodER。该结论是“资源面完成、执行面仍部分”，
不是 Corti 托管 Connector 的生产等价声明。

## 已完成

- 新增 Alembic `044` 和 `agent_connectors`、`connector_credentials`、
  `connector_execution_audit` 三张表；upgrade 到 `044`、downgrade 到 `043` 已实跑通过。
- 新增 `/api/v2/agentic/agents/{agent_id}/connectors` 三个资源路径、五项 CRUD 方法和
  credential reference 的 bind/rotate/delete；OpenAPI 由 248 增至 251 paths。
- `registry`、`mcp`、`agent`、`a2a`、`schema` 五类均有严格配置模型，类型创建后不可变，
  更新使用 `expected_version`，同 Agent 名称唯一。
- 所有查询以组织和源 Agent 为首要范围；跨租户、跨 Agent 和跨租户 target Agent 均按
  404 处理；Agent 自环、环路、深度和 fan-out 失败关闭。
- MCP/A2A 只接受规范 HTTPS，拒绝 userinfo、query、fragment、非 443 端口、IDN 混淆、
  loopback/private/link-local/metadata/CGNAT/unspecified/multicast/reserved 地址；CN 环境启用
  外部 Connector 时还要求精确域名出境 allowlist。
- Schema Connector 限制 dialect、大小、深度、节点、外部 `$ref` 和高风险正则；Registry
  仅允许服务器批准目录项。
- 配置递归拒绝 secret-shaped key/value；认证 API 只接收 Vault/KMS/Secret Manager 引用，
  响应只返回指纹、类型、版本和轮换时间。`secret_ref` 在 OpenAPI 标为 `writeOnly`，
  `ConnectorResponse` 不含 `secret_ref`/`credential_ref`，Connector 路径的校验错误也会删除
  被拒绝的原始输入，避免反射误填密钥。
- 写操作要求组织 owner/admin，并记录不含 URL、密钥或患者正文的最小必要审计。
- 删除采用不可见 tombstone：禁用 Connector、移除 credential reference、释放显示名称，但保留
  execution audit 的外键目标；含历史执行审计的删除路径已用 SQLite 实测。

## 验证结果

- Connector 单元、SQLite API 和 OpenAPI 专项：30/30。
- A2A v0.3/v1 + Connector + 既有 SSRF 联合回归：148/148；唯一警告为 Starlette
  TestClient/httpx 弃用提示。
- `python scripts/export_openapi.py --check`：通过；251 paths、3 个 Connector paths、
  五类配置 schema 全部存在，credential reference 为 write-only。
- 变更文件敏感形态扫描：0 命中。

## 仍未完成

- Connector executor、MCP handshake/A2A card 获取、真实异步调用和 mock executor E2E；
- 每次连接前 DNS 重校验、校验 IP/证书主机钉住、redirect 逐跳复验；
- Vault/KMS provider adapter、OAuth token exchange/rotation、专用 scope；
- timeout/retry/idempotency/budget/circuit breaker 和 execution audit 的真实写入；
- JavaScript/Python/.NET Connector SDK；
- PostgreSQL 多进程、Redis、Docker Linux 与受控外网证据。

后续 2026-08-22 已完成本地失败关闭 mock executor；当前剩余的是 Agent Planner graph 接线、
生产 transport/provider adapter 和三 SDK。详见
[`ICODER_AGENTIC_CONNECTOR_EXECUTOR_PHASE_SUMMARY_2026-08-22.md`](ICODER_AGENTIC_CONNECTOR_EXECUTOR_PHASE_SUMMARY_2026-08-22.md)。

机器可读证据：[`phase_evidence.json`](../../reports/agent_hub/agentic_connectors_phase_20260821/phase_evidence.json)。
