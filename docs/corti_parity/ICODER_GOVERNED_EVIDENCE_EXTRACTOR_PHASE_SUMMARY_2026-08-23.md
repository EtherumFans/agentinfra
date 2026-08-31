# iCoDer Evidence Extractor 精确提及定位本地基线阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是诊断、临床证据判定、编码、医保结算、生产或医院上线批准。
>
> 阶段：Governed exact evidence-mention location
>
> 状态：开发门禁通过；临床语义、目录权威性、独立质量和外部上线门禁仍开放

## 阶段结论

本阶段将 Hub 可见 `evidence-extractor` 从通用 LLM 的“证据强度判断”路径收敛为无需模型、无需网络、成本为 0 的 `icoder.governed-evidence-extractor.v1`。统一 Run、A2A、Hub readiness、Trace 与 Pack 现在执行同一套确定性精确提及定位策略。

该基线只处理显式提交的最多 20 个候选 ICD-10-CN 编码。它会屏蔽候选编码声明区，再在病历正文中定位完整代码字面量或固定 SHA-256 本地目录中的精确名称/同义词；每个候选最多返回 5 个字符 span。它只记录文档中明确出现的否定、既往、家族史和疑似上下文；`current_mention` 仅表示未检测到这些显式修饰，绝不表示诊断成立。

历史 `evidence_extractor_expert.py` 的离线 fallback 会按“炎/癌/症/病/瘤”等字面规则生成 diagnosis facts，可能把否定句当成诊断事实。本阶段没有把该历史 fallback 暴露到 Hub，也没有修改其历史调用方；新的上线候选路径与之隔离。

## 能力边界与失败关闭

- 不进行同义医学推理、缩写扩展、间接证据推断或临床支持评分。
- 不判断候选编码是否适用于本次就诊、是否有效、是否可结算，也不推荐、纠错或替换编码。
- 不扫描或生成新编码；`uncoded_findings` 由合同强制为空数组。
- 未提供候选编码返回 `INPUT_REQUIRED`；目录治理或完整性校验不可用返回 `CATALOG_UNAVAILABLE`，不输出目录事实。
- 目录未命中和无精确提及分别显式记录，不能把“未定位精确提及”解释为“临床无证据”。
- 重复输入编码按 `input_index` 保留，不静默去重；所有 `evidence_text` 必须与 `char_span` 指向的输入逐字一致。
- 已知不可信后缀和 canary 边界后的内容不会被反射或当作证据。
- 全部结果 `manual_review_required=true`，禁止自动写回、改码、提交或结算。

## 运行、合同与审计

- Agent：`icoder/evidence-extractor@1.1.0`。
- Provider：`icoder.governed-evidence-extractor.v1`，类型 `rule_engine`，确定性、无工具、无网络、无 LLM。
- 运行模式：`governed_local_exact_mention_extraction`。
- 最终输出合同：`icoder/CodedEvidence/v11`；旧 v1–v10 注册记录保留。
- Pack canonical SHA-256：`cab618db24b513cf9a567368b70454beb8e1293efdb1f0e1d9df8d50245e4374`。
- 目录：`cn.icd10cn.catalog@observed-local-2026-05-19`，37,897 条；术语索引 56,424 条。目录仍是 `source_unverified`、`external_review_required`、`billing_authoritative=false`。
- Trace 只记录目录标识/版本/治理状态和输入编码数、定位提及数、未匹配编码数，不记录病历正文、证据文本、本地路径或凭据。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 新增能力聚焦测试 | 16/16 | 精确 span、声明区遮蔽、代码字面量、上下文、重复输入、未知码、治理失败、canary、Provider、资产和 A2A |
| Registry/Pack/Trace 回归 | 88/88 | Provider 唯一注册、Pack 后端配置、Trace allowlist/边界 |
| 干净扩展回归 | 915 passed | 另有 5 skipped、6 deselected、0 failed；排除独立 Clone 端点套件 |
| 26-Agent 离线双场景 | 52/52 | 26 个示例 + 26 个对抗请求；6 个本地基线成功、20 个模型依赖安全失败关闭、0 个不安全响应 |
| 字段关系对抗回放 | 60/60 | 12 个 Agent、34 条关系 |
| 证据绑定对抗回放 | 24/24 | 6 个 Agent、12 条绑定 |
| 跨 Agent 关系对抗回放 | 16/16 | 6 个 Agent、8 条关系 |
| 部署候选静态预检 | 81/81 | 失败项 0；未运行 Docker/Cloud 外部门禁 |
| 运行矩阵 | 通过 | 26/26 visible/executable/provider-resolvable/launch-candidate；20 个外部 LLM 必需、1 个可选、5 个纯本地、6 个离线本地基线 |

机器证据位于 `reports/agent_hub/governed_evidence_extractor_phase_20260823/`。测试使用空 LLM 凭据、`LLM_PROVIDER=mock`、禁止外部 LLM并禁用原生 MedCodER；没有启动浏览器或 TCP Uvicorn。

扩展集内原有 Clone 端点套件有 4 个独立 404：Hub 可见 `medical-coding-agent`，但 Clone 的 DB 预置 Agent 查找失败。该问题单独复跑仍存在，与 Evidence Extractor 路径无关；本阶段没有修改 Clone 业务，也没有把它隐藏成通过。

## 对 Corti 的邻近能力差距

Corti 当前公开 [Agent Library](https://corti.ai/agents) 没有名为 “Evidence Extractor Agent” 的独立预构建 Agent，不能声称一一对应复刻。邻近对标是 [Medical Coding Agent](https://corti.ai/agents/medical-coding-icd-10-cpt-agent)、[Symphony Medical Coding](https://corti.ai/medical-coding) 以及公开研究中的 span-level evidence attribution；其公开边界包括从完整临床文档提取 supporting evidence、逐码关联文档、模型推理、替代编码和审计链。

| 能力 | iCoDer 当前状态 | 差距判断 |
|---|---|---|
| 输入范围 | 只处理显式提交的候选编码和单段输入文本 | 缺 Corti 邻近能力的全病历、多文档自动证据抽取 |
| span 证据 | 目录术语/代码字面量精确字符区间，候选声明区不算证据 | 审计基础对齐；临床改写、缩写、间接指标和语义相关证据不会被识别 |
| 证据含义 | 只标记显式否定/既往/家族史/疑似；不评估临床支持 | 更保守且诚实；不等价于 Corti 模型驱动 supporting evidence 或 reasoning |
| 编码能力 | 不生成、验证、推荐或排序编码 | 缺 ICD-10-CM/PCS、CPT/HCPCS 赋码、替代候选和规则解释 |
| 中国场景 | 中文目录术语、中文上下文标记、本地不出网、最小 Trace | 已建立可审计基线；缺权威目录许可、真实医院中文金标准和编码员盲评 |
| 质量证明 | 合成负向、篡改、注入、Run/A2A/Hub/Trace 与关系对抗回归 | 没有 Corti 同题对照、真实模型、独立临床 reviewer 或医院验收 |

因此，本阶段关闭的是“Evidence Extractor 无模型不可运行、候选声明可被误当证据、span 和上下文缺少确定性审计”的开发差距。它没有关闭全病历语义抽取、临床支持判断、编码系统覆盖、真实准确率或生产服务差距；静态 `semantic_live_e2e_verified` 和 `production_ready_verified` 仍为 0/26。

## 安全与外部门禁

- 未读取或使用用户曾暴露的 DeepSeek 密钥；该密钥应继续视为已泄露并在供应商控制台注销。
- 未操作 Corti Console，也未启动 Chromium；本机已有浏览器/测试内存崩溃风险。
- 保护数据库 SHA-256 最终仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 最终进程环境中两个 LLM 密钥长度均为 0；8000/18022 监听数为 0；Python/Uvicorn 进程数为 0。
- 未执行真实 LLM、真实 Corti 同题、真实医院数据、HIS/EMR、医保结算、Docker、Cloud、PostgreSQL 多副本或生产容量测试。
- 法务、数据授权、等保/个保/数安、渗透测试、医院验收、云基础设施和生产运维仍是外部上线门禁。

## 下一步

继续收敛上游 `diagnosis-extractor`：优先复用本阶段的精确 span 与显式上下文边界，但必须把词面提及、临床断言、候选编码生成和最终编码决策分层。另将 Clone 端点的预置 Agent 查找 404 作为独立开发问题处理。真实模型与 Corti 同题矩阵只在密钥轮换、预算和进程隔离条件满足后执行。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 新建阶段总结，记录精确提及定位、v11 合同、验证结果与 Corti 邻近能力差距 | Evidence Extractor 本地能力收敛 |
