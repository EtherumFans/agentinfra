# iCoDer Agent Hub 严格真实 Provider E2E 阶段总结（2026-08-25）

## 结论

本阶段已使用一次性 DeepSeek 凭据，在隔离临时数据库和真实 loopback HTTP 上完成当前 26 个 Hub 可见 Agent 的严格合成语义回归：happy、adversarial、reference 各 **26/26**，stability **156/156**（3 轮 × 2 场景 × 26 Agent）。最终 bundle 验证有效，Runtime Matrix 将 `visible_semantic_live_e2e_verified` 提升为 **26**，且没有把任何 Agent 提升为生产就绪。

这证明的是“当前 Pack 自有合成用例在当前实现和本次真实 Provider 配置下，通过了合同、安全、Trace、签名与重复性门禁”，不证明独立临床准确率、Corti 模型/工作流等价、医院验收或可直接临床上线。机器证据也明确记录 `independent_clinical_gold_used=false`、`corti_parity_proven=false`、`hospital_acceptance_proven=false`。

## 权威证据

唯一权威目录为 [`external_semantic_e2e_live_20260825-212957`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/)。此前 `195155`、`203010`、`203438`、`205738`、`211146`、`211741` 批次是失败诊断记录，不能替代最终证据。

- 顶层证据：[`external_semantic_e2e_evidence.json`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/external_semantic_e2e_evidence.json)，SHA-256 `fb43802eb2b45f44f66495f1dbc2fd05bd384e755a5f660d1a8d783f65a5c519`。
- 语义 bundle：[`agent_hub_semantic_evidence_bundle.json`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/bundle/agent_hub_semantic_evidence_bundle.json)，SHA-256 `6248223647de174ba3f908c20c80d5695428106b3fd6eb9f52b152dd0e6a611f`，`valid=true`。
- Runtime Matrix：[`agent_hub_runtime_matrix.json`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/runtime-matrix/agent_hub_runtime_matrix.json)，SHA-256 `9f679044b23f773088a597e74e222e0fc57adae828db48a2d85bdfcd50360b5b`，26 个可见 Agent 全部 executable、provider-resolvable、结构性 launch-candidate-ready，生产就绪仍为 0/26。
- 六个顶层源工件的哈希已独立重算并与顶层证据逐项一致；结果/Trace attestation、当前 Pack/schema、真实 provider/model、fresh HTTP、非 mock、非 degraded 均由 bundle 失败关闭验证。

## 量化结果

| 轴 | 结果 |
|---|---:|
| Happy | 26/26 |
| Adversarial | 26/26 |
| Reference | 26/26 |
| Stability | 156/156 |
| Stability pass / provider completion / contract / safety | 100% / 100% / 100% / 100% |
| Stability P50 / P95 | 0.449 秒 / 4.981 秒 |
| 成本覆盖 | 150/156（96.15%） |
| 已知稳定性成本 | CNY 0.001533 |
| 严格 live-provider 合成语义 | 26/26 |
| 独立临床校准 | 0/50 |
| 生产就绪 | 0/26 |

两个真实模型 Agent 的稳定性细分如下：

- CDI：6/6，P50 24.686 秒，P95 28.067 秒；6 次成本均未知。这是当前明确的可观测性和性能缺口。
- Medical Coding：6/6，P50 3.902 秒，P95 5.599 秒；成本覆盖 6/6，合计 CNY 0.001533。

## 本轮真实调用发现并关闭的问题

初次运行从 25/26 开始；后续每次失败均保留为诊断证据，并修复运行时或门禁本身，而不是放宽临床安全断言。

- 凭据扫描曾因仍在运行的 Uvicorn 占用 SQLite/WAL 而把 I/O 错误误报为泄漏，并掩盖 CDI 根因。Runner 现在先回收进程再扫描，区分“检测到凭据”和“扫描 I/O 失败”，且不再用二次扫描异常覆盖首个失败原因。
- CDI 公共投影补齐并规范化 encounter metadata；合同失败 Trace 改为只记录计数、路径和安全关键字，不记录临床正文。
- CDI 未执行的 query rewrite 分支现在也输出真实的 `not_executed` 审计占位，避免可选分支造成合同漂移。
- CDI Query 过滤掉病历中不存在的剂量、测量值、阈值和时间窗，且发布草案或待人工改写队列任一存在时都强制人工 CDI 操作。
- Medical Coding 删除虚构的安全占位阴性证据，并从输入原句确定性提取“已排除 / 未形成确诊 / 不考虑 / 否认”等否定证据；因此模型随机候选不能让 negated-only 病例漏掉不可编码项。
- CDI `human_review.cdi_specialist_review_required` 的评估器与当前 Pack 声明的嵌套合同对齐，没有新增未声明的结果级字段。

修复后的聚焦回归为 **155 passed、0 failed**；部署静态预检为 **101/101**；PowerShell AST 解析通过。该测试口径只覆盖本轮外部门禁、CDI、Medical Coding 公共投影和相关 E2E/预检，不替代此前全量后端、前端、SDK、迁移或浏览器证据。

## 凭据与数据边界

- Key 只存在于专用可见 PowerShell 进程环境中，不进入命令行或报告；Runner 的 `finally` 已清除 LLM 凭据环境变量。
- 最终报告精确凭据扫描通过；对权威报告额外执行通用长 Key 形态扫描，命中文件为 0。
- 临时 E2E 数据库已迁移并删除，残留 `icoder-agent-external-e2e-*` 临时目录为 0。
- 受保护开发库 [`backend/data/icoder.db`](../../backend/data/icoder.db) 未被本轮迁移或写入：8,536,064 bytes，最后修改 `2026-08-22 17:16:22`，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。

## 对标 Corti 的剩余差距

1. **独立临床质量没有证明。** 当前 26/26 只使用 Pack 自有合成病例；受治理 CDI/Medical Coding 多病例校准仍为 0/50，且尚无独立 CDI reviewer、编码员双盲金标准、置信区间、错误分层和医院 acceptance criteria。
2. **没有 Corti head-to-head。** 尚未用同一批经授权病例、同一输入信息和统一盲评 rubric 比较 Corti 与 iCoDer 的正确性、遗漏、幻觉、query leadingness、延迟和成本。
3. **Medical Coding 广度仍不足。** Corti 公开能力中的 ICD-10-CM、CPT、HCPCS、PCS、modifier/units、ranked alternatives、全球规则体系及持续更新权威库，尚未被 iCoDer 当前以 ICD-10-CN / ICD-9-CM-3 为主的开发目录覆盖。
4. **CDI 工作流仍不等价。** Transcript/事实/草稿到终稿的实时、近实时和批处理触发，多 Expert 外部知识组合、医院级 query policy、医生交互闭环与独立质量审核仍未完成；本次 CDI P95 28.067 秒且成本不可观测。
5. **中国生产适配仍需外部资产。** 权威且获许可的国家/省市/医院 ICD、病案首页、医保、DRG/DIP 规则及更新机制，真实中文病历与语音金标准、医院 HIS/EMR/结算互操作和本地合规审批均未取得。
6. **托管与生产运维仍未证明。** PostgreSQL/多副本队列、KMS/Secret Manager、对象存储、WAF/APM/SIEM、容量/SLA/灾备、法务/许可/认证和真实医院验收仍开放。语音 diarization、词级时间戳、真实中国医疗音频质量和 Corti 同音频比较也不属于本次 Agent Hub 门禁成果。

## 下一阶段

开发环境内的下一优先级是先补齐 CDI 成本遥测与超时/重试预算，再在明确数据授权和人工评审资源后执行 50 次临床校准；之后才能开展同病例 Corti head-to-head。没有独立金标准、医院授权或真实生产基础设施时，应继续维持 `production_ready_verified=0`，不得用本次 26/26 合成门禁替代上线审批。
