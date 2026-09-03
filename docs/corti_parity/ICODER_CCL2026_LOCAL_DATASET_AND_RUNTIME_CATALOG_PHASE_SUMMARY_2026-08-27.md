# iCoDer CCL 2026 本地数据与运行目录覆盖阶段总结（2026-08-27）

## 阶段结论

本阶段在用户明确授权 `E:\iCoDerA\data` 后，完成了两项开发环境整改：为受限临床工作簿建立不泄露病例的本地审计链；用获授权的非病例代码资产补齐运行目录对 CCL 2026 标签版本的覆盖。结果是 **1,800 条源记录与仓内 fixture 完全绑定，全部诊断/手术标签均为当前运行目录成员**。

这不等于允许把病例发送给 DeepSeek、Corti 或其他第三方，也不等于 CCL 训练标签是独立临床 gold。外部 Provider 外发、公开再分发、生产准确率和 Corti 临床等价仍固定为未证明。

## 数据源绑定与隐私边界

- 授权源：`E:\iCoDerA\data\train.xlsx`
- 源文件 SHA-256：`4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`
- 源记录：1,800；19 列；含四类诊断/手术标签。
- 仓内 fixture：`backend/tests/fixtures/ccl2026_train_gold.json`
- fixture SHA-256：`c71566686582ff4c3089c0547e2c2ebcccb6eb7b86756419309c680250093027`
- 完整规范化 case digest：1,800/1,800 按顺序完全一致；source-only 0、fixture-only 0、重复病案标识 0。
- 报告只输出文件哈希、计数、覆盖率和治理布尔值；不输出病例正文、病案标识或逐条标签。
- `external_provider_egress_allowed=false`、`source_workbook_copy_allowed=false`、`redistribution_rights_proven=false`、`independent_clinical_gold_proven=false`、`production_accuracy_claim_allowed=false`。

聚合证据：`reports/agent_hub/ccl2026_local_dataset_audit_20260827_v2/ccl2026_local_dataset_audit.json`；内部报告摘要 `e574cacffa226678ed703ee3d5ecdc90c48250fb8da52f9409a052b6f7fe6952`，文件 SHA-256 `83faeb517dce2bd688c178ec1d2f902d9b90095bda9c5576858c7722f4d44ca2`。

## 目录补齐

初始运行目录只能覆盖 CCL 的 817/960 个唯一诊断码和 28/48 个唯一手术码，且点号、大小写与 `x` 占位符归一化不能消除差距。新增两个完整性固定的非病例资产：

- `icd10_cn_standard_names.json`：37,897 条，SHA-256 `7aa0c2acab61596eb5e8b304ee891b06b94d788f87a17b97660ab1043806f0f9`，净增 6,452 个运行代码。
- `icd9cm3_code_catalog.json`：13,617 条，SHA-256 `4d0af72f8d5c3da5008741378ab97373f87f13775487cf5adcee6974cb4bca69`，净增 5,229 个运行代码。

目录发布标识更新为 `icoder-cn-runtime-2026-08-27.2`，合并后为 **39,756 个 ICD-10-CN 诊断代码、28,394 个 ICD-9-CM-3 手术代码**。原目录名称和 DRG 信息优先，补充资产只填补缺项。代码信任锚、清单、大小、SHA-256、记录数、JSON 结构和合并后唯一计数任一不符都会失败关闭。

CCL 聚合覆盖：9,442 次诊断标签分配、960 个唯一诊断码、0 未匹配；2,172 次手术标签分配、48 个唯一手术码、0 未匹配。

## Runtime Matrix 真实性修复

严格 26-Agent bundle 的每个 Agent 只有语义门结果，不证明 optional-provider Agent 当次走本地还是外部模型。因此矩阵采用保守派生：

- 普通、有效的严格 26-Agent bundle 只把 23 个结构上确定为 `local_deterministic_execution` 的 Agent 记为本地语义已验证。
- `code-validation-agent` 的 `local_baseline_with_optional_external_provider` 不从普通 bundle 推断，仍需专用本地证据。
- 只有包含独立验证 24-Agent 本地组件的 composite bundle 才能派生 24/24。
- bundle 无效或被篡改时派生 0；专用本地 bundle 有效时保持 24/24。

该规则关闭了历史矩阵“严格 26/26 但本地 0/24”的分类矛盾，同时不把可能的外部模型调用误标为本地能力。

## 验证

- Runtime Matrix、语义 bundle、目录、Dictionary RAG、编码适配器、Medical Coding A2A、Code Validation、CCL 审计、盲审、临床计划与部署门扩大回归：144 passed、5 skipped。
- 目录增量后的真实 loopback HTTP 本地回归：happy 24/24、adversarial 24/24、reference 24/24、stability 144/144，全部 fresh；矩阵本地 24/24，严格 26-Agent 外部模型门本阶段保持 0/26。证据位于 `reports/agent_hub/local_semantic_e2e_runtime_truth_phase_20260827_v2`。
- CCL 聚合审计：`ready_for_local_isolated_benchmark`。
- 双语盲审 readiness 已按新目录重新生成：`reports/agent_hub/bilingual_coding_review_readiness_20260827_v2`，仍为 `independent_gold_ready=false`。
- 临床校准计划已按新目录重新生成：`reports/agent_hub/clinical_calibration_plan_20260827_v3`，valid=true。
- 静态部署预检：107/107 passed；证据 `reports/deployment/ccl2026_catalog_runtime_truth_phase_20260827_v1/deployment_preflight.json`，文件 SHA-256 `1cfd756e0bbcaf67ca0677417189e30b2033b9f7b15ab429de62a25c05c93d16`。
- 全过程未调用真实 LLM，未使用外网，未读取新 API Key。

## 后续本地评价门

本数据资产现已接入严格的本地隔离预测评价器，详见 [`ICODER_CCL2026_LOCAL_PREDICTION_EVALUATOR_PHASE_SUMMARY_2026-08-27.md`](ICODER_CCL2026_LOCAL_PREDICTION_EVALUATOR_PHASE_SUMMARY_2026-08-27.md)。评价器对 1,800 条预测实施逐例 digest/顺序绑定、当前目录精确成员校验和聚合计分；父子码不会折叠，失败病例不会 fallback 成成功，任何完整性错误均不输出可信指标。1,800/1,800 oracle 自检已经通过，但只证明评价合同，不是模型质量结果。

## 与 Corti 的当前差距

本阶段加强的是 iCoDer 的中国编码本地化、数据来源可追溯和失败关闭，不能替代同病例临床对标：

1. Corti 与 iCoDer 尚未在同一批、合法可处理的病例上用同一评价表盲测。
2. CCL 是训练集单一来源，不是独立 held-out、多医院或双语临床 gold；不能据此给出生产泛化结论。
3. 目录条目齐全不等于编码选择正确；仍需真实模型复跑、独立编码员裁决和医院分布验证。
4. 真实 Docker build/scan、SBOM、镜像签名、目录正式许可、权威版本审批和更新/撤回流程仍是生产门。
5. 26-Agent 的生产 ready 仍为 0/26；Corti 私有工具行为、生产 SLA、医院集成和监管验收仍未复刻。
