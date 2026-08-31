# CDI 多证据片段整改记录（2026-08-12）

## 结论

`G8-CDI-CONFLICT-034` 暴露的证据拼接问题已在运行时契约层完成整改：Provider Query 现在支持多个相互独立、可逐段核验的 `evidence_spans`；旧字段 `evidence_span` 继续作为首个主片段，保持客户端和历史数据兼容。

这项整改不能被表述为冻结 40 例基准已经达标。冻结候选仍包含原有输出，因此重新计分仍为：

- `evidence_quote_verbatim_rate = 0.975`
- `unsupported_query_rate = 0.025`（40 条中 1 条）

只有生成新的候选结果并经过同一冻结流程后，才能用新证据替换上述历史指标。

## 已完成的工程闭环

- Domain：`ProviderQuery.evidence_spans` 为权威证据集；`all_evidence_spans()` 对旧单片段数据回退并去重。
- 生成契约：提示词要求非连续事实拆分为多个原文片段，禁止拼接为伪连续引用。
- 失败关闭：每个片段独立锚定到病历；任一片段不能核验时，整条 Query 不进入可发送列表，而进入 `NEEDS_EVIDENCE_REWRITE` 队列。
- 单维度门禁：复合查询进入 `NEEDS_CDI_REWRITE` 时保留全部证据片段及审计字段。
- 持久化：`cdi_provider_queries.evidence_spans` 使用 JSON 保存完整片段集合；迁移版本为 `034`。
- 兼容读取：旧记录的 `evidence_spans=[]` 会从 legacy 主片段自动回填，不向 v2 客户端暴露空证据假象。
- API/OpenAPI：`ProviderQuerySchema` 同时返回 `evidence_span` 和 `evidence_spans`，包含字符坐标与 `documented_at`。
- Clinician View：去编码投影保留全部证据片段。
- Agent Hub 契约：CDI Pack 已声明多片段权威语义并重新计算完整性哈希；仍保持 `production_ready=false`。
- 评估口径：一个多证据 Query 只有在所有声明片段均可核验时才计为 supported；旧单片段样本继续兼容。

## 验证结果

| 验证项 | 结果 |
|---|---:|
| 多片段锚定、拼接拦截、单片段幻觉失败关闭 | 5 passed |
| 多片段 + single-dimension 门禁 | 27 passed |
| 数据一致性 + clinician view | 24 passed |
| API 创建、读取、持久化定向闭环 | 3 passed |
| legacy 回填与字段级回归 | 7 passed |
| 评估器新旧契约 | 6 passed |
| 迁移临时库 `034 → 033 → 034` | passed |
| 开发库升级 `033 → 034` | 718 个 CDI 病例保持不变 |
| ORM 列归属 | 仅 `cdi_provider_queries` 有 `evidence_spans` |
| CDI Pack 规范化加载 | executable / launch candidate / 0 blockers |

测试均为低内存、小批量、串行执行；未启用浏览器自动化、BGE、sentence-transformers 或 Torch。

## 仍未完成的差距

- 冻结 CDI 基准仍有 4 项未达标：查询数量一致率、平均绝对查询数量差、明确缺口漏问率、历史无依据查询率。
- 本整改解决的是未来输出的证据表达和失败关闭，不会自动修正查询数量不足或过多。
- 需要在安全模型环境中生成新的只读候选，再执行完整 40 例逐例复核、计分和冻结；当前 Windows 原生环境不启用已知会触发 `0xc0000005` 的模型栈。
- 独立临床质量验证、医院互操作验证、安全隐私合规审查、生产基础设施审批仍是外部门禁。

## 查询门禁审计与数量偏差增量整改

本轮进一步消除了“门禁删除后无审计去向”的行为：必要性、资格、断言证据、语义必要性、单维度、证据锚定和非诱导式门禁所拦截的候选，均进入不可发送的 `query_rewrite_queue`。若一个文档缺口既没有存活 Query，也没有已有审计项，系统会创建 `NEEDS_QUERY_DRAFT` 工作项；该工作项只保留缺口和证据，不伪造临床问题或回答选项。

- NLQ `BLOCK` 候选现进入 `NEEDS_NON_LEADING_REWRITE`，不会继续出现在 `proposed_provider_queries`。
- 病历已明确记载“1型糖尿病”或“2型糖尿病”时，糖尿病分型追问由必要性门禁判定为重复询问并保留审计。
- 后端只向明确授权的 CDI、编码、质控、医保、科主任、管理员或 IT 角色投影审计队列；前端工作台仅向管理员、CDI 专员和审计角色展示，且不提供发送操作。
- A2A 仅输出门禁状态汇总，不泄露被拦截的问题正文。
- 定向后端门禁回归为 `21 passed`；前端 TypeScript 与生产构建通过。

冻结 40 例的原始对标指标没有被重写。补充诊断显示：在 Corti 查询数量本身落入病例预期范围的 20 例切片中，iCoDer 平均绝对差为 `0.30`、差值不超过 1 的一致率为 `1.00`；这只能说明偏差部分来自 Corti 冻结输出超出预期范围，不能替代全量原始指标，也不能证明已经实现 Corti 等价。

2026-08-13 增量：single-dimension gate 留置的复合草稿现可触发一次绑定原 gap 的受约束重写。替代候选需重新经过证据锚定、维度绑定、资格和必要性校验，并继续进入断言证据、语义必要性和 NLQ 门禁；异常或不合格结果保持 fail-closed。详见 `CORTI_ICODER_INCREMENTAL_AUDIT_2026-08-13.md`。
