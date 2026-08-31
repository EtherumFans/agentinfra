# Semantic Memory 隔离服务部署合同

> 状态：开发环境上线候选，不代表医院、患者、法务或监管授权已经完成。

持久 Memory Connector 的 `remember`、`recall`、`forget` 使用租户、已认证用户、Agent、用途和 consent 五重作用域。语义向量由隔离的同区域 HTTPS 服务生成，API 进程不加载 Torch、sentence-transformers、FAISS 或 PyArrow；向量与内容一起写入 Memory 行的加密字段。

## 授权边界

- `/memory-consent` 仅表示当前已认证用户对本人工作偏好和去标识化上下文的自助授权，权威分类固定为 `authenticated_user_self_service`。
- 该授权不是患者、监护人、法定代理人或医院授权；`patient_authority_verified=false`、`phi_storage_allowed=false`。
- `remember` 和 `recall` 只接受 `non_phi`/`deidentified`。即使用户已授权，`phi`/`restricted` 也不得持久化。
- 患者权威授权、撤回传播、病历法定保存期限和跨系统主体解析必须由医院身份/consent 系统、法务和隐私 reviewer 提供证据后另行开放。

## 远程合同

请求固定为：

```json
{
  "contract": "icoder.memory-embedding.request/v1",
  "texts": ["已经过去标识化的单条文本"],
  "normalize": true
}
```

响应固定为：

```json
{
  "contract": "icoder.memory-embedding.response/v1",
  "model": "approved-model-name",
  "model_version": "immutable-version",
  "dimensions": 1024,
  "embeddings": [[0.0]]
}
```

服务端拒绝未知响应字段、非有限值、零向量、16–4096 以外的维度和不一致长度。请求不发送 organization、user、patient、consent、run 或 connector 标识；文本在出站前再次脱敏，多行空白被规范化。模型名、版本和维度必须与已加密索引完全匹配，Cloud 模式发现缺失或旧版本向量时失败关闭，不混用不兼容向量。

## Cloud 必需配置

```dotenv
ICODER_MEMORY_SEMANTIC_URL=https://memory-embedding.example.cn/v1/embed
ICODER_CREDENTIAL_MEMORY_SEMANTIC=<KMS/Secret Manager 注入的 32–512 字符服务凭据>
ICODER_MEMORY_SEMANTIC_REQUIRED=true
ICODER_CONNECTOR_EGRESS_ALLOWLIST=memory-embedding.example.cn
ICODER_PHI_ENCRYPTION_KEY=<KMS 注入的 Fernet key>
```

Cloud 启动只接受 HTTPS 443、无内嵌凭据/query/fragment 的固定 URL，并要求其精确主机已进入 egress allowlist。语义服务凭据只由 `CredentialVault` 解析，不得写入 Connector config、日志、镜像、报告或 SDK。

Local 开发默认 `ICODER_MEMORY_SEMANTIC_REQUIRED=false`，服务不可用时会在输出中明确记录 `semantic_degraded=true`、原因、覆盖率和 lexical fallback 模式。该降级不能用于 Cloud 上线。

## 生命周期与审计

- 内容和向量共用版本化 at-rest 加密；Cloud 无加密 key 时拒绝启动。
- consent 撤销会硬删除对应 Memory 行和向量；到期行不可召回，并由 retention purge 物理删除。
- Connector execution audit 记录成功/失败、Run/Task/trace 归因和稳定错误码，不记录原始文本、向量或凭据。
- 返回内容固定标记 `authoritative=false`、`manual_review_required=true`、`content_trust=user_memory_untrusted`，不得作为临床事实来源。

## 已验证与外部门禁

仓库的真实 TCP E2E 已验证认证、最小请求、电话脱敏、语义同义召回、加密向量、审计、模型版本不匹配失败关闭和撤销硬删除。它使用确定性无原生依赖 fixture，只证明 iCoDer 网络与治理合同，不证明真实 embedding 模型质量、生产吞吐、灾备、延迟、供应链安全或患者授权。

生产仍需：同区域服务部署、真实 Secret Manager、模型/数据许可、临床检索质量集、回填与滚动升级方案、容量/故障注入、多副本一致性、医院隐私与安全审批、独立渗透测试和临床 reviewer 签字。
