> 声明：本文件记录开发环境工程证据，不构成出院小结临床质量、法规、医院验收或生产上线批准。
>
> 日期：2026-08-24
>
> 阶段：Agent Hub — Governed Discharge Summary Structuring
>
> 状态：开发环境上线候选切片完成；完整 Corti 能力与外部上线门禁未完成

# iCoDer Governed Discharge Summary Structuring 阶段总结

## 阶段结论

`discharge-summary-structuring` 已从外部 pure-LLM 模板收敛为 `icoder.governed-discharge-summary.v1` 本地确定性 Provider。它只结构化带明确中英文章节标题的出院小结，覆盖住院/出院日期、科室、去向、入院原因、诊断、操作、诊疗经过、检验/影像、医嘱、随访、转归、过敏、待回结果、并发症和冲突；每个发布事实都绑定脱敏输入中的精确 `[start,end)` 证据。

该能力不总结未标注自由叙事，不推断诊断、因果、严重程度、预后或治疗意图，不分配 ICD 编码，不执行药物重整或药品知识筛查，也不新增医嘱、随访、返院条件或医疗建议。无受支持标题时返回 `INPUT_REQUIRED`；核心章节不全时返回 `PARTIAL`。所有结果强制人工复核，生产写回固定阻断。

## 实现与合同

- Pack 升级为 `icoder/discharge-summary-structuring@1.1.0`，`model=null`、`experts=[]`、`tools=[]`、`network_required=false`、`llm_required=false`，并接入统一 Registry、Run、A2A、Trace、Hub discovery、项目副本和运行矩阵。
- 当前追加式合同为 `icoder/DischargeSummaryStructured/v5`，声明 25 个必填顶层字段、6 条跨字段关系和 1 组逐条证据绑定。`COMPLETED` 必须包含诊断、诊疗经过、医嘱、随访和出院状态；`INPUT_REQUIRED` 不得发布临床事实。
- `summary_generation_status=VERBATIM_SECTION_REORGANIZATION_ONLY`、`icd_codes_assigned=false`、`medication_reconciliation_performed=false`、`clinical_inference_performed=false`、`production_writeback_blocked=true`、`manual_review_required=true` 均为合同常量，结构化投影层再次强制覆盖。
- 输入最多 40,000 字符、证据最多 200 条、每节最多 100 项；空输入、单段未标注叙事、Prompt 注入 canary、稀疏章节、冲突和超限路径均有失败关闭测试。
- `v4` 曾以默认 `evidence_items.maxItems=100` 进入追加式注册表；运行时上限确认是 200 后没有覆写历史版本，而是保留 `v4` 并追加 `v5`。当前 Pack、Provider 和测试只使用 `v5`。
- Pack 示例输入与实际运行输出逐字段相等；A2A 和 HTTP 路径均验证脱敏后字符坐标与原文逐字一致。

## 真实开发环境证据

最终受控 loopback HTTP 使用临时 SQLite、临时租户和随机进程内 attestation key；真实 LLM、外网、原生 MedCodER/FAISS/BGE 均关闭。完整证据位于 [`local_semantic_e2e_discharge_summary_phase_20260824`](../../reports/agent_hub/local_semantic_e2e_discharge_summary_phase_20260824/)：

- happy：15/15；
- adversarial：15/15；
- Pack-owned reference replay：15/15；
- stability：90/90，三轮 happy + adversarial，全部 fresh HTTP，seeded=0；
- 26-Agent 离线安全 E2E：78/78；15 个本地基线 Agent 必须成功，11 个外部模型 Agent 必须安全失败且不得泄漏临床合同字段；
- 字段关系对抗回放：161/161（17 个 Agent、67 条关系）；证据绑定对抗回放：40/40（11 个 Agent、20 条绑定）；
- Discharge Summary A2A：2/2；聚焦 Provider/投影/合同套件：78/78；
- 最终相关宽回归：822/822；此前 812/822 的 10 项失败均为历史测试仍假设新本地 Agent 走 Mock LLM，更新为更强的本地安全断言后全绿；
- schema 生成器 dry-run：26 个可见 Agent、`changed_agents=[]`；
- 输出合同兼容：26 个可见合同、119 个注册版本，0 个未登记、漂移、无效或重复引用；
- 静态部署预检：90/90；
- 当前运行矩阵：11 个外部 LLM 必需、1 个可选增强、14 个纯本地、15 个离线本地基线；严格 26-Agent live-provider 验证和生产就绪验证仍为 0/26。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_discharge_summary_phase_20260824/phase_evidence.json)，部署预检见 [`development_preflight_discharge_summary_phase_20260824`](../../reports/deployment/development_preflight_discharge_summary_phase_20260824/)。受保护数据库 `backend/data/icoder.db` 保持 8,536,064 bytes、SHA-256 `9547e301…bb3e`、修订 `041`；源码迁移头为 `056`。

测试期间发现 E 盘可用空间为 0，新的隔离 SQLite 因 `database or disk is full` 无法建表。6 个本阶段可再生测试库被精确校验后移动到 C 盘专用临时目录，释放约 9.25 MB，未删除代码、报告、受保护数据库或备份；随后 C 盘隔离库的 822 项回归与 loopback E2E 均通过。此前可见 Uvicorn 的 `exit -1` 没有 Python traceback 或 Windows `0xC0000005` 事件，SQL `SELECT → ROLLBACK → 200` 正常；磁盘写满是重要环境风险，但现有证据不足以断言它就是该次 `-1` 的唯一根因。

这些结果只证明合成、明确标题输入下的结构合同、可追溯性、安全失败和开发稳定性，不证明自由叙事总结质量、真实病历遗漏率、严重错误率、医院模板符合性或 Corti 产品等价。

## 与 Corti 当前公开能力的差距

截至本阶段核对时，Corti 公开 Agent Library 没有名为“Discharge Summary Structuring”的独立预置 Agent；因此不存在可诚实声称的一对一 Agent 复刻。最近邻对照是 Textgen 标准 section `corti-discharge-summary`，其公开描述是把全部材料总结为出院记录格式；标准文档生成还可接受 facts、transcript 或医疗文档，并要求人工监督。[Corti Agent Library](https://corti.ai/agents) [Corti Standard Templates & Sections](https://docs.corti.ai/textgen/templates-standard) [Corti Standard Document Generation](https://docs.corti.ai/textgen/documents-standard)

Corti Patient Discharge Education Agent 是另一条相邻但不同的能力：它公开描述了多文档分类、诊断/结果/治疗/药物变化/随访事实抽取、患者友好解释和缺失/冲突提示。iCoDer 的本阶段 Agent只做临床出院小结结构化，不提供患者教育。[Corti Patient Discharge Education Agent](https://www.corti.ai/agents/patient-discharge-education-agent)

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| 产品定位 | 中国场景额外 Agent，专注明确章节结构化 | Corti 公开目录无同名独立 Agent；只能与 Textgen section 和 Discharge Education 邻近比较 |
| 输入覆盖 | 单份、明确中英文章节标题文本 | 缺 facts/transcript/多文档输入、文档身份、时间、版本、患者/就诊归并和冲突排序 |
| 生成能力 | 逐字章节重组，不生成新摘要 | 未复刻 Corti `corti-discharge-summary` 对全部材料的生成式出院记录总结 |
| 事实约束 | 精确 span、无推断、缺项显式返回 | 安全方向一致；缺跨文档 grounding、重复消解、事实优先级和生成 guardrail 实测 |
| 诊断与编码 | 只保留已写诊断，不分配编码 | 不含 Diagnostic/Medical Coding Agent 的编码、组合、排序和权威规则能力 |
| 用药 | 只保留已写出院用药/医嘱文本 | 缺入院前/MAR/出院变化、剂量归一、冲突、相互作用和药师工作流 |
| 模板输出 | 25 字段 JSON，可由客户端渲染 | 缺医院批准的出院小结模板、富文本/PDF、签名、版本、更正和写回 |
| Patient Discharge Education | 不做医学释义或患者友好转换 | 未替代 Corti 的多源患者教育、阅读等级、语言、照护者和结果解释能力 |
| 审批与写回 | 强制人工复核，生产写回阻断 | 缺医师审批签名、HIS/EMR 写入、撤回、更正、回滚和责任审计实联调 |

## 中国场景适配状态

已支持常见中文出院小结标题、住院/出院日期、科室、出院去向、主/次诊断、手术操作、诊疗经过、检验/影像、一般/用药/活动/饮食/伤口医嘱、随访、转归、过敏、待回结果、并发症和冲突；所有字段保留中文原文和精确 span，并在 CN 区域默认失败关闭。

仍缺中国医院真实 HIS/EMR、电子病历、医嘱、MAR/药房、LIS/PACS、病案首页、转诊/随访接口；缺医院/专科模板、电子签名、病历质控、归档、更正与版本控制；缺法定/行业数据集、真实医院缩写/错别字/OCR/粘贴表格/多文档时间线，以及临床科室、病案室、医务、信息、药学和护理共同批准的语义规则。

## 外部上线门禁

- 真实医院授权且去标识化的出院小结、多文档和医院模板金标准，以及章节准确率、事实遗漏率、错误添加率、证据一致率和严重危害错误率门槛；
- 医师、病案编码员、护士、药师和独立 reviewer 的双盲复核、一致性与失败升级流程；
- HIS/EMR、ADT、医嘱、MAR/药房、LIS/PACS、病案首页、转诊/随访的身份、时间、版本、冲突、签名、写回、更正和回滚验证；
- 中国 ICD/病案/医保规则与医院模板的合法来源、许可、生效版本、地区适用条件和回放；
- 法务、隐私、网络安全、伦理、等保及医疗软件监管审批；
- 生产多租户容量、延迟、可用性、灾备、监控、事故响应、数据留存、KMS/Secret Manager、镜像/SBOM 和区域基础设施审核。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Discharge Summary Structuring、v5 追加合同、15-Agent HTTP 门禁、822 项宽回归和 Corti 邻近能力差距 | 将该中国额外 Agent 从外部模型模板收敛为可运行、可审计、可测试的开发上线候选切片 |
