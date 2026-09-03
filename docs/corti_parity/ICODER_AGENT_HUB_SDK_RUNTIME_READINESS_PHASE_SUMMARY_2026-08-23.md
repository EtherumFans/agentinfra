# iCoDer Agent Hub SDK 运行就绪契约阶段总结（2026-08-23）

## 结论

本阶段将 Agent Hub schema `1.3` 的四轴运行就绪状态从前端内部类型提升为正式 API/OpenAPI/三 SDK 开发候选合同。此前 Hub 路由的 OpenAPI 200 响应只是任意 `object`，JavaScript/.NET Hub 类型也没有 `runtime_readiness`，Python 只返回无类型字典；这些缺口现已关闭。

- Hub 使用严格 `AgentHubListResponse → AgentHubCardResponse → AgentHubRuntimeReadiness` 响应模型，OpenAPI 明确九个必填就绪字段并禁止额外健康明细。
- JavaScript `1.0.0-beta.27`、Python `1.0.0b27`、.NET `1.0.0-beta.27` 均公开结构、配置、运行按钮、依赖、外部 LLM、在线健康、语义验证和生产审批字段。
- JavaScript、Python 与 .NET 源码均对“结构或当前配置不可用，却声明 `run_action_enabled=true`”失败关闭。
- 修正三 SDK 的历史类型错误：`GET /api/icoder/agents/{id}/card` 返回 A2A v0.3 发现卡，不再被标注为 Hub 卡片。
- SDK README 示例先检查 `run_action_enabled`，不再直接鼓励调用不可用 Agent。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| Hub/OpenAPI 合同 | 26/26 | 响应 `$ref`、九字段 readiness、mock 真实性和 use-case 筛选 |
| Hub 扩大回归 | 106/106 | Hub、发现统一、克隆、筛选、显示状态、卡片元数据与旧 Run 兼容 |
| 26-Agent 离线 API E2E | 52/52 | 1 个本地能力、25 个模型依赖 Agent 安全失败关闭；不代表 26-Agent 语义成功 |
| JavaScript SDK | 51/51 | TypeScript build、四轴解析、矛盾状态拒绝、A2A 发现卡分型 |
| Python SDK | 52/52 | 两个 Hub resource 均验证 schema 1.3，矛盾状态拒绝，发现卡分型 |
| .NET SDK | 未在本机执行 | 源码模型、运行时校验、发现卡模型及 OpenAPI/客户端 CI 测试已更新；本机无 `dotnet` CLI |
| OpenAPI `--check` | 通过 | `AgentHubListResponse` 已进入提交的权威 schema |
| 部署候选静态预检 | 81/81，合同测试 1/1 | 新增 OpenAPI 和三 SDK readiness/失败关闭/发现卡分型门禁 |

## 发布模拟

- JavaScript 生成 `icoder-sdk-1.0.0-beta.27.tgz`，50 个包条目，SHA-256 为 `7704acca48f5790f9e0b62dcb6e397116620e8dec5717708446138bd3c772bae`。
- 官方 npm registry 的 production audit 为 0 个已报告漏洞。开发机默认的 `npmmirror` 不实现 audit API，因此其 404 没有被误记为安全通过。
- Python 生成 `icoder_sdk-1.0.0b27-py3-none-any.whl`，并从 wheel 直接导入版本和新类型成功；SHA-256 为 `d068268561508ef5f3ed71668582dc668730be3f98e106fc5ad93c9a9ab7c8f4`。
- .NET 包未构建；源码保持 `net8.0;net10.0` 双框架合同，必须由带 SDK 的 CI 实际测试和打包。

机器证据位于 `reports/agent_hub/sdk_runtime_readiness_20260823/`。

## 对 Corti 的增量与剩余差距

本阶段使 iCoDer 开发者入口能够诚实消费 Agent 当前就绪状态，避免 API 文档或 SDK 把 Provider 类存在误读为模型在线、语义已验证或生产已批准。这关闭的是 iCoDer 自身的契约和误用风险，不代表 Corti 私有 SDK 或托管运行时已经完成双向互操作。

仍未关闭的核心差距：25 个外部模型 Agent 的当前真实 Provider 快乐/对抗/重复质量矩阵、持续健康与 P50/P95、容量/配额/成本/SLA、Corti 托管租户互操作、.NET 本机或 CI 运行证据、真实医院流程、中国权威编码与 DRG/DIP 资产，以及临床、法务、安全和生产运维验收。

## 安全与环境状态

- 全程空凭据、`LLM_PROVIDER=mock`、禁止外部 LLM、禁用原生 MedCodER；未读取或使用真实密钥。
- 未启动浏览器或 TCP Uvicorn；8000/18022 无监听，Python/Uvicorn 残留进程为 0。
- 受保护数据库 SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 测试 teardown 已删除隔离库中的表；宿主既有安全策略阻止删除本轮三个测试数据库文件，已在机器证据逐项记录。

