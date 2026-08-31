# iCoDer Models 与 LLM 数据出境门禁阶段总结

日期：2026-08-15  
结论：开发环境工程任务已完成；当前是可审计的上线候选能力，不等于真实模型、临床质量或 Corti 托管 SLA 已达标。

## 本轮对标证据

在用户已登录的 Corti 控制台中，只读确认了当前产品面：

- 首页明确展示 `Corti Models`，AI Studio 顶部包含 Transcribe、Document、Chat、Code。
- New Agent 支持从空白创建或使用模板、内嵌 “Ask the agent…” 试聊、JSON context 和实时费用展示。
- 当前模板目录共 20 项，覆盖 ICD-10 Navigator、Rule Explainer、Compliance Guardrail、Code Validation、诊断/手术实体抽取、CDI、Medical Coding、ICU、分诊、护理交班、用药核对、拒付申诉、预授权、转诊、指南等场景。

本轮没有向 Corti 提交临床内容、没有运行预测，也没有消耗 Corti credits。

## 发现并关闭的真实工程缺口

仓库原有 `RuntimeDataPolicy` 和单元测试，但实际 `LLMGateway.generate` / `generate_stream` 边界未强制执行该策略，旧 `LLMService` 路径也可绕过它。这意味着“配置中禁止外部 LLM”此前不等于“网络调用前必然阻断”。

现已完成：

- Gateway 在普通与流式调用前执行结构化出境决策；被拒 Provider 不会收到调用，并返回 `provider_egress_denied`。
- 外部 Provider 被拒时仍保持受控 fallback；只允许策略允许的本地/同区域 Provider 继续执行。
- 旧 `LLMService` 的 chat、stream、tool calling 三条直连路径同步失败关闭。
- Embedded Runtime 默认构造也从环境加载严格策略，避免非主入口绕过。
- Provider 名称归一化覆盖 DeepSeek、Qwen、Moonshot、Azure OpenAI、OpenAI-compatible、本地与 mock；未知/端点明显错配失败关闭。
- CN 默认配置为 `ICODER_ALLOW_EXTERNAL_LLM=false`、`ICODER_REGION=cn`、`ICODER_EGRESS_POLICY=strict`。

## Models 产品面

新增经过认证且禁止缓存的 `GET /api/v1/model-catalog`、双语 Models 页面和三套 SDK 入口。目录只陈述配置与策略证据：

- 当前 Provider、模型名、租户/Provider 区域、出境决策和 blocker；
- DeepSeek、Qwen、OpenAI-compatible、本地与 mock 的可配置能力；
- 只返回“所选 Provider 是否存在凭证”，不返回 API Key、endpoint 或其他秘密；
- `live_health_verified` 固定为 `false`，不会把静态配置冒充在线健康或质量证明；
- 状态区分 `available_to_configure`、`configured_not_live_verified`、`development_only` 和 `blocked`。

SDK 已统一为 JavaScript `sdk.models.getCatalog()`、Python `client.models.get_catalog()`、.NET `client.Models.GetCatalogAsync()`；版本统一提升到 JavaScript/.NET `1.0.0-beta.15`、Python `1.0.0b15`。

## 验证结果

- 后端扩大回归：128/128。
- 最后补充的 Embedded Runtime 默认门禁：13/13。
- 前端：19 个测试文件、120/120；生产构建通过，Models 独立 chunk 7.06 kB，主包 453.64 kB。
- JavaScript SDK：22/22；Python SDK：30/30。
- .NET：代码与合同测试已加入，当前机器无 `dotnet`，由 CI 执行。
- 发布候选验证器：5/5；本地 manifest 为 beta.15，因本机无 .NET 工件而诚实记录 artifacts=0。
- OpenAPI 已重导出为 651,476 bytes，`--check` 通过。
- 运行矩阵：磁盘 32 个 Pack、26 个可见 Agent，26/26 executable、provider-resolvable、launch-candidate-ready；6 个隐藏，其中 5 个仍为 metadata-only，不冒充上线能力。
- 静态部署预检通过：`reports/deployment/development_preflight_20260815_models_egress_final/`。
- 隔离进程 HTTP E2E：认证注册后请求 Models 目录返回 200；当前 Provider=mock、区域=cn、严格策略、外部 LLM=false、模型候选=5、`live_health_verified=false`，秘密字段为 0。证据：`reports/agent_hub/model_catalog_egress_e2e_20260815/model_catalog.json`。
- 隔离测试进程已停止，8015 无监听；WAL/SHM 不存在。临时 SQLite 主文件仍在本地，删除动作被当前执行策略拦截，不影响服务运行或上述只读证据。

所有本地 Python/HTTP 验证均主动移除 `ICODER_CREDENTIAL_LLM` 与 `DEEPSEEK_API_KEY`，固定 mock、禁止外部 LLM并禁用原生 MedCodER；未加载 FAISS/Torch/sentence-transformers/PyArrow，未使用真实 LLM。

## 与 Corti 的剩余能力差距

1. **托管模型基础设施**：iCoDer 已有可审计目录和强制出境边界，但没有证明具备与 Corti Models 等价的托管模型池、在线健康、容量、SLA、计费与自动故障切换。
2. **真实模型质量**：DeepSeek/Qwen/本地模型尚未用新安全凭证和统一去标识病例完成质量、P50/P95、成本及故障模式实跑。
3. **租户自助能力**：当前 Provider/模型选择主要是运维配置并在启动时加载，尚不是完整的逐租户自助切换、配额、账单、路由策略与灰度发布控制面。
4. **Corti 双边基准**：控制台走查只能证明产品面存在；Medical Coding、CDI、Facts、Text Generation、STT 和 20-Agent 同病例输出仍需授权预算与统一金标准逐项比较。
5. **中国生产适配**：CN 区域、失败关闭与中国编码/文书工程基础已具备；真实医院 HIS/EMR、国产化基础设施、地方规则、等保/个保/数安/网安、数据出境评估及医院验收仍是外部门禁。
6. **临床与商业上线**：独立临床 reviewer、双盲标注、法务/DPA、渗透测试、生产云 KMS/容灾/监控、支付结算和运营审批不能在当前开发机内完成。

## 阶段判定

“模型目录存在但不可验证”和“数据策略存在但可被绕过”两类开发环境缺口已经关闭。当前可进入下一阶段的真实、受控模型评测；在完成上述外部门禁前，不应使用“完整复刻 Corti”或“可直接临床上线”的表述。
