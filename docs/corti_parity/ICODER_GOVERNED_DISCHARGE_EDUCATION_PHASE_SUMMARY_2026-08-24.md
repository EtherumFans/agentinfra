> 声明：本文件记录开发环境工程证据，不构成出院宣教临床、法规、医院验收或生产上线批准。
>
> 日期：2026-08-24
>
> 阶段：Agent Hub — Governed Patient Discharge Education
>
> 状态：开发环境上线候选切片完成；完整 Corti 能力与外部上线门禁未完成

# iCoDer Governed Patient Discharge Education 阶段总结

## 阶段结论

`discharge-edu` 已从外部 pure-LLM v2 模板收敛为 `icoder.governed-discharge-education.v1` 本地确定性 Provider。它只接受明确标注的出院诊断、就诊原因、诊疗经过、出院去向、检验、影像、操作/手术、出院用药、复诊/随访、警示症状、生活方式/家庭护理、待回结果和资料冲突，并为每条原文事实保存脱敏输入中的 `[start,end)` 字符证据。

该能力不把医学术语改写成通俗释义，不解释检验或影像意义，不执行药物重整、相互作用、剂量、禁忌、过敏或肝肾功能审查，不补写诊断、预后、警示症状、返院条件、随访步骤或其他医疗建议。未标注自由文本返回 `INPUT_REQUIRED`；字段不全返回 `PARTIAL` 和明确缺口/澄清问题。所有患者可见内容都是须临床人员复核的草稿，生产写回固定阻断。

## 实现与合同

- Pack 升级为 `icoder/discharge-edu@1.1.0`，`model=null`、`experts=[]`、`tools=[]`、`network_required=false`、`llm_required=false`，并接入统一 Registry、Run、A2A、Trace、Hub discovery、项目副本和运行矩阵。
- 追加式合同为 `icoder/DischargeEducationOutput/v3`，声明 24 个必填顶层字段，覆盖 encounter、结果、用药、随访、警示症状、生活方式、待回结果、teach-back、澄清问题、冲突、来源完整性、证据、限制和审计引用。
- 合同包含 6 条跨字段关系和 1 组逐条证据绑定；`COMPLETED` 必须具有五类核心内容且无缺项，`PARTIAL` 必须有证据和缺项，`INPUT_REQUIRED` 不得发布出院事实。
- `medication_reconciliation_status=NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED`、`translation_status=VERBATIM_DOCUMENTED_CONTENT_ONLY`、`external_knowledge_used=false`、`clinical_interpretation_performed=false`、`clinical_recommendations_generated=false`、`production_writeback_blocked=true`、`manual_review_required=true` 均为合同常量，结构化投影层再次强制覆盖。
- 输入最多 40,000 字符、证据最多 200 条、teach-back/澄清问题各最多 30 条；空输入、未标注文本、Prompt 注入 canary、稀疏记录和超限路径均有失败关闭测试。
- Pack 示例输入与实际运行输出逐字段完全相等；A2A 和 HTTP 路径均在实际 PHI 脱敏文本上验证证据坐标。

## 真实开发环境证据

最终受控 loopback HTTP 使用新建、迁移并删除的临时 SQLite、临时租户和随机本地 secret；真实 LLM、外网、原生 MedCodER/FAISS/BGE 均关闭。完整证据位于 [`local_semantic_e2e_discharge_education_phase_20260824_rerun1`](../../reports/agent_hub/local_semantic_e2e_discharge_education_phase_20260824_rerun1/)：

- happy：14/14；
- adversarial：14/14；
- Pack-owned reference replay：14/14；
- stability：84/84，三轮 happy + adversarial，全部为 fresh HTTP，seeded=0；
- 26-Agent 离线安全 E2E：78/78；14 个本地基线 Agent 必须成功，12 个外部模型 Agent 必须安全失败且不得泄漏临床合同字段；
- 字段关系对抗回放：138/138（16 个 Agent、61 条关系）；证据绑定对抗回放：38/38（10 个 Agent、19 条绑定）；
- Discharge Education A2A：2/2；Provider/投影聚焦测试：9/9；针对性合同/矩阵/重放：127/127；
- 最终相关宽回归：744/744；schema 生成器专项：6/6；
- 输出合同兼容：26 个可见合同、117 个注册版本，0 个新增未登记、漂移、无效或重复引用；
- 静态部署预检：90/90；
- Corti 历史 20-Agent 开发映射：中国适配声明与开发门禁 20/20，独立临床质量和生产就绪仍为 0/20；
- 当前运行矩阵：12 个外部 LLM 必需、1 个可选增强、13 个纯本地、14 个离线本地基线；严格 26-Agent live-provider 验证仍为 0/26，生产就绪验证仍为 0/26。

第一次 HTTP 运行的 happy 14/14 已通过，但对抗清单误用了执行器不支持的 `contains_all` 操作符，测试在第 4 项前停止；这不是 Agent 运行失败。清单被拆成四个受支持且等强度的断言后，在新目录 `_rerun1` 完整重跑通过。首次目录保留为不完整诊断证据，不被计入上述通过结果。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_discharge_education_phase_20260824_rerun1/phase_evidence.json)。受保护数据库 `backend/data/icoder.db` 保持 8,536,064 bytes、SHA-256 `9547e301…bb3e`、修订 `041`；源码迁移头为 `056`。测试结束后无 Python/Uvicorn 进程和 8000 端口监听。

这些结果只证明合成输入下的合同、可追溯性、安全失败和开发稳定性，不证明患者理解、依从性、再入院结果、临床遗漏率、严重错误率或 Corti 产品等价。

## 与 Corti 当前公开能力的差距

Corti 当前公开的 Patient Discharge Education Agent 接受出院摘要/AVS、出院指示与返院注意事项、药物、检验、影像、操作、随访/转诊和待回结果，并可结合阅读水平、语言和照护者需求。其公开页面描述了患者友好语言、保守结果解释、药物变化、检查清单、门户消息和缺失/冲突指示，以及 PubMed、Web Search、Medical Calculator 专家；同时明确只使用已记录的出院信息，不诊断、不改变照护计划、不新增随访或医疗建议、不猜测结果意义，并把缺失/冲突转成患者可安全提出的问题。[Corti Patient Discharge Education Agent](https://www.corti.ai/agents/patient-discharge-education-agent)

| 能力 | iCoDer 当前 | 差距判断 |
|---|---|---|
| 输入覆盖 | 支持 13 类明确中英文标签和单段文本 | 缺真实 AVS/出院摘要/医嘱/药物/检验/影像/转诊多源解析与纵向病历合并 |
| 事实约束 | 只逐字重排已记录内容，缺失/冲突显式返回 | 安全边界与 Corti 公开原则方向一致；尚无跨文档身份、时间、版本和冲突消解 |
| 患者友好语言 | 固定 `VERBATIM_DOCUMENTED_CONTENT_ONLY` | 未复刻通俗医学释义、阅读等级、健康素养、年龄/文化适配 |
| 多语言 | 接受中英文标签，输出固定中文模板问题 | 未提供受验证的患者语言翻译、术语一致性或双语审阅工作流 |
| 结果解释 | 只显示逐字结果并标注“未解释” | 未复刻 Corti 的保守结果解释；需临床规则、参考范围、上下文和独立验证 |
| 用药变化 | 只复述明确出院用药 | 未做入院前/住院/出院药物重整、变化原因、品牌/通用名或药品知识解释 |
| Teach-back / 澄清问题 | 按已记录章节生成通用复述问题，缺项生成确认问题 | 有开发基线；缺患者可用性、阅读负荷、误解风险和照护者研究 |
| 检查清单与门户消息 | 有结构化字段，可由客户端渲染 | 缺患者门户模板、发送审批、撤回、更正、回执、可访问性和真实写入接口 |
| PubMed / Web Search / Medical Calculator | 固定未调用 | Corti 专家能力未复刻；需授权、区域网络、引用、版本和知识治理 |
| 审批与写回 | 强制人工复核，生产写回阻断 | 安全方向一致；缺医师/护士/药师审批签名、患者门户发布、回滚和责任审计 |

## 中国场景适配状态

已完成中文出院诊断、诊疗经过、出院去向、检验/影像、操作、用药、复诊、警示症状、生活方式、待回结果和冲突标签；支持中文 teach-back/澄清问题、精确证据 span、CN 区域失败关闭和强制临床复核。

仍缺中国医院 HIS/EMR、电子病历、出院小结、医嘱、药房/MAR、LIS/PACS、转诊、随访和互联网医院/患者服务平台接口；缺医院出院宣教模板、药品商品名/通用名/复方/剂型、中文医学术语通俗化、老年与低健康素养可读性、方言/少数民族语言、无障碍、照护者模式，以及临床科室、护理部、药学部、医务和患者代表共同批准的内容资产。

本地词法整理不能自行升级为患者医疗建议。医学释义、结果解释、药物变化、返院条件和个性化教育必须由医院临床、护理、药学、患者教育、法务与独立 reviewer 提供和批准。

## 外部上线门禁

- 真实医院授权且去标识化的出院记录/AVS/患者教育金标准，以及事实遗漏率、错误添加率、证据一致率、严重危害错误率和临床人员一致性门槛；
- 患者与照护者的理解、teach-back 完成度、可读性、健康素养、无障碍、语言公平性、依从性和误解风险评估；
- HIS/EMR、医嘱、MAR/药房、LIS/PACS、转诊/随访、互联网医院和患者门户的身份、时间、版本、冲突、审批、发送、撤回和回滚验证；
- PubMed、Web Search、Medical Calculator、药品库和医院知识资产的授权、区域、引用、版本、适用条件与独立临床验证；
- 临床科室、护理部、药学部、患者教育、医务、法务、隐私、网络安全、伦理和医疗软件监管审批；
- 生产多租户容量、延迟、可用性、灾备、监控、事故响应、数据留存和区域基础设施审核。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Patient Discharge Education、v3 追加合同、14-Agent HTTP 门禁和 Corti 逐项差距 | 将该 Hub Agent 从外部模型模板收敛为可运行、可审计、可测试的开发上线候选切片 |
