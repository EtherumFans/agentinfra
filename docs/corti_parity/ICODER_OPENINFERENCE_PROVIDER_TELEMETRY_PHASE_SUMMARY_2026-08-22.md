# iCoDer OpenInference Provider Telemetry 阶段总结（2026-08-22）

## 结论

本阶段关闭了 Agentic Context `/trace` 中 Provider Registry LLM 与 Connector 的标准属性缺口：真实捕获到的模型 Provider、AI system、model、prompt/completion/total token、总成本、finish reason、tool name/id 现在投影为 OpenInference 语义属性；根 span 使用 `AGENT`，模型与工具 child span 分别使用 `LLM`、`TOOL`。缺失或非法 telemetry 继续省略，绝不补零、猜测或伪造。

这仍是中国医疗最小必要导出。API 不输出 prompt、病历、模型正文、tool 参数/结果、reasoning 正文或任意 Provider 原始 payload；每个 span 明确标记 `icoder.trace.input_exported=false` 和 `icoder.trace.output_exported=false`。

## 官方合同核验

2026-08-22 再次获取 Corti 官方 [`Export OpenInference traces`](https://docs.corti.ai/agentic/guides/export-traces.md)，HTTP 200，UTF-8 3,708 bytes，SHA-256 `c0185cd104d29e71638863841a3b0c21d2949e0b2200a2b86530bb725d0a76cd`。官方合同仍为单数 `GET /v2/agentic/contexts/{context_id}/trace`、最新优先、`pageSize` 最大 200、opaque `pageToken`、`totalSize` 当前不填充，并明确以 `llm.token_count.total`、`tool.name`、`input.value` 为示例属性。

iCoDer 保持路径、分页与 trace/span 结构兼容，但有意不输出 Corti 示例中的 `input.value`。这是中国医疗 PHI 最小化差异，不记为需要放宽的缺陷。

## 实现

- LLM Gateway 对成功 primary、pinned failure 和 fallback 结果补充真实选中 Provider provenance；已有 Provider 字段优先，不覆盖供应商返回值。
- Pure LLM 对单次调用提取有界 `provider/model/usage/cost/finish_reason`；成功、incomplete、degraded 与空响应均保留真实可用 telemetry。
- LLM-with-tools 对 preflight、每轮工具调用和最终 synthesis 的 token/cost 做真实汇总；Provider/model 发生变化时标记 `mixed`，不冒充单一模型。
- RunTrace 写入入口只接受 ASCII 有界模型标识、0–100,000,000 的整数计数、有限非负成本和稳定 finish reason；非法值直接省略。
- Context trace 投影新增标准 `llm.provider`、`llm.system`、`llm.model_name`、`llm.token_count.*`、`llm.cost.total`、`llm.finish_reason`、`tool.name`、`tool.id` 与 `session.id`。
- Rule Engine/普通编排事件继续是 `CHAIN`，没有模型证据时不会被误标为 LLM；Connector/tool 事件映射为 `TOOL`。
- 部署预检新增 `openinference_export_uses_standard_bounded_provider_tool_and_usage_attributes`。

## 验证

- 聚焦 Provider/RunTrace/trace export：83 passed；修正非法计数后复核 56 passed。
- Provider backend、A2A、RunTrace、模型路由、重试/降级、安全脱敏与部署门禁扩大串行回归：首次 677 passed/2 failed；其中一个 A2A artifact 时序失败无法独立复现，endpoint 文件 43/43 通过；另一个为旧云配置测试夹具缺少现行必填安全变量，补齐而未放宽生产策略。
- 同一扩大矩阵最终重跑：**679 passed、0 failed、100 warnings，159.77 秒**。
- OpenAPI：**270 paths、290 schemas、851,708 bytes**，无 schema drift。
- 静态部署候选预检：**74/74**。
- 未启动独立后端，未调用真实 LLM/ASR，未加载 Windows 原生 MedCodER；源数据库无迁移、无 cutover。

## 尚未完成/不得宣称

1. 本阶段证明 API JSON 的 OpenInference 语义投影，不等同于 OTLP Collector push、跨服务 W3C trace context 传播或第三方 APM 生产验收。
2. Provider Registry 的 Pure LLM/LLM-with-tools 与 Connector 已覆盖；专用 Medical Coding、CDI、ASR 只有在其运行链真实捕获同类 telemetry 时才会输出，不能推断其具备完整模型/token 属性。
3. 不输出 `input.value`/`output.value` 会降低调试复现能力；未来若要受控正文导出，必须另建高权限 purpose、独立 retention、患者/医院权威许可、DLP/去标识验证与失败关闭审计。
4. 真实 Provider、生产多副本、OTLP/APM/SIEM、医院环境、法务、认证和独立 reviewer 仍是外部门禁。

机器证据：`reports/agent_hub/openinference_provider_telemetry_phase_20260822/phase_evidence.json`。
