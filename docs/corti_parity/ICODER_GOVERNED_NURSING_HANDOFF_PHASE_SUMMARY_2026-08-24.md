> 声明：本文件记录开发环境工程证据，不构成护理、临床、法规、医院验收或生产上线批准。
>
> 日期：2026-08-24
>
> 阶段：Agent Hub — Governed Nursing Handoff
>
> 状态：开发环境上线候选切片完成；完整 Corti 能力与外部上线门禁未完成

# iCoDer Governed Nursing Handoff 阶段总结

## 阶段结论

`nursing-handoff` 已从依赖通用 LLM 的模板收敛为 `icoder.governed-nursing-handoff.v1` 本地确定性 Provider。它只整理明确标注的患者、床位、主要问题、当前状态、背景、近期事件、LDA/管路设备、MAR/用药、检验、待办、安全、升级事项和资料缺口；所有临床事实均保留输入中的逐字文本与 `[start,end)` 字符证据。

该能力不会评估患者病情严重程度、护理优先级或工作队列，不会推断医嘱、管路状态、升级条件或缺失结果，也不会替代交接双方床旁核验。只有输入明确写明“待结果、待回报、未出、pending”等状态时，检验项才能进入待办。最多处理 10 名患者，超过上限、无患者标签或缺少可用事实时失败关闭。

## 实现与合同

- Pack 升级为 `icoder/nursing-handoff@1.1.0`，`model=null`、`experts=[]`、`tools=[]`、`network_required=false`、`llm_required=false`，并接入统一 Registry、Run、A2A、Trace、Hub discovery、运行矩阵和项目运行路径。
- 输出采用追加式 `icoder/NursingHandoffOutput/v4`。注册过程中发现统一运行时权威 `trace_refs` 是对象而不是数组，因此不覆盖已经冻结的中间 `v3`，而以 `v4` 修正并追加注册。
- `v4` 声明 19 个必填顶层字段、递归患者/证据结构、5 条跨字段关系和 1 组逐字证据绑定；完成或部分完成的交接必须有证据，患者条目必须可追溯到输入。
- `clinical_priority_assessed=false`、`medical_calculator_used=false`、`production_writeback_blocked=true`、`manual_review_required=true` 是合同常量，结构化投影层也会强制覆盖，防止下游把模型式推断包装成已验证结果。
- Prompt 注入 canary、证据数量、输入长度、患者数量和输出边界均有有界检查；未记录的安全状态、检验结果、升级标准和任务优先级保持为空或明确列入资料缺口。
- 针对现有 PHI 脱敏器会把“管路/安全”误识别为姓名的问题，解析器只兼容脱敏后仍可证明的标签后缀；A2A 测试以路由实际脱敏文本重新核验 span，不绕过隐私处理。

## 真实开发环境证据

真实 loopback HTTP 使用新建、迁移并删除的临时 SQLite、临时租户和随机本地 secret；真实 LLM、外网、原生 MedCodER/FAISS/BGE 均关闭。证据位于 [`local_semantic_e2e_nursing_handoff_phase_20260824`](../../reports/agent_hub/local_semantic_e2e_nursing_handoff_phase_20260824/)：

- happy：12/12；
- adversarial：12/12；
- Pack-owned reference replay：12/12；
- stability：72/72，三轮 happy + adversarial，全部为 fresh HTTP，seeded=0；
- 26-Agent 离线安全 E2E：78/78；12 个本地 Agent 必须成功，14 个外部模型 Agent 必须安全失败且不得泄漏临床合同字段；
- 字段关系对抗回放：95/95；证据绑定对抗回放：34/34；
- Nursing Handoff A2A：2/2；针对性全局合同/矩阵回归：102/102；最终相关宽回归：655/655；
- 输出合同兼容：26 个可见合同、115 个注册版本，0 个新增未登记、漂移、无效或重复引用；
- 静态部署预检：90/90；
- Corti 历史 20-Agent 开发映射：中国适配声明与开发门禁 20/20，独立临床质量和生产就绪仍为 0/20；
- 当前运行矩阵：14 个外部 LLM 必需、1 个可选增强、11 个纯本地、12 个离线本地基线；严格 26-Agent live-provider 验证仍为 0/26，生产就绪验证仍为 0/26。

阶段机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_nursing_handoff_phase_20260824/phase_evidence.json)。受保护数据库 `backend/data/icoder.db` 保持 8,536,064 bytes、SHA-256 `9547e301…bb3e`、修订 `041`；源码迁移头为 `056`。测试结束后无后端进程和 8000 端口监听。三个 `reports/test-temp/nursing-*` 可再生测试目录因本机执行策略拒绝递归删除而保留，未绕过策略强删。

这些结果只证明合成输入下的合同、可追溯性、安全失败和开发稳定性，不证明真实护理交接质量、遗漏率、护士一致性、医院工作流效果或 Corti 产品等价。

## 与 Corti 当前公开能力的差距

Corti 当前公开的 Nursing Shift Handoff Agent 支持每个 assignment 最多 10 名患者，输入包括既往护理记录/交接、任务清单或 flowsheet、MAR、检验和诊断资料；输出为全体患者汇总及逐患者 SBAR 风格内容，覆盖诊断背景、当前状态、近期事件、LDA、MAR、检验、任务、安全和资料缺口，可选 Medical Calculator。公开边界同时说明该 Agent 不评估 acuity/priority，也不替代接班护士核验。[Corti Nursing Shift Handoff Agent](https://www.corti.ai/agents/nursing-shift-handoff-agent)

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| 最多 10 名患者 | 有严格上限，超过即失败关闭 | 合同边界对齐 |
| 患者级输入分段 | 支持显式中英文患者标签和床位 | 开发切片完成；缺真实 assignment、ADT 与患者身份主索引 |
| 诊断背景、当前状态、近期事件 | 逐字整理明确字段并绑定 span | 可审计完成；不做自由文本全病历综合、时间线合并和冲突消解 |
| LDA、MAR、检验、任务、安全、资料缺口 | 明确标签下保守提取，缺失保持缺失 | 开发切片完成；缺 flowsheet、设备、药品与检验系统实时状态 |
| 待回报检验 | 仅明确 pending 词面才能进入待办 | 安全边界明确；缺 LIS 状态、临界值和结果通知闭环 |
| 全 assignment 汇总 | 输出患者计数和逐患者摘要 | 缺 Corti 的自由文本全体摘要质量和护士可用性验证 |
| SBAR | 保留现有结构化 SBAR 字段，同时输出患者级分区 | 结构可表示；缺独立护士对内容选择、冗余和遗漏的评价 |
| Acuity / priority | 固定 `clinical_priority_assessed=false` | 与 Corti 公开“不评估优先级”边界一致 |
| Medical Calculator | 固定未使用 | Corti 可选能力未复刻；缺受治理计算器、适用条件和结果核验 |
| 输出呈现 | A2A `DataPart` 严格 JSON，可由客户端渲染 | 未复刻 Corti 控制台的可读交接版式与交互体验 |
| 接班核验和写回 | 强制人工复核，生产写回阻断 | 安全方向一致；缺护士确认、签名、交班责任转移、回滚和 EMR 写回 |

## 中国场景适配状态

已完成的是中文患者/床位/护理字段、中文 LDA/MAR/检验/待办/安全标签、精确证据 span、CN 区域失败关闭，以及不评估优先级和强制人工复核。仍缺中国医院 HIS/EMR、护理文书、电子体温单、医嘱、MAR、LIS/PACS、护理任务单和设备告警接口；也缺科室自定义交接模板、护理等级/压疮/跌倒/VTE 等经医院批准的规则、中文缩写词典、方言或语音交接、护士身份与电子签名。

这些本地词法能力不能自行升级为护理风险判断。国家标准、医院制度、科室规则和责任边界必须由医院护理部、信息科、法务与独立临床 reviewer 提供和批准。

## 外部上线门禁

- 真实医院、经授权且去标识化的交接金标准，以及护士级遗漏率、正确率、严重差错率、冗余率和一致性门槛；
- HIS/EMR、ADT、护理文书、flowsheet、MAR、LIS/PACS、任务和设备系统的身份匹配、实时性、断线、冲突、审批、写回与回滚验证；
- 经医院批准的护理风险/升级规则、Medical Calculator、版本治理、适用条件、引用和独立验证；
- 护理部、医务、法务、隐私、网络安全、医疗软件监管和伦理审查，以及护士工作流、可用性和责任归属验收；
- 生产多租户容量、延迟、可用性、灾备、监控、事故响应、数据留存与区域基础设施审核。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Nursing Handoff、v4 追加合同、12-Agent HTTP 门禁和 Corti 逐项差距 | 将该 Hub Agent 从 LLM 模板收敛为可运行、可审计、可测试的开发上线候选切片 |
