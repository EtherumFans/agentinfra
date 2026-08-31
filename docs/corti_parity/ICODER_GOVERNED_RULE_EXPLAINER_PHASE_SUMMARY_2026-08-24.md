# iCoDer Governed Rule Explainer 阶段总结（2026-08-24）

## 阶段结论

`rule-explainer` 已从强制 `deepseek-chat + MCP tools` 的外部模型路径收敛为 `icoder.governed-rule-explainer.v1` 本地确定性 Provider。它现在能在无 LLM、无外网条件下，通过固定大小与 SHA-256 的 `cn.icd10cn.catalog@observed-local-2026-05-19` 解释一个明确 ICD-10-CN 编码的目录存在性、中文名称、章节、类别/前缀、最多十个更具体条目和“是否为目录可分配叶子”。全部输出仍要求人工复核，不能作为临床适用性或结算权威结论。

本阶段没有把旧 `get_guidelines` 内嵌字典包装成权威来源。该字典缺少版本、授权与适用范围治理，且当前本地目录不含 Includes、Excludes1/2、Code First、Use Additional Code、Code Also、组合码或排序规则。新 Provider 因而固定返回 `rule_content_status=UNAVAILABLE_IN_GOVERNED_ASSET`，逐项列出 `unsupported_scope`，从不以 LLM 记忆补写规则。

## 实现与合同

- Pack 升级为 `icoder/rule-explainer@1.2.0`，Provider 改为 `icoder.governed-rule-explainer.v1`，`model=null`、`tools=[]`、`network_required=false`、`llm_required=false`。
- 新增本地 Agent 实现与 Provider，接入 Registry、统一 Run、A2A v0.3、Trace、Hub discovery、项目 Clone 和运行矩阵。
- `icoder/RuleExplanationOutput/v3` 保持冻结；新增 `v4` 追加注册，包含 `catalog_status`、结构化 hierarchy、`catalog_facts`、固定规则资产状态、证据引用、未支持范围、资产版本和强制人工复核。
- 新增四条跨字段失败关闭关系：可分配条目必须是 `ASSIGNABLE`；类别/未知/缺输入/目录不可用必须不可分配；缺失受治理规则内容必须带规则缺口、未支持范围和人工复核；`REQUIRES_REVIEW` 必须人工复核。
- 输入仅接受一个显式编码；无输入为 `INPUT_REQUIRED`，格式异常或未命中不推断有效，目录完整性/使用策略异常为 `CATALOG_UNAVAILABLE` 并抑制确定性事实。
- 提示注入 canary 后缀在解析前被截断；Trace 只记录 Provider、资产治理、事实数量与零模型调用，不记录密钥或临床正文。

## 真实开发环境证据

真实 loopback HTTP 使用新迁移的临时 SQLite、临时租户和随机本地 secret；外部 LLM、网络、原生 MedCodER/FAISS/BGE 和真实密钥全部关闭。证据位于 `reports/agent_hub/local_semantic_e2e_rule_explainer_phase_20260824/`：

- happy：10/10；
- adversarial：10/10；
- pack-owned reference replay：10/10；
- stability：60/60，三轮 happy + adversarial，60 次均为 fresh HTTP、seeded=0；
- 本地语义 bundle：10/10，有效；
- 运行矩阵：10 个本地确定性/受治理基线、16 个外部模型依赖；严格 26-Agent live-provider 验证仍为 0/26；
- Corti 历史 20-Agent 开发映射：中国适配与开发门禁 20/20，临床质量和生产就绪均为 0/20；
- 扩大回归首次运行 725 passed，仅发现字段关系总数测试仍固定为旧 34/60 口径；同步到新增 37 条关系/65 个对抗断言后，最终干净扩大回归 **726/726**；
- 静态部署预检：90/90。

这些测试是 Pack 自有合成样例和开发安全/稳定性证据，不是独立临床金标准、医院验收或生产批准。

## 与 Corti Rule Explainer 的当前差距

Corti 当前公开页面将 Rule Explainer 定义为对已提交的 ICD-10-CM、ICD-10-PCS 和 CPT 编码解释官方描述、assignability、Includes/Excludes、Code First、Use Additional Code、Code Also、章节惯例和层级关系；要求先 Verify、每个编码调用 Guidelines，工具失败时明确报告且不得猜测，并可面向 coder/auditor/clinician 调整表达。来源：[Corti Rule Explainer Agent](https://corti.ai/agents/rule-explainer-agent)。

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| 已提交编码目录存在性、名称、章节、层级、叶子状态 | ICD-10-CN 固定开发目录，本地确定性完成 | 开发切片已完成；目录来源与许可仍待独立核验 |
| 不分配新编码、不建议替代、不判断就诊正确性 | 明确禁止，类别只展示子条目且不选择 | 基本对齐 |
| Includes/Excludes/Code First/Use Additional Code/Code Also | 当前资产没有，固定失败关闭 | 核心未复刻 |
| 章节与通用官方指南 | 不使用无版本治理的 legacy 内嵌字典 | 核心未复刻；需要合法授权、可版本化、可引用的中国规则资产 |
| 编码体系覆盖 | 仅 ICD-10-CN | 缺 Corti 的 ICD-10-CM、ICD-10-PCS、CPT；中国场景还需权威 ICD-9-CM-3、医保、DRG/DIP 和地方规则 |
| 工具实时性与来源引用 | 本地资产版本、治理状态和事实引用可审计 | 缺官方 live rule tool、规则段落级引用和更新 SLA |
| 受众自适应自然语言解释 | 固定中文目录事实说明 | 缺 coder/auditor/clinician 分层表达与经验证的解释质量 |
| 独立质量与生产 | 无独立编码员盲评、医院集成或生产许可 | 外部门禁未通过 |

## 下一阶段建议

开发环境中下一步应优先选择不依赖伪造政策权威、且能在现有安全资产上形成可审计闭环的 Agent。Rule Explainer 的完整能力不能通过继续扩写内嵌规则完成；必须先取得合法授权、版本固定、可引用和可更新的中国 ICD/医保/DRG/DIP 规则资产，再增加逐条 provenance、变更审计、回归集与编码员盲评。对其余 16 个外部模型 Agent，继续按“本地可证明事实 + 明确未支持范围 + 失败关闭”原则逐项收敛，严格 26-Agent 真实 Provider bundle 与独立临床质量矩阵仍为最高开放门禁。
