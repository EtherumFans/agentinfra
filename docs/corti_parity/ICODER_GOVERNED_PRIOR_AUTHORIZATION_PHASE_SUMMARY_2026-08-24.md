# iCoDer Prior Authorization 受治理本地能力阶段总结（2026-08-24）

## 阶段结论

`prior-auth` 已从依赖外部模型、存在自由生成风险的模板，收敛为可运行、可审计、可测试的本地开发上线候选切片：

- Agent：`icoder/prior-auth@1.1.0`
- Provider：`icoder.governed-prior-authorization.v1`
- 输出合同：`icoder/PriorAuthorizationOutput/v5`
- 执行：确定性规则引擎，无 LLM、网络、外部工具或模型成本
- 安全边界：只复制明确标题下的脱敏事实；不检索政策、不评估医疗必要性、不新增诊断/治疗/证据、不校验编码、不提交、不写回
- 审核：所有非输入缺失结果仍是 review-only，必须由临床人员与医保/商保专员复核

本阶段证明的是合成、明确字段输入下的开发能力，不证明完整 Corti Prior Authorization 复刻、支付政策符合性、医疗必要性、自由叙事理解、真实提交或生产上线。严格 26-Agent live-provider 语义验证和 production-ready 验证仍为 0/26。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_prior_auth_phase_20260824_v5/phase_evidence.json)，真实 loopback HTTP 证据见 [`local_semantic_e2e_prior_auth_phase_20260824_v5`](../../reports/agent_hub/local_semantic_e2e_prior_auth_phase_20260824_v5/)，部署预检见 [`development_preflight_prior_auth_phase_20260824_v5`](../../reports/deployment/development_preflight_prior_auth_phase_20260824_v5/)。

## 本轮实现

### 可追溯预授权证据包

Provider 识别明确标注的中英文预授权字段，并把每项复制内容绑定到脱敏输入中的精确字符 span。覆盖：

- 患者姓名、出生日期、参保人/会员编号；
- 申请医师、资质、执业编号/NPI、机构和联系方式；
- 支付方、计划和统筹区；
- 药品/项目、剂量、途径、频次、疗程和已记录编码；
- 诊断、申请原因、临床文书、客观证据、既往治疗、禁忌/不耐受和既往拒绝原因；
- 用户提供的支付政策要求、编号、版本、生效日期和来源。

状态机固定为：

- 核心字段缺失：`INPUT_REQUIRED`，不生成草案；
- 核心字段完整但政策资料缺失/不完整：`POLICY_REQUIRED`，仅生成明确标注缺口的 review-only 草案；
- 核心字段和带版本政策资料完整：`READY_FOR_REVIEW`，仍不等于批准、提交或医疗必要性结论。

药品申请额外要求剂量、途径和频次。输入上限为 40,000 字符、证据上限为 200、单列表上限为 60；canary 和不可信指令边界之后的内容被截断。

### 中国场景适配

- 支持医保经办机构、商保支付方、计划、统筹区和参保编号；
- 支付政策必须显式提供编号、版本、生效日期和来源；
- 不把用户给出的政策摘要冒充官方政策，不自动判断目录、适应证或支付资格；
- 医保/商保平台提交、HIS/EMR 写回和真实表单操作固定阻断；
- 中国常见中文字段和药品预授权要素已纳入确定性解析。

### PHI 脱敏集成修复

A2A 首次完整样例暴露了真实缺陷：宽泛中文姓名规则会把“申请医师、支付方、申请类型、申请药品、支付政策、皮下注射、继续使用”等结构或临床词误删，导致完整材料变成 `INPUT_REQUIRED`。

修复后：

- 结构标签和已记录临床/政策文本保留；
- 患者姓名、出生日期、参保编号和医师编号改为保留标签、只替换值的 typed placeholder；
- 医师姓名仍被脱敏；
- 脱敏后 21/21 证据 span 精确有效，A2A 完整样例恢复为 `READY_FOR_REVIEW`；
- PHI 回归 29/29、Prior Auth A2A 2/2 通过。

### Runtime、合同与审计闭环

- Provider 已进入统一 Provider Registry、Run/A2A 路由、结构化投影和 Trace；
- v5 合同有 34 个必需字段、递归 field schema、8 条字段关系和 1 条证据绑定；
- 公开投影隐藏 provider trace 时允许 `provider_trace_refs=[]`，v5 明确该语义；
- v3/v4/v5 均按追加式注册保留，未覆盖历史合同；注册表共 123 个版本，26/26 可见 Agent 当前合同无漂移；
- schema 生成器 dry-run 为 `changed_agents=[]`；Corti 20-Agent 目录开发映射和中国 profile 均为 20/20。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Prior Auth Provider/投影/矩阵聚焦测试 | 48/48 |
| PHI 脱敏 | 29/29 |
| Prior Auth A2A | 2/2 |
| 26-Agent 离线安全 E2E | 78/78 |
| 兼容 Agent Run 外部/本地路由 | 11/11 |
| 原生导入保护 | 4/4 |
| 本地真实 HTTP happy / adversarial / reference | 17/17 / 17/17 / 17/17 |
| 三轮稳定性 | 102/102，fresh=102，seeded=0 |
| 字段关系对抗回放 | 210/210（19 Agent、82 条关系） |
| 证据绑定对抗回放 | 44/44（13 Agent、22 条绑定） |
| 最终宽回归 | 1146 passed、5 skipped、6 deselected、0 failed；587.77 秒 |
| Corti 20-Agent 开发映射 | 20/20 |
| 静态部署预检 | 90/90；11 项外部限制保留 |

所有 pytest 和 loopback HTTP 测试均在 C 盘隔离 SQLite 上串行运行，禁用了本机原生 MedCodER、FAISS/BGE 和本地 STT，未使用真实 LLM 或外部网络。两轮 17-Agent HTTP E2E 及最终宽回归中未发生内存访问冲突。

当前矩阵：26 个用户可见 Agent 全部具有可解析 Provider 和开发候选结构；9 个仍强依赖外部模型，1 个具有可选外部增强，16 个纯本地，17 个具备离线本地基线，17 个通过本地语义 HTTP 门禁。

## 与 Corti 当前公开 Prior Authorization 的逐项差距

公开对照以 Corti 的 [Prior Authorization Agent](https://www.corti.ai/agents/prior-authorization-agent)、[Agent Library](https://corti.ai/agents) 和 [Solutions](https://corti.ai/solutions) 为准。Corti 公开描述强调药品、剂量/途径/频次/疗程、支付方、患者与医师标识、临床记录、客观证据、既往用药/不耐受/禁忌、拒绝原因及支付方要求；要求缺失信息明确、精确日期和值、不推断或捏造，并可借助 PubMed、Web Search、Medical Calculator 和 Medical Coding 形成结构化预授权信。Solutions 页面还宣称生成和提交工作流。

| 能力 | iCoDer 本阶段 | 对 Corti 的结论 |
|---|---|---|
| 必填字段与药品要素 | 核心字段和药品剂量/途径/频次缺失即阻断 | 开发合同覆盖 |
| 缺失信息显式化 | required/supporting/policy 三类缺口分别输出 | 开发合同覆盖 |
| 不推断、不捏造 | 常量、投影、关系、对抗和证据 span 多层约束 | 开发合同覆盖；无独立临床金标准 |
| 结构化预授权信 | 固定模板逐字装配，review-only | 部分覆盖；不等同生成式专业文本质量 |
| 支付政策 | 只使用用户提供且带版本的摘要 | 无实时 payer/CMS/医保/商保政策检索与权威校验 |
| 医疗必要性 | 明确输出“未评估” | 未覆盖 Corti 文档化必要性组织/政策匹配能力 |
| 客观指标与既往治疗 | 可逐字收集列表 | 不计算量表，不判断治疗失败、疗程充分性或禁忌有效性 |
| PubMed/Web/Calculator/Coding | 全部禁用并在合同中声明 | 未覆盖 |
| 自由叙事和多文档综合 | 只接受明确标题字段 | 未覆盖 |
| 表单和提交 | 固定阻断 | 无 payer-specific 表单、门户、传真、提交、回执或状态追踪 |
| 中国支付场景 | 统筹区、医保/商保和版本政策元数据 | 仍无合法授权的区域政策库、医保接口和医院工作流 |
| 真实质量 | Pack 自有合成样例 | 无医生盲评、严重错误率、同例 Corti 对照或医院验收 |

因此可以诚实声称“Prior Authorization 的明确材料收集、缺失门禁、版本化政策引用、逐字草案和不提交边界已成为开发候选基线”；不能声称“已判断支付资格/医疗必要性”“已自动提交”或“与 Corti 质量等价”。

## 剩余 9 个外部模型 Agent

`claim-check`、`clinical-documentation-improvement-agent`、`clinical-education`、`clinical-guidelines`、`denial-appeals`、`drg-analyzer`、`medical-coding-agent`、`principal-diagnosis-review`、`triage`。

下一阶段应优先处理与本阶段最相邻的 `claim-check`：建立“明确病历事实 + 版本固定的用户提供政策/合同条款”的本地审查基线，严格区分证据一致性、政策不可用和支付资格未判定；真实医保/商保政策源、结算接口和独立专业审核继续保留为外部门禁。

## 环境和不可突破门禁

受保护数据库仍为 8,536,064 bytes、SHA-256 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`、修订 `041`，源码迁移头为 `056`，本阶段未修改。阶段结束时无 Python/Uvicorn 后端监听，E 盘余量约 113.15 MiB。

Windows 事件记录曾在本阶段前显示 `python.exe` 于 `pyarrow/arrow.dll` 发生 `0xc0000005`；本阶段只证明禁用相关原生路径后的测试稳定，不能证明第三方原生库问题已根治。12 个本阶段 pytest 临时数据库仍位于 C 盘系统临时目录（共 23,093,248 bytes）；执行环境阻止了删除操作，它们不属于项目或生产数据库。

以下门禁仍必须由外部证据关闭：真实医院数据与接口、合法且版本受控的支付政策资产、医保/商保门户和提交回执、真实云/PostgreSQL 多副本、容量/灾备/可用性、法务与数据合规、医疗器械/安全认证、独立临床及医保 reviewer、医院模板和工作流验收。
