# Agent Run 生命周期与残余假入口阶段总结（2026-08-15）

## 阶段结论

本轮完成了开发环境可关闭的 Run 运维控制与 Console 真实性缺口。26 个可见 Agent 共用的
Agent Run 入口现在具备组织绑定 OAuth 调用、状态查询、诚实取消和签名 SSE 生命周期事件；
三套 SDK 已通过同一临时租户服务的真实 HTTP/SSE 端到端验证。

这仍是开发上线候选，不是临床生产批准，也不证明与 Corti 的托管 SLA、真实模型质量、
容量、计费或正式发布渠道等价。

## 本轮发现并关闭的缺口

1. JavaScript SDK 仍声称后端没有 Run SSE，Python/.NET 也没有完整的状态、取消、事件入口。
   三套 SDK 现统一提供 Run 状态查询、取消和签名事件流。
2. Provider 无法中途停止时，后端过去以 HTTP 200 返回；现在返回 202 + `RECORDED_ONLY`。
3. `CANCEL_NOT_SUPPORTED` 过去被错误标记为终态，轮询方会提前停止，最终 Provider 状态也
   无法覆盖。现在它是非终态，结束后写入真实 `COMPLETED` 或 `FAILED`。
4. `CLIENT_ABORTED` 同样不再伪装成终态；Provider 成功结束后写入
   `COMPLETED_AFTER_CLIENT_ABORT`，失败则写入 `FAILED`。
5. OAuth Client 创建未绑定当前组织，机器 token 能访问公开 Hub，却不能真实调用或取消
   Agent Run。现在 Client 与 token 均携带权威组织作用域，取消接口同时支持用户与 OAuth
   principal，且继续执行跨组织 404 隔离。
6. Python OAuth 仍发送 JSON；现已按公开 FastAPI/RFC 6749 合同发送表单。
7. 已知不安全 Windows 原生栈下，API 启动健康检查仍会导入 FAISS DLL。现在只做资产存在性
   检查并显式降级，不再把已知会崩溃的原生库装入 API 进程；真实语义检索仍要求隔离的
   Linux worker。
8. AI Studio 的 STT、Text Generation、Embedded、Fact Extraction 卡片此前进入错误页面；
   现均进入各自真实工作台。Templates 的无动作反馈按钮现进入 Support 页面。

## 最终验证证据

- 前端：106/106，TypeScript 与 Vite 生产构建通过。
- 后端：Run/取消/审计 15/15；终态语义 3/3；OAuth 14/14；原生健康门禁 1/1。
- JavaScript SDK：15/15，`1.0.0-beta.7`，`npm pack --dry-run` 通过。
- Python SDK：22/22，`1.0.0b6` wheel 构建通过。
- .NET SDK：net8.0/net10.0 各 27/27，`1.0.0-beta.7` NuGet/Symbol 包含双框架资产。
- OpenAPI：导出与 `--check` 通过，取消接口明确包含 202 响应。
- 三 SDK E2E：[local_e2e_20260815_run_lifecycle.json](../../reports/sdk/local_e2e_20260815_run_lifecycle.json)
  记录 26/26 Hub、三种 OAuth form-token、Run 终态查询、`ALREADY_COMPLETE`、签名
  `stream.completed`，且无真实 LLM/ASR、无音频发送。
- 部署预检：[development_preflight_20260815_run_lifecycle](../../reports/deployment/development_preflight_20260815_run_lifecycle/)
  全部通过。

## 与 Corti 的阶段差距

Corti 公开 Agentic Architecture 明确包含 A2A Task 的 `canceled` 状态和 SSE 实时事件。本轮后，
iCoDer 在开发合同层已具备对应的状态、取消、流式事件与 SDK 消费面，并额外明确区分
“真正取消”和“只记录但 Provider 继续运行”。

仍未关闭的差距：

- 没有 Corti 托管环境下的长期任务、断线重连、限流、并发、跨区域与 SLA 对比证据。
- 没有同一批去标识病例在 Corti 与 iCoDer 上的真实 LLM/ASR 质量、延迟、成本和稳定性对比。
- 没有真实医院 HIS/EMR/FHIR、医保、地方 DRG/DIP 规则包和临床 reviewer 验收。
- 没有正式 registry 发布、包签名、独立渗透测试、等保/ISO/SOC 或生产云运维批准。

因此，总目标继续保持进行中；下一阶段应优先使用全新临时凭证和统一病例完成真实双边
模型复验，或在 Linux/Docker 环境完成隔离 BGE/FAISS worker 的运行门禁。
