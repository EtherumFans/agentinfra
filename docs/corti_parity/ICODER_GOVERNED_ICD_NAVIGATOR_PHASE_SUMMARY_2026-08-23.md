# iCoDer ICD-10 Navigator 受治理本地索引阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床编码、医保结算、生产、监管或医院上线批准。
>
> 阶段：Governed ICD-10-CN Search + one-level Explore
>
> 状态：开发门禁通过；目录来源/许可、权威说明、临床质量和外部上线门禁仍开放

## 阶段结论

本阶段将 `icd10-navigator` 从只有 Pack 描述且依赖通用 LLM 的入口，收敛为可真实执行的 `icoder.governed-icd-navigator.v1`。默认路径只读取经 manifest 固定大小和 SHA-256 的本地 ICD-10-CN 目录及术语反向索引，不调用网络或 LLM，成本为 0。

已实现的能力边界是：接受明确的中文术语或编码；执行一次 Search；首次未命中时最多按输入中明确连接词拆分一次；返回最多 3 个候选；对候选展示一层父类目、同层和子条目。它不解释病历、不判断临床适用性、不执行 Verify/Guidelines、不分配或推荐编码，也不生成资产中不存在的包括/不包括说明。所有候选均 `manual_review_required=true`，必须进入 Code Validation 并由编码员审核。

## 资产与治理

| 资产 | 数量 | 大小 | SHA-256 | 当前治理状态 |
|---|---:|---:|---|---|
| `icd10cn_code_catalog.json` | 37,897 条 | 25,996,500 bytes | `c83d35e65c4d17a3167221964a65df67659745d630f9f0b9d41f7d4a22bf0984` | 来源未核验、许可待外部复核、仅开发使用、非结算权威 |
| `icd10cn_synonym_map.json` | 56,424 个术语索引、21 类同义词 | 15,292,266 bytes | `714424136ae80ac08cc67d8ad4a6768120d4b61b1b508e0d7aacfcf54dc6b5d0` | 与同一资产绑定，来源/许可边界相同 |

此前运行时会加载术语映射，但 manifest 只固定主目录。本阶段把两个实际加载文件都纳入同一完整性声明。文件缺失、大小或哈希不符、Cloud 使用或健康探针失败时，Navigator 返回 `CATALOG_UNAVAILABLE` 或在 Hub 中禁用运行，不会仅凭 Pack metadata 显示 ready。

源目录中少数自动生成类目名称与上级编码可能存在语义错配。运行时对生成类目及生成父类目隐藏 `display`，只保留代码层级，不把可疑名称呈现为临床事实；叶子名称仍是来源数据，必须继续人工复核。这是已识别的数据质量门禁，不是已修复的权威数据问题。

## 运行、合同与审计

- Provider Registry 路径：`icoder.governed-icd-navigator.v1`，类型 `rule_engine`，确定性、本地、无工具调用、无网络/LLM。
- Agent：`icoder/icd10-navigator@1.1.0`；运行模式 `governed_local_index_navigation`。
- 最终输出合同：`icoder/Icd10NavigatorOutput/v4`。v2/v3 保持注册记录不变；严格 schema 加固使用新 v4，未覆盖既有指纹。
- Pack canonical SHA-256：`27d83b6cb4cb5234b21c1327c9792eaeed978c936f1fb6c92145afd8a07b9ccb`。
- Unified Run、A2A、Hub readiness 与 trace 使用同一 Provider；A2A DataPart 只包含 v4 公共字段，Provider 身份留在安全 metadata。
- Trace 只记录有界资产 ID/版本、候选数、查询词数和是否重述，不记录本地绝对路径、输入全文或密钥。
- 输入中的已知对抗后缀和 canary 边界会被剥离；未知术语不会猜码，空输入返回 `INPUT_REQUIRED`。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 最终扩大回归 | 967/967 | Agent Hub、Provider、Pack、合同、A2A、统一 Run、可见性/发现、Navigator 算法/资产和 26-Agent 双场景 |
| 26-Agent 离线双场景 | 52/52 | 26 个示例 + 26 个对抗请求；4 个本地基线成功、22 个模型依赖安全失败关闭、0 个不安全响应 |
| Hub 本地健康降级 | 8/8（包含于扩大回归） | Navigator 索引健康失败只禁用自身；Code Validation 等其他本地 Agent 不受误伤 |
| 合同与递归 schema | 通过 | 候选最多 3、层级数组最多 10、枚举/常量/数值范围受统一同步器约束，v4 已追加注册 |
| 部署候选静态预检 | 81/81 | 失败项 0；未运行 Docker/Cloud 外部门禁 |
| 运行矩阵 | 通过 | 26/26 visible/executable/provider-resolvable/launch-candidate；22 个外部 LLM 必需、1 个可选、3 个纯本地、4 个离线本地基线 |

机器证据位于 `reports/agent_hub/governed_icd_navigator_phase_20260823/`。测试使用空 LLM 凭据、`LLM_PROVIDER=mock`、禁止外部 LLM并禁用原生 MedCodER；没有启动浏览器或 TCP Uvicorn。

## 对 Corti ICD-10 Index Navigator 的差距

[Corti 官方 ICD-10 Index Navigator Agent 页面](https://www.corti.ai/agents/icd-10-index-navigator-agent) 当前公开边界是：临床术语搜索候选；首次无结果时最多重述一次；对主要结果向上/向下各探索一层并展示 siblings/children；默认最多 3 个主术语块；只有工具返回时才展示 inclusion/exclusion notes；只使用 Search + Explore，不使用 Verify/Guidelines；不负责分配、验证、推荐编码或解释说明。

| 能力 | iCoDer 当前状态 | 差距判断 |
|---|---|---|
| Search 与一次重述 | 中文术语、精确编码/前缀、固定术语索引和有界词面命中；显式复合连接词最多拆分一次 | 公开流程边界基本对齐；不是 Corti 托管 Search 工具，也没有同题返回集对照 |
| 一层 Explore | 父类目、最多 10 个同层及子条目，最多 3 个主候选 | 结构对齐；本地目录层级由编码前缀生成，尚未用权威索引树验证 |
| Instructional notes | 资产不含可验证说明时明确报告 unavailable，不生成或解释 | 安全边界对齐；缺权威 inclusion/exclusion notes 数据与精确来源引用 |
| 不分配/不验证 | 明确不执行 Verify/Guidelines，不判断适用性，强制下游 Code Validation + 人工复核 | 行为边界对齐；下游 Code Validation 本身仍缺完整权威语义规则 |
| 中国场景 | ICD-10-CN 中文术语、同义词和中文复合表述，本地不出网 | 已建立中国场景开发基线；目录来源、许可、地区生效版本和医保/医院权威性均未完成 |
| 质量证明 | 确定性合成回归、篡改/Cloud/注入失败关闭、Run/A2A/Hub/Trace 一致 | 没有当前 Corti Console 同题对照、独立临床金标准、盲评 reviewer、真实医院验收或生产稳定性证据 |

因此，本阶段关闭的是“Navigator 只有元数据、默认依赖 LLM、没有受治理本地 Search/Explore、Hub 不验证索引资产”的开发差距。它没有关闭 Corti 托管工具、权威 ICD 数据与说明、临床质量或生产服务能力差距；`semantic_live_e2e_verified` 与 `production_ready_verified` 仍为 0/26。

## 安全与外部门禁

- 未读取或使用用户曾在对话中暴露的 DeepSeek 密钥；该密钥应继续视为已泄露并在供应商控制台注销。
- 未操作 Corti Console，也未启动 Chromium；本机已有浏览器/测试内存崩溃风险。
- 未执行真实 LLM、真实 Corti 同题、医院 HIS/EMR、医保结算、Docker、Cloud、PostgreSQL 多副本、.NET 本机或生产容量测试。
- 目录不得打包分发或部署生产，直到合法权利方确认来源、再分发许可、版本、生效地区、更新和撤回机制。
- 法务、等保/个保/数安、渗透测试、独立临床 reviewer、医院验收和生产运维仍是外部上线门禁。

## 下一步

继续按开发环境可关闭价值推进下一个仍完全依赖外部模型的 Hub Agent；同时为 Navigator 建立可替换的权威目录/说明适配接口和不含受限数据的独立评测夹具。真实模型与 Corti 同题矩阵只应在密钥已轮换、预算明确且浏览器/进程隔离后执行，不能用单次合成成功替代临床质量结论。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 新建阶段总结，记录受治理本地 Search/Explore、双资产完整性、v4 合同、验证结果和 Corti 差距 | ICD-10 Navigator 本地能力收敛 |
