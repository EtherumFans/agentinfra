# iCoDer CDI 安全门计量与时延阶段总结（2026-08-25）

## 阶段结论

本轮关闭了 CDI 专用运行时中的两个开发环境工程缺口：claim-evidence 与 semantic-necessity 必需安全门的真实 LLM 调用此前未进入聚合 token/成本/Provider 时延；11 个编排阶段此前也没有内容无关的耗时归因。当前实现已覆盖这两类计量，并在不改变临床门禁因果顺序的前提下，将同一安全门内彼此独立的逐 Query 调用改为最多 2 路有界并发。

2026-08-25 22:49 启动的 fresh live-provider 源级证据已确认调用覆盖、成本与性能改善：happy/adversarial/reference 各 26/26、stability 156/156；CDI 6/6 的 P50/P95 为 20.378/26.662 秒、成本覆盖 6/6，Medical Coding 6/6 为 5.511/6.688 秒、成本覆盖 6/6。两个 per-Agent 预算均通过，整体成本覆盖从旧证据的 150/156 提升为新源报告的 156/156。

但该次 wrapper 在有效 bundle 与 Runtime Matrix 已落盘后、顶层 evidence 写入前终止，精确异常和后端退出码未持久化。因此 [`external_semantic_e2e_forensic_recovery.json`](../../reports/agent_hub/external_semantic_e2e_live_20260825-224918/external_semantic_e2e_forensic_recovery.json) 将它固定为“核心证据通过、wrapper 终态失败”，不提升为顶层权威成功。原完整顶层权威 [`212957`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/) 仍保留；新源级数据可证明本轮开发改进，但不是 Corti 性能等价或生产 SLA。

## 已完成实现

- 新增内容无关 `CDIModelCallTrace`，仅记录固定 stage 标识、provider、model、毫秒时延、prompt/completion/total token 与 degraded；不接收或保存病历、Query、Prompt、Completion、Claims 或证据正文。
- claim-evidence 与 semantic-necessity 的每次实际 `llm.chat` 均通过透明代理计量；成功但 JSON 无效的调用仍计算已发生 token，调用异常则保留 unknown token 并使聚合成本保持 unknown。
- CDI aggregate telemetry 现在统一聚合主阶段、实际 Expert 与安全门调用。只有所有已发生调用均具有完整 observed usage 时，才生成 `configured_usage_pricing_estimate`；配置估算继续固定 `billing_authoritative=false`。
- `CDIOrchestrator` 对 11 个固定阶段记录内部毫秒耗时；Run Trace 只投影总编排时延、模型调用时延和、阶段耗时合计、最慢阶段/时延及预算状态，不公开逐阶段临床结果。若并发使调用时延和超过墙钟时延，则显式标记 overlap，并省略不可可靠相减的 `non_provider_wall_latency_ms`。
- 开发单次预算为 30,000 ms，仅产生内容无关告警，不替代 Provider timeout、不改变临床失败关闭，也不冒充 Corti SLA。
- 同一安全门内的逐 Query 调用最大并发为 2，并强制限制在 1–4；`asyncio.gather` 保持原 Query 顺序。encounter → gap → expert → query → claim-evidence → semantic-necessity → compliance 的主链仍串行。
- 严格 stability runner 新增 per-Agent P95 门禁：CDI 30 秒、Medical Coding 10 秒。全局 P95 即使合格，也不能掩盖任一高时延专用 Agent 超预算。
- strict wrapper 在主失败时新增 `external_semantic_e2e_failure.json`，只记录执行阶段、退出码与日志字节数，不保存异常正文、日志正文或凭据；下一次异常不会再丢失终态诊断。

## 验证结果

- 最终扩大无网络回归：**493 passed、0 failed**，覆盖全部 CDI 单元、公开 A2A 投影、成本/RunHistory/账本、Trace 严格白名单、Agent Hub happy/adversarial/reference/stability/bundle、凭据 runner 安全、wrapper 失败诊断与部署预检。
- 有界并发测试证明 5 条输入的峰值并发严格为 2，返回顺序与输入一致。
- 安全门计量测试证明 claim-evidence 与 semantic-necessity 各产生一条无临床内容的调用记录，并进入聚合 call-count/token/provider latency。
- 静态部署预检 [`deployment_preflight.json`](../../reports/deployment/cdi_gate_telemetry_latency_phase_20260826_v2/deployment_preflight.json)：**101/101**，SHA-256 `ae5fbe9bc65015ca34adcb3ba13acf0403aead35a06fa1d6799f93b55bb919f2`。
- live stability：整体 **156/156**、P50/P95 **0.753/6.348 秒**、成本覆盖 **156/156**、unknown 0；配置估算总额 CNY 0.01162510。
- CDI 六次调用数为 7–11（旧 Trace 为 3–4），证明逐 Query 安全门已进入 aggregate；CDI 配置估算合计 CNY 0.01006110，Medical Coding CNY 0.00156400，均为 `billing_authoritative=false`。
- 本轮变更及生成范围长 Key 形态扫描命中 0；专用窗口标题确认 Key 已清除。用户仍应在 DeepSeek 控制台撤销该临时 Key。
- 受保护数据库保持 8,536,064 bytes、最后修改 `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。

## 证据口径修订

历史只读回放 [`cdi_cost_telemetry_replay.json`](../../reports/agent_hub/cdi_cost_telemetry_offline_replay_20260825_v1/cdi_cost_telemetry_replay.json) 已从 `passed` 修订为 `partial_historical_replay`。旧 Trace 的 CNY `0.00428106` 仅是当时已记录主阶段/Expert 调用的下界估算；它不包含当时遗漏的逐 Query 安全门调用，不能提升原权威成本覆盖率，也不能作为完整 CDI 成本或 Provider 账单。

## 下一门禁

1. 下一次需要真实 Provider 时，先验证 wrapper 能生成顶层 success 或内容无关 failure evidence；无需为了重复已有调用结果立即消耗新 Key。
2. 以修正后的并发时延合同生成新 Trace，确认 overlap 时 `non_provider_wall_latency_known=false` 且不输出虚假 0；本次 `224918` Trace 生成于该跟进修复之前，不能证明这一字段。
3. Provider 控制台/账单对账、50 次独立临床校准、Corti 同病例盲评、医院工作流与生产容量仍为外部门禁，不因本轮工程通过而提升。
