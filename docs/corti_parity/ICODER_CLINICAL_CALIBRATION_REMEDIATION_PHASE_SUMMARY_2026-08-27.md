# iCoDer 临床校准修复阶段总结（2026-08-27）

## 阶段结论

本阶段完成了一次隔离环境、真实 DeepSeek、串行 50 次临床校准，并据此修复了 CDI 公开契约污染和 Medical Coding 目录外编码发布两个真实缺陷。

当前结论仍是：**Agent Hub 工程主链路可继续作为上线候选推进，但临床校准门尚未通过，不能据此宣称已达到 Corti 临床质量或可直接生产上线。** 修复后尚需使用新临时 Key 重跑同一 50 次门，并需要独立编码专家确认双语 gold set。

目录打包阻断项随后已在 [`ICODER_CN_CODE_CATALOG_ASSET_PHASE_SUMMARY_2026-08-27.md`](ICODER_CN_CODE_CATALOG_ASSET_PHASE_SUMMARY_2026-08-27.md) 中完成开发环境整改：33,304 个诊断代码与 23,165 个术式映射已内置到后端构建上下文，并以代码信任锚、清单、SHA-256、大小和计数失败关闭；组合回归 115 passed、5 skipped，静态预检 105/105。正式再分发许可、真实 Docker build/scan 和修复后真实 50 次校准仍是开放门。

其后的 CCL 本地数据与目录覆盖增量把运行目录提升为 39,756 个诊断代码、28,394 个手术代码，并以获授权 `train.xlsx` 的 1,800 条记录逐条绑定仓内 fixture；9,442 次诊断标签与 2,172 次手术标签均为 0 目录未匹配。该结果只使本地隔离 benchmark 技术就绪，仍不允许 CCL 病例外发，也不把 CCL 训练标签升级为独立临床 gold。详见 [`ICODER_CCL2026_LOCAL_DATASET_AND_RUNTIME_CATALOG_PHASE_SUMMARY_2026-08-27.md`](ICODER_CCL2026_LOCAL_DATASET_AND_RUNTIME_CATALOG_PHASE_SUMMARY_2026-08-27.md)。

独立 gold reviewer 工程链随后已在 [`ICODER_BILINGUAL_CODING_GOLD_REVIEW_PHASE_SUMMARY_2026-08-27.md`](ICODER_BILINGUAL_CODING_GOLD_REVIEW_PHASE_SUMMARY_2026-08-27.md) 中就绪：5-case 盲化 packet 完全移除工程 expected/notes/evidence/模型输出，两位不同 reviewer 的目录成员与中英文精确 evidence 被独立校验，分歧强制第三方仲裁，身份/资质/签字/冲突必须外部核验；真实校准 runner 与严格 wrapper 已可选择性使用通过校验的最终 adjudication。当前没有外部提交，因此 `independent_gold_ready=false`。扩大组合回归 133 passed、5 skipped，静态预检 106/106。

## 真实运行证据

- 证据目录：`reports/agent_hub/clinical_calibration_live_20260827-111843`
- 主报告：`agent_hub_clinical_calibration_e2e.json`
- 文件 SHA-256：`2bcaf5dfe9239a531350f942584b8fb66fed07fd7496bd3ba81a9ceced6b2ca3`
- 报告内部摘要：`41b9d93f96228f27ee2af0d8cfe7c58e1aee60b4b71be31be130d0aeba45a28d`
- 执行来源：50/50 fresh HTTP，0 resumed，0 seeded，0 unknown
- 结果：42 `capability_passed`，8 `safe_fail_closed`
- 最终门：`invalid_or_incomplete_evidence`

该运行使用 `C:\Temp` 下的随机隔离 SQLite 和随机 loopback 端口。结束后隔离后端与 runner 均停止，临时目录数量为 0。受保护数据库 `backend/data/icoder.db` 保持：

- size：8,536,064 bytes
- mtime：2026-08-22 17:16:22
- SHA-256：`2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`

临时 Key 仅存在于可见 PowerShell 子进程环境中，脚本结束时已清除变量；Key 未进入 Codex 进程或命令行。用户仍须在 DeepSeek 控制台撤销该临时 Key。

## 运行结果与根因

### CDI（40 次）

- query count expected-range：82.5%
- complete-chart over-query：0%
- clear-gap under-query：40%
- single-dimension：100%
- evidence exact anchor：99.375%
- non-leading gate：100%
- human-review enforcement：80%

8 次 `safe_fail_closed` 均为真实模型调用完成后公开契约校验失败，不是模型未调用。失败路径统一为 `trace_refs.gate_results` 的 `additionalProperties`：内部脱敏遥测键 `encounter_synthesis::ungrounded_removed` 或 `specialist_trace_emit::quantity_redacted` 被放进严格公共 Pack。

修复：公共 `gate_results` 只投影 Pack 已声明字段；内部隐私计数仍保留在内部 `stage_run_ids`/trace，不再污染公开结果或阻止签名。

### Medical Coding（10 次）

原始校准指标：

- principal exact match：20%
- secondary set F1：66%
- primary procedure exact match：50%
- assigned-code evidence exact anchor：100%
- cross-language exact code-set consistency：0%
- human-review enforcement：100%

10 次输出中发现 13 个目录外缩写或幽灵码，包括 `M80.08`、`81.05`、`J18.1`、`E11.10`、`99.29/99.290`、`I21.1`、`I50.0`、`36.06`。旧链路只验证格式与证据，未把完整中国目录成员资格作为发布边界。

修复：

- DeepSeek 输出先按完整 ICD-10-CN / ICD-9-CM-3 目录精确校验并规范为目录原始大小写。
- 目录外编码被撤下，追加 `CATALOG_CODE_WITHHELD` 高优先级问题并强制人工复核。
- 提示词禁止缩写、补位和仅凭共现推断组合编码；删除“骨质疏松 + 椎体骨折 + 高龄即可推断 M80”的错误示例。
- 中英文等价短语、空格差异、手术术式统一映射到同一中文目录检索词。
- 对字典搜索的 partial-ratio 结果加入全名称相似度重排，避免短父类名称挤掉明确子类。

修复后，本地只读候选覆盖为 26/28（92.86%）。仅剩两处缺失均是 fixture 要求父码 `S22.000`，而病历明确“胸椎压缩性骨折”且目录返回更具体子码 `S22.000x003`；该差异需要独立编码专家决定 gold 是否应接受父子层级等价，不能由工程侧为通过指标自行改写。

## 验证

- CDI handler、dictionary RAG、DeepSeek adapter：43 passed
- coding runtime、Medical Coding A2A、公共投影、校准评估：86 passed，5 skipped
- 本阶段合计：129 passed，5 skipped
- 部署静态预检：104/104 passed
- 预检证据：`reports/deployment/clinical_calibration_phase_20260827_v3/deployment_preflight.json`
- 预检 SHA-256：`563e2f271adcf1df8f9fe3b39be597dde128258bc2389a8630518e022c8da0fe`

预检仍不包含 Docker 构建、镜像扫描、真实云区域、容量/SLA、生产告警或真实 ASR 质量。

## 与 Corti 的阶段差距

本阶段改善的是可验证的安全与工程事实，不等同于临床质量对标完成：

1. 修复后尚未重新执行真实 50 次，新的 CDI 合同成功率和编码 exact/F1/双语一致性没有真实模型证据。
2. 当前双语集合只有 5 个合成病例、10 次调用，且 gold 由工程团队维护，不是独立编码员盲评。
3. 尚无同病例、同输入、同评价表的 Corti 输出，因此不能给出可信的 Corti 相对临床效果结论。
4. 完整编码目录现已从本轮获授权的 `E:\iCoDerA\data` 原字节内置到后端构建上下文，仓外依赖与极小 fallback 已移除；但正式再分发许可、权威版本审批、更新/撤回机制和真实容器构建扫描仍是生产阻断项。
5. 26-Agent 严格真实模型回归已有全通过证据，但它证明的是 Agent Pack/runtime/安全契约，不证明每个专科 Agent 已完成外部临床效度验证。

## 下一阶段门

1. 目录资产开发环境内置和失败关闭已完成；下一步在受控构建机实际 build/scan 镜像，并补齐正式再分发许可、权威版本审批和更新/撤回机制。
2. 双 reviewer、分歧仲裁和外部身份核验工作流已就绪；现在由至少两名独立编码专家完成当前 5 个盲化病例并由第三方裁决分歧，随后扩展到治理文件目标的 100 个双语病例。
3. 使用新临时 DeepSeek Key 重跑修复后的严格 50 次；要求 50/50 fresh、结果签名与 trace 签名有效、无目录外编码、CDI 40 次无合同失败。
4. 在相同病例和评价表下采集 Corti 输出，分别报告结构能力、证据锚定、安全拒答、编码准确性与双语一致性，禁止把静态功能映射当作临床质量等价。
