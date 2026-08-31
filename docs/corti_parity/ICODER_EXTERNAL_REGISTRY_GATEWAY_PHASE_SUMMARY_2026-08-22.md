# iCoDer DrugBank / POSOS / Web Search 网关阶段总结

日期：2026-08-22  
结论：三项 Registry 已从运行时无条件 `PROVIDER_UNAVAILABLE` 收敛为可配置、可执行、可审计、失败关闭的开发环境上线候选合同；没有真实商业许可证或隐私供应商时仍不得声称生产可用或与 Corti 托管服务等价。

## 本阶段完成

- 新增 `GovernedExternalRegistryProvider`，覆盖 `drugbank/lookup`、`posos/guide`、`web-search/search`。
- 采用版本化企业适配网关合同，不臆造未获授权的 DrugBank/POSOS 厂商 API。固定 HTTPS endpoint、Bearer 凭证、区域和字段映射均由服务端控制。
- Connector Registry adapter 不再无条件拒绝三项 key；应用启动时接入 Provider，健康状态只暴露无密钥的配置布尔值。
- 外发前强制 `deidentified` 和 PHI 检测；Agent 只能提供 `query/max_results`，不能提供 URL、header、token 或供应商参数。
- Cloud/CN 精确 host allowlist、DNS-to-socket pin、系统代理隔离、禁止 redirect、JSON-only、请求/响应上限和超时继续由统一 Connector transport 执行。
- DrugBank/POSOS 必须有 Vault 凭证，且禁止 LLM fallback；Web Search 必须同时满足平台 opt-in 和当前组织精确 allowlist。
- 严格校验 v1 envelope、provider、总数、结果数量、DrugBank ID、引用 HTTPS URL；只投影临床复核所需的最小字段，不透传未知供应商 payload。
- 旧同步 Expert API 保持“显式调用也不隐式发网”的兼容语义，新增 `lookup_async`、`guide_async`、`search_async` 受治理入口，删除“授权后仍永远空结果”的陈旧桩描述。
- Compose、Cloud env 模板、TypeScript 内置 Registry key 类型、JavaScript/Python SDK 文档、云部署合同和静态部署预检已同步。

## 验证证据

所有命令均显式使用 `LLM_PROVIDER=mock`、`ICODER_ALLOW_EXTERNAL_LLM=false`、空 `ICODER_CREDENTIAL_LLM` 和 `ICODER_DISABLE_NATIVE_MEDCODER=true`，未调用真实 DeepSeek。

| 验证 | 结果 |
|---|---:|
| Provider/transport/adapter/runtime/credential/旧 Expert/Connector Executor/真实 TCP 联合回归 | 111/111 |
| 独立真实 TCP fixture 专项 | 1/1 |
| 主线 A2A/health invariant | 6/6 |
| TypeScript SDK build + tests | 41/41 |
| Python SDK tests | 48/48 |
| 静态部署候选预检 | 53/53，0 failed |
| 部署预检自身单测 | 1/1 |

真实 TCP 测试启动独立 Uvicorn fixture，经 loopback socket 执行三种 Provider，并证明：

- 三条 Connector 调用成功且三条审计记录均为 allow/success；
- PHI 分类在 socket 前失败，fixture 调用计数不增加；
- 错误凭证跨真实 socket 返回 401，并转换为稳定的 `CONNECTOR_UPSTREAM_401`；
- 测试明文 HTTP 只能通过构造器显式开启且仅限 loopback；应用运行时没有生产开关。

机器证据位于 [`reports/agent_hub/external_registry_gateway_phase_20260822`](../../reports/agent_hub/external_registry_gateway_phase_20260822/)，部署合同见 [`docs/cloud/EXTERNAL_REGISTRY_GATEWAYS.md`](../cloud/EXTERNAL_REGISTRY_GATEWAYS.md)。

## 对 Corti 差距的影响

已关闭的是“iCoDer 没有 DrugBank/POSOS/Web Search 可执行 adapter、安全合同或开发 E2E”这一工程缺口。未关闭的是 Corti 托管产品所隐含的真实供应商集成、许可证、内容覆盖、可用性、区域承诺和临床质量。

## 保留的外部门禁

- DrugBank/POSOS 合法商业许可、实际产品版本、字段映射、配额和 SLA；
- 隐私搜索供应商选型、DPA、中国个保/网安/跨境评估和租户批准；
- 生产 KMS/Secret Manager、证书、DNS、代理网络、容量、故障注入与多副本验证；
- 药师/医生独立内容质量评审、医院验收、法务、认证与上线审批。

此外，当前开发数据库仍是历史 `041/create_all` 混合状态。本阶段没有迁移、重启或写入开发数据库；新源码不能直接对该库执行启动迁移，必须先按既定 reconcile 流程处理。
