> 声明：本文件记录开发环境工程证据，不构成临床、药学、法规、医院验收或生产上线批准。
>
> 日期：2026-08-24
>
> 阶段：Agent Hub — Governed Medication Reconciliation
>
> 状态：开发环境上线候选切片完成；完整 Corti 能力与外部上线门禁未完成

# iCoDer Governed Medication Reconciliation 阶段总结

## 阶段结论

`med-reconciliation` 已从依赖通用 LLM 的模板收敛为 `icoder.governed-medication-reconciliation.v1` 本地确定性 Provider。它只处理明确标注的入院前/家庭用药、住院 MAR/用药和拟出院/出院用药来源；逐字提取药名、已记录剂量、途径、频次、状态和原因，并保存 `[start,end)` 字符证据。来源间只按药名字面值和双方均明确记录的字段比较，输出 `CONTINUE / START / STOP / CHANGE / NEEDS_CLARIFICATION`。这些分类是清单差异，不是处方或停药建议。

旧 Pack 示例曾在输入没有肾功能结果、禁忌判断或恢复条件时生成“恢复二甲双胍前确认肾功能/无禁忌”类内容。本阶段删除了该无证据推断：缺失字段保持空值，暂停后重新列出只报告依据缺失，绝不自行补写恢复条件、适应证、途径或治疗计划。

## 实现与合同

- Pack 升级为 `icoder/med-reconciliation@1.1.0`，`model=null`、`experts=[]`、`tools=[]`、`network_required=false`、`llm_required=false`，并接入统一 Registry、Run、A2A v0.3、Trace、Hub discovery、运行矩阵和项目运行路径。
- 输出采用 `icoder/MedicationReconciliationOutput/v4`。旧 `v2` 及注册过程中已冻结的中间 `v3` 均未覆盖；字段关系与证据绑定纠正后以 `v4` 追加注册。
- `v4` 声明 17 个必填顶层字段、递归对象/数组约束、7 条跨字段关系和 4 条逐字证据绑定；药物条目必须具有来源、身份依据、证据文本和精确 span。
- `interaction_screening_status` 固定为 `NOT_ASSESSED_LICENSED_SOURCE_REQUIRED`，`interaction_risks` 固定为空，`manual_review_required` 固定为 `true`。结构化投影层也会覆盖模型式相互作用声明，防止未授权知识被包装成已评估结果。
- 只允许一个受限相邻指代：当入院前来源恰好只有一个明确药名、紧邻住院来源只有“暂停/停用/恢复”等无药名状态句时，可继承该唯一药名，并标记 `identity_basis=adjacent_single_medication_reference`；其他无药名内容进入 `unresolved_mentions`。
- 过敏检查只做活动/出院药物与过敏原的完全相同字面匹配；不做盐型、品牌/通用名、同类或交叉过敏推断。
- 修正 Pack Loader 对“无 experts/tools 但有专用非提示词后端”的误分类，不再把受治理本地 Provider 标记为 pure-prompt。

## 真实开发环境证据

真实 loopback HTTP 使用新建、迁移并删除的临时 SQLite、临时租户和随机本地 secret；真实 LLM、外网、原生 MedCodER/FAISS/BGE 均关闭。证据位于 `reports/agent_hub/local_semantic_e2e_med_reconciliation_phase_20260824/`：

- happy：11/11；
- adversarial：11/11；
- Pack-owned reference replay：11/11；
- stability：66/66，三轮 happy + adversarial，全部为 fresh HTTP，seeded=0；
- 26-Agent 离线安全 E2E：78/78；11 个本地 Agent 必须成功，15 个外部模型 Agent 必须安全失败且不得泄漏临床合同字段；
- 字段关系对抗回放：81/81；证据绑定对抗回放：32/32；
- 最终宽回归：745/745；静态部署预检：90/90；
- Corti 历史 20-Agent 开发映射：中国适配与开发门禁 20/20，独立临床质量和生产就绪仍为 0/20；
- 当前运行矩阵：15 个外部 LLM 必需、1 个可选增强、10 个纯本地、11 个离线本地基线；严格 26-Agent live-provider 验证仍为 0/26，生产就绪验证仍为 0/26。

这些结果只证明合成输入下的合同、可追溯性、安全失败和开发稳定性，不证明真实药物识别召回率、相互作用准确率、药师一致性、医院工作流效果或 Corti 产品等价。

## 与 Corti 当前公开能力的差距

Corti 当前公开的 Medication Reconciliation Agent 会比较 Home、Inpatient MAR 与 Discharge 来源，提取已记录药名、剂量/强度、途径、频次、状态和时间信息，执行品牌/通用名归一化，识别遗漏、新增、重复及字段冲突，分类 Continue/Start/Stop/Change/Needs Clarification，并通过 DrugBank、Medical Calculator 和 Web Search 支持同类重复、制剂、单位与过敏/禁忌检查；其公开提示同时禁止开新药、建议调量、猜测适应证或以最佳猜测解决冲突。[Corti Medication Reconciliation Agent](https://www.corti.ai/agents/medication-reconciliation-agent)

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| Home / MAR / Discharge 分源抽取 | 明确中文标签、逐字字段和精确 span，本地完成 | 开发切片完成；缺表格、FHIR/EMR、药房历史、OCR 与复杂文档解析 |
| Continue / Start / Stop / Change / Needs Clarification | 按精确药名和已记录字段保守比较 | 基本对齐清单逻辑；不代表治疗意图或临床正确性 |
| 缺字段、遗漏、新增、明确剂量/途径/频次变化 | 可审计完成，并保留缺失原因与中性确认项 | 开发切片完成；尚无独立药师质量基准 |
| 同名重复 | 只识别同一来源内完全相同药名字面重复 | 缺同类重复、成分/复方/盐型/剂型归一化 |
| 品牌—通用名与制剂对齐 | 不执行 | Corti 核心公开能力未复刻；需合法授权、版本化药品知识库 |
| 相互作用、禁忌、过敏 | 相互作用固定未评估；过敏仅完全相同字面匹配 | 核心未复刻；缺 DrugBank/医院药品库、反应严重度、交叉过敏和证据引用 |
| 高风险药物类别 | 不从药名推断抗凝药、胰岛素、阿片、β 阻滞剂等类别 | Corti 核心公开能力未复刻 |
| 剂量/单位与临床适宜性 | 只保留明确字符串并比较；不做单位换算、肾/肝功能或剂量适宜性判断 | 缺 Medical Calculator/药学规则和经验证计算 |
| 时间信息 | 可保留状态原因，但未结构化 start/last-dose/stop date | 未对齐 |
| 输出呈现 | A2A `DataPart` 的严格 JSON 合同，可由客户端渲染 | 未复刻 Corti 的强制 Markdown 表格/警示布局与受众体验 |
| 医师/药师复核与写回 | 强制人工复核，生产写回阻断 | 安全边界对齐；缺受控处方/HIS/EMR 工作流、审批、回滚与医院验收 |

## 中国场景适配状态

已完成的是中文来源标签、中文药名/剂量/途径/频次、住院暂停与出院重列、精确证据 span、CN 区域失败关闭及医师/药师复核。仍缺国家药监局/医院药品目录合法来源、批准文号与本位码映射、国产商品名/通用名/复方/中成药/中药饮片、医院医嘱缩写、处方前置审核规则、区域医保与真实 HIS/EMR/FHIR 接口。上述数据、许可、临床规则和医院工作流不能在开发代码中伪造。

## 外部上线门禁

- 合法授权、版本固定、可更新并可引用的 DrugBank 或中国医院药品知识库；
- 独立药师/临床 reviewer 的盲评集与药物级 precision、recall、F1、严重差错率及一致性门槛；
- 真实医院 Home/MAR/Discharge、过敏、实验室和处方系统的互操作、身份匹配、审批、写回与回滚验证；
- 法务、隐私、网络安全、药事管理、医疗器械/软件监管判断及生产云基础设施审核；
- 真实多租户容量、延迟、可用性、灾备、监控、事故响应与持续药品知识更新 SLA。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Medication Reconciliation、v4 追加合同、11-Agent HTTP 门禁和 Corti 逐项差距 | 将该 Hub Agent 从 LLM 模板收敛为可运行、可审计、可测试的开发上线候选切片 |
