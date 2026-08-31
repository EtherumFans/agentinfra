# iCoDer 编排器 LLM 不可用失败关闭阶段总结（2026-08-22）

> 声明：本报告证明开发环境中的缺配置失败语义、公共/内部 Agent 边界和自动化回归，不代表真实模型临床质量、Corti 私有运行时等价或医院生产批准。

## 结论

Agent Runtime 的深度编排工厂过去在 LLM Gateway 缺失或没有 Provider 时返回一个伪造的 `model=stub`、`content={}` 响应。Planner 随后会拒绝空计划，所以它不会形成假临床成功，但 trace 会先把一次并不存在的模型调用表示成正常响应，最终错误也退化为通用 500。

本阶段已删除生产工厂的该 fallback。缺失或未配置 Gateway 现在直接抛出分类后的 `planning_failed`，HTTP 503、可重试，不生成模型名、正文、token、费用或临床输出。配置正常时仍使用真实 `LMGatewaySyncAdapter`；需要确定性响应的单元测试必须显式注入 test double。

## 公共 Agent 边界

应用装配回归同时发现一组旧 smoke 测试仍把 `medcoder-coding-review` 当作公共 Agent，并要求 mock provider 生成成功临床结果。这两个假设均已过期：

- `medcoder-coding-review` 是内部执行引擎，公共 A2A 路径稳定返回 404 `AGENT_NOT_FOUND`；不能为通过旧测试而重新暴露。
- `medical-coding-agent` 是规范公共 facade。mock provider 不能证明临床编码能力，当前稳定返回 503 且 JSON-RPC envelope 不含 `result`；不能伪造 message/task 成功。
- 真实 LLM 或受治理确定性 Provider 配置存在时，原有公开执行路径不受本次缺配置分支影响。

## 验证结果

- 工厂、Planner、InboundHandler、A2A 错误和部署预检聚焦回归：**135/135**。
- 真实 FastAPI lifespan、A2A 迁移和 Agent Run 应用装配回归：**55 passed、5 skipped**；跳过项为既有环境条件门禁。
- mock 公共/内部边界专项：**2/2**。
- 静态部署候选预检：**66/66**，新增 `orchestrator_missing_llm_is_retryable_503_without_stub_response`。
- OpenAPI 未发生合同变化，仍为 269 paths、288 schemas、842,015 bytes。
- 未使用真实 LLM、未允许外部 LLM、未加载 Windows 原生 MedCodER、未启动独立 8000 后端。
- 开发主库 `backend/data/icoder.db` SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

## 仍开放的差距

1. 503 只证明缺配置时诚实失败；不证明 DeepSeek、Qwen、Azure OpenAI 或 Corti 托管模型的连通性、语义质量、延迟、成本与 SLA。
2. 当前响应 wire contract 保留 `planning_failed` 业务码并通过 HTTP 503 表达服务不可用；没有新增非标准 A2A 业务码。
3. 完整 26-Agent 真实模型快乐/对抗/重复矩阵仍需轮换后的临时凭据、明确预算、全新响应和独立临床复核。
4. Docker/Linux MedCodER、PostgreSQL 多副本、生产队列、KMS、医院互操作、云、法务、认证和独立 reviewer 仍是外部门禁。

机器证据目录：`reports/agent_hub/orchestrator_llm_fail_closed_phase_20260822/`。

