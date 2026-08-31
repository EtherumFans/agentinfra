# DrugBank、POSOS 与 Web Search 企业网关合同

状态：开发环境工程合同完成；真实供应商许可、数据处理协议、区域评估和生产网关未验证。

## 为什么使用企业适配网关

DrugBank 与 POSOS 是商业数据源，公开信息不足以让 iCoDer 安全地假定客户获授的产品、版本、API 路径或字段。Web Search 也必须选定满足医疗数据与中国区域要求的供应商。因此 iCoDer 不直连臆造的厂商 API，而是要求医院/云运维部署一个固定 HTTPS 适配网关。适配层把已授权供应商响应映射为本文件定义的最小合同。

该设计不会绕过外部门禁：没有合法许可、合同、凭证和获批网关时，能力保持失败关闭。

## 运行时门禁

- 请求必须标记为 `deidentified`，且通过服务端 PHI 检测；患者姓名、电话等内容在建立 socket 前被拒绝。
- Agent 只能提供 `query` 和 `max_results`，不能提供 URL、header、令牌或供应商参数。
- 网关 URL 必须是无 userinfo、query、fragment 的固定 HTTPS URL，默认只允许 443；重定向禁止。
- Cloud/CN 模式下，主机还必须逐字出现在 `ICODER_CONNECTOR_EGRESS_ALLOWLIST`。
- DrugBank/POSOS 必须存在相应 Vault 凭证，且不允许 LLM 猜测或降级生成相互作用/处方建议。
- Web Search 必须同时设置平台 opt-in，并把当前 `organization_id` 放入精确租户 allowlist；不支持 `*`。
- 区域必须明确为 `CN`、`EU` 或 `US`。
- DNS 到 socket 固定、系统代理隔离、连接/总超时、64 KiB 请求和 512 KiB 响应上限、JSON-only 与最小字段投影均由 Connector transport 强制执行。
- 每次通过 Agent Connector 执行都会写入 Connector audit；审计不记录 query、响应正文或凭证。

## 配置

凭证只能由 KMS/Secret Manager 注入运行环境，不能写入仓库、Connector config 或 Agent prompt。

```text
ICODER_REGION=CN
ICODER_CONNECTOR_EGRESS_ALLOWLIST=registry-gateway.example.cn,search-gateway.example.cn

ICODER_DRUGBANK_GATEWAY_URL=https://registry-gateway.example.cn/drugbank/query
ICODER_CREDENTIAL_DRUGBANK=<KMS 注入>

ICODER_POSOS_GATEWAY_URL=https://registry-gateway.example.cn/posos/query
ICODER_CREDENTIAL_POSOS=<KMS 注入>

ICODER_WEB_SEARCH_GATEWAY_URL=https://search-gateway.example.cn/query
ICODER_CREDENTIAL_WEB_SEARCH=<KMS 注入>
ICODER_WEB_SEARCH_PROVIDER_OPT_IN=true
ICODER_WEB_SEARCH_TENANT_OPT_IN_ORGANIZATIONS=org_hospital1,org_hospital2
```

配置变化需要按受控发布流程重启服务。健康状态只暴露 endpoint/credential/egress/region/opt-in 是否就绪，不回显 URL、主机名、组织 ID 或令牌。

## HTTP 合同

三项能力均使用 `POST` 和 Bearer 认证。请求示例：

```json
{
  "contract": "icoder.external-registry.gateway-request/v1",
  "provider": "drugbank",
  "operation": "lookup",
  "query": "aspirin",
  "max_results": 5,
  "region": "CN"
}
```

响应顶层只能包含以下字段：

```json
{
  "contract": "icoder.external-registry.gateway-response/v1",
  "provider": "drugbank",
  "total_available": 1,
  "results": []
}
```

Provider 与操作对应关系：

| Registry key | 操作 | `results[]` 最小映射 |
|---|---|---|
| `drugbank` | `lookup` | `drugbank_id`、`name`；可选 `description`、`indication`、`source_url`、最多 20 条 `interactions` |
| `posos` | `guide` | `medication`、`summary`；可选 `contraindications`、`interactions`、`citations` |
| `web-search` | `search` | `title`、HTTPS `url`；可选 `snippet`、`source`、`published` |

所有 URL 必须为 HTTPS。未知供应商字段不会透传；合同、provider、总数、数组类型、结果数、DrugBank ID 和引用 URL 异常时整体失败关闭。

## 开发验证与未关闭门禁

自动化测试启动独立 Uvicorn fixture，经真实 loopback TCP 执行三种 provider，并验证审计、错误凭证 401、PHI 发网前拒绝和调用计数。明文 loopback 仅能通过测试构造器显式启用，应用运行时没有对应环境变量或生产开关。

开发验证不能证明以下事项：真实 DrugBank/POSOS 许可范围和字段映射、真实搜索供应商隐私承诺、中国跨境/网安/个保评估、医院 DPA、供应商 SLA、生产证书与 DNS、临床内容质量、药师/医生独立评审。上述证据齐备前不得标记生产上线。
