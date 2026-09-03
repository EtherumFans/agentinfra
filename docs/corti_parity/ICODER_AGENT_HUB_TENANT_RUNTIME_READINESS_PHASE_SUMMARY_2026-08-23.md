# iCoDer Agent Hub 租户运行就绪阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床、生产、监管或医院上线批准。
>
> 日期：2026-08-23
>
> 阶段：Agent Hub tenant-bound runtime readiness
>
> 状态：开发门禁通过；外部上线门禁仍开放

## 阶段结论

本阶段关闭了 Agent Hub 就绪状态的一个关键租户边界缺口：公开 Hub 不再根据进程级 Provider 配置推断任何租户是否可运行；只有鉴权后的 `GET /api/icoder/agents/hub/readiness` 才返回当前组织的模型选择、配置状态和有时效的连通性证据。公开浏览接口中的 26 个卡片全部保持 `not_checked`、运行操作禁用，不泄露租户或运维配置。

- 配置探针与进程内 Canary 缓存现按 `organization_id + deployment_id` 绑定，租户 A 的状态不能投影给租户 B。
- 实网 Canary 的成功证据从租户自有、无患者正文的审计记录恢复，默认有效期 900 秒；只有固定合成输入、`reachable/ok`、预期 token 匹配且 `patient_data_sent=false` 才可声明 `live_health_verified=true`。
- 切换模型部署会立即使旧部署证据失效；过期证据只撤销“在线已验证”声明，不把“配置存在”伪装成健康；明确失败的最新 Canary 会禁用所有依赖 LLM 的 Hub 操作。本地确定性 Compliance Guardrail 不受模型连通性影响。
- 语义验证与生产审批继续独立保持 `not_verified` / `not_approved`，连通性成功不会提升临床质量或上线结论。

## 产品与开发者入口

前端首先读取公开 Hub，再并行读取鉴权后的租户就绪接口；只有 schema `1.0`、总数、唯一 Agent ID、执行目标、LLM 依赖分类和四轴状态全部一致时，才整批合并并启用允许的操作。任何 401、网络错误、缺项、重复项或矛盾状态都会让整个列表继续失效关闭。Agents 列表和由 Hub 回退加载的 Agent 详情页均使用该门禁，聊天与测试入口不会绕过禁用状态。

OpenAPI 新增严格的 `AgentHubTenantReadinessResponse → AgentHubTenantReadinessItem → AgentHubTenantRuntimeReadiness` 合同，禁止额外字段，并声明 Bearer 鉴权。JavaScript `1.0.0-beta.28`、Python `1.0.0b28` 和 .NET `1.0.0-beta.28` 均新增租户就绪类型及读取方法；三套源码都拒绝重复、缺失或“未验证连通性却声明在线健康”的响应。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 后端定向接口与隔离 | 31/31 | 匿名拒绝、mock 失败关闭、配置可运行、跨租户隔离、部署切换、过期和失败 Canary |
| Hub/Models 扩大回归 | 127/127 | Hub、发现、克隆、显示状态、Pack 矩阵、模型目录、租户选择/探针/Canary |
| 26-Agent 离线双场景 E2E | 52/52 | 每个可见 Agent 的示例与对抗输入；证明开发链路和安全失败关闭，不证明 25 个 LLM Agent 的语义成功 |
| 前端 | 141/141 + production build | 严格合并、整批失效关闭、列表/详情门禁和现有页面回归 |
| JavaScript SDK | 52/52 | 新 `hubReadiness()`、严格 schema 1.0 校验、发布包生成 |
| Python SDK | 53/53 | `agents.hub_readiness()` 与 `agent_hub.readiness()`、wheel 直接导入 |
| .NET SDK | 本机未执行 | 模型、`GetReadinessAsync()`、失败关闭与 OpenAPI/客户端测试已更新；本机无 `dotnet` CLI |
| OpenAPI | export + `--check` 通过 | 271 paths、298 schemas、严格 Bearer 合同 |
| 部署候选预检 | 81/81；合同测试 1/1 | 新的公开/租户边界、前端和三 SDK 断言进入门禁 |

## 发布模拟

- JavaScript 包 `icoder-sdk-1.0.0-beta.28.tgz`：51,947 bytes，SHA-256 `3192231c3c787a3f079915b3efaf475b2886824e2845d10610efe08acebfe159`；官方 npm registry production audit 报告 0 个漏洞。
- Python wheel `icoder_sdk-1.0.0b28-py3-none-any.whl`：34,643 bytes，SHA-256 `0295836340df36292ce539e704868e90fa9153e39f8e5a15f7a9aa9d56fbaa83`；从 wheel 路径直接导入版本与新类型成功。
- .NET 包没有在本机生成；源码仍要求 `net8.0;net10.0`，必须由安装了 SDK 的 CI 执行测试和打包。
- 权威 OpenAPI SHA-256 为 `8934e9cf7d4f507f5cb3eac2cba8ca62909f235fa802bb104a97bcaac85efbf7`。

机器证据位于 `reports/agent_hub/tenant_runtime_readiness_20260823/`。

## 对 Corti 的能力差距增量

这一步使 iCoDer 的公开 Agent 目录、租户模型路由和短期连通性证明形成了可审计边界，避免把某一进程、某一组织或一次 Canary 的状态错误扩散为全局“可上线”。它提升的是多租户安全、开发者可用性和状态真实性。

仍未关闭的 Corti 核心差距包括：Corti 托管模型控制平面与正式 SLA、当前 25 个 LLM Agent 的真实 Provider 快乐/对抗/重复质量矩阵、持续 P50/P95/错误率/成本/配额监控、Corti 托管租户双向 SDK 互操作，以及真实医院数据、临床金标准、编码/DRG/DIP 权威资产、法务/监管/安全认证和独立临床 reviewer。一次无患者数据的连通 Canary 不能替代这些门禁。

本阶段没有重新打开 Corti 浏览器会话：此前该宿主出现过浏览器/原生栈内存崩溃风险，本轮只复用已归档的 Corti 公开/可访问能力基线，并集中完成可在开发环境内证明的租户就绪收敛。

## 安全与环境状态

- 全程空 `ICODER_CREDENTIAL_LLM` / `DEEPSEEK_API_KEY`、`LLM_PROVIDER=mock`、禁止外部 LLM、禁用原生 MedCodER；没有读取或使用真实密钥。
- 未启动浏览器或 TCP Uvicorn；8000/18022 无监听，Python/Uvicorn 运行进程为 0。
- 受保护数据库 SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 五个本轮隔离测试数据库已由 pytest teardown 删除全部表，但宿主安全策略阻止删除数据库文件；它们保留在 `backend/data/test_tenant_readiness*.db`，不包含真实密钥或本轮真实患者数据。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 新增租户绑定、可过期、无密钥的 Agent Hub 就绪合同，完成前端/三 SDK/OpenAPI/回归与发布模拟 | Agent Hub 不能从全局 Provider 状态推断租户可运行性 |
