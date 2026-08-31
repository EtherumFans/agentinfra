# iCoDer 受治理 Triage 问卷路径复核阶段总结（2026-08-25）

## 阶段结论

`triage` 已从依赖外部模型的泛化模板收敛为可在开发环境重复运行的受治理确定性问卷路径复核能力：`icoder/triage@1.1.2`、Provider `icoder.governed-triage-questionnaire.v1`、不可变输出合同 `icoder/TriageOutput/v5`。它是开发期协议候选复核器，不是自主急诊分诊系统，也不代表已达到 Corti 等价或临床生产上线。

本实现只接收调用方明确提供的问卷定义、显式结构化答案及 `来源记录`，验证有限问题/分支图，沿确定性路径到达候选端点，并把答案的 `evidence_text` 绑定到来源记录中的唯一字符区间。协议来源、版本、声明和医院状态均由调用方提供；平台不验证其权威性、许可、最新版本或医院批准真实性。

固定安全边界如下：

- 不从护士—患者对话或自由文本抽取问卷答案；
- 不补全、猜测或推断缺失答案和临床事实；
- 不调用 LLM、外网、医学计算器、药品或外部知识工具；
- 不把问卷端点升级为最终急诊分诊级别；
- 不生成治疗指令，不触发生产动作，不提交或写回医院系统；
- 所有到达端点只标记为 `DEVELOPMENT_UNVERIFIED_PROTOCOL_CANDIDATE`，强制现场人工复核。

## 中国场景适配

开发合同显式覆盖“中国医院急诊分诊”，要求协议标识、版本、来源、声明状态、医院状态和来源记录，并支持中文问题、枚举、红旗标记、候选处置和澄清项。适配重点是把本地医院协议的责任边界、版本和审计信息带入运行链路，而不是在平台内置未经授权的国家或医院分诊规则。

因此，本阶段只证明中国场景的工程承载和失败关闭机制；真实医院协议授权、地方规则差异、急诊流程、人机工效、HIS/EMR 集成和临床验收仍须在院完成。

## 开发环境验证

- Triage 单元与 A2A：8/8；聚焦合同/运行矩阵/部署回归：59/59；26-Agent 离线安全：78/78；Note Completeness 回归：24/24。
- 最新重签 loopback HTTP：happy 24/24、adversarial 24/24、reference 24/24；稳定性 144/144，全部为 fresh HTTP，三轮重复，P50 0.527 秒、P95 1.025 秒。
- 当前合同注册 138 个追加版本；26/26 可见引用兼容；字段关系 110 条、对抗断言 340/340；证据绑定 30 条、60/60；跨 Agent 关系 10 条、20/20。
- 静态部署预检 90/90；Corti 20-Agent 目录开发映射 20/20、中国声明 20/20，但临床质量和生产就绪仍为 0/20。
- 26 个 Hub 可见 Agent 均 executable、Provider-resolvable、launch-candidate-ready。24 个具有开发环境本地语义证据；CDI 与 Medical Coding 两个外部模型必需项仍待新鲜真实 Provider 证据。严格 26-Agent live-provider 门禁和生产就绪均为 0/26。
- 本轮未使用真实 LLM、外网或独立临床金标准，成本为 0 CNY；未观察到内存访问冲突。受保护数据库字节数、最后写入时间和 SHA-256 均保持不变。

机器证据位于 [`phase_evidence.json`](../../reports/agent_hub/triage_questionnaire_phase_20260825_v1/phase_evidence.json)；最新重签 HTTP bundle 位于 [`agent_hub_local_semantic_evidence_bundle.json`](../../reports/agent_hub/local_semantic_e2e_external_gate_phase_20260825_v3/bundle/agent_hub_local_semantic_evidence_bundle.json)。

## 与 Corti 当前 Triage 能力的差距

Corti 当前公开的 Triage and Initial Assessment Agent 接受带分支/决策规则的问卷 JSON 和护士—患者对话，公开描述包含解析配置、从对话抽取字段、校验完整性、沿规则分支推进，以及信息不足时停止或澄清；其公开配置还列出 PubMed、Interviewing、Medical Calculator 和 DrugBank 等能力。Corti 同时声明不自行开展访谈、不在数据不完整时给出最终级别、也不覆盖临床判断。对照页面：[`Triage and Initial Assessment Agent`](https://corti.ai/agents/triage-and-initial-assessment-agent)。

当前 iCoDer 已对齐的是：有界问卷结构校验、确定性分支、缺失/冲突失败关闭、证据追踪、人工复核和禁止自动写回。尚未复刻的是：

- 从对话或自由文本可靠抽取问卷答案；
- 交互式访谈、动态追问和完整临床上下文编排；
- PubMed、医学计算器、药品知识及其他经许可临床工具链；
- 经医院批准和版本治理的真实分诊规则库；
- 经独立临床验证的最终 acuity/分诊级别分配；
- 医院身份、用户角色、动作审批、HIS/EMR 闭环和生产审计；
- 临床质量、人因、网络安全、容量、SLA、法务、监管和认证证据。

所以，本阶段缩小了“问卷协议执行与可审计失败关闭”的工程差距，但没有证明模型、临床质量、工作流或托管产品与 Corti 等价。

## 下一阶段优先级

1. 在隔离临时数据库和轮换后的临时凭据下，为 CDI 与 Medical Coding 完成新鲜、签名、非 mock 的 happy/adversarial/reference/stability 证据，形成严格 26-Agent bundle。
2. 为 Triage 增加受治理的自由文本/对话字段抽取层，但保持抽取、协议路径和最终临床判断三层分离；任何推断必须可追溯并在缺失或冲突时失败关闭。
3. 与真实中国医院确定问卷版本权威、红旗和处置语义、护士复核点及接口边界，再进行独立临床金标准和人因评测。
4. 补齐医院互操作、生产云、安全、隐私、法务、监管、认证和运维门禁；未取得外部证据前继续保持生产就绪 0/26。
