# iCoDer CDI 成本遥测阶段总结（2026-08-25）

## 结论

严格 26-Agent 真实 Provider E2E 暴露的 CDI 成本投影路径已在开发环境实现：CDI 专用运行时只在真实模型调用及完整 token usage 均被观察到时，使用当前配置的 CNY 每百万 token 价格生成成本估算，并沿 A2A metadata、统一 Agent Run 响应、RunHistory 和 Usage 聚合传播。估算固定标记 `source=configured_usage_pricing_estimate` 与 `billing_authoritative=false`，不会冒充 Provider 发票。

后续性能审计发现，本阶段最初只聚合 `RealCDIRunner` 的主阶段与 Expert 调用，遗漏了 claim-evidence 与 semantic-necessity 两个必需安全门内部的逐 Query LLM 调用。因此下文旧 Trace 重算已降级为“历史已记录调用的下界估算”，不能证明 CDI 全调用成本完整；当前代码已增加安全门内容无关计量，但完整闭环仍必须由 fresh live-provider 回归证明。

原权威运行 [`external_semantic_e2e_live_20260825-212957`](../../reports/agent_hub/external_semantic_e2e_live_20260825-212957/) 生成于修复之前，其中 CDI 6 次成本仍应保持 unknown；本阶段没有回填或改写原报告。后续 [`224918`](../../reports/agent_hub/external_semantic_e2e_live_20260825-224918/) 源级 stability 已得到 CDI 6/6 成本已知与总报告 156/156 覆盖，但 wrapper 在顶层 evidence 写入前终止，故 forensic recovery 不把该运行提升为顶层权威成功。

## 根因与修复

最终真实 CDI Trace 已记录主阶段/Expert 的模型、调用次数及 input/output/total token，但 `CDIA2AHandler → AgentRunResponse` 之间没有成本投影；同时该聚合 Trace 没有覆盖两个后置安全门的模型调用。稳定性 runner 正确地把缺失的 `response.cost` 判为 unknown。

- 新增 observed-usage-only CNY 估算器：缺调用证据、缺任一 token、价格为布尔/负数/NaN/Infinity 或标识缺失时返回 unknown，不根据病历字符数推断 token。
- CDI aggregate telemetry 在同一内容无关 Trace 中写入 `cost_amount`、`cost_currency`、`cost_source` 和 `billing_authoritative`；四个字段加入严格 safe-metadata allowlist，不保存 prompt、病历、模型输出或工具参数。后续补丁又把 claim-evidence 与 semantic-necessity 的实际调用纳入相同 observed-usage 聚合。
- CDI 成功、降级、合同失败和 attestation 失败路径都可保留已经发生且可证明的估算成本；临床结果仍按原失败关闭策略处理。
- 统一 Run 边界只接受 CNY、有限非负金额、指定估算来源且 `billing_authoritative=false` 的成本；USD、provider-invoice 或自称权威的 metadata 被丢弃。
- 统一响应中的金额继续进入现有 RunHistory 兼容列和 Usage 聚合；公开响应保留来源与非权威标志，避免把配置估算解释为供应商结算金额。

## 验证

- 最终聚焦组合回归：**256 passed、0 failed**，覆盖 CDI/Medical Coding 公共投影、CDI orchestration、专用 telemetry、Trace allowlist、Agent Run/RunHistory/Usage、账本结算、四类 Agent Hub 语义门禁、凭据 runner 安全与部署预检。
- 专用 API E2E 以无网络脚本化 CDI 响应证明成本从 CDI metadata 到公开 Run，再到 RunHistory：3/3。
- 静态部署预检：[`deployment_preflight.json`](../../reports/deployment/cdi_cost_telemetry_phase_20260825_v1/deployment_preflight.json) **101/101**，SHA-256 `43763f0f28e956dbfd8b27e1b86d1402edb1d2ed7449f13155d9d9f47dcc82a7`。
- 新增/生成范围通用长 Key 形态扫描命中 0；未使用真实 LLM Key或网络调用。
- 受保护开发库未改变：8,536,064 bytes，最后修改 `2026-08-22 17:16:22`，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。

## 对既有真实证据的只读重算

机器证据见已修订的 [`cdi_cost_telemetry_replay.json`](../../reports/agent_hub/cdi_cost_telemetry_offline_replay_20260825_v1/cdi_cost_telemetry_replay.json)。六份最终 CDI stability Trace 的哈希均已绑定，6/6 对“旧 Trace 已记录的主阶段/Expert 调用”具备完整 observed usage。按当前配置快照 `input CNY 0.14/1M`、`output CNY 0.28/1M` 重算：

| 场景 | 运行 | Input tokens | Output tokens | 调用数 | 配置估算 CNY |
|---|---:|---:|---:|---:|---:|
| adversarial | r001 | 2,544 | 1,427 | 3 | 0.00075572 |
| adversarial | r002 | 2,601 | 1,761 | 3 | 0.00085722 |
| adversarial | r003 | 2,448 | 1,371 | 3 | 0.00072660 |
| happy | r001 | 2,432 | 1,158 | 4 | 0.00066472 |
| happy | r002 | 2,530 | 1,065 | 4 | 0.00065240 |
| happy | r003 | 2,406 | 1,027 | 4 | 0.00062440 |
| 合计 | 6 | 14,961 | 7,809 | 21 | **0.00428106** |

该重算只证明旧 Trace 中已记录调用的 usage 足够支持新公式，合计 `0.00428106` 是历史记录范围的下界估算；它遗漏当时未进入聚合 Trace 的安全门调用，不是完整 CDI 成本，也不是 Provider 发票、账单对账、临床质量、Corti 对比或生产验收。

## 剩余差距

1. `224918` 源级报告已证明主阶段、Expert 与两个必需安全门进入 6/6 CDI stability 成本聚合，调用数 7–11、CDI 配置估算合计 CNY 0.01006110；但顶层 wrapper 终态失败，完整 phase success 仍未提升。原 `212957` 权威报告继续保持 150/156，旧离线重算不得改写它。
2. Provider 账单/控制台对账仍未完成；配置价格的版本、有效期、缓存/非缓存 token 档位和供应商价格变化需要运营治理。
3. CDI P95 仍为 28.067 秒。成本可观测性关闭不等于性能达标，下一开发切片应建立分阶段延迟预算、并行安全性与超时/重试门禁。
4. 独立临床校准仍为 0/50，Corti head-to-head、医院验收和生产就绪仍为 0/26。
