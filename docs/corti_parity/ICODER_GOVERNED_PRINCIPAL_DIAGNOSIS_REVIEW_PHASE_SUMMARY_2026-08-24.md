# iCoDer 受治理主诊断初稿复核阶段总结

> 声明：本文件记录开发环境证据，不构成主诊断选择、临床诊断、编码授权、医保结算、医院、法律、认证或生产上线批准。  
> 日期：2026-08-24  
> 阶段：Agent Hub `principal-diagnosis-review` 受治理本地基线  
> 状态：开发候选切片通过；Corti 自动编码能力与外部门禁开放

## 本轮结果

`principal-diagnosis-review` 已从外部 pure-LLM 模板升级为
`icoder/principal-diagnosis-review@1.1.0`、Pack format 1.2、
`icoder.governed-principal-diagnosis-review.v1` 和不可变当前合同
`icoder/PrincipalDxReview/v11`。26 个公开 Agent 均为 executable、Provider-resolvable、
结构性 launch-candidate-ready；纯本地 Agent 从 20 增至 21，本地确定性或受治理基线从
21 增至 22，外部 LLM 强依赖从 5 降至 4。

旧 Pack 会根据“危害最大、资源消耗、主要治疗”等宽泛描述直接推荐 `S22.000`，部分证据
span 为 `[0,0]`，并输出未被输入逐字支持的选择理由。新运行时删除所有 `recommended`、
`principal_dx`、`not_recommended` 和自动选择语义，只接收明确标注的：

- 审核目的、编码标准/版本、病案文档范围；
- 编码员已经填写的主诊断初稿；
- 显式候选集合及每项来源文档、逐字证据；
- 编码员声明的入院原因、主要治疗、资源使用或医院批准的其他选择依据。

它只检查初稿是否在候选集合中唯一精确出现、候选与依据是否重复/冲突、依据是否引用已知
候选、初稿候选是否具有精确证据，以及依据是否已提供。它不从自由文本提取诊断，不新增、
分配、排序、推荐或替换编码，不判断诊断成立、病因、严重程度、主要治疗或资源消耗，也不
执行国家、医保、病案首页或医院主诊断规则。所有输出均禁止提交和写回并要求编码员复核。

## 中国医院场景适配

输入显式保留 `ICD-10-CN`、医院批准版本、入院/出院/手术等中文病案来源、编码员初稿与
`ADMISSION_REASON`、`MAIN_TREATMENT`、`RESOURCE_USE`、
`HOSPITAL_APPROVED_OTHER` 四类声明依据。每个来源字段、候选证据和选择依据都绑定到脱敏后
输入的 `[start,end)` 精确 span。这能形成病案首页编码员复核包，但医院批准版本只是用户
提供的元数据；当前没有权威国家/省市/医院规则资产，也没有证明该初稿符合中国主诊断选择、
DRG/DIP、医保结算或病案统计规范。

## 契约与安全修复

- 26 个必需公开字段、5 条跨字段关系、3 条证据绑定和 1 条可选上游 Diagnosis Extractor
  签名关系均通过定义与对抗重放。
- 投影器对 v11 使用严格 26 字段白名单；即使收到恶意 JSON，也会删除旧版
  `recommended/principal_dx` 并强制“不提取、不分配、不选择、不推理、不外部用规则、
  禁止提交/写回、人工复核”。
- 重复候选 ID 或编码即进入声明冲突；超过 100 个候选/依据或 60,000 字输入时失败关闭，
  不静默截断为可复核结果。
- v11 已追加到不可变合同注册表；26 个可见合同、131 个历史注册版本无漂移。

## 验证证据

| 验证 | 结果 |
|---|---:|
| 新 Provider/合同/投影与矩阵聚焦测试 | 53/53 |
| A2A 与统一 Run 聚焦集成 | 17/17 |
| 字段关系对抗重放 | 301/301，20 个 Agent、101 条关系 |
| 证据绑定对抗重放 | 56/56，17 个 Agent、28 条绑定 |
| 真实 loopback happy | 22/22 |
| 真实 loopback adversarial | 22/22 |
| Pack reference replay | 22/22 |
| 三轮稳定性 | 132/132 fresh HTTP，p50 0.403 秒，p95 0.590 秒 |
| 扩大串行回归 | 1203 passed、5 skipped、6 deselected、0 failed |
| 静态部署模拟 | 90/90 |

机器证据见：

- [`phase_evidence.json`](../../reports/agent_hub/principal_diagnosis_review_phase_20260824_v1/phase_evidence.json)
- [`22-Agent 本地语义 E2E`](../../reports/agent_hub/local_semantic_e2e_principal_diagnosis_review_phase_20260824_v1/)
- [`部署模拟`](../../reports/deployment/principal_diagnosis_review_phase_20260824_v1/)

## 与 Corti 的逐项差距

Corti 当前公开资料没有同名的独立 Principal Diagnosis Review Agent，因此本阶段采用相邻的
[Medical Coding Agent](https://corti.ai/agents/medical-coding-icd-10-cpt-agent)、
[Medical Coding API Core Concepts](https://docs.corti.ai/coding/introduction) 和
[Encounter Diagnosis Coding](https://docs.corti.ai/coding/encounter-coding) 对照。Corti 声明从
自由文本临床上下文提取诊断和操作，分配主/次诊断与程序编码，验证选择、顺序和 modifier，
返回结构化 `codes`、`candidates`、逐字 evidence spans 和 alternatives，并把结果送人工复核。
其 [Agentic Framework](https://docs.corti.ai/agentic/overview) 还声明可回放 trace、结构化日志、
多 Agent、上下文/记忆与第三方集成。

| 能力 | 本轮 iCoDer | 与 Corti 的剩余差距 |
|---|---|---|
| 输入理解 | 只解析明确标签和分隔格式 | 不从完整病案自由文本提取诊断、症状、发现和操作 |
| 主诊断 | 只核对编码员初稿是否唯一存在于显式候选集合 | 不选择主诊断，不依据 encounter reason/after study 等规则排序 |
| 编码 | 保留用户提供 ICD-10-CN 代码字面量 | 不搜索、分配或验证代码，不遍历目录层级，不生成 alternatives |
| 证据 | 候选、依据和元数据均有精确输入 span | 不建立模型预测到全病历多来源 evidence 的召回质量证明 |
| 编码规则 | 固定声明“不使用外部规则” | 无 ICD-10-CM/CPT/HCPCS 选择、顺序、modifier 和官方指南工具闭环 |
| 中国适配 | ICD-10-CN、医院版本、中文病案来源与四类声明依据 | 无权威国家/地方/医院版本、病案首页主诊断、DRG/DIP/医保规则资产 |
| 审计与安全 | 严格 schema、关系、证据绑定、Trace/attestation、失败关闭 | 无独立临床 benchmark、编码员盲评、医院验收、生产合规与 Corti 同题质量数据 |

因此，本轮关闭的是“编码员已填写初稿 + 显式候选/依据 + 精确证据 + 集合一致性 + 中国医院
字段 + 失败关闭”的开发基线，不是 Corti Medical Coding 的自动编码或主诊断选择复刻。严格
26-Agent 真实 Provider 语义验证和生产验证仍为 0/26。

## 运行、浏览器与密钥边界

全部测试使用临时 SQLite，关闭外部 LLM、原生 MedCodER、本地 STT 和模型 Canary；E2E
没有访问外部网络。受保护数据库保持 8,536,064 bytes、SHA-256
`2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`，最后写入仍为
2026-08-22 17:16:22；测试结束后无 Python/Uvicorn 进程或监听，未出现内存访问冲突。

本阶段尝试只读连接用户已登录的 Corti Console 时，Codex 浏览器运行组件因本地 kernel asset
路径缺失而无法初始化，因此没有把控制台交互冒充为已复测；差距只引用 2026-08-24 检索到的
Corti 官方公开页面。三个 LLM Key 环境变量在进程、用户和机器级长度均为 0。此前在对话中
明文暴露的 DeepSeek Key 仍必须在 DeepSeek 控制台注销/轮换。

## 下一阶段

剩余 4 个外部强依赖 Agent 为 `clinical-documentation-improvement-agent`、`drg-analyzer`、
`medical-coding-agent` 和 `triage`。CDI 与 Medical Coding 已有专用复杂运行时，不应为减少计数
而降级为窄规则；DRG 需要权威分组器/规则资产，Triage 属高风险临床决策。开发环境应继续
完善真实 Provider 的签名 happy/adversarial/reference/stability 证据、质量集和失败关闭，
但国家/医院规则、临床 gold set、医院集成、云容量、法务、认证与独立 reviewer 必须保持
外部门禁。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理主诊断初稿复核 Provider、v11 合同、22-Agent HTTP E2E、投影白名单和 Corti 相邻编码差距 | 删除旧版无证据自动推荐并建立中国医院编码员复核基线 |
