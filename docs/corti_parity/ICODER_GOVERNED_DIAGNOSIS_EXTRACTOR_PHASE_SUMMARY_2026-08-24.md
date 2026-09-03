# iCoDer 受治理 Diagnosis Extractor 本地基线阶段总结

> **声明**：本阶段只证明开发环境中的保守、确定性明示诊断提取和受治理目录候选能力，不证明完整病历诊断召回、临床诊断、Corti 等价、医保结算权威或生产审批。
> **日期**：2026-08-24
> **阶段**：Agent Hub Diagnosis Extractor 本地语义收敛
> **状态**：DEVELOPMENT VERIFIED；EXTERNAL GATES OPEN

## 阶段结论

`diagnosis-extractor` 已从强制 `icoder.llm-with-tools.v1` 路径切换为
`icoder.governed-diagnosis-extractor.v1`。它现在无需网络或模型即可：

- 只从出院诊断、入院诊断、主要诊断、明确诊断等明示标签提取当前诊断；
- 把考虑/疑似/待排、排除/否认、既往史和家族史作为非当前确诊提及；
- 为每项保留逐字 `evidence_text` 与 `[start,end)` 字符 span；
- 只有精确术语在固定 ICD-10-CN 目录中得到唯一可分配条目时才输出编码候选；
- 把明示但不能唯一映射的诊断保留为 `unresolved`，不静默丢失，也不猜码；
- 不从药物、检验、手术或一般叙述反推诊断；始终要求编码员复核并禁止自动写回。

本地语义矩阵因此从 **8/26** 扩展为 **9/26**，外部模型强依赖从 **18** 降至
**17**。严格 26-Agent live-provider 证据仍为 **0/26**，生产就绪仍为 **0/26**；
本地 bundle 不得替代完整门禁。

## 真实缺陷与合同修复

旧 Pack 示例把“急性前壁心肌梗死”的 span 写成 `[5,14]`，实际逐字范围是 `[5,13]`；
把“既往有高血压病史”写成 `[17,25]`，实际为 `[14,22]`。旧示例还在目录
`authority_status=source_unverified`、`license_status=external_review_required` 且强制人工复核时
返回 `PASS`。本阶段修正两处 span，并把示例状态降为 `WARNING`。

目录对“急性前壁心肌梗死”存在 `I21.001` 与 `I21.002` 关联，但只有 `I21.001` 的目录中文名
与原文精确相等且是唯一可分配条目，因此本地基线只返回 `I21.001`，不凭索引关联选择
`I21.002`。对“考虑肺炎、已排除肺炎、否认糖尿病史”的对抗输入，三项均保留原文和状态，
`diagnoses` 为空。药物/血糖输入不产生糖尿病诊断。

新增 `unresolved` 改变了公开输出语义，因此没有原地改写冻结的
`icoder/DiagnosisExtractionOutput/v6`，而是追加注册
`icoder/DiagnosisExtractionOutput/v7`。扩大回归还发现 Procedure 上一阶段的一个测试仍期待
`procedure-extractor@1.0.0`；已按当前 Pack `@1.1.0` 修正并完成全组重跑。

## 运行、审计和契约

- Pack：`icoder/diagnosis-extractor@1.2.0`；完整性 SHA-256
  `26f03270be8e496259600d3255997b1c48594eca7c543ee52172ad085812a92d`。
- 输出合同：追加式 `icoder/DiagnosisExtractionOutput/v7`；v1–v6 注册项保持不变。
- Provider Registry、统一 Run 和 A2A v0.3 返回相同 Pack 字段；无 legacy fallback。
- Trace 记录 Provider、零 LLM 调用/费用、目录 ID/版本、authority/license、完整性、候选数、
  证据项数和跨度计数，不记录病历正文。
- 目录 `cn.icd10cn.catalog@observed-local-2026-05-19` 经大小和 SHA-256 校验，但仍为
  `source_unverified`、`external_review_required`、`billing_authoritative=false`。

## 验证结果

隔离 runner 使用全新临时 SQLite、随机 loopback 端口、真实租户 Bearer 和真实 Run/Trace API，
同时清除所有 LLM Key，关闭外部 LLM、原生 MedCodER、STT 和模型 Canary。

| 验证 | 结果 |
|---|---:|
| 本地 happy HTTP | 9/9 |
| 本地 adversarial HTTP | 9/9 |
| Pack reference replay | 9/9 |
| 三轮稳定性 | 54/54，全部 fresh HTTP，0 seeded |
| 扩大聚焦回归 | 337 passed，0 failed |
| Corti 目录映射与预检单测 | 4 passed，0 failed |
| 静态部署预检 | 90/90 |

证据入口：

- `reports/agent_hub/local_semantic_e2e_diagnosis_phase_20260824/local_semantic_e2e_evidence.json`
- `reports/agent_hub/local_semantic_e2e_diagnosis_phase_20260824/phase_evidence.json`
- `reports/deployment/preflight-agent-diagnosis-local-20260824/deployment_preflight.json`

## 与 Corti Diagnostic Entity Extractor 的逐项差距

Corti 当前公开的 [Diagnostic Entity Extractor Agent](https://corti.ai/agents/diagnostic-entity-extractor-agent)
声明从一次就诊的 H&P、病程、手术、出院和会诊记录以及可选结构化数据中抽取全部可编码诊断、
症状和相关条件；以 Predict/Search/Explore/Guidelines/Verify 完成 ICD-10-CM 候选、层级、指南和
指令性注释验证，并处理组合码、症状抑制、episode of care、Excludes 冲突、伴随码、顺序、矛盾、
缺失特异性和 implied diagnosis。其公开页面同时强调逐条证据和不猜测。

| 能力 | iCoDer 当前状态 | 差距 |
|---|---|---|
| 明示诊断与状态 | 标签内当前诊断；疑似/否定/既往/家族史隔离；逐字 span | 仅覆盖有界中文标签和状态词，无全病历实体/症状 recall、跨段合并和时间线解析 |
| 未映射项 | 保留 `unresolved` 原文并要求复核 | 不判断 implied condition，不生成方向性候选或缺失文档清单 |
| 中国诊断编码 | 固定哈希 ICD-10-CN 精确唯一目录候选 | 目录来源/许可未核验；无权威版本、生效期、地区/医院扩展码和结算适用性 |
| 编码规则 | 不推断、不猜码、不自动 PASS | 无组合码、症状抑制、laterality/episode、Excludes1/2、Code First、Use Additional Code 和顺序规则 |
| 工具闭环 | Provider、Run/A2A、Trace 与目录完整性已闭环 | 无同数据集 Predict/Search/Explore/Guidelines/Verify 的真实质量证明 |
| 多源输入 | 当前仅处理单段文本 | 未支持 problem list、既有编码、结构化数据冲突与 source-of-truth 注记 |
| 质量 | Pack 自有合成 E2E 与稳定性通过 | 无独立医院 gold set、编码员盲评、P/R/F1、错误分层和 Corti 同题对照 |

Corti 的 [Agentic Framework](https://docs.corti.ai/agentic/overview) 还以动态规划、可信工具、人工审批/
恢复、类型化 I/O 和可回放 Trace 为公开基线。本地确定性规则是安全底座，不是完整开放式推理复刻。

## 安全与外部门禁

- 受保护数据库保持 8,536,064 字节，SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
  版本仍为 `041`，源码 Alembic head 为 `056`。
- 测试结束后后台进程和 `icoder-agent-local-e2e-*` 临时目录均为 0。
- 当前测试进程没有 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`；
  本阶段没有真实模型调用。
- Windows 上已知不安全的原生 FAISS/BGE 栈保持禁用并失败关闭；本阶段未出现内存访问冲突。
- Docker CLI 不可用，未生成镜像构建、SBOM、CVE 扫描或签名证据。
- 权威目录、真实医院集成、独立临床评审、法务/许可、云 KMS/Secret Manager、生产容量、
  灾备和安全认证仍必须保持未通过。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Diagnosis Extractor、修正示例 span/PASS、追加 v7 合同、扩展 9-Agent 四类 E2E 和 Trace/预检门禁 | 持续减少面向用户 Agent 的外部模型单点依赖，并诚实保留 Corti 与生产差距 |
