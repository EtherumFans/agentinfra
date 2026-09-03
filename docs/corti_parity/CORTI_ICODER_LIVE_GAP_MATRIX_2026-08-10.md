# Corti × iCoDer 实时能力差距矩阵

> 审核快照：2026-08-09 至 2026-08-10（Asia/Shanghai）  
> 结论口径：登录后 Corti Console 直接观察 + Corti 官方文档 + iCoDer 仓库与测试实证  
> 本报告是当前状态快照；历史审计文件保留，不以旧结论覆盖新证据。

## 1. 执行结论

- Corti Console 的 20 个 Pre-built Agents 已全部在 iCoDer Agent Hub 中找到对应的用户可见 Agent，目录覆盖率为 **20/20**。
- iCoDer 另有 6 个面向中国编码/医保场景的用户可见 Agent：结算合规核查、出院小结结构化、DRG/DIP 风险复核、证据排序、证据提取、主诊断复核。
- 仓库共有 **32** 个 Agent Pack：**27 executable、5 metadata-only、0 invalid**。其中 **26 个用户可见 Agent 全部通过开发环境发布候选门禁**；另 1 个可执行 Pack 是隐藏的内部 MedCodER 引擎。5 个 metadata-only 均不在 Hub：2 个是已废弃迁移别名，3 个是隐藏的 MedCodER 内部阶段骨架，不能据此声称为用户能力。
- **production_ready = 0**。这不是测试失败，而是明确保留真实医院验证、安全合规、生产基础设施、临床治理和独立评审等外部门禁。
- 当前达到的是“开发环境工程发布候选 + Corti Agent 目录覆盖”，不是 Corti 整体产品的生产等价。主要差距仍在生产级 Experts/MCP 生态、语音产品深度、自动语义记忆、全球编码体系、计费、云运维、认证和真实医院验证。

## 2. 证据与口径

### 2.1 Corti 直接观察

在登录后的 Corti Console 项目中直接观察到：

- AI Studio：Agents、Speech to Text（Dictation、Ambient、Pre-recorded）、Text Generation、Embedded Assistant、Fact Extraction、Medical Coding。
- 管理面：API Clients、Team、Billing、Usage、Customers、Templates、Settings。
- Agent 创建流：Start from scratch、Use a template、Customize agent、Add context、Suggested prompts。
- Medical Coding：编码体系选择、Predict codes、Config、样例、Event Inspector，以及 JavaScript SDK、.NET SDK、JSON Config 示例。
- Pre-built Agents 共 20 个，详见第 3 节。

未执行 Corti 的预测请求，因为该操作会消耗项目 credits；本轮没有在未经确认的情况下产生该费用。

### 2.2 Corti 官方资料

- [Agentic Experts](https://docs.corti.ai/agentic/experts)：公开 Expert registry、MCP 扩展，并在本次快照时注明 A2A/direct expert endpoints 仍为后续能力。
- [Agentic overview](https://docs.corti.ai/agentic/overview)：受控动作、人工批准、审计、可回放 trace、结构化日志、上下文与 FHIR。
- [Context and memory](https://docs.corti.ai/agentic/context-memory)：服务端 `contextId`、消息、任务、工件与自动语义记忆。
- [Create an agent](https://docs.corti.ai/agentic/agents/create-agent)：`agentType`、`systemPrompt`、Experts 与 MCP servers。
- [Predict codes](https://docs.corti.ai/api-reference/codes/predict-codes)：15 个全球编码体系，以及 codes、candidates、evidence、alternatives、usage 返回结构。
- [Transcribe](https://docs.corti.ai/api-reference/transcribe)：实时 WSS dictation、ambient streams 与 prerecorded transcripts。
- [Safety](https://www.corti.ai/safety)：静态/传输加密、客户密钥、RBAC、审计、地域冗余与故障转移。
- [ISO audits announcement](https://www.corti.ai/stories/corti-completes-iso-audits-with-zero-nonconformities)：Corti 公布的 ISO、SOC 2、BSI C5、HIPAA/GDPR 等外部保障信息。

### 2.3 iCoDer 实证等级

- **已验证**：仓库中存在可执行实现，且本轮自动化测试通过。
- **部分**：存在接口/页面/本地实现，但产品深度、数据覆盖或生产实证不足。
- **外部门禁**：无法仅靠开发机合法、可信地完成，需要医院、云、法务、认证机构、支付渠道或独立 reviewer。
- **未实现/不等价**：只有占位、模拟、局部兼容或缺少关键生产路径。

## 3. Corti 20 个 Pre-built Agents 对照

| Corti Console 名称 | iCoDer 对应 Agent | 当前状态 | 等价性判断 |
|---|---|---:|---|
| ICD-10 Index Navigator | `icoder/icd10-navigator@1.0.0` | 发布候选 | 目录覆盖；中国 ICD 本地化更强，全球体系较弱 |
| Rule Explainer | `icoder/rule-explainer@1.1.0` | 发布候选 | 有真实 LLM-with-tools 路径与必选 grounding tools |
| Compliance Guardrail | `icoder/compliance-guardrail-agent@1.0.0` | 发布候选 | 规则引擎、失败关闭、审计路径已验证 |
| Code Validation | `icoder/code-validation-agent@2.0.0` | 发布候选 | 有真实工具调用与 trace；仍缺独立临床基准 |
| Procedure Entity Extractor | `icoder/procedure-extractor@1.0.0` | 发布候选 | 输入证据驱动；产品深度待真实数据验证 |
| Diagnostic Entity Extractor | `icoder/diagnosis-extractor@1.1.0` | 发布候选 | 有 LLM-with-tools；待真实病历基准 |
| Surgical Registry Intelligence | `icoder/surgical-registry@1.0.0` | 发布候选 | 只读结构化候选；无真实登记平台集成 |
| ICU Admission Summary | `icoder/icu-summary@1.0.0` | 发布候选 | 只读摘要；无真实 ICU 系统验证 |
| Triage and Initial Assessment | `icoder/triage@1.0.0` | 发布候选 | 有边界与人工复核；不得作为独立分诊决策器 |
| Note Completeness | `icoder/note-completeness-agent@1.0.0` | 发布候选 | Pure LLM + 本地 fallback；已移除虚假 MCP 声明 |
| Medication Reconciliation | `icoder/med-reconciliation@1.0.0` | 发布候选 | 只读差异识别；无处方/药库生产集成 |
| Denial Appeals | `icoder/denial-appeals@1.1.0` | 发布候选 | 明确字段与用户提供政策驱动的 review-only 草案；不自动分类、提交或写回 |
| Patient Discharge Education | `icoder/discharge-edu@1.0.0` | 发布候选 | 中国场景与人工复核约束；无院内发布闭环 |
| Nursing Shift Handoff | `icoder/nursing-handoff@1.0.0` | 发布候选 | 结构化交班草案；无护理系统验证 |
| Prior Authorization | `icoder/prior-auth@1.0.0` | 发布候选 | 只读材料准备；无支付方实时接口 |
| Referral Generator | `icoder/referral-gen@1.0.0` | 发布候选 | 转诊草案；无区域转诊平台写入 |
| Clinical Education | `icoder/clinical-education@1.1.0` | 发布候选 | 医院批准来源原句装配与证据 span；不做生成式临床推理或外部检索 |
| Medical Coding | `icoder/medical-coding-agent@2.0.0` | 发布候选 | 中国编码体系优势；全球体系与独立准确率仍有差距 |
| Clinical Guidelines | `icoder/clinical-guidelines@1.0.0` | 发布候选 | 本轮新增；指南锁定、逐条证据与人工复核 |
| Clinical Documentation Improvement (CDI) | `icoder/clinical-documentation-improvement-agent@1.0.0` | 发布候选 | 有可执行编排；仍需医院 CDI 团队验证 |

“发布候选”表示开发环境可执行、可审计、可测试且边界明确，不表示已获生产、临床或合规批准。

## 4. 产品能力差距矩阵

| 能力面 | Corti 当前证据 | iCoDer 当前证据 | 判断 |
|---|---|---|---|
| Pre-built Agent 目录 | Console 20 个 | 20/20 对应，另有 6 个中国场景 Agent | **目录覆盖达成，能力深度部分等价** |
| Agent 创建与模板 | 从零、模板、上下文、建议提示 | 页面、模板、Preset、克隆与配置接口 | **部分等价**；Corti 创建体验更成熟 |
| Experts / MCP 生态 | 官方 registry：memory、coding、calculator、DrugBank、POSOS、PubMed、trials、web search、interviewing；支持自定义 MCP | 本地 Expert/Tool registry、MCP 兼容层、部分真实工具 | **Corti 优势**；iCoDer 生产数据源与第三方生态不足 |
| A2A | 本次官方文档注明 endpoints 后续提供 | 已有 Agent Card、message/send、任务状态与 trace | **iCoDer 当前接口优势**，但尚无跨机构生产互操作实证 |
| Context / Memory | 首轮服务端生成 `contextId`，续轮复用；严格隔离；TextPart/DataPart 自动索引并语义检索 | 已实现持久化多轮 Context、租户/Agent/active 校验、GET history、原子写入脱敏消息、PHI 加密、删除 scrub，以及 6,000 字符预算的中文 bigram 相关性注入 | **部分等价**；多轮与隔离主线已对齐，危险 Windows embedding 失败关闭后仍是词法回退，尚未达到 Corti 自动语义索引深度 |
| Audit / Trace | 官方声明可回放 traces 与结构化日志 | 可见 Run Trace、阶段事件、后端元数据、签名/租户审计 | **双方有能力，深度未完全同口径验证** |
| 医疗编码体系 | 官方 API 列出 15 个国际/国家体系 | 本地加载 33,304 条 ICD-10-CN 与 23,165 条 ICD-9-CM-3，并覆盖 DRG/DIP 场景 | **各有优势**：Corti 全球覆盖强；iCoDer 中国编码本地化强 |
| 编码结果结构 | codes、candidates、evidence、alternatives、usage | 代码候选、证据、trace、使用量/成本字段 | **结构部分等价**；仍缺同数据集准确率对照 |
| Speech to Text | 实时 Dictation、Ambient、Pre-recorded 产品与 API | v2 录音/转录采用加密数据库持久化、租户与主体隔离、同步及异步 `202 + Location`、重启恢复、完整查询/删除；Ambient 已接真实中文 ASR 和真实 LLM fact extraction，失败时不生成合成临床文本 | **Corti 仍有产品深度优势**；iCoDer 中文真实路径已从 Stub 升级，仍缺英语/多语、说话人分离、多通道和生产对象存储 |
| Text Generation / Fact Extraction / Embedded | Console 独立产品入口 | 路由、页面、SDK/嵌入能力存在 | **部分等价**；缺托管生产验证和客户案例 |
| SDK | Console 提供 JavaScript、.NET、JSON Config | TypeScript、Python、Web Embedded、.NET 8/10；三种语言已在同一真实临时 uvicorn/租户令牌上通过 Agent Hub、Agent Run 与 v2 STT consumer E2E | **开发环境覆盖已对齐**；npm、PyPI、NuGet 均未正式发布，托管云 API 外部网络消费仍待验证 |
| API Clients / OAuth | 托管项目内管理 | 本地 API Client、OAuth/租户隔离测试通过 | **开发环境部分等价**；未做托管多租户运行验证 |
| Billing / Credits | 真实 credits、usage 与账单产品 | credits/usage 页面和接口存在，但本地充值未接支付清算 | **Corti 明显优势**；iCoDer 当前不是生产计费系统 |
| 多区域与灾备 | 官方声明地域冗余与 failover | 部署配置存在，但无已启用的多区域生产环境 | **Corti 明显优势** |
| 安全与认证 | Corti 公布 ISO/SOC 2/BSI C5/HIPAA/GDPR 等 | 有代码级鉴权、审计、PHI、租户隔离与安全测试 | **Corti 明显优势**；代码控制不等于外部认证 |
| 中国医疗适配 | 全球产品，可配置编码系统 | ICD-10-CN、ICD-9-CM-3、DRG/DIP、医保与中文工作流 | **iCoDer 方向性优势**；仍缺真实医院和地方规则持续维护 |

## 5. 本轮已在开发环境完成

1. 根据登录态 Corti Console 补齐 Clinical Education 与 Clinical Guidelines 两个 Agent。
2. 将用户可见 Agent 收敛为 26 个全部可执行、全部通过开发发布候选门禁。
3. 增加发布门禁：`icoder.pure-llm.v1` 后端不得声明运行时工具。
4. 修正 Claim Check、Denial Appeals、Evidence Ranker、Note Completeness 的清单，使其与真实 Provider 行为一致；不再把未调用的工具描述为已接入能力。
5. Mock Provider 失败关闭：没有真实模型时返回明确 degraded/safe failure，不伪造临床成功。
6. SQLite 并发治理：WAL、busy timeout、回滚与事务边界；并发运行不再出现数据库锁导致的假结果。
7. 幂等失败重试：FAILED 记录可原子地重新获取执行权，避免永久卡死或重复执行。
8. 真实 uvicorn 测试数据库隔离：子进程使用临时 SQLite，开发库时间戳前后完全一致。
9. OpenAPI、前端 SDK 契约、Agent Hub 展示、运行接口与审计链路同步更新。
10. 接通 Corti v2 STT 的真实中文生命周期：上传音频、加密数据库持久化、租户/主体隔离、原始音频读取、FunASR/Whisper 转录、状态/列表/删除；模型不可用返回明确错误，未验证英语返回 422。
11. 增加异步转录任务：`202 Accepted`、`Location`、持久任务状态、应用重启恢复，并覆盖跨租户访问、密文/摘要篡改和并发首次写入。
12. 接通 Ambient v2 的真实中文缓冲 ASR 与 LLM fact extraction；移除生产路径的合成临床 transcript/facts，补齐签名 token、OAuth scope、配置校验、150 MB 内存上限和失败关闭。
13. 定位 Windows 原生崩溃为 `torch_cpu.dll` 的 `0xc0000005` 访问冲突；当前 `torch 2.11.0 + sentence-transformers 3.2.1` 组合失败关闭，正常退出回收 worker，异常父进程退出由管道监测避免孤儿进程。详见 [Windows BGE/FAISS 本地运行安全门禁](../dev/WINDOWS_BGE_RUNTIME_SAFETY.md)。
14. 新增 [.NET 10 LTS SDK](../../packages/icoder-dotnet/README.md)：覆盖 Agent Run/Hub、医学编码、Corti-compatible v2 STT、Facts、OAuth refresh、幂等键、取消令牌、HTTPS 默认门禁和 PHI-safe 异常；OpenAPI 契约测试、Release 构建及 NuGet 打包均通过。
15. 用真实 uvicorn、临时 SQLite 与一次性 tenant-bound JWT 运行 .NET 外部 consumer：验证 Hub 26/26、Agent Run 无模型失败关闭且 trace 可用、录音 upload/list/download/delete。该测试发现并修复 STT 错从 `User.organization_id` 取租户的问题；现在由已验证 token 的 `get_current_organization` 提供权威组织范围。
16. 将 JavaScript、Python 与 .NET 消费者纳入同一受控真实服务 E2E：三者均验证 Hub 26/26、无模型 Agent Run 失败关闭、trace 存在及录音 upload/list/download/delete；TypeScript 构建、npm dry-run 包清单、Python 3.9 语法和 wheel 元数据也通过。
17. 为既有 40 例 Corti/iCoDer CDI 冻结基准增加离线只读校验门禁：验证 4 个汇总工件和 40 个逐例文件的大小、SHA-256、唯一 case ID 与显式脱敏标记，并将工件完整性和能力达标分开。当前完整性通过，严格对标门禁按预期失败并明确暴露 4 项差距。
18. 按 Corti 当前 Context & Memory 契约修正旧单轮语义：A2A 首轮创建持久化 `contextId`，续轮只接受同租户/同 Agent/active 的服务端 ID；以单事务写入脱敏用户消息和 Agent 输出，提供 Context history 查询，并把最多 6,000 字符的中文相关历史注入 Orchestrator。Memory PHI 字段已接加密，危险 Windows sentence-transformers 栈失败关闭。
19. 将 A2A 多轮 Context 纳入 JavaScript `1.0.0-beta.4`、Python `1.0.0b3` 与 .NET `1.0.0-beta.2` SDK；修复确定性 Agent 旁路未复用 Context、未先脱敏及首轮 Context 被安全回收的问题。JavaScript/Python 已在真实临时 uvicorn 完成 send/continue/get/delete；所有 A2A 协议/传输异常均不保留请求、响应正文或令牌。.NET 源码与契约测试已补齐，但当前机器缺少 `dotnet.exe`，本次增量尚未复跑。

## 6. 本轮自动化验证

| 测试组 | 结果 |
|---|---:|
| Agent loader / registry / Hub / Agent run 定向组合 | 142 passed |
| 全量 API（Agent、STT 与 Ambient 最终状态） | 1234 passed |
| integration + regression + review + E2E + product E2E | 319 passed, 3 skipped, 10 deselected |
| unit + coding runtime + services + models + compliance + concurrency | 2516 passed, 11 skipped |
| 真实 uvicorn 数据库隔离复核 | 3 passed；开发 DB mtime 未变化 |
| Frontend Vitest | 80 passed |
| Frontend production build | passed |
| Frontend lint | 0 errors, 384 warnings |
| STT / Ambient 定向组合 | 82 passed |
| Windows BGE 安全门禁、worker 生命周期与策略定向组合 | 79 passed, 1 skipped；前后均 0 个残留 worker |
| .NET SDK | `net8.0` 7 passed + `net10.0` 7 passed；Release build 0 warnings / 0 errors；双 framework `.nupkg` + `.snupkg` generated |
| JavaScript SDK | TypeScript build 0 diagnostics；当前源码版本 `1.0.0-beta.4`；A2A send/continue/get/delete 真实 consumer passed |
| Python SDK | A2A MockTransport 3 passed；当前源码版本 `1.0.0b3`；A2A send/continue/get/delete 真实 consumer passed |
| .NET + JavaScript + Python → real uvicorn consumer E2E | 三者 passed；Hub 26/26、Agent fail-closed + trace、STT upload/list/download/delete、临时 DB 与服务均已回收 |
| A2A SDK 增量 | JavaScript + Python → real uvicorn passed；.NET `1.0.0-beta.2` 源码/2 个契约测试已新增，但本机无 .NET SDK，待在有 `dotnet` 的开发/CI 环境复跑 |
| Corti/iCoDer 冻结基准离线校验 | 4 tests passed；44 files / 40 unique de-identified cases verified；0 network、0 model load；strict parity gate exit 2（4 项已知差距） |
| Context / Memory 定向组合 | 60 passed（多轮、鉴权、跨租户不透明、非法 ID、中文相关性、原生门禁）；另 162 passed（生命周期、repository、GC、全存储 scrub） |
| OpenAPI export check | passed |

说明：3 个真实启动测试已包含在 319 项组合中，单独复核不重复计入后端累计。默认 pytest 配置排除了 `heavy`、`retrieval`、`infra` 标记；它们需要模型资源、检索索引或显式启动的外部基础设施，不应被误报为已验证。此前的全量 API 结果是在 Ambient 完成后取得；原生崩溃修复后采用隔离批次复核，避免再次把 Codex 宿主暴露给已知不安全的 Windows PyTorch 栈。

## 7. 哪些剩余任务可以在开发环境完成

### 7.1 可以继续完成

1. 建立 Corti/iCoDer 同输入、同评价量表的离线评测框架，并加入脱敏合成样例、误差分层、可回放 trace 和版本化结果。
2. 在已完成的加密持久化、异步 pre-recorded 与 Ambient 中文真实链路之上，继续实现外部对象存储/外部任务队列、英语/多语模型、说话人分离、多通道时间戳和音频时长/格式深度校验。
3. 产品化 context/memory：语义检索、生命周期、租户隔离、删除/导出、来源与记忆污染测试。
4. 扩展真实 Experts/MCP 工具，并对每个工具实施权限、超时、来源、失败关闭、注入防护与审计测试。
5. 扩展三语言 SDK 的 API 表面与真实托管云 API 外部网络验证；npm/PyPI/NuGet 组织、签名、供应链证明和正式发布仍需发布权限。
6. 清理前端 384 条 lint warning，并拆分 706 KB 主 bundle。
7. 增加负载、混沌、恢复、升级/回滚演练脚本；开发环境可验证机制，但不能代替真实多区域演练。
8. 建立地方医保/DRG/DIP 规则包的版本、来源、有效期、地区隔离、差异审查与回滚机制。
9. 对所有 26 个用户可见 Agent 增加结构化输出 schema 的属性测试、注入测试、缺失证据测试和中文临床边界测试。

### 7.2 只能完成“工具和流程”，不能在开发机闭环

- 真实医院脱敏数据集与独立专家标注：开发环境可建评测框架，数据授权、标注和结论必须由医院完成。
- HIS/EMR/FHIR/医保平台集成：可建模拟器与契约测试，真实网络、证书、字段映射和验收需合作方完成。
- 多区域容灾：可写 IaC 和演练脚本，真实 RTO/RPO 证据需云环境与运维审批。
- 支付计费：可接 sandbox，真实商户、结算、发票和退款需支付渠道及财务/法务。

### 7.3 外部门禁

- 独立临床质量验证与医院伦理/治理批准。
- 中国数据与网络合规：个人信息保护法、数据安全法、网络安全法、等保及医院制度审查。
- 独立渗透测试、供应链审计和外部认证。
- 生产云账户、密钥托管、监控值守、备份恢复和灾备演练。
- 模型、药品库、指南、编码字典与医保规则的数据许可。
- 真实支付渠道、合同、发票、退款与财务对账。

## 8. 当前最终判断

**Agent Hub 目录复刻目标已在开发环境达到：Corti 20/20 对应，iCoDer 用户可见 26/26 可执行且通过工程发布候选门禁。**

**Corti 整体生产能力复刻尚未达到。** 当前最关键的可开发差距是 STT 的多语/说话人/生产外部存储深度、语义记忆、生产级 Experts/MCP、SDK 正式发布与托管云外部网络验证、离线临床评测体系和前端质量债务。当前 Windows 开发栈的 BGE/FAISS 语义检索因已证实原生崩溃而失败关闭，必须迁移到验证过的依赖构建或隔离 Linux 检索服务后才能恢复生产等价验证。最关键的不可本地闭环差距仍是真实医院验证、生产基础设施、安全认证、数据许可与合规审批。

因此总目标应保持进行中，不能将 `production_ready` 从 0 人为改成通过，也不能用页面、Stub、Mock 或合成测试替代真实生产证据。

## 9. 2026-08-27 shadow 作业运营控制面增量

在持久化分布式 shadow 作业的创建、幂等、租约、接管和结算能力之上，开发环境已新增可治理取消、旧 worker 结算 fencing、租户级聚合健康、确定性告警码及有界维护清扫。JavaScript/Python/.NET SDK、Console 和 OpenAPI 已同步，运营证据、116 项部署预检及各语言全量回归均通过。详见 [shadow 作业运营韧性阶段总结](./ICODER_CLINICAL_MODEL_SHADOW_JOB_OPERATIONS_PHASE_SUMMARY_2026-08-27.md)。

该增量缩小了 Corti Models 类运营控制面的工程差距，但没有改变 `production_ready = 0`：尚缺生产 broker、dead-letter 与受治理重放、指标 exporter 和告警投递、多主机/多区域混沌与长稳、真实模型编排，以及合法真实患者 shadow 和独立临床对标。当前结论仍是开发环境发布候选，不是 Corti 生产能力等价。
