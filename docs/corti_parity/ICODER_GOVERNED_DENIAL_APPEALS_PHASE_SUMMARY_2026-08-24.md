# iCoDer Governed Denial Appeals 阶段总结

> 声明：本文件记录开发环境证据，不构成临床、医保、商保、法律、认证或生产上线批准。  
> 日期：2026-08-24  
> 阶段：Agent Hub `denial-appeals` 受治理本地基线  
> 状态：开发候选切片通过；外部能力与生产门禁开放

## 本轮结果

`denial-appeals` 已从 v1.1 外部模型模板升级为 `icoder/denial-appeals@1.1.0`、Pack format 1.2、`icoder.governed-denial-appeals.v1` 和不可变合同 `icoder/DenialAppealOutput/v3`。26 个公开 Agent 均可解析；本地确定性或受治理基线由 18 增至 19，外部 LLM 强依赖由 8 降至 7。

本地 Provider 只读取明确标注的拒付、结算、病历、授权、待遇资格和用户提供政策字段，保留逐字 evidence span，并在用户明确指定路径时生成固定模板的人工复核申诉草案或更正申报清单。缺少关键字段、路径或政策时分别返回 `INPUT_REQUIRED`、`PATH_REVIEW_REQUIRED` 或 `POLICY_REQUIRED`，不会用推断补齐。

以下安全边界固定为真值：不自动分类拒付、不推断根因、不判断临床支持、医疗必要性或待遇资格，不验证 ICD-10/CPT/HCPCS、modifier 或 units，不检索支付政策，不调用外部知识，不提交、不写回，且始终要求人工复核。

## 中国场景适配

输出覆盖结算单/拒付通知、参保人、医疗机构/医师、基本医保/商保类型、统筹区、经办机构、申诉截止日期/层级/渠道、授权、待遇资格、支付政策编号/版本/生效日期/来源，以及申诉与更正申报双路径。脱敏器同步修复支付方通知、金额和拟申诉项目等结构词被误识别为中文姓名的问题，并改为最长短语优先保护；患者、参保编号、医师姓名和执业编号仍被脱敏，二次脱敏保持幂等。

## 验证证据

- 聚焦 Provider/A2A/投影/矩阵/合同：73/73；最终脱敏专项：40/40。
- 离线 Agent Run 与 API：124/124。
- 字段关系对抗：234/234，覆盖 20 个 Agent、89 条关系。
- 证据绑定对抗：48/48，覆盖 15 个 Agent、24 条绑定。
- 最终签名 loopback HTTP：happy 19/19、adversarial 19/19、reference 19/19、三轮 stability 114/114，p95 0.197 秒；证据 bundle 验签 19/19。
- 最终串行宽回归：1167 passed、5 skipped、6 deselected、0 failed，耗时 797.68 秒。
- 合同注册：26 个可见合同、125 个注册版本，无新增未登记、漂移、无效或重复引用。
- 静态部署预检：90/90；Corti 目录映射/开发验证/中国 profile 为 20/20，但临床质量与生产就绪均为 0/20。
- 受保护数据库未写入：8,536,064 bytes，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。测试后无 Python 后端或监听器残留。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/denial_appeals_phase_20260824_v1/phase_evidence.json) 和 [`最终签名本地语义证据`](../../reports/agent_hub/local_semantic_e2e_denial_appeals_phase_20260824_v4/)。

## 与 Corti 的差距

Corti 当前公开的 [Denial Appeals Agent](https://corti.ai/agents/denial-appeals-agent) 描述了拒付原因/受影响明细抽取、拒付分类、申诉或更正申报路径选择、ICD-10-CM 与 CPT/HCPCS/modifier/units 验证、材料缺口识别，以及 payer-ready 草案；还列出 PubMed、Web Search 支付政策/时限和 Medical Coding 专家。其 [Practice Management](https://corti.ai/solutions/practice-management) 与 [Revenue Cycle 文档](https://docs.corti.ai/coding/revenue-cycle) 进一步覆盖工作流和收入周期集成。

iCoDer 本轮只关闭了“明确字段的可追溯抽取 + 用户已记录路径的固定模板草案/清单 + 中国医保字段 + 安全失败关闭”。仍未复刻：自动拒付分类和根因分析、自动路径选择、编码/modifier/units 校验、支付政策和截止日检索、PubMed/Web/Medical Coding 专家、医疗必要性支撑判断、Claim/EOB/ERA 与提交集成、拒付模式/胜诉率/收入挽回分析，以及真实机构成效验证。

本轮浏览器控制客户端因本机资源路径错误未能初始化，因此没有把已登录 Corti 控制台当作证据；对标仅依据上述当前公开官方页面。`production_ready=false`、严格 26-Agent 真实 Provider 语义验证仍为 0/26。

## 运行与密钥边界

全部测试使用临时 SQLite、mock Provider、关闭外部 LLM、原生 MedCodER 和本地 STT；未使用真实 DeepSeek Key。进程、用户和机器级 `ICODER_CREDENTIAL_LLM` 长度最终均为 0。此前曾在对话中明文暴露的 Key 应立即在 DeepSeek 控制台注销/轮换，不能继续视为安全凭据。

## 下一阶段

开发环境下一优先级是 7 个仍依赖外部模型的 Agent 的新鲜真实 Provider 语义证据，并为 Denial Appeals 增加受许可、可版本化的中国医保/商保政策连接器与编码校验链；这些能力必须继续区分“开发合同通过”与“独立临床/支付方验证”。真实医院/支付方互操作、数据治理、法规、认证、容量和生产云验收属于外部门禁。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理 Denial Appeals Provider、v3 合同、签名 E2E、安全脱敏与 Corti 差距证据 | 将最后一个官方 v1.1 Pack 迁移为可执行 v1.2 开发候选 |
