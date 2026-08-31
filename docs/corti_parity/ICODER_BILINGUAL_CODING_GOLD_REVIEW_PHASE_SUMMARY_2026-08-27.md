# iCoDer 双语编码独立 Gold 复核工作流阶段总结（2026-08-27）

## 阶段结论

本阶段已完成所有可在开发环境独立实现的 reviewer 基础设施：当前 5 个中英双语 Medical Coding 病例可以生成真正盲化的复核包，由两名不同 reviewer 独立提交逐码决定；代码必须属于固定哈希的 ICD-10-CN / ICD-9-CM-3 目录，每个代码必须分别绑定中英文病历中的逐字 evidence。两份提交自动比较，任何分歧都进入第三名独立 adjudicator；最终 gold 还必须绑定 reviewer/adjudicator 身份、资质、签字、机构和利益冲突的外部核验证据。

当前状态是 **ready for external review，not independent gold ready**。本阶段没有伪造 reviewer、没有替工程标签签字，也没有把测试中的虚拟身份当作真实临床证据。外部 reviewer 尚未提交，因此 `independent_gold_ready=false`，临床准确率、Corti 等价和生产就绪继续为 false。

## 审计发现

修复前：

- `held_out_bilingual_v1.json` 同时包含病历和工程团队维护的 `expected_*`、notes、evidence；评分器直接读取这些字段。
- 5-case fixture 明确是 synthetic、engineering-team-authored，不是独立 gold。
- `HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md` 仍写“双语 runner 未实现”，但真实 50 次临床校准 runner 已经支持 5×2 双语调用，文档与代码漂移。
- HOBV1-001 的 `S22.000` 父码与目录检索给出的 `S22.000x003` 子码存在待裁决分歧，工程团队不能为了指标自行改写 gold。

## 实现

### 盲化 packet

`backend/scripts/corti_parity/bilingual_coding_gold_review.py` 生成 `icoder.bilingual-coding-blind-review-packet/v1`：

- 只包含 case ID、科室、中文病历、英文病历和待完成的编码任务。
- 明确移除 `expected_principal_diagnosis`、`expected_secondary_diagnoses`、`expected_primary_procedure`、旧 evidence、notes 和全部模型输出。
- 每例和整个 packet 都使用 canonical SHA-256；packet 同时绑定源 fixture 摘要和当前代码目录发布快照。

### 双 reviewer 与分歧仲裁

- `icoder.bilingual-coding-independent-review/v1` 要求不同 reviewer ID、允许的专业角色、资质引用、机构、独立性/盲化/未查看模型输出/无利益冲突声明、带时区签署时间和签名引用。
- 主诊断必填，secondary 可为空，primary procedure 可为 null；所有非空代码必须是当前目录精确成员。
- 每个代码的中文与英文 evidence 必须分别是对应病历的精确子串。
- 两份完整响应逐例比较 principal、secondary set 和 procedure；相同 reviewer 不能满足独立性。
- 任一不一致产生 `requires_adjudication=true`；最终 `icoder.bilingual-coding-gold-adjudication/v1` 要求第三名、与两 reviewer 不同的合格 adjudicator，并绑定两份 response digest。
- 即使两个 reviewer 完全一致，在外部身份/资质/签字/冲突核验完成前仍保持 `independent_gold_ready=false`。

### 真实校准前置门

`run_agent_hub_clinical_calibration_e2e.py` 新增四件套输入：blind packet、review A、review B、gold adjudication。四件必须同时存在且全部通过治理校验，才会在任何登录或模型调用前把工程 expected 标签替换为最终 adjudicated decisions。输入被复制进本次报告目录并重新校验路径、SHA-256 和内容；缺件、目录外代码、非精确 evidence、同一 reviewer、未仲裁分歧、未完成身份核验或摘要漂移都会在外发前失败关闭。

默认不提供四件套时，runner 保持原有工程合成校准模式和 `independent_gold_used=false`，不会悄悄提升证据等级。严格 26-Agent PowerShell wrapper 已支持同一四件套透传；顶层 evidence 只在临床报告同时声明 reviewed quality scope 和有效 gold snapshot 时接受 `independent_gold_used=true`，且仍强制 `production_ready_proven=false`。

## 生成证据

Reviewer readiness 目录：`reports/agent_hub/bilingual_coding_review_readiness_20260827_v1`

- `blind_review_packet.json`：文件 SHA-256 `6d5a9642a83982011a7654d156141a3f1f26a73aac2109bd49c47316a9cb3593`；canonical packet digest `7fc55eeb0ae6323b0a1262744915717c478ebb859636a5b9e082ae04e587c5a1`。
- `reviewer_a_response_template.json`：`816d7cc55fb99265dbbc02883f28d1d553dbd7a59aefc764557f1c5e1c996a8e`。
- `reviewer_b_response_template.json`：`1ed47798279f6c68ba92205e45c937e41129cfa9c25e64ae344240a593a480c3`。
- `adjudication_template.json`：`66a0303249538847d3f2d998668f0eb53b08c3eb7dd14903b2367e8e275faba9`。
- `review_readiness_report.json`：文件 SHA-256 `3d9250dd021ee8e3810f7631eeef470dbc22b4f0d15811135518dfc7c43b1f3d`；内部 report digest `e8edf37beb9b94aca0f6086d103370184c35c52ee76027aeaa4dc6b31c88a96a`。

更新后的临床校准计划：`reports/agent_hub/clinical_calibration_plan_20260827_v2/agent_hub_clinical_calibration_plan.json`，valid=true，文件 SHA-256 `a6afc15e2a06d4cf0215c5c7b0472d55f5b88f9870c136dbb98bc0fc948fdf5b`，内部 plan digest `03f7d2f108aaf89a1c60dd43174a3c2bedb505a5d7c9b6868abafcbbb0a15e2b`。

## 验证

- 盲化、篡改、pending template、目录成员、双语 evidence、双 reviewer、同人拒绝、分歧仲裁、外部身份核验、最终 adjudication、真实 runner 标签替换和顶层 artifact claim：聚焦新增 26 passed。
- 与目录资产、dictionary RAG、DeepSeek adapter、G001 runtime、Medical Coding A2A、公共投影、CDI、临床校准组合扩大回归：133 passed、5 skipped。
- PowerShell 5.1 语法解析：PASS。
- 部署静态预检：106/106 passed。
- 预检报告：`reports/deployment/bilingual_coding_gold_review_phase_20260827_v1/deployment_preflight.json`。
- 预检 SHA-256：`413336673f6b0e4359775062193be56b750b87cbd197a9a4ea22ac8d32ba5462`。
- 受保护数据库仍为 size 8,536,064、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- 本阶段未调用真实 LLM，未使用 API Key，未启动后端。

## 仍开放的外部门

1. 两名与 iCoDer 工程团队独立、资质可核验的中文临床编码 reviewer 完成两份盲化模板。
2. 对所有分歧（特别是 HOBV1-001 的父/子码）由第三名独立合格 adjudicator 裁决。
3. 临床治理 owner 外部核验三人的身份、资质、签字、机构关系与利益冲突，并批准最终 adjudication。
4. 扩展到至少 100 个合法、双语、覆盖医院分布的病例；5 个 synthetic case 即便复核完成也不能支持生产准确率或 Corti 等价声明。
5. reviewer 完成后使用新临时 Key 重跑 50 次真实校准，再进行相同病例的 Corti head-to-head；真实医院、法务、许可、云、认证和医院验收仍不由本机测试替代。
