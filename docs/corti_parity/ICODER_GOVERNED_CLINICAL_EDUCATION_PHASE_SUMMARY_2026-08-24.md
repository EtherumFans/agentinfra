# iCoDer Governed Clinical Education 阶段总结

> 声明：本文件记录开发环境证据，不构成临床教育质量、医疗建议、医院、法律、认证或生产上线批准。  
> 日期：2026-08-24  
> 阶段：Agent Hub `clinical-education` 受治理本地基线  
> 状态：开发候选切片通过；外部能力与生产门禁开放

## 本轮结果

`clinical-education` 已从外部模型模板升级为 `icoder/clinical-education@1.1.0`、Pack format 1.2、`icoder.governed-clinical-education.v1` 和不可变当前合同 `icoder/ClinicalEducationOutput/v6`。26 个公开 Agent 均可解析；纯本地 Agent 由 18 增至 19，本地确定性或受治理基线由 19 增至 20，外部 LLM 强依赖由 7 降至 6。

本地 Provider 只读取用户明确标注的主题、受众和医院批准来源元数据与正文，按来源原句装配学习目标、要点和开放式复习题，并为每项内容保留精确 evidence span。缺少主题/受众/来源、来源未明确批准或元数据不足时分别返回 `INPUT_REQUIRED` 或 `SOURCE_REVIEW_REQUIRED`，不会从模型记忆、互联网或隐含医学知识补齐。

以下边界固定为真值：不做问题分类、诊断/机制/鉴别诊断/治疗推理、药物相互作用判断、PubMed/Web/Medical Calculator 调用、来源检索或真实性验证、学习者水平自适应、Board-style 题库生成或患者个体化建议；不自动发布或写回，并始终要求人工复核。

## 中国场景适配

输入要求显式记录来源机构、版本或发布日期、批准状态/日期/机构、院内 URL 或文档编号和适用范围；中文批准状态只接受精确的“已批准”，避免把“待批准”等文字误当成有效授权。输出保留院内来源、中文受众与适用范围，可作为中国医院内部、来源受控的教学材料草案，但不能代替医院教学委员会、临床专家或法律/合规审批。

脱敏器同步修复“应立即”被宽泛中文姓氏规则误识别为姓名的问题；真实人员与其他受保护标识仍保持脱敏。

## 验证证据

- 聚焦 Provider/投影 41/41；脱敏/A2A/原生流 35/35；矩阵/语义 bundle 21/21；API 定向 11/11；陈旧基线回归 5/5。
- 字段关系对抗 262/262，覆盖 20 个 Agent、95 条关系；证据绑定对抗 50/50，覆盖 16 个 Agent、25 条绑定。
- 真实 loopback HTTP：happy 20/20、adversarial 20/20、reference 20/20、三轮 stability 120/120，p50 0.213 秒、p95 0.320 秒；签名证据 bundle 验签 20/20。
- 最终串行宽回归：1176 passed、5 skipped、6 deselected、0 failed，耗时 668.05 秒。
- 合同注册：26 个可见合同、128 个注册版本；无新增未登记、漂移、无效或重复引用。
- 静态部署预检 90/90；Corti 目录映射/开发验证/中国 profile 为 20/20，但临床质量与生产就绪均为 0/20。
- 受保护数据库未写入：8,536,064 bytes，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。本轮无 Uvicorn 残留，也未观察到内存访问冲突；机器上另有用户任务 Python 进程，未终止或修改。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/clinical_education_phase_20260824_v1/phase_evidence.json) 和 [`最终签名本地语义证据`](../../reports/agent_hub/local_semantic_e2e_clinical_education_phase_20260824_v1/)。

## 与 Corti 的差距

Corti 当前公开的 [Clinical Education Agent](https://corti.ai/agents/clinical-education-agent) 面向学生和早期培训者，描述了问题分类、Quick/Tutor/Board-style 模式、诊断与机制/鉴别诊断/药物相互作用/临床推理，以及 PubMed、Web Search 和 Medical Calculator 路由，并声明会验证来源、适配学习者水平且不提供患者个体化建议。其 [Clinical Guidelines Agent](https://corti.ai/agents/clinical-guidelines-agent)、[Agents 目录](https://corti.ai/agents) 与 [Agentic Framework](https://corti.ai/agentic-framework) 提供邻近的指南与工具编排对照。

iCoDer 本轮只关闭了“医院批准来源约束 + 原句证据绑定 + 固定教学材料模板 + 中文院内来源字段 + 失败关闭”。仍未复刻上述问题分类、三种自适应教学模式、生成式临床教学推理、药物相互作用、外部来源检索/验证、工具路由、个性化学习层级、Board-style 评测、学习管理系统闭环或真实培训成效验证。

本阶段没有把已登录 Corti 控制台作为证据；对标仅依据当前公开官方页面。`production_ready=false`，严格 26-Agent 真实 Provider 语义验证仍为 0/26。

## 运行与密钥边界

全部测试使用临时 SQLite，关闭外部 LLM、原生 MedCodER 和本地 STT；未使用真实 DeepSeek Key，也未访问外部网络。进程、用户和机器级 `ICODER_CREDENTIAL_LLM` 长度最终均为 0。此前曾在对话中明文暴露的 Key 应立即在 DeepSeek 控制台注销/轮换，不能继续视为安全凭据。

## 下一阶段

开发环境下一优先级是剩余 6 个外部模型强依赖 Agent 的新鲜、签名、非 mock 真实 Provider happy/adversarial/reference/stability 证据，同时继续保持本地受治理基线与严格 26-Agent 质量门禁分离。Clinical Education 若要进一步接近 Corti，还需要合法授权、可版本化的 PubMed/指南/药物/计算器连接器，教学模式与学习者适配，以及独立临床教育专家盲评；医院数据、真实系统集成、法规、认证、容量和生产云验收仍属于外部门禁。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理 Clinical Education Provider、v6 合同、20-Agent 签名 E2E、安全脱敏与 Corti 差距证据 | 将外部模型模板收敛为来源受控、可执行、可审计的开发候选基线 |
