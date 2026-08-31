# iCoDer Governed Clinical Guidelines 阶段总结

> 声明：本文件记录开发环境证据，不构成指南真实性、临床质量、医疗建议、医院、法律、认证或生产上线批准。  
> 日期：2026-08-24  
> 阶段：Agent Hub `clinical-guidelines` 受治理本地基线  
> 状态：开发候选切片通过；Corti 检索/推理能力与外部门禁开放

## 本轮结果

`clinical-guidelines` 已从外部 DeepSeek 模板升级为 `icoder/clinical-guidelines@1.1.0`、Pack format 1.2、`icoder.governed-clinical-guidelines.v1` 和不可变当前合同 `icoder/ClinicalGuidelinesOutput/v6`。26 个公开 Agent 均可解析；纯本地 Agent 由 19 增至 20，本地确定性或受治理基线由 20 增至 21，外部 LLM 强依赖由 6 降至 5。

本地 Provider 只读取明确标注的临床问题、指南域、标题、版本/日期、医院批准信息、来源 URL、人群、文档范围、指南条款、确定性规则与病例事实。它支持 `PRESENT`、`EQUALS` 和 `TIME_WINDOW_HOURS`，能复算时间差、识别同名字段的多文档冲突，并把来源、规则和病例事实绑定到脱敏后输入的精确字符 span。缺字段、来源元数据不足、字符串域不匹配、人群文本不精确匹配或事实冲突时，分别进入 `INPUT_REQUIRED`、`SOURCE_REVIEW_REQUIRED`、`APPLICABILITY_REVIEW_REQUIRED` 或 `NOT_ASSESSABLE`，不会补写未知临床事实。

固定安全边界是：不联网检索或抓取指南，不把用户填写的批准/来源信息冒充独立真实性验证，不验证是否为最新版本，不做诊断、患者适用性、指南强度或临床意义推理，不生成治疗建议，不自动处罚、发布或写回，并始终要求人工复核。

## 中国场景适配

输入和输出显式保留医院批准状态、批准日期、批准机构、来源机构、院内 URL、中文人群与文档范围；域匹配只是对用户提供 URL 的确定性字符串校验。该切片适合中国医院内部已经完成授权、版本与审批治理后的规则复核草案，但不能把院内元数据替代指南委员会、临床专家、知识产权、法务或合规审核。

## 验证证据

- 聚焦 Provider/投影/合约 75/75；A2A/流式失败关闭 9/9；矩阵、语义包、离线安全和 API 145/145；数值来源审计 23/23；Corti parity 单元域 90/90。
- 字段关系对抗 287/287，覆盖 20 个 Agent、101 条关系；证据绑定对抗 52/52，覆盖 17 个 Agent、26 条绑定。
- 真实 loopback HTTP：happy 21/21、adversarial 21/21、reference 21/21、三轮 stability 126/126，p50 0.223 秒、p95 0.455 秒；签名证据 bundle 验证 21/21。
- 最终串行宽回归：1193 passed、5 skipped、6 deselected、0 failed，耗时 693.12 秒。
- 合同注册：26 个可见合同、130 个注册版本；无新增未登记、漂移、无效或重复引用。字段 schema dry-run 为零变更。
- 静态部署预检 90/90；Corti 目录映射/开发验证/中国 profile 为 20/20，但临床质量与生产就绪均为 0/20。
- 受保护数据库未写入：8,536,064 bytes，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`，最后写入仍为 2026-08-22 17:16:22。本轮无 Python/Uvicorn 残留、无监听、无内存访问冲突。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/clinical_guidelines_phase_20260824_v1/phase_evidence.json) 和 [`最终签名本地语义证据`](../../reports/agent_hub/local_semantic_e2e_clinical_guidelines_phase_20260824_v1/)。

## 与 Corti 的逐项差距

Corti 当前公开的 [Clinical Guidelines Agent](https://corti.ai/agents/clinical-guidelines-agent) 声明会在预配置专业指南域内使用 Web Search 检索并验证来源，综合多份临床文档、识别不一致，将已记录照护与适用指南建议比较，输出 aligned/gap/not applicable、指南可用性、完整 URL/日期/章节引用，并按推荐强度说明临床意义；同时禁止临床推断和治疗建议。其 [Agentic Framework 文档](https://docs.corti.ai/agentic/overview) 将可信连接器、类型化输入输出、可重放 Trace、人工审批和运行时上下文列为框架能力。

| 能力 | 本轮 iCoDer | 与 Corti 的剩余差距 |
|---|---|---|
| 指南域控制 | 接收明确域并做来源 URL 字符串匹配 | 无 Web Search/Web Fetch，不验证专业性、真实性、许可或域所有权 |
| 版本与时效 | 保留用户提供版本、发布日期和批准日期 | 不查最新版本，不证明 currency |
| 多文档综合 | 比较明确 `文档|字段=值`，识别重复字段冲突 | 不从自由文本综合诊断、发现、干预或完整照护路径 |
| 指南比较 | 对声明规则执行 PRESENT/EQUALS/时间窗 | 不选择适用推荐，不做临床适用性推理 |
| 结果分类 | 输出 MET/NOT_MET/NOT_ASSESSABLE 与偏差 | 不权威判断 not applicable、无指南或部分覆盖 |
| 临床意义 | 明确固定为未评估 | 未按 strong/conditional/expert opinion 分级 |
| 引用 | 条款、规则和病例事实精确绑定输入 span | 无外部全文、章节/推荐编号与可验证来源引用 |
| 安全与审计 | 严格合同、失败关闭、Trace/attestation、人工复核、禁止写回 | 未取得独立临床 benchmark、医院验收或生产合规证据 |

因此，本轮关闭的是“已批准院内来源元数据 + 声明规则确定性比较 + 冲突识别 + 精确证据 + 中国医院审批字段 + 失败关闭”的开发环境基线，不证明 Corti 的检索、来源验证、临床文档综合、适用性、临床意义或托管模型等价。严格 26-Agent 真实 Provider 语义验证和生产验证仍为 0/26。

## 运行与密钥边界

全部测试使用临时 SQLite，关闭外部 LLM、原生 MedCodER 和本地 STT；真实 loopback E2E 没有访问外部网络。`ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY` 和 `OPENAI_API_KEY` 在进程、用户和机器级最终长度均为 0。此前曾在对话中明文暴露的 DeepSeek Key 必须在 DeepSeek 控制台注销/轮换，不能继续视为安全凭据。

## 下一阶段

开发环境下一优先级是剩余 5 个外部模型强依赖 Agent：`clinical-documentation-improvement-agent`、`drg-analyzer`、`medical-coding-agent`、`principal-diagnosis-review` 和 `triage`。需要为其生成新鲜、签名、非 mock 的真实 Provider happy/adversarial/reference/stability 证据，并继续保持局部本地证据与严格 26-Agent 门禁隔离。

Clinical Guidelines 若要进一步接近 Corti，还需要合法授权、可版本化且域限制的指南检索连接器，来源真实性/许可/时效验证，多文档自由文本综合、适用性与推荐强度处理、章节级引用，以及独立临床专家盲评。医院数据、EHR/知识库集成、真实云容量、法务、认证和医院上线验收仍是外部门禁。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增受治理 Clinical Guidelines Provider、v6 合同、21-Agent 签名 HTTP E2E、ISO 时间来源审计与 Corti 逐项差距证据 | 将外部模型模板收敛为来源受控、可执行、可审计的开发候选基线 |
