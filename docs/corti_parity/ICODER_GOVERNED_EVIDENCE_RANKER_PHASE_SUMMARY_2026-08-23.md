# iCoDer Evidence Ranker 文档可追溯性本地基线阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床证据判定、诊断、编码、医保结算、生产或医院上线批准。
>
> 阶段：Governed documentation-grounding evidence ranking
>
> 状态：开发门禁通过；临床语义、权威编码规则、独立质量和外部上线门禁仍开放

## 阶段结论

本阶段将 `evidence-ranker` 从 `icoder.pure-llm.v1` 收敛为无需模型、无需网络、成本为 0 的 `icoder.governed-evidence-ranker.v1`。统一 Run、A2A、Hub readiness、Trace 和 Pack 现在执行同一套确定性文档可追溯性排序策略。

该本地基线只处理用户显式提供的候选编码、证据内容、来源标签、source document 字符区间、certainty 和 negation 标记。`documentation_grounding_score` 由内容、来源标签、唯一 evidence ID、精确 span 和候选码词面出现等可审计分量组成；来源文档类型不会影响分数。它不解释医学含义、不判断证据是否临床支持候选编码、不验证或推荐编码，也不把分数称为诊断概率或编码置信度。

现有 `app.services.evidence_ranker` 会给任意证据 0.5 基线分，并按出院记录、既往史等文档类型增减分，可能把来源类型误当作临床支持度。本阶段没有把该历史服务直接暴露到 Hub，也没有修改其历史调用方；上线候选路径由新的保守 Provider 隔离承载。

## 输入、排序与失败关闭

- 支持结构化 JSON：最多 50 个 `evidence_items` 和 50 个 `source_documents`；也支持 `证据A（来源）：内容` 的有界中文标签格式。
- 同时提供 `doc_id`、`char_start`、`char_end` 时执行精确字符区间校验；不一致、越界或 source document 不可用都会显式降级。
- 重复 evidence ID 只保留首次出现项并报告结构冲突，不合并或猜测哪一项正确。
- `confirmed/suspected/probable/ruled_out/unknown` 和显式 negation 只作为用户提供的排序标记；不从病历文字推断这些状态。
- 未提供来源标签、内容为空或 span 无法验证时进入 `unsupported_claims`；没有可排序证据时返回 `INPUT_REQUIRED`，不生成合成成功结果。
- 已知对抗后缀和 canary 边界后的内容不会进入排序。
- 全部输出始终 `manual_review_required=true`，不允许自动写回、改码、提交或结算。

## 运行、合同与审计

- Agent：`icoder/evidence-ranker@1.1.0`。
- Provider：`icoder.governed-evidence-ranker.v1`，类型 `rule_engine`，确定性、无工具、无网络、无 LLM。
- 策略：`icoder.documentation-grounding-ranking@1.0.0`；`clinical_support_assessed=false`。
- 最终输出合同：`icoder/EvidenceRankerOutput/v4`。旧 v2 和本轮中间 v3 均保留注册记录；最终严格字段关系通过 v4 append-only 注册。
- Pack canonical SHA-256：`411b2a77f7588ed0a8dc1d57285a227853028398599c4483647dfce83e02d80a`。
- v4 约束候选证据最多 50 项、score 0–1、枚举状态、固定 `DOCUMENTATION_GROUNDING_ONLY`，并强制 `INPUT_REQUIRED` 为空、`RANKED*` 非空和人工复核。
- Trace 只记录 evidence/span 数量及 0–1 来源覆盖率，不记录证据正文、来源文本、本地路径或凭据。
- Hub 健康检查绑定该 Provider 自身策略；探针失败时只禁用 Evidence Ranker，不误伤其他本地 Agent。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 最终扩大回归 | 986/986 | Agent Hub、Provider、Pack、合同、A2A、统一 Run、可见性/发现、Navigator/Evidence Ranker 算法和 26-Agent 双场景 |
| 26-Agent 离线双场景 | 52/52 | 26 个示例 + 26 个对抗请求；5 个本地基线成功、21 个模型依赖安全失败关闭、0 个不安全响应 |
| Evidence Ranker 集中回归 | 220/220 | 算法负向、Provider、Run/A2A、Hub、Trace、Pack、合同、参考回放和离线矩阵 |
| 字段关系对抗回放 | 63/63 | 12 个 Agent 的 38 条关系均能检测故意破坏的输出；定义错误 0 |
| 部署候选静态预检 | 81/81 | 失败项 0；未运行 Docker/Cloud 外部门禁 |
| 运行矩阵 | 通过 | 26/26 visible/executable/provider-resolvable/launch-candidate；21 个外部 LLM 必需、1 个可选、4 个纯本地、5 个离线本地基线 |

机器证据位于 `reports/agent_hub/governed_evidence_ranker_phase_20260823/`。测试使用空 LLM 凭据、`LLM_PROVIDER=mock`、禁止外部 LLM并禁用原生 MedCodER；没有启动浏览器或 TCP Uvicorn。

## 对 Corti 的邻近能力差距

Corti 当前公开 [Agent Library](https://corti.ai/agents) 没有名为 “Evidence Ranker Agent” 的独立预构建 Agent，因此不能声称存在一一对应复刻。邻近对标是 [Corti Medical Coding Agent](https://corti.ai/agents/medical-coding-icd-10-cpt-agent) 和 [Symphony Medical Coding](https://corti.ai/medical-coding)：公开说明要求编码严格锚定病历证据、每个代码关联具体文档、证据不足时显式报告，并提供 supporting evidence、ranked alternatives 和 audit trail。Corti 的研究页面还公开说明其支持每个预测代码的 span-level evidence attribution。

| 能力 | iCoDer 当前状态 | 差距判断 |
|---|---|---|
| 文档锚定 | 对输入中已经给出的 evidence 执行来源/span 精确校验和可解释排序 | 审计基础对齐；不会从整份病历抽取证据或判定临床支持 |
| 排序含义 | 只表示 documentation grounding，不表示医学相关性、诊断或编码置信度 | 更保守且诚实；与 Corti 的模型驱动 supporting evidence / ranked alternatives 不是等价能力 |
| 编码能力 | 候选码仅作词面参照，不分配、验证或推荐 | 缺 Corti 的 ICD-10-CM/PCS、CPT/HCPCS 赋码、规则验证、排序替代和解释链 |
| 证据冲突 | 仅检测重复 ID、span 不一致、来源缺失等可确定结构问题 | 不检测医学语义矛盾；这需要受验证模型、工具和独立临床质量证据 |
| 中国场景 | 中文标签、中文来源名称、本地不出网、适配中国病历证据链输入 | 已建立最小可审计基线；缺合法真实医院数据、中文临床语义评测和权威 CN 编码规则联动 |
| 质量证明 | 合成负向、篡改、注入、Run/A2A/Hub/Trace 与关系对抗回归 | 没有 Corti 同题对照、真实模型、独立金标准、盲评 reviewer 或医院验收 |

因此，本阶段关闭的是“Evidence Ranker 依赖通用 LLM、无模型不可运行、排序分数不可审计、来源/span 不验证”的开发差距。它没有关闭 Corti 的模型推理、证据抽取、编码系统覆盖、真实临床准确率或生产服务差距；静态 `semantic_live_e2e_verified` 和 `production_ready_verified` 仍为 0/26。

## 安全与外部门禁

- 未读取或使用用户曾暴露的 DeepSeek 密钥；该密钥应继续视为已泄露并在供应商控制台注销。
- 未操作 Corti Console，也未启动 Chromium；本机已有浏览器/测试内存崩溃风险。
- 未执行真实 LLM、真实 Corti 同题、真实医院数据、HIS/EMR、医保结算、Docker、Cloud、PostgreSQL 多副本或生产容量测试。
- 真实证据排序的临床含义必须由合法数据、盲评标注、编码员/临床 reviewer 和医院流程验证，不能由当前规则或单元测试替代。
- 法务、数据授权、等保/个保/数安、渗透测试、医院验收、云基础设施和生产运维仍是外部上线门禁。

## 下一步

继续收敛证据链上游的 `evidence-extractor` 或 `diagnosis-extractor`，优先复用精确 span、否定/不确定状态和本地 ICD-10-CN 导航能力；任何本地抽取基线都必须把词面抽取与医学/编码判断分开。真实模型与 Corti 同题矩阵只在密钥轮换、预算和进程隔离条件满足后执行。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 新建阶段总结，记录保守文档可追溯性排序、v4 合同、验证结果与 Corti 邻近能力差距 | Evidence Ranker 本地能力收敛 |
