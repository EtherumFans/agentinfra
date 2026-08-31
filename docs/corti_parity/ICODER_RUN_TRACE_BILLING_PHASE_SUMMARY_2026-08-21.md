# iCoDer Run Trace、Agent Run 结算与真实模型修复阶段总结

日期：2026-08-21  
阶段结论：Run Trace 安全摘要、逐 Run 开发预授权/幂等结算、OAuth/API Client owner 归集、scope 门禁、崩溃 reservation 协调、三语言 SDK 和前端操作面已完成开发环境闭环。中国临床资产新增版本/完整性/权限/许可/生效期治理门；原先冒充“production/real grouper”的 DRG/DIP 启发式已收敛为非权威、非结算、始终人工复核的开发风险提示。Models 新增默认关闭的固定无患者数据实网 Canary，且 Provider 现在实际执行调用级 token、超时和重试上限。一次真实 DeepSeek 合成 Run 暴露的 diagnosis v6 合同问题已按“不猜测编码”原则修复并通过离线回归；修复后又完成了唯一一次去标识化真实复测，v6 合同通过并签名，但本地检索器禁用使 `search_icd` 失败，最终保持人工复核。本阶段不是临床质量、真实计费或生产 SLA 证明。

## 本轮已完成

### 1. Run Trace 安全组合摘要

- Timeline/raw API 提供不含输入和输出正文的运行摘要：Agent、Run/Trace 状态、模式、延迟、CNY 成本、错误、捕获状态、时间和复核信号。
- `review_signal.authoritative=false`，仅用于工程分流，不冒充临床 reviewer 结论。
- Run Trace 页面统一显示状态、模式、延迟、成本、捕获状态和人工复核信号。

### 2. 真实模型合同缺陷修复

- 脱敏合成 DeepSeek Run `run-84162dd8-dfac-43cc-9346-7f9972158d85` 在 47,683 ms、¥0.002997、4 个 tool rounds 后因模型对未核验 ICD-10-CN 编码留空而触发 `output_contract_violation`。
- 修复不生成或猜测编码：缺少编码或名称的诊断不进入可编码列表，并强制 `REQUIRES_REVIEW` / `manual_review_required=true`；畸形非对象输入仍失败关闭。
- 离线公共投影回归 28/28 通过。
- 修复后唯一一次去标识化 DeepSeek Run `run-71447985-6a29-4c88-9346-d7dd728d2009` 完成：32,619 ms、¥0.003083、5 个 tool rounds、6 次工具调用；`icoder/DiagnosisExtractionOutput/v6` 通过并获得结果签名，输出 1 条已校验候选 `I21.001`，未发生模型重试，也未触发 Models Canary。
- 因安全启动脚本禁用 Windows 原生 MedCodER，本次两次 `search_icd` 均以 `RETRIEVER_UNAVAILABLE` 失败；三次 `verify_code` 和一次 `explore_code` 成功。Provider 状态因此为 `incomplete`，`finish_reason=mandatory_tools_not_completed:search_icd`，响应无运行错误但保留 `manual_review_required=true`。这证明合同修复与失败保护有效，同时证明 ICD 检索链路仍是上线阻断项。
- 新增 `backend/scripts/start_visible_deepseek_e2e_backend.ps1`：只接受同一可见 PowerShell 进程中的临时凭据，强制 DeepSeek/CN 严格出境策略、禁用 Windows 原生 MedCodER 和额外 Models Canary，并在 8000 已占用时失败关闭；脚本不会打印凭据。
- 真实 Run 后停止了临时 8000 后端；随后在不导入原生 ML、不调用 LLM 的条件下完成远端检索客户端/Worker/双索引就绪/资产治理/子进程清理合同 31/31、Cloud 失败关闭配置 40/40、静态部署预检 51/51，四个索引和元数据文件的大小及 SHA-256 均与清单一致。
- 新发现：本地 Compose 的 `ml` profile 虽能声明 `medcoder-retriever`，但后端 `MEDCODER_RETRIEVER_URL` 默认仍为空，现有文档命令也没有设置 `http://medcoder-retriever:8100`；CI 没有实际构建并启动 ML Worker 与 API 做远端检索 E2E。因此静态 51/51 不能证明容器接线可用，下一轮必须修复配置/文档/门禁后在具备 Docker 的 Linux 环境实跑。

### 3. Agent Run 开发预算与结算

- 只有 local/development 且同时启用 `ICODER_BILLING_SIMULATION`、`ICODER_AGENT_RUN_BILLING_ENFORCED` 时生效；云环境拒绝模拟写入。
- Provider 调用前预授权；余额不足返回 402 且 Provider 调用计数为 0。
- Provider 实际成本只结算一次；同一幂等键重放不重复执行或扣费。
- 实际成本超过余额时隐藏临床输出但保留成本证据；充值后可按同一 run id 幂等重试。
- 余额区分账本余额、占用和可用额度；结算列表不含病例输入/输出。

### 4. OAuth/API Client 与 scope

- client_credentials Run 使用 token 中权威 `org_id` 和 `owner_id` 归集开发账本，RunHistory/Trace 继续记录 `api_client_id`。
- 通用 `agents:run`、兼容 `api:write` 和医疗编码/CDI/DRG-DIP 专项 scope 已覆盖；只读 token 在输入处理、预授权和 Provider 调用前返回 403。
- 相同姓名用户注册时默认组织名称不再触发唯一约束 500，组织名和 slug 使用确定性后缀寻找可用组合。

### 5. 崩溃恢复与并发合同

- 显式开发协调器只处理超过最小年龄阈值且没有活跃 RunHistory 的记录。
- 孤立 `RESERVED` 转为 `RELEASED`；孤立 `SETTLING` 保留占用和实际成本，转为可重试 `SETTLEMENT_FAILED`；已有结算失败不被免除；活跃 Run 跳过。
- 预授权、结算、协调、模拟充值和模拟扣费共用 owner 行锁；PostgreSQL 方言确认生成 `SELECT ... FOR UPDATE`。
- SQLite 不提供等价行锁语义，因此真实 PostgreSQL 多副本并发仍是外部验证门禁。

### 6. 中国临床资产与 DRG/DIP 真实性治理

- 新增 `china_clinical_assets_manifest.json`，对本机 ICD-10-CN、ICD-9-CM-3 和 DRG/DIP 风险规则包记录不可变版本、SHA-256、大小、地域、authority/license 状态、生效期、用途限制和人工复核要求。
- 两个本机编码目录已按实际文件固定 SHA-256，但来源和再分发许可明确保持 `source_unverified` / `external_review_required`，不把“文件存在”伪装成官方授权。
- DRG/DIP 本地规则包明确为 `experimental_unverified`、`billing_authoritative=false`、`CN_GENERIC_DEVELOPMENT`；支付权重、DIP 分值和支付金额统一为 0，不再输出伪精确估算。
- 本地只允许风险复核；billing、settlement、production grouping 以及未验证规则包的 cloud 使用全部失败关闭。校验和错误、重复版本、未显式选择回滚版本和路径逃逸均有反例测试。
- DRG API 整体要求认证；Agent Pack 输出合同升级为 `icoder/DRGDIPRiskReview/v4`，治理字段由运行时 const 权威注入，模型即使声称 `billing_authoritative=true` 也会被强制覆盖为 false。
- DRG/DIP OpenAPI 成功响应已从无类型对象收敛为明确的治理、规则、分析 schema；年龄/性别边界在分析前返回 422，任何内部 Adapter 失败返回 503 而不是携带不可用结果的 200。
- JavaScript `beta.17`、Python `b17`、.NET `beta.17` 新增认证的 DRG/DIP 风险审查资源；客户端共同拒绝权威声明、非零权重/分值/支付金额或免人工复核响应，不公开伪装成官方分组器的便捷入口。
- UI 和 Embedded Assistant 已从“DRG/DIP 支付分析”改为“风险复核（非结算）”，并禁止提示词要求预测官方分组、权重、分值或支付金额。

### 7. Models 受控实网 Canary

- 功能默认关闭；只允许 owner/admin 在已登记且当前精确路由的 DeepSeek、Qwen 或 OpenAI-compatible 外部部署上显式确认调用。
- 请求 schema 禁止额外字段，因此调用方不能传入提示词、患者文本或其他自由文本；服务端只发送固定合成连通性载荷，模型完成正文既不返回也不写入日志/审计。
- 先持久化 `started` 审计再发起网络请求；同一组织在 300 秒冷却期内的第二次调用返回 429，且不会触发第二次 Provider 调用。
- 服务端上限为 ¥0.05、最多 8 个输出 token、15 秒、仅 1 次尝试；租户出境策略、凭据状态、精确部署和保守成本估算任一不满足都在网络调用前失败关闭。
- Gateway 的请求级 `max_tokens`、timeout 和 `max_attempts` 现在会真正传递给 Provider，且调用方只能收紧、不能放宽服务端上限。
- 目录和三 SDK、前端明确把结果标记为 `connectivity_only_no_patient_data`；即使成功也不把 `live_health_verified` 改为 true，不证明质量、持续健康、SLA 或权威账单。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Diagnosis 安全投影 | 28/28 passed |
| Run Trace 定向 | 11/11 passed |
| Billing + OAuth scope + 崩溃协调 + PG 锁合同 | 11/11 passed |
| Billing 模拟与 Agent Run 结算组合 | 13/13 passed |
| Runtime Token / OAuth | 28/28 passed |
| API Client CRUD | 15/15 passed |
| Agent Run 幂等与生命周期 | 15/15 passed |
| Auth（含同名默认组织） | 10/10 passed |
| 数据库约束与审计脱敏 | 37/37 passed |
| Alembic / schema drift | 9/9 passed；单 head `043` |
| 中国资产治理 + DRG/DIP API/Adapter/OpenAPI | 63/63 passed |
| Agent Hub/Pack/发现/部署当前扩大回归 | 194/194 passed；同时修复 Python 3.12 Clone DB 断言 event-loop 兼容性 |
| Pack schema/example/不可变注册/运行矩阵 | 32 disk Packs、26 visible、6 hidden（其中 5 metadata-only）；101 registered contracts；可见面 26/26 executable/provider-resolvable/launch-ready，无可见 stub |
| Corti 20-Agent 目录与中国适配映射 | 20/20 catalog mapped、development verified、China profile declared；临床质量/生产就绪仍诚实为 0/20 |
| 部署候选静态预检 | 51/51 passed；`development_preflight_20260821_model_canary`，新增 Canary 固定载荷/无正文/预算/冷却/三 SDK 门禁 |
| Models Canary + Provider 限额 + 审计定向 | 48/48 passed；与工具门/诊断投影组合回归 116/116 passed |
| 前端 | 21 files，132/132 passed；生产构建 passed |
| Embedded Assistant | TypeScript build passed |
| JavaScript SDK | 31/31 passed；`1.0.0-beta.17` dry-run package passed |
| Python SDK | 38/38 passed；`1.0.0b17` wheel built |
| .NET SDK | `1.0.0-beta.17` DRG/DIP 与 Models Canary 源码合同及反例测试已更新；本机无 `dotnet`，待 CI |
| Release candidate 版本门 | 5/5 passed；三 SDK 归一版本 `1.0.0-beta.17`；本机构建 JS `.tgz` 与 Python `.whl` 两个 SHA-256 工件；.NET 工件缺失；`source_tree_state=dirty`、`publication.performed=false`，不得冒充可由 HEAD 复现的正式发布物 |
| OpenAPI | 715,968 bytes；已包含 DRG/DIP 和 Models Canary 类型合同；`--check` passed |

不同后端测试集合存在交集，不能把上表简单相加成一个“总通过数”。

## 当前与 Corti 的能力差距

| 能力 | 本轮状态 | 仍缺证据 |
|---|---|---|
| Run/Trace 审计 | 开发闭环 | 生产可观测性、告警、长期留存和医院审计验收 |
| 项目计量/计费 | owner 归集开发账本、预授权和幂等结算 | 真实项目财务账户、支付、发票、退款、税务和财务对账 |
| 模型托管 | 外部/本地部署路由、逐 Run 追踪及固定无患者数据的单次连通 Canary | Corti 等价托管模型池、个人 Key 生命周期、容量、持续在线健康和 SLA |
| 真实模型质量 | 历史单 Agent 4/4 最小成功；本轮 diagnosis 修复后单次真实复测通过 v6 并签名，但因 `search_icd` 不可用保持人工复核 | 26-Agent 快乐/对抗/重复真实模型矩阵，以及启用受治理 ICD 检索后的重复质量验证 |
| 中国场景 | ICD-10-CN、ICD-9-CM-3、DRG/DIP、CN 出境门禁及资产治理工程链；未验证规则明确非权威并失败关闭 | 官方/地区/医院规则包、来源与再分发许可、生效版本、真实医院接口、临床 reviewer 和法规认证 |

## 外部门禁

- 真实 DeepSeek/Qwen/医院本地模型的 26-Agent 合成质量、P50/P95、成本和稳定性。
- Linux/.NET CI、真实 PostgreSQL 多副本、Docker/Nginx/SSE、SBOM、漏洞和渗透测试。
- 云 KMS、容量、监控、灾备、值守和 SLA 演练。
- 医院 HIS/EMR/FHIR、身份、网络隔离和数据治理验收。
- 国家/省市/医院 DRG/DIP 与编码目录的合法来源、许可、生效期、地区规则和结算引擎验收。
- 独立临床 reviewer、双盲标注、误差/偏差评估。
- 中国法务、等保、个保/数安/网安、备案/认证和必要的数据出境评估。

结构化证据：[`run_trace_billing_settlement_phase_20260821`](../../reports/agent_hub/run_trace_billing_settlement_phase_20260821/phase_evidence.json)。  
权威差距矩阵：[`CORTI_ICODER_LIVE_GAP_MATRIX_2026-08-21.md`](CORTI_ICODER_LIVE_GAP_MATRIX_2026-08-21.md)。
