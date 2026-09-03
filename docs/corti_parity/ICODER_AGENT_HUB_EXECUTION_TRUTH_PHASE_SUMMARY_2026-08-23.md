# iCoDer Agent Hub 执行真实性阶段总结（2026-08-23）

## 结论

本阶段关闭了“Provider 可解析即被写成 26/26 运行能力”的证据口径缺陷，并完成 26 个 Hub 可见 Agent 的离线 API 执行与审计复核。

- 26/26 Pack 为 executable、Provider-resolvable、结构性 launch candidate；21 个走 Provider Registry、5 个走专用路由、0 个 legacy fallback。
- 25/26 依赖外部 LLM；`compliance-guardrail-agent` 是唯一可在当前空凭据环境中完成本地确定性执行的 Agent。
- 静态清单不再推导语义质量：`semantic_live_e2e_verified=0/26`、`production_ready_verified=0/26`。
- 示例与对抗 API E2E 共 52/52 通过。25 个模型依赖 Agent 只允许稳定失败关闭、抑制领域结果并强制人工复核；Compliance Guardrail 返回契约有效的本地结果。
- 52 个 Run 均能查询审计 trace；对抗 canary 未泄漏。
- 修复 CDI 在 `LLM_PROVIDER=mock` 时返回安全错误但没有 trace 的缺口，现记录无正文的请求开始和失败完成事件。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 运行矩阵 v2 | 9/9 | 结构、依赖、语义证据和生产证据分轴 |
| 26-Agent 示例 API | 26/26 | 1 个本地能力完成，25 个安全失败关闭 |
| 26-Agent 对抗 API | 26/26 | 同上，且注入 canary 不泄漏 |
| CDI/契约/安全相关回归 | 29/29 | 包含 CDI trace 新语义 |
| Corti 历史 20-Agent 逐项映射 | 20/20 | 临床质量 0/20，生产就绪 0/20 |
| 部署候选静态预检 | 81/81 | 无失败项 |

机器证据位于：

- `reports/agent_hub/execution_truth_audit_20260823/runtime-matrix/`
- `reports/agent_hub/execution_truth_audit_20260823/offline-safety-e2e/junit.xml`
- `reports/agent_hub/execution_truth_audit_20260823/regression/junit.xml`
- `reports/agent_hub/execution_truth_audit_20260823/corti-prebuilt-parity/`
- `reports/agent_hub/execution_truth_audit_20260823/preflight/`
- `reports/agent_hub/execution_truth_audit_20260823/phase_evidence.json`

## 与 Corti 的剩余差距

历史 20-Agent 目录已全部映射并声明中国适配，但逐 Agent 报告仍为临床质量 0/20、生产就绪 0/20。主要未关闭项是同数据集临床准确率/召回率、医院工作流集成、真实支付方/药品/指南/编码资产、真实模型成本与 P95、托管模型池、KMS/Secret Manager、生产对象存储与独立 AV/OCR/DLP、Linux 原生检索 Worker、PostgreSQL 多副本和独立临床/法务/安全验收。

因此，本阶段证明的是开发环境中的路由、契约、安全失败和审计可用性，不是 Corti 私有模型质量等效，也不是中国临床生产批准。

## 安全状态

- 未读取或使用真实 LLM 密钥；本轮执行环境显式为空凭据、`LLM_PROVIDER=mock`、禁止外部 LLM、禁用原生 MedCodER。
- 未启动浏览器或 Uvicorn；8000/18022 端口关闭，无 Python/Uvicorn 残留进程。
- `backend/data/icoder.db` SHA-256 保持 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 测试 teardown 已删除隔离库中的表；宿主安全策略拒绝删除两个明确的空闲测试文件，当前仍保留 `backend/data/test_execution_truth.db`（1,699,840 bytes）和 `backend/data/test_execution_truth_regression.db`（1,654,784 bytes）。它们不是受保护开发库，可在允许删除文件的维护环境中清理。
