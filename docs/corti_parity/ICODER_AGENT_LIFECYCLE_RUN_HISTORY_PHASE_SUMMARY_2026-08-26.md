# iCoDer Agent 生命周期与真实运行历史阶段总结（2026-08-26）

## 阶段结论

本阶段关闭的是 iCoDer 项目 Agent 在开发环境中的生命周期真实性、执行失败关闭、审计可追溯和详情页运行历史真实性问题。它不证明 Corti 私有生命周期实现等价，也不把合成模型回归解释为临床质量、医院上线或生产 SLA。

当前实现采用一个后端权威状态机：

- `draft`：允许发布或删除，不允许运行。
- `published`：允许运行、归档、显式版本提升或删除。
- `archived`：允许恢复或删除，不允许运行或编辑。
- Hub 的“自定义/Clone”创建保留源 Pack、Runtime 与安全图的已发布项目副本，可立即运行；通用 REST Clone 保持草稿语义，必须显式发布。
- 直接通过通用更新接口修改 `status`、`is_published` 或 `version` 会被拒绝，避免绕过生命周期端点。
- 已发布 Agent 的实际配置变更自动提升 patch 版本；归档 Agent 的配置编辑失败关闭。

## 执行与审计闭环

HTTP 统一 Run 和 A2A 两条入口都在解析租户项目 Agent 后执行相同的发布状态门禁。草稿或归档状态即使绕过前端也返回稳定的 `agent_not_published` 业务错误；A2A 已将该错误纳入公开错误分类、HTTP/JSON-RPC 映射和旧兼容翻译，不再误降级为 `INTERNAL_ERROR`。

生命周期创建、Clone、更新、发布、版本、归档、恢复和删除均写入组织/用户归属的系统审计。审计 detail 只允许源 Agent 标识、变更字段名、前后状态和版本等安全元数据，不记录 System Prompt 或用户输入正文。

## 前端真实性

AgentDetailPage 以后端返回的 `lifecycle` 投影显示状态、允许操作和版本：

- 未发布或已归档时，聊天和测试入口禁用。
- 已归档时，设置保存禁用并提示先恢复。
- 项目 Agent 不再错误套用 Registry install/enable 状态。
- 原先本地生成的金标准 accuracy、通过率和 CSV“评估”已移除。
- “运行记录”只读取后端持久化 Run History，展示 run ID、状态、时间、Runtime mode 和延迟；空列表保持诚实空白状态。
- 运行历史加载失败显示持久错误和 Toast，不再伪装成空列表；保存与删除失败也不再静默吞掉。

## 当前验证证据

截至本文件当前修订：

- PowerShell 严格真实模型 runner 与新增失败诊断逻辑均通过解析；启动等待从 90 秒提高到可配置的 240 秒。Windows PowerShell 5.1 无法解析合法的大型 adversarial JSON 的问题已改由 Python 读取六个源报告并输出带 SHA-256 的小型、内容无关验证摘要；随后又移除顶层证据对 `Get-FileHash` cmdlet 的依赖，改用 .NET SHA-256 流式计算。Failure metadata 只保留凭据脱敏首行（最多 1,000 字符）和凭据脱敏 stderr tail（最多 8,000 字符），不再把整个报告复制进失败文件。最终相关 validator/runner safety 回归已包含在下述 89/89 语义证据专项中。
- 新鲜文件级 Corti 目录核验为 **20/20 mapped、20/20 development profile、20/20 China profile declared**，同时仍诚实报告 **0/20 clinical-quality verified、0/20 production-ready verified**。
- 最终 Hub Runtime Matrix 为 **26/26 executable、26/26 provider-resolvable、26/26 launch-candidate-ready、26/26 strict live semantic verified**；26/26 具有完整示例、类型/嵌套 schema、字段关系、证据绑定、跨 Agent 关系、不可变注册合同和严格输出 allowlist。生产就绪仍诚实报告 **0/26**。
- 生命周期/A2A 完整 E2E 最终 **2/2**；CDI 并发与专用遥测 **58/58**；26-Agent 离线安全 **78/78**；examples/adversarial/reference/stability、Bundle、临床校准边界、运行矩阵和外部 artifact validator 专项 **89/89**；Hub API、租户 readiness 和运行时投影 **33/33**。这些不重复口径合计 **260/260**。
- 第四次真实运行暴露 Provider 失败归因过粗后，新增内容无关的错误类别、HTTP 状态、底层尝试次数和 retryable 遥测；相关 LLM 服务、CDI Runner、专用遥测、红线脱敏、编排和外部证据安全增量回归 **108/108**。
- 第五次真实运行把失败进一步收敛为连续 3 次 `connection`，并通过无有效凭据的机制探针复现全局 `AsyncOpenAI` 跨短生命周期事件循环复用时认证响应/连接错误交替。首次请求级循环修复后的第六次运行没有再返回 `connection`，但 CDI 在 18.24 秒后暴露本地 `RuntimeError`，严格示例门禁为 **25/26** 并提前停止。最终实现改为每个 CDI 请求一个专用事件循环线程，`AsyncOpenAI` 在该运行中循环内创建，全部阶段通过 `run_coroutine_threadsafe` 在同一循环执行，并在同一循环关闭；相关 CDI Runner/Orchestrator/LLM/遥测 **309/309**，CDI A2A/项目 Clone **34/34**，合计 **343/343**，另有真实 `AsyncOpenAI/HTTPX` 本地回环生命周期复现通过。
- 专用循环线程修复后的第七次运行消除了本地 `RuntimeError`，但真实 Provider 返回的结构化内容使 CDI 与 Medical Coding 分别以 `provider_execution_failed` 和 `schema_returned_error` 安全失败，examples 为 **24/26**。两条路径现均只对结构化输出失败追加一次内容无关修复重试，第二次仍不合规则以 `invalid_response` 失败关闭；不回显 Provider 原文、不放宽合同、不增加网络重试上限。相关核心/适配器 **341/341**、A2A/Clone/Medical Coding 合同 **37/37**，合计 **378/378**。
- 有界结构化修复后的第八次严格真实模型 wrapper 已从启动到清理一次通过：happy/adversarial/reference 各 **26/26**、stability **156/156**、Bundle/Matrix/artifact validation 全部有效并生成顶层 `status=passed` 证据；无 failure 文件。全局 P50/P95 **0.348/3.751 秒**，CDI **6/6、P95 15.482/30 秒**，Medical Coding **6/6、P95 3.933/10 秒**，26/26 per-Agent 延迟门通过。
- 前端完整 Vitest 最终 **151/151**（25 个测试文件）；TypeScript 与 Vite 生产构建通过，仅保留既有动态/静态 import 分块提示。
- 部署预检现共有 104 项，其中本阶段新增的 `agent_definition_lifecycle_is_audited_fail_closed_and_ui_truthful`、PowerShell 5.1 artifact validator、failure diagnostic 边界、cmdlet-independent SHA-256、CDI 有界并发、content-free Provider failure diagnostics 和两条核心临床路径的有界结构化修复重试均已通过；最终静态预检为 **104/104**，报告 SHA-256 `1abd4033c80b1563f96b18691a5db36e128149135f6d23a7b32f8a8a3cf31898`。独立的严格真实模型 wrapper 顶层终态也已通过。
- 受保护开发数据库保持 **8,536,064 bytes / 2026-08-22 17:16:22 / SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`**，三项不变性均通过；本阶段代码、文档和新报告的同行凭据赋值/Provider Key 形态扫描通过。首次宽松正则跨行命中预检脚本自身的字符串合同，收紧为同行赋值后确认为误报，未发现凭据值。

## 2026-08-27 受治理 50 次临床校准与修复

首次 50 次串行真实模型调用已完整产出 40 个 CDI 中文病例与 5 个双语 Medical Coding 病例的 10 次调用。原始报告位于 `reports/agent_hub/clinical_calibration_live_20260827-095102/agent_hub_clinical_calibration_e2e.json`，SHA-256 为 `09599269726ec41b510384a0fb58ece980cfcb65bc2a477163f1ce1be411fe96`。该报告终态是 `invalid_or_incomplete_evidence`，不是 50/50 通过证据；原始证据保持不改写。

复盘发现通用数字溯源检查错误地把 50 个当前病例响应与 Agent Pack 第一个示例输入比较。修正为显式使用本次调用输入后，对原响应的只读离线重评分从 20 个 `capability_passed` 修正为 41 个，29 个 `unsafe_or_invalid` 降为 8 个；另有 1 个安全失败关闭。这个重评分只用于定位评测器假阳性，不替换原始签名报告，也不提升临床质量结论。

其余真实工程缺口已完成以下修复：

- Medical Coding Agent Pack 入口默认同时请求 ICD-10-CN 与 ICD-9-CM-3，并允许调用方在受支持集合内显式选择；50 次 runner 也显式声明两套编码系统，避免在未请求手术编码时评估手术编码命中率。
- 中英文临床别名统一进入受控中国编码目录检索，组合请求为诊断与手术目录各保留候选预算，避免英文碎片的高模糊分数挤掉真实手术候选。
- CDI 的 encounter summary、gap、query、risk flag 和 specialist trace 增加病历外定量值拦截；证据不能回到原文时不发布到临床结果。Medical Coding 对所有公共字段清除病历外定量值，并将 assigned-code evidence 修正为原文片段；无可验证证据时按 `no evidence = no code` 隐藏编码。
- 中文 PHI 规则不再把“单纯性”“阴性”“ST 段抬高”“双肺底”等高频临床词误删为姓名。
- 双语种子版本提升为 1.0.1。修正 3 个不属于当前运行时目录的旧编码，并移除两类违反不可推断红线的标签：吸烟史不再直接标注烟草依赖，骨质疏松合并骨折不再直接标注病理性骨折。校准计划现在逐个验证期望诊断/手术编码的目录成员资格；新计划 `clinical_calibration_plan_20260827_v2` 为 valid，计划摘要 SHA-256 `0b4087f2f8e48753c42c87187ba5c45e8f317a19882cf6bbf1178bbd9921b596`。

修复后的相关聚焦回归为 173/173；扩大回归首次为 488 passed、4 failed、5 skipped，4 个失败均来自 CDI mock 仍提供与 chart 不一致的旧证据。mock 改为原文证据后 `test_real_runner.py` 为 18/18。部署预检为 104/104。下一次 50 次真实模型调用必须使用新的临时凭据，并生成新的独立证据目录；当前结果仍不证明 Corti 同病例等价、独立临床准确率、医院验收或生产就绪。

## 开发环境完成状态

1. 26-Agent happy、adversarial、reference 和三轮 stability 均已在隔离临时数据库、真实 loopback HTTP 与一次性 DeepSeek 凭据下完成并通过。
2. 最终新 Bundle、Runtime Matrix 和 Python artifact validation 均有效；响应/Trace、Provider/model、mock/degraded、签名与延迟门均通过。顶层 `external_semantic_e2e_evidence.json` 为 `status=passed`，不存在 failure 文件，成功证据 SHA-256 为 `cd54d441df3074dfca7024e9018526ef36bad9c56745bf0b6f8b3d9b45811400`。
3. 生命周期、A2A/Hub、26-Agent 离线安全、前端全量、生产构建和 104 项静态预检均已最终复跑通过；最新事件循环与结构化修复重试的聚焦回归为 378/378。
4. 受保护开发数据库大小与 SHA-256 保持不变；最终证据目录通用 Provider Key 形态扫描为 0 命中，顶层证据明示 `credential_persisted=false`，临时 Uvicorn 已停止、临时数据库已创建/迁移/删除、临时启动器已删除。
5. 开发环境严格合成 Pack 门禁已闭环；独立临床金标准、Corti 同病例 head-to-head、真实医院验收和生产基础设施仍未完成，不得由该成功证据推导 Corti 等价或生产就绪。

## 本轮真实模型执行记录

### `external_semantic_e2e_live_20260826-111257`

- Happy 26/26、Adversarial 26/26、Reference 26/26、Stability 156/156。
- 全部运行证据为 fresh HTTP；DeepSeek `deepseek-chat` 调用被 Trace 观察，mock/degraded 均为 false，Trace attestation 存在、claims-bound 且验签通过。
- Bundle 与 Runtime Matrix 已生成，但 Windows PowerShell 5.1 在 artifact validation 读取大型合法 JSON 时抛出 `ArgumentException`，因此顶层只有 `external_semantic_e2e_failure.json`，不得提升为权威成功。
- 根因和 failure metadata 过大问题均已按上文修复；现有源报告通过新 Python validator，负向错误计数验证会以 exit 2 失败关闭。

### `external_semantic_e2e_live_20260826-120015`

- Happy 26/26、Adversarial 26/26、Reference 26/26；Stability 语义/安全 156/156。
- Stability runner 正确因 per-Agent latency gate 返回 1：CDI P95 36.10 秒超过开发预算 30 秒；Medical Coding P95 5.06 秒通过 10 秒预算。故 wrapper 停在 `reference_complete`，未构建 Bundle/Matrix，也不得提升为权威成功。
- CDI 六次均 HTTP 200 且语义通过，耗时为 24.41、36.10、26.43、28.83、30.86、27.20 秒；最慢运行有 3 个 Query 和 11 次模型调用。两组逐 Query 必需安全门原并发上限 2，需要两轮 Provider 等待。
- 默认有界并发已从 2 调整为 3，常见三 Query 病例每个安全门可在一轮完成；硬上限仍为 4，主阶段及两类安全门的因果顺序不变。并发 3、异常配置 99→4、配置 0→1 和顺序保持等聚焦回归连同遥测为 13/13 通过。
- 该次失败后未放宽预算，而是只优化有界并发并执行下面的新鲜重试。

### `external_semantic_e2e_live_20260826-124556`

- Happy **26/26**、Adversarial **26/26**、Reference **26/26**、Stability **156/156**，四组失败均为 0；stability provider completion、contract 和 safety pass rate 均为 1.0。
- 全局 Stability P50 **0.465 秒**、P95 **3.672 秒**；CDI P95 **28.98 秒 / 30 秒预算**，Medical Coding P95 **3.916 秒 / 10 秒预算**，26/26 per-Agent latency gate 全部通过。
- Bundle `valid=true` 且 `semantic_live_e2e_verified=26`；Runtime Matrix 为 executable/provider-resolvable/launch-candidate-ready **26/26**、live semantic **26/26**、external pending 为空、production ready **0/26**。Python `artifact_validation.json` 的 10 项源产物/Bundle/Matrix 校验全部通过。
- runner 在 `top_level_evidence` 阶段调用当前会话不可用的 `Get-FileHash`，因此生成脱敏、限长的 `external_semantic_e2e_failure.json`，没有生成顶层 success 文件。`credential_value_recorded=false`，临时后端已停止，证据目录通用 Key 形态扫描 0 命中；该目录仍按失败运行保留，不能删除 failure 文件后冒充完整成功。
- 根因已改为 cmdlet-independent 的 .NET SHA-256 流式计算并加回归断言，相关安全测试通过。现有源产物在修复后的 Python validator 下仍全部有效，但“wrapper 全流程一次通过”需要新临时 Key 再执行一次。

### `external_semantic_e2e_live_20260826-215513`

- 使用修复后 wrapper 完成 Happy **26/26**、Adversarial **26/26**、Reference **26/26**；Stability 完整执行 **156** 次，其中 **155 通过、1 失败**，pass rate **99.36%**。全局 P50/P95 **0.307/4.778 秒**，26/26 per-Agent latency gate 全部通过。
- 唯一失败是 CDI `ambiguous-aki` adversarial 第 2 轮：HTTP 200，但运行结果为安全失败关闭 `provider_execution_failed`；Trace 证明真实 `deepseek/deepseek-chat` 调用、mock=false、fallback=false、签名有效，耗时 16.994 秒，CDI 本轮 P95 27.497 秒仍在 30 秒预算内。
- 严格门禁没有重试整批或掩盖失败，正确停止于 `reference_complete` 并生成 failure 文件；顶层 success、Bundle 和 Matrix 未被生成。凭据值未记录，证据目录通用 Key 形态扫描 0 命中，临时后端已停止，受保护数据库未变化。
- 该 Trace 当时只能保留 `provider_execution_failed`，无法区分限流、超时、连接错误或服务端 5xx。现已增加固定枚举错误类别、可选 HTTP 状态、0–10 次有界尝试计数和 retryable 布尔值；原始 Provider 异常正文不进入日志、Trace 或响应。现有底层重试仍为最多 3 次，没有因单次失败盲目增加重试或放宽 100% stability 门。

### `external_semantic_e2e_live_20260826-222012`

- 使用带安全 Provider 诊断的新实现再次得到 Happy **26/26**、Adversarial **26/26**、Reference **26/26**；Stability **155/156**，全局 P50/P95 **0.273/4.207 秒**，26/26 per-Agent latency gate 通过。
- 唯一失败仍为 CDI `ambiguous-aki` adversarial，但在第 3 轮发生；新 Trace 明确记录 `provider_error_category=connection`、`provider_attempt_count=3`、`provider_retryable=true`、无 HTTP 状态，15.235 秒后安全失败关闭。原始异常、病例和凭据均未持久化。
- Clash WinINET 代理为 `127.0.0.1:7897`，但 Python 进程没有显式 HTTP(S)/ALL_PROXY；显式代理和强制直连的无 Key curl 各 5/5、HTTPX 并发各 20/20 均返回预期 401，基础 DNS/TLS/连接池探针不能解释只在 CDI 高调用路径重复出现的失败。
- 随后的 OpenAI 客户端机制探针使用假 Key、不发送病例：同一 `AsyncOpenAI` 实例跨 6 个连续 `asyncio.run()` 调用时，第 1/3/5 次为预期 AuthenticationError，第 2/4/6 次为 `APIConnectionError > RuntimeError > AttributeError`。这与 CDI 原实现“每阶段新事件循环、全局异步客户端连接池复用”一致。
- 当前已改为每个 CDI 请求独立 `LLMService/AsyncOpenAI`，完整 CDI 编排只使用一个请求级事件循环，所有阶段和并发安全门共享该循环，请求结束在循环关闭前显式 `aclose()`；跨阶段同循环和客户端关闭均有回归锁定。修复后仍需新的临时 Key取得一次完整 wrapper 证据。

### `external_semantic_e2e_live_20260826-225658`

- 首次请求级事件循环修复后的真实运行完成 26 个 examples，结果 **25/26**；25 个 Agent HTTP 200 且语义通过，唯一失败仍是 CDI，但错误从此前有界诊断的 `provider_execution_failed/connection` 改为本地 `runtime_crash/RuntimeError`，耗时 **18.24 秒**。严格 runner 在初始化阶段即失败关闭，没有继续 adversarial/reference/stability，也没有生成 Bundle、Matrix 或顶层成功证据。
- Failure metadata 为内容受限诊断，`credential_value_recorded=false`；证据目录和最新预检目录的通用 Key 形态扫描均为 0，临时后端与启动器已停止/删除，受保护数据库保持原大小、时间和 SHA-256。
- 本地真实 `AsyncOpenAI/HTTPX` 回环验证排除了 CDI 业务合同和基础客户端关闭失败；残余风险位于 Windows 下同步编排线程反复 `run_until_complete` 驱动事件循环的边界。实现随后升级为每请求专用事件循环线程，并让请求级客户端的创建、全部调用和关闭都发生于该运行中循环；聚焦回归 **343/343**、预检 **104/104**。该修复仍需新临时 Key 获取完整 wrapper 终态证据，当前失败目录不被改写为成功。

### `external_semantic_e2e_live_20260826-232845`

- 专用事件循环线程修复后的真实 examples 为 **24/26**，其余 24 个 Agent HTTP 200 且语义通过；CDI HTTP 200、7.41 秒后以 `provider_execution_failed` 安全失败，Medical Coding HTTP 200、4.64 秒后以 `schema_returned_error` 安全失败。两者均完成真实 `deepseek/deepseek-chat` 调用，说明 Key 和基本 Provider 通路有效；本轮没有复现本地 `RuntimeError`。
- 严格 runner 在 examples 阶段失败关闭，没有继续 adversarial/reference/stability，也没有生成 Bundle、Matrix 或顶层成功证据。Failure metadata 明示 `credential_value_recorded=false`；证据目录和最新预检目录的通用 Key 形态扫描均为 0，临时后端与启动器已停止/删除，受保护数据库保持原大小、时间和 SHA-256。
- 根因收敛为 Provider 结构化内容的随机不合规，而原实现只修复同一文本、不会重新请求：CDI 把最终解析失败归入泛化 `unknown`，Medical Coding 返回 DS001 error schema。当前两条路径均增加一次、且仅一次结构化修复重试，并用固定补充指令要求单一 JSON 对象；CDI 最终失败分类新增 `invalid_response`，Medical Coding 不再把原始 Provider 内容或异常正文写入日志。修复后聚焦回归 **378/378**、预检 **104/104**；仍需新临时 Key 取得完整 wrapper 终态证据。

### `external_semantic_e2e_live_20260826-235457`

- 有界结构化修复后的最终严格 wrapper 已完整通过：Happy **26/26**、Adversarial **26/26**、Reference **26/26**、三轮 Stability **156/156**，Provider completion、contract、safety、完整性和 26/26 per-Agent latency gates 全部通过。
- Stability 全局 P50/P95 为 **0.348/3.751 秒**；CDI **6/6**、P50/P95 **13.19/15.482 秒**、低于 30 秒开发预算；Medical Coding **6/6**、P50/P95 **3.174/3.933 秒**、低于 10 秒开发预算。两者成本覆盖率均为 1.0。
- Bundle `valid=true` 且 verified **26/26**；Runtime Matrix strict live semantic verified **26/26**、pending/external pending 均为空、production ready **0/26**；Python artifact validation 的 10 项检查全部为 true，六项源工件 SHA-256 已固化。
- 顶层证据 `status=passed`、`real_llm_used=true`、`transport=real_loopback_http`、`credential_persisted=false`，明确 `synthetic_pack_owned_cases_only=true`、`corti_parity_proven=false`、`independent_clinical_gold_used=false`、`hospital_acceptance_proven=false`。成功证据 SHA-256 为 `cd54d441df3074dfca7024e9018526ef36bad9c56745bf0b6f8b3d9b45811400`，无 failure 文件。
- 证据目录通用 Key 形态扫描为 0，临时后端已停止且无 Python/Uvicorn 子进程，临时数据库状态为 `created_migrated_removed`；受保护数据库仍为 **8,536,064 bytes / 2026-08-22 17:16:22 / SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`**。临时启动器已删除，用户仍须在 DeepSeek 控制台撤销本次临时 Key。

## Corti 差距边界

本阶段没有对 Corti 创建、发布、归档、恢复或运行 Agent，因此只能证明 iCoDer 内部状态机和 UI/执行一致性，不能声称与 Corti 私有生命周期语义等价。当前已登录 Corti Console 的只读证据只支持 20/20 当前可见 Pre-built Agent 目录映射。

即使本阶段全部开发门禁通过，以下仍是外部上线门禁：

- 同病例 Corti head-to-head、独立临床 reviewer、双盲标注和统计学质量评估。
- 真实中国医院数据、HIS/EMR/医保/编码库/药品库/登记库集成及医院验收。
- 获许可的权威数据源、生产云资源、KMS/HSM、区域容灾、容量与 SLA。
- 个保法/数据安全法/网络安全法、等保、数据出境、医疗器械边界、合同和认证评估。
