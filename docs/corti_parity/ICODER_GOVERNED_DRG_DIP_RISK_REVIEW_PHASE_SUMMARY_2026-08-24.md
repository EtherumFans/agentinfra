# iCoDer DRG/DIP 受治理本地风险复核阶段总结（2026-08-24）

> **声明：** 本文记录开发环境证据，不是医疗、医保、编码、支付或生产上线批准。
> **日期：** 2026-08-24
> **阶段：** Agent Hub 本地语义能力 23/26
> **状态：** DRG/DIP 开发候选切片已验证；总体 Corti 复刻与生产门禁仍开放

## 阶段结论

`drg-analyzer` 已从需要外部 LLM 的泛化模板收敛为可运行、可审计、可测试的本地确定性开发候选切片：

- Agent：`icoder/drg-analyzer@1.1.3`
- Provider：`icoder.governed-drg-dip-risk-review.v1`
- 输出合同：`icoder/DRGDIPRiskReview/v8`，旧版本保留且不可变
- 运行模式：`governed_local_explicit_coded_case_risk_review`
- 规则资产：`cn.drg_dip.risk_heuristics@1.0.0-development`
- 权威状态：`experimental_unverified` / `external_review_required`
- 执行：无 LLM、无网络、无工具调用，确定性、成本为 0

它只处理编码员明确提供的 ICD-10-CN / ICD-9-CM-3 编码、版本和逐字证据，输出开发期风险提示及非官方候选分组。它不从自由文本提取或分配编码，不验证编码正确性，不进行临床推断，不运行官方 DRG 分组或 DIP 计分，不输出权重、CMI、支付或结算金额，并固定阻断提交和写回。

机器证据见 [phase_evidence.json](../../reports/agent_hub/drg_dip_risk_review_phase_20260824_v1/phase_evidence.json)，23-Agent 签名 HTTP 证据见 [local_semantic_e2e_drg_dip_phase_20260824_v1](../../reports/agent_hub/local_semantic_e2e_drg_dip_phase_20260824_v1/)，部署预检见 [drg_dip_risk_review_phase_20260824_v1](../../reports/deployment/drg_dip_risk_review_phase_20260824_v1/)。

## 本轮实现

### 输入、证据和失败关闭

Provider 仅接受明确标签字段：审核目的、诊断/手术编码标准及版本、患者性别/年龄、主诊断、次诊断和手术操作。每个编码项使用 `code|display|source_document|evidence_text`，并绑定脱敏输入中的精确字符 span。

缺失编码标准、版本、主诊断或逐字证据时返回 `INPUT_REQUIRED`；冲突或可疑输入进入人工复核。提示注入、超长输入、非法编码格式、重复证据及缺失来源均按合同失败关闭，不会回退到模型猜测。

### 中国场景适配

- 支持 ICD-10-CN 与 ICD-9-CM-3 的明确版本声明；
- 支持中文病案首页和手术记录来源标签；
- 输出 DRG/DIP 开发期风险提示，同时明确地区与规则版本边界；
- 对中国医院提交、医保结算、HIS/EMR 写回默认阻断；
- 可与经过签名证明的 Medical Coding 上游结果执行主诊断、次诊断和手术编码集合一致性检查。

当前并未接入 CHS-DRG、CN-DRG、国家/省市 DIP、医院或商保的授权分组器、目录、权重和结算政策，因此“中国适配”只表示输入语义、治理边界和失败关闭适配，不表示官方分组能力。

### Runtime、合同和审计闭环

- Provider 已进入统一 Registry、Agent Run、A2A、项目副本路由、结构化投影和 RunTrace；
- v8 合同包含 27 个必需字段、递归类型约束、DRG 专属字段关系、证据绑定和 3 条 Medical Coding 跨 Agent 关系；
- 合同注册表当前含 135 个追加版本，26/26 可见合同无漂移、无重复或无效引用；
- schema dry-run 为 `changed_agents=[]`；
- 全 Hub 累计 106 条字段关系、29 条证据绑定和 10 条跨 Agent 关系全部通过定义与对抗回放；
- 本轮 API 关系测试改为调用真实本地 DRG Provider，删除了会产生证据坐标漂移的静态假输出。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| DRG Provider / A2A 聚焦测试 | 7/7 |
| 本轮受影响回归 | 59/59 |
| 26-Agent 离线安全 E2E | 78/78 |
| 语义 E2E / 合同专项 | 95/95 |
| 本地真实 HTTP happy / adversarial / reference | 23/23 / 23/23 / 23/23 |
| 三轮稳定性 | 138/138；p50 0.212s，p95 0.328s |
| 字段关系对抗回放 | 323/323（106 条关系） |
| 证据绑定对抗回放 | 58/58（29 条绑定） |
| 跨 Agent 关系对抗回放 | 20/20（10 条关系） |
| 合同兼容 | 26 个可见合同、135 个注册版本、0 漂移 |
| 静态部署预检 | 90/90 |

一次更宽的串行回归得到 2562 passed、5 skipped、6 deselected、10 failed，耗时 976.34 秒且未发生进程崩溃。10 个失败中，本轮引入或暴露的 8 个 DRG/计数/离线覆盖问题均已通过后续 59/59、78/78 和 95/95 定向回归关闭。仍有 2 个独立 Note Completeness 旧预期失败：完整 EMR 与外科手术记录用例期望 `PASS`，当前规则返回 `WARNING`。因此本阶段不声称“整个后端全绿”。

当前运行矩阵为：26 个用户可见 Agent 均具备开发候选结构；23 个已通过本地签名语义 HTTP 门禁；仅 CDI、Medical Coding、Triage 仍待真实外部模型语义验证；production-ready 仍为 0/26。

## 与 Corti 当前公开能力的差距

Corti 当前公开 Agent Library 未见独立同名 DRG/DIP Agent，因此本阶段采用最接近的 [Medical Coding Agent](https://corti.ai/agents/medical-coding-icd-10-cpt-agent)、[Medical Coding API](https://corti.ai/medical-coding) 和 [Agentic Framework](https://docs.corti.ai/agentic/overview) 作为邻近对照。公开资料显示 Corti Medical Coding 能从完整临床记录提取诊断与操作、分配和验证 ICD-10-CM/CPT/HCPCS 编码、给出逐码证据、排序替代项和规则理由，并通过 Agent/Connector/Context/Trace 体系组合运行。

| 能力 | iCoDer 本阶段 | 对 Corti 的结论 |
|---|---|---|
| 明确编码病例风险复核 | 固定规则、可重复、精确证据 | 中国场景开发差异化能力；非 Corti 同名复刻 |
| 自由病历理解 | 只接受明确标签和编码员提供的编码 | 未覆盖 Corti 邻近的全病历理解 |
| 编码提取与分配 | 明确禁止 | 未覆盖 |
| 编码验证、顺序和修饰符 | 仅检查已签名上下游集合一致性 | 未覆盖 Corti 的正式编码知识与规则验证 |
| 证据和审计 | 精确字符 span、合同、签名、RunTrace | 开发证据闭环已覆盖；尚无独立临床审计 |
| 候选与理由 | 只输出开发期非官方候选和风险动作 | 不等价于 Corti 排序编码候选与规则理由 |
| DRG/DIP 官方能力 | 明确不执行 | 无授权 grouper、地区版本、权重、CMI、DIP 分值和结算 |
| 多 Agent/Context | 支持签名上游关系及统一 Runtime | 仍缺真实外部 Provider、医院数据与长期场景验证 |
| 真实质量 | 合成 Pack 样例与对抗样例 | 无编码员盲评、分组准确率、严重错误率或同例 Corti 对照 |

因此，当前可以声称“DRG/DIP 明确编码输入的受治理本地风险复核已成为开发候选基线”，不能声称“已复刻 Corti Medical Coding”、 “具备官方 DRG/DIP 分组能力”或“可用于医保支付结算”。

## 下一阶段与不可突破门禁

开发环境下一优先级是关闭剩余 3 个外部模型 Agent 的真实 Provider 证据，并处理 2 个 Note Completeness 回归预期。DRG/DIP 的进一步提升应先获得合法、固定版本、可审计的官方或医院授权规则资产，再建设地区 profile、版本迁移、金标准病例、编码员双盲评审和严重错误门禁；不能用更多未授权关键词规则代替官方分组器。

以下门禁只能由外部证据关闭：医院 EHR/HIS/病案首页接口、授权 DRG/DIP 分组器及政策资产、真实病例和独立编码员/临床 reviewer、地区医保或 payer 联调、生产云/PostgreSQL/容量/灾备/SLA、安全与隐私评估、法务许可、医疗器械或相关认证、医院工作流验收。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理 DRG/DIP 本地 Provider、v8 合同、跨 Agent 一致性、23-Agent 签名 HTTP E2E、串行回归和 Corti 邻近能力差距 | Agent Hub 本地语义能力扩展至 23/26，外部模型强依赖降至 3 |
