# iCoDer 租户模型路由与逐 Run 审计阶段总结

日期：2026-08-15  
阶段结论：开发环境中的租户模型选择、精确路由、失败关闭、管理权限、版本冲突、审计、前端和三语言 SDK 已完成；这仍不是 Corti Models 托管服务、真实模型质量或生产 SLA 的等价证明。

## Corti 当前只读证据

在用户已登录的 Corti Console `Corti Models` 页面只读确认：

- Corti 将该能力描述为运行在欧洲基础设施上的托管 frontier models，并声明 EU 数据驻留和 GDPR 合规；
- 页面提供 `npx @corti/cli models init`，通过浏览器认证生成个人模型 API Key；
- 使用量计入所选项目账单，页面同时提供 Billing 余额入口；
- 当前项目尚未创建 Corti Models Key，本轮没有创建 Key、调用模型、提交临床内容或消耗 credits。

因此，本阶段对标的是“项目/租户可选模型、可追溯实际路由、失败关闭”的开发控制面，不把 iCoDer 的运维声明部署冒充 Corti 的托管模型池。

## 已完成的开发能力

### 1. 租户级模型选择

- 新增认证且 `Cache-Control: no-store` 的 `PUT /api/v1/model-catalog/selection`；只有组织 owner/admin 可修改。
- 支持 `inherit` 和 `pinned` 两种模式；更新必须提交 `expected_version`，并在数据库行锁下检测并发冲突。
- 组织通用设置接口把 `_model_routing` 设为保留字段，不能绕过专用权限、校验和审计入口修改。
- 选择结果写入组织设置并产生 `model.selection.update` 审计，保留前后模式、部署 ID 和版本，不记录 endpoint 或凭证。

### 2. 多部署、秘密隔离与精确路由

- 运维可通过 `ICODER_LLM_DEPLOYMENTS_JSON` 声明最多 16 个命名部署；支持 DeepSeek、Qwen、OpenAI-compatible 和医院本地部署。
- 配置只接受部署 ID、Provider、模型、endpoint、凭证环境变量名及租户可选标志；内联 `api_key`、`secret`、`credential` 等字段会被拒绝。
- 外部部署要求 HTTPS；凭证环境变量名必须符合 `ICODER_CREDENTIAL_LLM_*`，目录只公开 `credential_configured` 布尔值。
- Gateway 对 pinned 部署执行 `get_exact()`：部署缺失、策略解析失败、显式 Provider 冲突或数据出境策略拒绝时均失败关闭，绝不静默回退到全局默认或 mock。
- `inherit` 保留运维默认和受控 fallback 语义；租户选择通过请求 ContextVar 绑定到权威组织 ID，并在每次模型调用前从数据库读取当前版本。

### 3. 目录、UI、SDK 与逐 Run 追踪

- Models 目录同时显示运维默认、租户有效部署、租户选择版本、可选部署清单和策略 blocker；不返回 endpoint 或密钥。
- Models 页面为 owner/admin 提供继承/固定部署切换，并处理乐观锁冲突和部署不可用错误。
- JavaScript、Python、.NET SDK 均新增读取目录和版本化更新选择的强类型接口；候选版本统一为 JS/.NET `1.0.0-beta.16`、Python `1.0.0b16`。
- Pure LLM 和 LLM-with-tools 的成功及失败路径都会在 Run Trace 写入：`model_deployment_id`、`model_routing_mode`、`model_selection_version`、`model_routing_decision`。
- Run Trace 页面直接展示上述字段。工具型 Provider 中此前缺失的路由提取辅助函数已补齐，避免相关分支出现 `NameError`。
- 审计脱敏允许安全的枚举化 `runtime_mode`，自由文本 `error_reason` 仍默认拒绝，避免扩大 PHI 泄露面。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| 后端模型路由、目录、Run Trace、Agent Run、审计组合 | 132/132 passed |
| Run Trace 定向修复 | 38/38 passed（包含在上述组合中） |
| 前端全量 | 20 files，129/129 passed |
| 前端生产构建 | passed；主 chunk 454.25 kB，Models chunk 9.82 kB |
| JavaScript SDK | 26/26 passed |
| Python SDK | 33/33 passed |
| 发布候选验证器 | 5/5 passed；beta.16，`artifacts=0` |
| OpenAPI | 666,639 bytes；`--check` passed |
| 部署候选静态预检 | 50/50 passed |
| Agent Hub 运行矩阵 | 26/26 可见 Agent executable、provider-resolvable、launch-candidate-ready |
| 模型配置健康探针 | 4/4 model-catalog API 定向测试；无网络调用、无密钥/端点回显、脱敏审计和租户目录回显 |
| Agent Run 开发预算与结算 | Billing/OAuth scope/崩溃协调/PG 锁合同 11/11、Runtime/OAuth 28/28、API Client 15/15、幂等/生命周期 15/15；Provider 前预授权、实际成本一次结算、幂等重放不重复调用/扣费、结算不足隐藏输出并可充值重试；API Client owner 归集、专项 scope、陈旧协调和 owner 行锁 SQL 合同已闭环 |
| 迁移与 schema drift | 9/9 passed；Alembic 单 head `043` |
| Corti 20-Agent 目录门禁 | 20/20 映射、开发验证和中国适配声明；临床质量/生产就绪 0/20 |
| .NET | 源码和合同测试已更新；本机无 `dotnet`，由 CI 阻断验证 |

最终预检证据：[`reports/deployment/development_preflight_20260815_tenant_model_routing_final/`](../../reports/deployment/development_preflight_20260815_tenant_model_routing_final/)。
运行矩阵与目录证据：[`runtime_matrix_20260815_tenant_model_routing_final/`](../../reports/agent_hub/runtime_matrix_20260815_tenant_model_routing_final/)、[`corti_catalog_20260815_tenant_model_routing_final/`](../../reports/agent_hub/corti_catalog_20260815_tenant_model_routing_final/)。

## 隔离 HTTP E2E

使用独立 SQLite、随机测试组织、mock 全局默认和第二个命名本地部署 `hospital-local-e2e` 完成真实 HTTP 流程：

1. 目录初始为 `inherit/version=0`；
2. owner 固定到命名部署后变为 `pinned/version=1`；
3. 目录有效 Provider/模型/部署分别为 `local`、`hospital-model-e2e`、`hospital-local-e2e`；
4. Diagnosis Extractor 实际调用固定部署并得到 `provider_http_502`，运行失败关闭；
5. 没有观察到 mock fallback；目录扫描未发现 `api_key`、`credential_llm` 或 `base_url`。

证据：[`tenant_model_routing.json`](../../reports/agent_hub/tenant_model_routing_e2e_20260815/tenant_model_routing.json)。该目标是 `127.0.0.1:9`，本机 Clash/代理环境可能参与了 502 返回，因此该 E2E 证明“租户选择进入真实运行路径且失败不回退”，不证明网络隔离或真实 Provider 可用性。

## 真实 DeepSeek 最小 E2E（2026-08-16）

用户在专用可见 PowerShell 中输入临时凭证后，使用隔离 SQLite 和 `LLM_PROVIDER=deepseek` 启动 8000。健康接口返回 `llm_provider=deepseek`、`llm_model=deepseek-chat`，原生 MedCodER 被显式禁用。

- 4 次合成中文 `diagnosis-extractor` 最小 Run 均返回 `error=false`，每次约 4.8–4.9 秒；没有发送真实患者信息。
- 最后一次 Run 的 `schema_ref` 为 `icoder/DiagnosisExtractionOutput/v6`，内部 Trace 返回 3 个事件。
- Trace 的后端审计字段为：Provider `icoder.llm-with-tools.v1`、类型 `llm_with_tools`、部署 `deepseek`、路由 `inherit`、选择版本 `0`、决策 `allow`、Provider 状态 `requires_review`、`fallback_used=false`。
- 8000 后端进程和专用 PowerShell 已停止，端口已确认关闭；脚本 finally 已清除窗口临时变量。
- 主机安全策略拒绝了对临时数据库的删除命令，`C:\Users\huawei\AppData\Local\Temp\icoder-deepseek-smoke-20260815.db` 仍可能存在，需在用户确认后手动删除；它不在项目目录。
- 本次临时 API Key 尚未由 Codex 代为注销；用户必须立即在 DeepSeek 控制台撤销/轮换，不能把聊天中出现过的凭证继续用于生产。

真实烟测结构化证据：[`tenant_model_routing_real_deepseek_e2e_20260816.json`](../../reports/agent_hub/tenant_model_routing_real_deepseek_e2e_20260816.json)。

## 26-Agent 隔离 mock HTTP 矩阵（2026-08-21）

在不使用真实密钥的隔离服务上完成全量合成回归：快乐路径 26/26、对抗路径 26/26 均完成 HTTP 请求；两套矩阵均为 1 个确定性 Compliance Guardrail 通过、25 个 LLM 依赖 Agent 显式 `degraded:mock_provider` 或结构化错误失败，且均无 5xx。该结果验证请求合同、Run/Trace、内容安全和失败关闭，不代表真实模型质量或临床成功率。

证据：[`mock_examples_e2e_20260821`](../../reports/agent_hub/mock_examples_e2e_20260821/)、[`mock_adversarial_e2e_20260821`](../../reports/agent_hub/mock_adversarial_e2e_20260821/)。隔离服务已停止；临时 SQLite 测试库在主机临时目录，因主机策略未强删。

健康探针实现与测试：`backend/app/api/model_catalog.py` 的 `POST /api/v1/model-catalog/health-probe` 只调用已注册 Provider 的本地 `health_check()`，记录 `model.health.probe` 审计事件，并将最近状态安全地展示在租户模型目录中。它仍不会把配置状态宣称为实时网络健康或临床质量。

账本模拟实现与测试：`backend/app/api/billing.py` 现在按租户交易金额求和计算余额；无交易用户为真实 `0`，开发环境可显式执行模拟充值和 `/simulation/debit`，低余额和透支均有明确合同，云环境拒绝模拟变更。`run_billing_settlement.py` 通过双开关把 Agent Run 接入 Provider 前预算预授权和实际成本幂等结算；结算不足会保留成本证据但隐藏临床输出，并允许充值后按同一 run id 重试。client_credentials 运行按 token 中权威 org/owner 归集账本，Run/Trace 保留 `api_client_id`；只读 token 在输入处理前被拒绝，通用及医疗编码/CDI/DRG-DIP 专项 scope 已测试。开发操作员可显式协调超过阈值的崩溃状态：孤立 RESERVED 才释放，孤立 SETTLING 转成保留成本的可重试失败，活跃 RunHistory 跳过。预授权、结算和协调在 PostgreSQL 方言下统一编译为 owner 行 `FOR UPDATE`；该账本不是支付、发票或 Corti 项目结算系统，真实 PostgreSQL 多副本并发仍未证明。

注册回归同时发现并修复了同名用户默认组织名称的唯一约束 500：组织名与 slug 现在共同使用确定性后缀寻找可用组合，10/10 Auth 回归通过。

Run Trace 组合审计视图已增加不含输入/输出的安全摘要，统一展示运行状态、模式、延迟、成本、Trace 捕获状态及非权威人工复核信号；后端定向测试 11/11，前端生产构建及全量 129/129 通过。信号只用于工程分流，不冒充临床判定。

2026-08-21 的一次脱敏合成 DeepSeek Run（`run-84162dd8-dfac-43cc-9346-7f9972158d85`）在 47,683 ms、¥0.002997、4 个 tool rounds 后因模型对未核验 ICD-10-CN 编码留空而触发 v6 输出合同失败。修复不会猜测编码：缺少编码或名称的候选不进入可编码诊断，结果强制 `REQUIRES_REVIEW`；畸形对象仍失败关闭。离线投影回归 28/28 通过，修复后真实复测仍待 8000 后端成功启动。

本阶段结构化证据：[`health_billing_phase_20260821`](../../reports/agent_hub/health_billing_phase_20260821/phase_evidence.json)。
本轮追加证据：[`run_trace_billing_settlement_phase_20260821`](../../reports/agent_hub/run_trace_billing_settlement_phase_20260821/phase_evidence.json)。

## 与 Corti Models 的剩余差距

| 能力 | iCoDer 当前证据 | 仍缺内容 |
|---|---|---|
| 租户模型选择 | owner/admin、版本锁、审计、精确失败关闭 | 灰度、按 Agent/任务策略、自动健康切换 |
| 模型托管 | 可声明外部或医院本地部署 | Corti 等价托管模型池、容量、升级、SLA |
| 凭证生命周期 | KMS/环境注入边界，API 不回显秘密 | 个人模型 Key 的签发、撤销、轮换、作用域与使用审计 |
| 健康和质量 | `live_health_verified=false`，不伪造在线状态 | 多 Provider 实时健康、质量、P50/P95、成本和故障演练 |
| 计量计费 | 运行成本字段和 SDK 合同 | 项目余额、配额、账单、发票、退款和财务对账 |
| 区域合规 | CN 严格出境门禁、本地部署合同 | 真实国产云/医院部署、等保、个保/数安/网安审查与数据出境评估 |

## 尚未关闭的门禁

- 真实 DeepSeek/Qwen/本地模型的统一脱敏病例质量、延迟、成本、稳定性与失败模式需要新安全凭证和受控后端进程。
- Docker、PostgreSQL 多副本、反向代理、KMS、监控、容量和灾备未在本机实跑。
- 临床 reviewer、医院 HIS/EMR、法规/法务、渗透测试、独立认证、模型/字典/指南许可和商业结算仍是外部门禁。

真实密钥不会写入代码、配置、报告或命令输出；完成真实烟测后必须在 DeepSeek 控制台注销/轮换本次凭证。
