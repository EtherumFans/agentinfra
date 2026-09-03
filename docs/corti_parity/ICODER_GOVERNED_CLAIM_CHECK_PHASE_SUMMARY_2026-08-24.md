# iCoDer Claim Check 受治理本地能力阶段总结（2026-08-24）

> 声明：开发环境阶段证据，不构成临床、编码、医保支付或生产上线批准。
> 日期：2026-08-24
> 阶段：Agent Hub — Governed Claim Check
> 状态：本地开发候选切片通过；真实 Provider、独立质量与生产门禁开放

## 阶段结论

`claim-check` 已从外部模型依赖模板收敛为可运行、可审计、可测试的本地开发上线候选切片：

- Agent：`icoder/claim-check@1.1.0`
- Provider：`icoder.governed-claim-check.v1`
- 输出合同：`icoder/ClaimCheckOutput/v4`
- 执行：确定性规则引擎，无 LLM、网络、外部工具或模型成本
- 能力：把明确标注的结算单、就诊、患者、机构、医师、支付方、拟报编码/项目、金额、临床文书和用户提供的版本化政策整理成 review-only 核查包，并为复制事实绑定脱敏输入中的精确字符 span
- 安全边界：不判断编码支持、医疗必要性、待遇资格、覆盖范围、支付/拒付概率，不分组 DRG/DIP，不提交、不修改、不写回

本阶段证明的是“明确材料装配、缺失门禁、证据定位和审阅边界”的开发能力，不证明完整 Corti 收入周期能力、真实结算审核质量或生产上线。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/claim_check_phase_20260824_v8/phase_evidence.json)，最终本机 HTTP 证据见 [`local_semantic_e2e_claim_check_phase_20260824_v8`](../../reports/agent_hub/local_semantic_e2e_claim_check_phase_20260824_v8/)。

## 本轮实现

### 明确字段核查包

Provider 支持中英文明确标题字段，输入上限 40,000 字符、证据上限 200。输出合同有 29 个必需字段、4 条字段关系和 1 条证据绑定，状态固定为：

- `INPUT_REQUIRED`：结算核查核心字段缺失，不生成核查包；
- `POLICY_REQUIRED`：核心字段存在，但支付政策资料缺失或不完整；
- `READY_FOR_REVIEW`：核心字段及用户提供的版本化政策资料齐备，仍只表示可人工复核。

政策状态区分 `POLICY_NOT_PROVIDED`、`DOCUMENTED_POLICY_INCOMPLETE` 和 `DOCUMENTED_POLICY_ONLY`。无论状态如何，`clinical_support_assessed`、`medical_necessity_assessed`、`benefit_eligibility_determined`、`code_assignment_performed`、`drg_dip_grouping_performed` 和 `external_knowledge_used` 均固定为 `false`；提交、写回固定阻断，人工复核固定要求。

### 中国场景适配

- 支持城镇职工/居民医保、商保等结算类型文本；
- 支持医保经办机构、保险计划、统筹区、参保编号、医疗机构和医师执业编号；
- 支持 ICD-10-CN、ICD-9-CM-3 风格的拟报诊断/手术字面量，但只复制，不校验或重新编码；
- 支持人民币申报金额、拟报费用项目、用户提供的支付政策编号/版本/生效日期/来源；
- 明确保留真实医保政策库、区域目录、DIP/DRG 分组、HIS/EMR/结算平台接口和提交回执为外部门禁。

### 双重脱敏与 Connector 回归修复

完整中文 A2A 用例暴露了两个真实问题：

1. 宽泛中文姓名规则把“申报总金额”中的“申报总”误判为姓名，入口与 Provider handler 的第二次安全脱敏又把剩余“金额”误判，导致证据坐标漂移。
2. 内部 Agent Connector 测试返回静态未脱敏示例，却要求输出证据匹配路由后的脱敏输入。

修复后，“申报总金额/申报金额/申报总额/结算金额”作为结构短语保留；完整 Claim Check 文本第一次脱敏识别 `NAME`、`INSURANCE_NO`、`PROVIDER_ID`，第二次脱敏不再改变文本。Connector 集成测试改为调用正式的 `GovernedClaimCheckProvider`，证据始终从实际路由输入生成，而不是绕过运行时契约。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Provider、投影、脱敏、矩阵、A2A、Connector 定向测试 | 82/82 |
| 全可见 Agent 离线安全、Agent Run、关系/证据单元门禁 | 127/127 |
| 本地真实 HTTP happy / adversarial / reference | 18/18 / 18/18 / 18/18 |
| 三轮稳定性 | 108/108，全部 fresh HTTP，p95 0.227 秒 |
| 字段关系对抗回放 | 216/216（19 Agent、84 条关系） |
| 证据绑定对抗回放 | 46/46（14 Agent、23 条绑定） |
| 最终宽回归 | 1156 passed、5 skipped、6 deselected、0 failed；500.53 秒 |
| 合同兼容 | 26 个可见合同、124 个注册版本，无新增/漂移/非法/重复引用 |
| Corti 20-Agent 开发映射 | 20/20；临床质量 0、生产就绪 0 |
| 静态部署预检 | 90/90；11 项外部限制保留 |

最终矩阵为：26 个用户可见 Agent 全部具备可解析 Provider、严格输出合同和 launch-candidate 结构；17 个纯本地、1 个具有本地基线及可选外部增强，合计 18 个通过带签名 Trace 的本机 HTTP 语义门禁；8 个外部模型 Agent 未做真实 Provider 语义验证；严格 26-Agent live-provider 和 production-ready 验证均仍为 0/26。

所有 pytest 与 HTTP E2E 均使用 C 盘隔离 SQLite，真实 LLM 密钥长度在进程/用户/机器环境均为 0，外部 LLM、原生 MedCodER 和本地 STT 均关闭。本阶段未观察到内存访问冲突。

## 与 Corti 当前公开能力的逐项差距

当前可访问的 Corti 官方资料没有给出一个公开命名为 “Claim Check” 的独立 Agent。因此本阶段对照的是 Corti 官方 [Revenue Cycle](https://docs.corti.ai/coding/revenue-cycle) 能力说明，而不是臆造一项同名产品。该说明把收入周期能力描述为：基于完整临床文档产生支持的编码，再与原始申报进行比较，并在集成层处理工作流；公开材料还强调 per-code supporting evidence、reviewer 验证以及 HCC/DRG 等影响。

| 能力 | iCoDer 本阶段 | 对 Corti 的结论 |
|---|---|---|
| 结算/病历/政策材料装配 | 明确标题下逐字复制，缺失即阻断 | 已形成开发基线 |
| 证据定位 | 脱敏输入精确 span，关系和对抗回放失败关闭 | 已形成开发基线；仅 Pack 自有合成数据 |
| 原始申报对照 | 收集拟报诊断、手术、项目和金额 | 未生成“文档支持编码”，不能完成 Corti 式差异对照 |
| 医学编码预测/赋码 | 固定声明未执行 | 未覆盖 |
| 临床支持判断 | 固定声明未评估 | 未覆盖 |
| HCC、DRG、DIP 影响 | 固定声明未分组/未评估 | 未覆盖 |
| 支付政策与待遇资格 | 只展示用户提供、带版本的条款 | 无权威政策检索、目录匹配、医疗必要性、覆盖或待遇资格判断 |
| 拒付与支付结论 | 只收集已记录拒付原因 | 无拒付预测、支付决定或金额调整 |
| 人工复核 | 所有结果强制 review-only | 合同层覆盖；无真实编码员/医保 reviewer 验收 |
| Claims 集成 | 禁止提交、修改、写回 | 未覆盖理赔/医保接口、回执和状态跟踪 |
| 中国适配 | 统筹区、医保经办机构、ICD-10-CN/ICD-9-CM-3 字面量、人民币金额、DIP/DRG 边界 | 结构字段已适配；真实区域政策、分组器和医院接口未覆盖 |
| 临床/业务质量 | 18-Agent 合成 HTTP、对抗、稳定性和合同验证 | 无同例 Corti 对照、独立金标准、盲评或医院验收 |

因此可以声称“Claim Check 的明确材料收集、版本化政策引用、逐字核查包、精确证据和不提交边界已成为开发候选基线”；不能声称“已完成编码/支付审核”“已复刻 Corti Revenue Cycle”或“已达到生产质量”。

## 数据库恢复审计事件

一次非 pytest 的 TestClient 诊断错误地设置了 `ICODER_DATABASE_URL`；该变量只由 pytest `conftest` 映射，独立应用实际读取 `DATABASE_URL`，因此诊断启动误开了开发库。保护检查发现库从 8,536,064 增至 9,117,696 字节，新增 14 个 seed Agent 和 11 张 `create_all` 表。

处理过程可逆且有证据：

- 异常状态完整备份为 `C:\Temp\icoder-claim-check\accidental-dev-db-after-testclient-20260824-165304.db`，SHA256 为 `d4f274888c803e5de928e3c8059eb1f9e291d54c762b9a6f524fab2989f80825`；
- 使用 2026-08-22 的只读 SQLite 一致性快照恢复；历史 reconciliation 报告证明源库与快照的所有既有表数据指纹一致、无数据保留差异；
- 最终恢复为修订 `041`、59 张表、122 个 Agent、8,536,064 字节，`integrity_check=ok`；
- SQLite 一致性快照会重新布局页面，因此最终 SHA256 是 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`，不是事故前原始文件布局的 `9547e301...`。逻辑状态已恢复，但不能声称原字节级哈希已恢复。

后续所有独立 Uvicorn 均显式设置 `DATABASE_URL` 到 C 盘临时库。阶段结束时没有项目 Python/Uvicorn 进程，8000、8875–8878、18022 均无监听。

## 未关闭门禁与下一阶段

仍必须由外部证据关闭：真实医院数据和接口、合法且版本受控的医保/商保政策资产、编码员与医保 reviewer 独立盲评、真实 Claims/医保结算平台、云 PostgreSQL 多副本、容量/灾备/可用性、法务和数据合规、医疗器械/安全认证、医院工作流验收。

下一开发阶段应优先收敛 `denial-appeals`：复用本阶段的结算事实、已记录拒付原因、版本化政策和证据绑定，先建立“不新增事实、不冒充政策、不自动提交”的本地拒付申诉材料基线；自由叙事生成质量、实时政策检索和真实申诉提交继续保留为外部门禁。

此前在对话中公开过的 DeepSeek API Key 应视为已泄露并立即在供应商控制台注销；本阶段没有使用该密钥。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 建立 Claim Check 本地 Provider、v4 合同、证据/关系门禁、中国结算字段、18-Agent 签名 HTTP E2E；修复金额标签双重脱敏与 Connector 静态证据错位；记录并恢复诊断误写开发库事件 | Agent Hub 全部面向用户 Agent 向可运行、可审计、可测试上线候选持续收敛 |
