# iCoDer 受治理 Procedure Extractor 本地基线阶段总结

> **声明**：本阶段只证明开发环境中的保守、确定性手术操作提取和受治理目录候选能力，不证明完整临床编码准确率、Corti 等价、医保结算权威或生产审批。
> **日期**：2026-08-24
> **阶段**：Agent Hub Procedure Extractor 本地语义收敛
> **状态**：DEVELOPMENT VERIFIED；EXTERNAL GATES OPEN

> **后续口径**：本文件的 8-Agent / 18 外部模型数字是本阶段完成时的历史快照；当前数量已由
> [`ICODER_GOVERNED_DIAGNOSIS_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`](ICODER_GOVERNED_DIAGNOSIS_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md)
> 更新为 9 个本地基线、17 个外部模型强依赖。Procedure 的实现和测试证据仍有效。

## 阶段结论

`procedure-extractor` 已从 `icoder.pure-llm.v1` 强制外部模型路径切换为
`icoder.governed-procedure-extractor.v1`。它现在无需网络或模型即可从已脱敏原文中：

- 定位带明示状态的手术/操作，并为每项保留逐字 `evidence_text` 与字符 span；
- 只把 `performed` 放入 `procedures`，把 `planned`、`historical`、`cancelled`、
  `negated` 和 `unknown` 放入 `non_billable_mentions`；
- 仅在输入编码命中固定目录，或有界词法规范化得到唯一目录条目时输出
  ICD-9-CM-3 候选；未唯一命中时保留明示术式但 `code` 为空；
- 始终要求编码员复核，禁止自动结算和 EMR/HIS 写回。

本地语义矩阵因此从 **7/26** 扩展为 **8/26**，外部模型强依赖从 **19** 降至
**18**。严格 26-Agent live-provider 证据仍为 **0/26**，生产就绪仍为 **0/26**；
本地 bundle 不得替代完整门禁。

## E2E 暴露并关闭的真实缺口

原 Pack 的 T12 椎体骨折切开复位内固定术示例填入了 `81.0100`。固定目录显示该码的
名称是“寰-枢脊柱融合”，与示例事实不符；对应的示例 span `[28, 46]` 也不能逐字切回
原文。本阶段将示例改为目录中的 `03.5304 — 胸椎骨折切开复位内固定术`，span 改为
`[22, 38]`。映射只使用原文明示的 `T12`、骨折和切开复位内固定术，不扩展到未记录的
入路、器械、分级或其他临床语义。

对抗用例“原拟行腹腔镜胆囊切除术，因患者拒绝已取消，本次未实施任何手术”现在稳定返回
空 `procedures`、`cancelled` 的非计费提及和人工复核问题。既往、否定和未知状态同样不会被
提升为本次已实施操作。

## 运行、审计和契约

- Pack：`icoder/procedure-extractor@1.1.0`；完整性 SHA-256
  `7ca0f0e8986f33241fa7746f7f9a1a9671d6dd220e0259ba6d1b766fb880971f`。
- 输出继续遵循 `icoder/ProcedureCodingOutput/v8`，避免破坏现有 Run/A2A/SDK 消费端。
- Provider Registry、统一 Run 和 A2A v0.3 均返回同一 Pack 字段；无 legacy fallback。
- Trace 记录 Provider、零 LLM 调用/费用、目录 ID/版本、authority/license、完整性结果、
  候选编码数和证据项数，不记录病历正文。
- 目录 `cn.icd9cm3.catalog@observed-local-2026-05-19` 虽经大小和 SHA-256 校验，仍是
  `authority_status=source_unverified`、`license_status=external_review_required`、
  `billing_authoritative=false`。

## 验证结果

隔离 runner 使用全新临时 SQLite、随机 loopback 端口、真实租户 Bearer、真实 Run/Trace API，
并清除所有 LLM Key、关闭外部 LLM、原生 MedCodER、STT 和模型 Canary。

| 验证 | 结果 |
|---|---:|
| 本地 happy HTTP | 8/8 |
| 本地 adversarial HTTP | 8/8 |
| Pack reference replay | 8/8 |
| 三轮稳定性 | 48/48，全部 fresh HTTP，0 seeded |
| 扩大聚焦回归 | 305 passed，0 failed |
| Corti 目录映射与预检单测 | 4 passed，0 failed |
| 静态部署预检 | 90/90 |

证据入口：

- `reports/agent_hub/local_semantic_e2e_procedure_phase_20260824/local_semantic_e2e_evidence.json`
- `reports/agent_hub/local_semantic_e2e_procedure_phase_20260824/phase_evidence.json`
- `reports/deployment/preflight-agent-procedure-local-20260824/deployment_preflight.json`

## 与 Corti Procedure Entity Extractor 的逐项差距

Corti 当前公开的 [Procedure Entity Extractor Agent](https://corti.ai/agents/procedure-entity-extractor-agent)
声明从一次就诊的手术、操作、麻醉、影像、检验、输注和器械记录中提取全部可编码服务，按场景
路由至 ICD-10-PCS、CPT 或二者，并通过 Predict/Search/Explore/Guidelines/Verify 工具验证编码；
它还覆盖七轴 PCS 构造、root operation、bundling、双侧规则、矛盾和缺失特异性。

| 能力 | iCoDer 当前状态 | 差距 |
|---|---|---|
| 明示术式与状态 | 本地逐字 span；performed 与五类非计费状态隔离 | 仅覆盖有界中文状态词，尚无真实病历 recall/precision |
| 中国操作编码 | 固定哈希 ICD-9-CM-3 唯一词法候选 | 目录来源/许可未核验；无权威版本、生效期和医院扩展码 |
| 编码体系 | ICD-9-CM-3 开发基线 | 未复刻 Corti 的 ICD-10-PCS、CPT/HCPCS 和双体系路由 |
| 术式理解 | 只允许唯一词法匹配及明示脊柱节段的窄规范化 | 无全病历模型抽取、缩写/同义词推理、跨段合并和矛盾解析 |
| 编码规则 | 不判断适用性，不猜测 | 无 PCS 七轴、root operation、bundling、双侧和 separately-reportable 规则 |
| 工具闭环 | Provider、Run/A2A、Trace 已闭环 | 无同数据集 Predict/Search/Explore/Guidelines/Verify 质量证明 |
| 质量 | Pack 自带合成 E2E 通过 | 无独立医院 gold set、编码员盲评、P/R/F1、错误分层和 Corti 同题对照 |

Corti 的 [Agentic Framework](https://docs.corti.ai/agentic/overview) 还以 LLM 动态规划、可信工具、
人工审批/恢复、类型化 I/O 和可回放 Trace 为公开基线。本地确定性规则适合作为安全底座，但不能
冒充 Corti 所述的开放式推理和多工具编码能力。

## 安全与外部门禁

- 受保护数据库保持 8,536,064 字节，SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
  版本仍为 `041`，源码 Alembic head 为 `056`。
- 测试结束后后台进程和 `icoder-agent-local-e2e-*` 临时目录均为 0。
- 当前进程没有 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`；
  本阶段没有真实模型或外网调用。
- Docker CLI 不可用，未生成镜像构建、SBOM、CVE 扫描或签名证据。
- 权威目录、真实医院集成、独立临床评审、法务/许可、云 KMS/Secret Manager、生产容量、
  灾备和安全认证仍必须保持未通过。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理本地 Procedure Extractor、修正错误示例编码/span、扩展 8-Agent 四类 E2E 和 Trace/预检门禁 | 持续减少面向用户 Agent 的 metadata/外部模型单点依赖，并诚实保留 Corti 与生产差距 |
