# iCoDer Code Validation 受治理本地目录阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床、医保结算、生产、监管或医院上线批准。
>
> 日期：2026-08-23
>
> 阶段：Governed Code Validation local catalog baseline
>
> 状态：开发门禁通过；目录来源/许可、完整语义质量与外部上线门禁仍开放

## 阶段结论

本阶段将 `code-validation-agent` 的默认执行路径从“外部 LLM 主路径 + 弱格式规则回退”收敛为 `icoder.governed-code-validation.v1`。统一 Run、A2A、Agent Pack、Hub readiness 和运行矩阵现在先执行哈希固定的 ICD-10-CN / ICD-9-CM-3 本地目录校验；即使没有模型密钥、网络被禁止，该 Agent 仍能给出目录成员关系、目录可分配性和重复输入检查结果。

这不是完整编码语义验证，也不是权威计费能力。两份本机目录均为 `source_unverified`、`external_review_required`、`billing_authoritative=false`，所以：

- 目录完整性校验通过后才能加载，缺失、大小/哈希不符或 Cloud 使用都会失败关闭。
- 精确叶子条目可标记为目录可分配；目录分类项、未知代码和重复输入会被明确标记。
- 不根据文本猜测替换码，不把目录未命中改写成有效，也不自动写回 EMR/HIS 或提交理赔。
- 即使所有代码都命中，结论仍为 `WARNING` 且 `manual_review_required=true`，直到来源、许可和临床语义都经外部验证。
- 可选 LLM 只允许追加需人工复核的跨代码观察，不能覆盖 `in_catalog`、`assignable`、单码状态或选择替换码。

## 目录资产与治理边界

| 资产 | 版本 | 条目数 | SHA-256 | 当前治理状态 |
|---|---|---:|---|---|
| ICD-10-CN | `observed-local-2026-05-19` | 37,897 | `c83d35e65c4d17a3167221964a65df67659745d630f9f0b9d41f7d4a22bf0984` | 来源未核验、许可待外部复核、仅开发使用、非结算权威 |
| ICD-9-CM-3 | `observed-local-2026-05-19` | 13,617 | `4e00e89f3ab5df55596762c7f725a3ce806ae8292d03b4d655f92a0dc1e91015` | 来源未核验、许可待外部复核、仅开发使用、非结算权威 |

Manifest 同时固定文件大小、司法辖区、用途限制和人工复核要求。Provider 健康检查在报告 ready 前实际核验两个资产；Hub 不会仅凭 Pack metadata 把目录缺失或被篡改的 Agent 显示为本地可运行。

## 运行、合约与审计

- 默认路径：`dedicated.governed_code_validation` → `icoder.governed-code-validation.v1`。
- 输出合同：`icoder/CodeValidationOutput/v7`；旧 v6 保持不可变，新约束通过新版本注册。
- Pack canonical SHA-256：`04126e1bb38b23cad8b93bce5b991872727c9a41ac0daf707d40da5f49bfbb8f`。
- Unified Run 与 A2A 都输出同一严格公共结构；外层 Provider 归因、领域结果和 trace 使用同一 run/provider 身份。
- Trace 仅记录有界资产 ID、版本、authority/license 状态、完整性结果、是否启用语义增强、工具轮次和实际模型成本，不记录本地绝对目录或密钥。
- 本地基线不出网、模型成本为 0。只有同时显式允许外部 LLM、存在进程内凭据且 Provider 非 mock 时才可尝试语义增强。
- HTTP/OpenAPI/SDK 的结果 envelope 未改变；本阶段只升级 Agent 输出 `schema_ref`，无需新增 SDK HTTP 方法。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 定向闭环 | 125/125 | Provider、Pack、矩阵、统一 Run/A2A、Hub readiness 与离线 Agent E2E |
| 合约/参考/预检/资产专项 | 9/9 | v7 不可变注册、参考质量规则、部署预检单测、真实目录计数/Cloud 拒绝 |
| 扩展回归 | 957 passed、5 skipped、0 failed | Agent Hub、Provider、A2A、统一 Run、可见性/发现和 26-Agent 双场景；显式环境依赖项跳过 |
| 26-Agent 离线双场景 | 52/52 | 26 个示例 + 26 个对抗请求；3 个本地基线成功、23 个模型依赖安全失败关闭、0 个不安全响应 |
| 部署候选静态预检 | 81/81 | `deployment_preflight.json` 失败项 0 |
| 运行矩阵 | 通过 | 26/26 visible/executable/provider-resolvable/launch-candidate；23 个外部 LLM 必需、1 个可选、2 个纯本地、3 个具备离线本地基线 |

机器证据位于 `reports/agent_hub/governed_code_validation_phase_20260823/`。测试使用空 LLM 凭据、`LLM_PROVIDER=mock`、禁止外部 LLM 并禁用原生 MedCodER；没有启动浏览器或 TCP Uvicorn。

## 对 Corti Code Validation 的逐项差距

[Corti 官方 Code Validation Agent 页面](https://corti.ai/agents/code-validation-agent) 当前公开说明其输入覆盖 ICD-10-CM、ICD-10-PCS、CPT 与 ICD-10-WHO，并要求每个代码通过 Verify 和 Guidelines 工具验证。公开能力还包括 7th character、laterality、年龄/性别、无依据特异性，以及 Excludes1、sequencing、missing companion、combination code、症状抑制和重复/矛盾代码的整组检查，并要求每个问题引用具体 instructional note 或 guideline。

| 能力 | iCoDer 当前状态 | 差距判断 |
|---|---|---|
| 代码体系 | 本地 ICD-10-CN、ICD-9-CM-3 目录成员/可分配性 | 中国场景基线已建立；未覆盖 Corti 的 ICD-10-CM、ICD-10-PCS、CPT/HCPCS 与 ICD-10-WHO |
| 每码验证 | 精确命中、分类项、未知码、复合匕首/星号代码和重复输入 | 缺 7th character、placeholder、laterality、年龄/性别、文书支持度和 modifier 语义 |
| 跨码验证 | 默认不臆测；可选模型只能追加人工复核观察 | 缺权威 Excludes1、sequencing、companion、combination、症状抑制和矛盾规则引擎 |
| 规则证据 | 记录目录资产 ID、版本、完整性和治理状态 | 缺逐问题官方 instructional note / guideline 原文与规则版本引用 |
| 替换建议 | 明确不自动推断或分配替换码 | 尚无经权威 Explore/Search 验证的候选建议链 |
| 质量证明 | 合成工程回归和安全失败关闭已通过 | 没有当前 Corti 同题对照、独立临床金标准、盲评 reviewer 或医院验收 |
| 上线资格 | `production_ready=false`、强制人工复核 | 目录来源/再分发许可、地区生效版本、医保/医院规则和生产认证均未通过 |

因此，本阶段关闭的是“Code Validation 无模型即不可运行、默认结果不受目录事实约束、Hub readiness 不验证本地资产”的开发差距。它没有关闭 Corti 的完整编码体系、权威规则引用和跨码语义能力差距，也不能把静态 `semantic_live_e2e_verified` 或 `production_ready_verified` 从 0/26 提升。

## 安全与外部门禁

- 未读取或使用用户曾在对话中暴露的真实 DeepSeek 密钥；该密钥应继续视为已泄露并由用户在供应商控制台注销。
- 未操作已登录的 Corti Console；本机存在浏览器内存崩溃风险，本阶段只读取 Corti 官方公开页面。
- 受保护开发数据库 SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；最终没有 Python/Uvicorn 进程，8000/18022 均未监听。
- 未执行 26-Agent 真实 Provider 语义矩阵，也未产生当前 Corti 同题输出、P50/P95、成本或重复稳定性对照。
- 目录不得打包分发或部署生产，直到权利方提供可验证来源、许可、版本、生效地区和更新/撤回机制。
- 医院 EMR/HIS、医保结算、云基础设施、法务、等保/个保/数安、渗透测试、独立临床 reviewer 和生产运维仍是外部上线门禁。

## 下一步

继续按开发环境可关闭的价值排序推进：为 `code-validation-agent` 建立不含受限数据的版本化规则接口和独立合成评测夹具，以便未来接入合法的国家/省市/医院 instructional-note 与交叉编码规则包；同时收敛下一个仍完全依赖外部模型的 Hub Agent。真实模型矩阵只应在密钥已轮换、预算明确、浏览器崩溃风险隔离后执行，且不得用单次合成成功替代临床质量结论。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 新建阶段总结，记录受治理本地目录 Provider、v7 合约、运行矩阵、验证结果和 Corti 差距 | Code Validation 本地基线收敛 |
