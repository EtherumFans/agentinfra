# iCoDer Agent Hub 运行就绪真实性阶段总结（2026-08-23）

## 结论

本阶段关闭了 Agent Hub 将“Provider 类已注册”误展示为“当前可用”的口径缺口。Hub schema 升级到 `1.3`，卡片和操作入口现在分别表达结构就绪、当前配置、语义验证、生产审批四个轴，不再把任一轴替代为另一轴。

当前空凭据、`LLM_PROVIDER=mock`、禁止外部 LLM 的开发配置下：

- 26/26 可见 Agent 均为结构性 launch candidate。
- 25/26 依赖外部 LLM，公开状态为 `unavailable / mock_provider`，`Use Agent` 操作被禁用。
- `compliance-guardrail-agent` 是唯一 `local_ready` 的本地确定性 Agent，操作保持可用。
- 26/26 均明确 `live_health_verified=false`、`semantic_validation_status=not_verified`。
- 26/26 均未取得生产审批；Pack 中 `production_ready=false` 不会被当前配置状态覆盖。

注入式配置合同测试还验证：存在受支持的 Provider 配置时，外部模型 Agent 只能显示 `configured_not_live_verified`，不能显示“在线健康已验证”；Provider 健康明细中的内部错误、端点或密钥类字段不会投影到公开 Hub。

## 实现结果

| 范围 | 本阶段结果 |
|---|---|
| 执行路径 | 专用路由、外部 LLM 目标、运行依赖与健康 Provider 映射集中到同一权威模块，运行矩阵复用该定义 |
| Gateway 配置判断 | 区分 mock、未注册、外联策略拒绝、已配置但未实网验证；返回无密钥的配置快照 |
| Provider health | Pure LLM 和 LLM-with-tools 在 mock/拒绝/未配置时返回 `degraded`，不再因对象存在而返回 `ok` |
| Hub API | schema `1.3` 新增 `execution_path`、`execution_target` 与四轴 `runtime_readiness` |
| 前端 | 显示当前运行状态和“语义质量未验证”；Provider 不可用时禁用 `Use Agent` 并解释原因 |
| 发布预检 | 从固定检查 schema `1.2` 升级为检查 `1.3` 四轴合同和禁用入口 |

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| Provider/Gateway/Hub/矩阵后端组合 | 96/96 | 包含 mock、配置存在、外联拒绝、原因脱敏、26 卡片状态 |
| 26-Agent 示例与对抗离线 API E2E | 52/52 | 1 个本地能力完成，25 个模型依赖 Agent 安全失败关闭；不是 26-Agent 语义成功 |
| Hub 前端契约 | 7/7 | 四轴字段、状态文案与禁用操作静态合同 |
| 前端生产构建 | 通过 | TypeScript 与 Vite 构建成功；仅保留既存分块警告 |
| 运行矩阵 | 26/26 | 21 个 Registry 路由、5 个专用路由、0 个 legacy fallback；语义 0/26、生产 0/26 |
| 部署候选静态预检 | 81/81，合同测试 1/1 | 首次发现旧 schema 字面门禁并完成同步后通过 |

机器证据：

- `reports/agent_hub/runtime_readiness_truth_20260823/phase_evidence.json`
- `reports/agent_hub/runtime_readiness_truth_20260823/backend-regression-junit.xml`
- `reports/agent_hub/runtime_readiness_truth_20260823/offline-safety-e2e-junit.xml`
- `reports/agent_hub/runtime_readiness_truth_20260823/runtime-matrix/`
- `reports/agent_hub/runtime_readiness_truth_20260823/preflight/`

## 与 Corti 的能力差距

本阶段只修复 iCoDer Console 的运行就绪真实性，没有产生新的 Corti 托管环境能力证据。对照 2026-08-21 已归档的 Corti 只读控制台观察和项目内当前公开文档基线：

- iCoDer 已能诚实区分结构、配置、语义和生产状态，并避免不可用 Agent 产生误导操作入口。
- 仍未完成 25 个外部模型 Agent 的当前真实 Provider 快乐/对抗/重复质量矩阵，语义验证仍为 0/26。
- 仍没有持续在线健康、P50/P95、容量、成本、配额和 SLA 证据；“配置存在”不等于 Corti 托管模型可用性。
- 仍缺 Corti 托管租户双向互操作、真实医院流程、独立临床金标准、中国权威编码/DRG-DIP 资产、法务/安全/认证及生产 SRE 门禁。

因此当前准确结论仍是“开发环境可审计上线候选”，不是“已复刻 Corti 全部能力”，也不是“中国临床生产可上线”。

## 安全与环境状态

- 未读取或使用真实 LLM 密钥；测试进程内两类密钥为空，外部 LLM 被禁止。
- 未启动浏览器或 TCP Uvicorn；8000/18022 无监听，Python/Uvicorn 残留进程为 0。
- `backend/data/icoder.db` SHA-256 保持 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 测试 teardown 已删除本轮隔离库中的表。宿主安全策略拒绝删除三个测试文件：`test_runtime_readiness.db`（2,007,040 bytes）、`test_runtime_readiness_regression.db`（2,007,040 bytes）、`test_runtime_readiness_e2e.db`（1,699,840 bytes）。它们不是受保护开发库，可在允许删除的维护环境中清理。
