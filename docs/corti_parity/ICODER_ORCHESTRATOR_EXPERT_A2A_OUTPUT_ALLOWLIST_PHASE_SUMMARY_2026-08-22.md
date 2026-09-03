# iCoDer 编排专家失败关闭与 A2A 输出精确白名单阶段总结（2026-08-22）

> 声明：本阶段证明运行时不会通过内置 noop/stub 专家制造成功，并证明带 Pack `schema_ref` 的 A2A `DataPart.data` 只公开声明的领域字段；不代表真实模型的临床质量、Corti 托管运行时等价或生产上线批准。

## 结论

编排器中仍可导入的 `noop_invoker` 与 `_stub_expert_invoker` 已从运行时代码和公开导出中删除。缺失或未知专家只有明确的非重试 503 `expert_failed`，测试所需的成功专家均改为测试文件内局部 fake，不能被生产装配误用。

A2A 输出边界同时收紧：21 个 Provider Registry Agent 与 Code Validation、Compliance Guardrail、Note Completeness 三条专用简单路由，会在 attestation 前按当前 Pack 的 `required_fields + optional_fields` 精确投影领域结果。统一 Run envelope 可继续保留工程诊断，但 `backend_provider`、`backend_type`、`finish_reason`、`tool_calls`、`structured_extraction` 等未声明字段不会进入带领域 `schema_ref` 的 `DataPart.data`；Provider 身份、延迟等传输信息只留在 A2A metadata。Medical Coding 与 CDI 既有专用验证路径继续失败关闭，使 26 个用户可见 Agent 的 schema-labelled A2A 输出边界保持一致。

## 修复内容

- 删除运行时 `delegator.noop_invoker` 及其公共导出。
- 删除运行时 `_stub_expert_invoker`；未知专家继续由 `unavailable_expert_invoker` 返回 503。
- 把 Corti-like orchestrator 成功专家改为测试局部 fake，并删除已不存在的 `_stub_llm_call` 旧导入。
- `ProviderA2AHandler` 在签名前投影 Pack 声明字段；签名覆盖与客户端实际收到的领域数据一致。
- 三条专用简单 A2A 路由执行相同投影，修复 Code Validation 曾泄露 10 个统一 Run 工程字段的问题。
- 更新旧回归：mock Medical Coding 现在必须 503、无 `result`；三条专用 Agent 断言当前不可变 Pack 契约，而非已删除的内部字段。
- 部署候选预检新增三项失败关闭门禁：无 noop/stub 专家成功、mock 临床成功被拒绝、Provider A2A DataPart 精确白名单。

## 验证结果

- 编排器、缺失专家和部署预检组合：**334/334**。
- 修复前扩大 A2A 诊断：236 passed、4 failed、5 skipped；四项均定位为旧假成功/旧字段断言及 DataPart 工程字段污染。
- 精确白名单聚焦回归：**13/13**。
- 最终扩大 A2A/API/可见 Agent/Task/Artifact/Connector 合同回归：**348 passed、5 skipped**；39 条为 Starlette TestClient 或测试日期 API 弃用警告。该集合包含真实 DeepSeek SSE 协议形状的离线 `MockTransport`，证明 provisional 阶段只公开字符计数等无正文遥测，终态才公开精确 Pack 字段。
- 静态部署候选预检：**72/72**。
- OpenAPI `--check` 通过，仍为 269 paths、288 schemas、842,015 bytes。
- 未启动独立后端，未调用真实 LLM/ASR，未加载 Windows 原生 MedCodER；端口 8000 未监听。
- 开发主库 `backend/data/icoder.db` SHA-256 保持 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

## 对 Corti 的差距判断

本阶段关闭的是运行时真实性和协议最小披露缺口：内部测试替身不再是可导入的生产能力，A2A 领域输出也不再混入实现细节。它提高了 SDK/外部 Agent 消费时的稳定性、签名可解释性和 PHI 最小化，但没有新增临床推理能力。

仍需使用轮换后的隔离凭据，对 26 个 Agent 执行完整快乐、对抗、重复和成本/延迟矩阵；还需用同一批合法去标识临床金标准与 Corti 做双边质量比较。Provider 原生首 token 流、真实中文 ASR、Linux MedCodER、外部 Connector、生产多副本、云 Secret Manager、医院互操作、法务、认证与独立临床复核继续是开放门禁。

机器证据目录：`reports/agent_hub/orchestrator_expert_a2a_output_allowlist_phase_20260822/`。
