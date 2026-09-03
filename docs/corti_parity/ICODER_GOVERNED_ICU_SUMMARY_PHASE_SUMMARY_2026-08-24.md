> 声明：本文件记录开发环境工程证据，不构成 ICU 临床、法规、医院验收或生产上线批准。
>
> 日期：2026-08-24
>
> 阶段：Agent Hub — Governed ICU Admission Summary
>
> 状态：开发环境上线候选切片完成；完整 Corti 能力与外部上线门禁未完成

# iCoDer Governed ICU Admission Summary 阶段总结

## 阶段结论

`icu-summary` 已从外部 LLM 模板收敛为 `icoder.governed-icu-summary.v1` 本地确定性 Provider。它只重排明确标注的 ICU 入院原因、诊断、病史、过敏、活动问题、药物、生命体征、检验、操作、器官支持、时间线、趋势、待办、风险和冲突/缺口，并为每项事实保存脱敏输入中的逐字文本与 `[start,end)` 字符证据。

该能力不解释生命体征或检验是否异常，不推断病情变化、风险或诊断，不计算 APACHE II、SOFA、GCS、死亡风险，不执行药物相互作用、剂量或肝肾功能筛查，也不生成治疗建议。缺少受支持标签时返回 `INPUT_REQUIRED`，所有输出均为须 ICU 医师复核的草稿，生产写回固定阻断。

## 实现与合同

- Pack 升级为 `icoder/icu-summary@1.1.0`，`model=null`、`experts=[]`、`tools=[]`、`network_required=false`、`llm_required=false`，并接入统一 Registry、Run、A2A、Trace、Hub discovery、项目副本和运行矩阵。
- 追加式输出合同为 `icoder/IcuSummaryOutput/v3`，声明 24 个必填顶层字段、递归患者/临床事实/证据结构、6 条跨字段关系和 1 组逐字证据绑定。
- `clinical_scores_status=NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED`、`medication_screening_status=NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED`、`clinical_recommendations_generated=false`、`production_writeback_blocked=true`、`manual_review_required=true` 均为合同常量，结构化投影层再次强制覆盖。
- 输入最多 40,000 字符、证据最多 200 条；Prompt 注入 canary、未标注自由文本、空输入和超限路径均有失败关闭测试。
- A2A 和 HTTP 路径均按实际 PHI 脱敏后的文本验证证据坐标，没有通过跳过脱敏来获得“正确 span”。
- 本阶段还修复了 schema 生成器的顺序依赖：`trace_refs` 曾直接引用共享 primitive 模板，前序 Agent 的递归约束会污染后续 Pack；现改为深拷贝，26 个可见 Pack dry-run 为零漂移。

## 真实开发环境证据

真实 loopback HTTP 使用新建、迁移并删除的临时 SQLite、临时租户和随机本地 secret；真实 LLM、外网、原生 MedCodER/FAISS/BGE 均关闭。证据位于 [`local_semantic_e2e_icu_summary_phase_20260824`](../../reports/agent_hub/local_semantic_e2e_icu_summary_phase_20260824/)：

- happy：13/13；
- adversarial：13/13；
- Pack-owned reference replay：13/13；
- stability：78/78，三轮 happy + adversarial，全部为 fresh HTTP，seeded=0；
- 26-Agent 离线安全 E2E：78/78；13 个本地基线 Agent 必须成功，13 个外部模型 Agent 必须安全失败且不得泄漏临床合同字段；
- 字段关系对抗回放：112/112；证据绑定对抗回放：36/36；
- ICU Summary A2A：2/2；针对性合同/矩阵/重放：75/75；内容安全与对抗合同：26/26；
- 最终相关宽回归：719/719；schema 生成器专项：6/6；
- 输出合同兼容：26 个可见合同、116 个注册版本，0 个新增未登记、漂移、无效或重复引用；
- 静态部署预检：90/90；
- Corti 历史 20-Agent 开发映射：中国适配声明与开发门禁 20/20，独立临床质量和生产就绪仍为 0/20；
- 当前运行矩阵：13 个外部 LLM 必需、1 个可选增强、12 个纯本地、13 个离线本地基线；严格 26-Agent live-provider 验证仍为 0/26，生产就绪验证仍为 0/26。

阶段机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_icu_summary_phase_20260824/phase_evidence.json)。受保护数据库 `backend/data/icoder.db` 保持 8,536,064 bytes、SHA-256 `9547e301…bb3e`、修订 `041`；源码迁移头为 `056`。测试结束后无 Uvicorn 进程和 8000 端口监听。可再生 `reports/test-temp/icu-*` 测试目录保留，未绕过本机执行策略强删。

这些结果只证明合成输入下的合同、可追溯性、安全失败和开发稳定性，不证明 ICU 摘要临床质量、遗漏率、严重错误率、医师可用性或 Corti 产品等价。

## 与 Corti 当前公开能力的差距

Corti 当前公开的 ICU Admission Summary Agent 会把 EHR 中的人口学信息、入院诊断和原因、内外科/社会史、过敏、活动问题、药物、生命体征、检验、操作和待办综合进机构模板；公开页面还列出 PubMed、Medical Calculator（含 APACHE II、SOFA、GCS/死亡风险）和 DrugBank（剂量、相互作用、肝肾功能）专家，以及 EHR 连接、机构阈值与审批工作流。其输出仍是临床草稿，不替代专业判断，也不应在未经复核批准时修改记录。[Corti ICU Admission Summary Agent](https://www.corti.ai/agents/icu-admission-summary-agent)

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| ICU 入院事实覆盖 | 支持 18 类明确中英文标签，逐字整理并绑定 span | 开发切片完成；不做自由文本、多文档或纵向病历综合 |
| 患者背景、入院原因和诊断 | 仅保留明确记录，不补写 | 可审计完成；缺患者主索引、ADT 和 EHR 结构化字段映射 |
| 药物、生命体征、检验、操作、器官支持 | 明确标签下保守提取 | 缺 MAR、LIS、监护设备、呼吸机和操作系统实时接入 |
| 时间线、趋势、待办、风险和冲突 | 仅记录原文明确表达 | 不推断趋势、异常、优先级或风险；缺跨文档冲突消解 |
| 机构模板 | 固定 JSON 合同，可由客户端渲染 | 缺医院可配置模板、科室字段映射、版本审批和 Corti 控制台交互 |
| 机构阈值 | 不应用任何参考范围或阈值 | Corti 公开能力未复刻；需医院批准的范围、版本和适用条件 |
| APACHE II / SOFA / GCS / 死亡风险 | 固定未计算 | 缺受治理计算器、输入完整性、时间窗、单位、引用和独立验证 |
| PubMed | 未连接 | 缺检索、证据版本、适用性评价和医院知识治理 |
| DrugBank 药物能力 | 固定未筛查 | 缺授权数据、品牌/通用名、剂量、相互作用、禁忌和肝肾调整验证 |
| 审批与写回 | 强制人工复核，生产写回阻断 | 安全方向一致；缺 ICU 医师签名、审批、EHR 写回、回滚和责任审计 |

## 中国场景适配状态

已完成中文 ICU/AICU 标签、中文病史/过敏/药物/生命体征/检验/器官支持/待办字段、精确证据 span、CN 区域失败关闭和强制 ICU 医师复核。仍缺中国医院 HIS/EMR、ADT、医嘱、MAR、LIS/PACS、重症监护、呼吸机和床旁设备接口；缺 GB/T、WS/T、医院重症模板和数据元映射；缺中文缩写、单位归一、参考范围、评分时窗及医院批准的知识资产。

本地词法整理不能自行升级为 ICU 临床判断。评分、异常阈值、药物知识、风险提示和治疗路径必须由医院重症医学科、药学部、信息科、医务、法务与独立临床 reviewer 提供和批准。

## 外部上线门禁

- 真实医院、经授权且去标识化的 ICU 入院摘要金标准，以及字段遗漏率、事实错误率、证据一致率、严重危害错误率和医师一致性门槛；
- HIS/EMR、ADT、MAR、LIS/PACS、监护设备、呼吸机和操作系统的身份匹配、单位、时间窗、实时性、断线、冲突与回滚验证；
- APACHE II、SOFA、GCS、死亡风险、参考阈值和 DrugBank/医院药品库的授权、版本、适用条件、引用和独立临床验证；
- 重症医学科、药学部、医务、法务、隐私、网络安全、医疗软件监管和伦理审查，以及医师工作流和责任归属验收；
- 生产多租户容量、延迟、可用性、灾备、监控、事故响应、数据留存与区域基础设施审核。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 ICU Admission Summary、v3 追加合同、13-Agent HTTP 门禁、schema 顺序依赖修复和 Corti 逐项差距 | 将该 Hub Agent 从外部模型模板收敛为可运行、可审计、可测试的开发上线候选切片 |
