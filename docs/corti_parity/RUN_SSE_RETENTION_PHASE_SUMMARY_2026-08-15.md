# Run SSE 保留期与过期游标阶段总结（2026-08-15）

## 阶段结论

本阶段关闭了 Run SSE “配置了保留天数但没有独立清理行为”的缺口。Run trace 现在具备可执行的 90 天默认保留策略、终态 Run 限定、持久化清理墓碑、聚合审计、只读 dry-run CLI、显式执行开关，以及 409 未知游标和 410 已过期游标/trace 的稳定区分。JavaScript、Python、.NET 三套 SDK 均把 410 映射为 PHI-safe、不可重试的专用异常。

该结论是开发环境上线候选证据，不是生产上线批准。生产调度器、真实 PostgreSQL/Nginx、备份与法务保留策略、容量/SLA、医院验收和 Corti 私有托管能力仍未完成。

## 本阶段完成内容

1. Alembic 040 为 `run_history` 增加 `trace_events_purged_at` 和 `trace_events_purged_count`，使清理后仍能可靠区分“从未有事件”和“事件已过保留期”。全新 SQLite 数据库已从头迁移到 head 并验证两列存在。
2. `purge_expired_run_trace_events` 只清理已终态 Run 的过期事件；RUNNING 事件和未过期事件不会删除。dry-run 只统计，execute 在同一事务中写墓碑、删除精确事件并产生 `retention.purge` 审计；删除数量不一致时回滚并失败关闭。
3. 运维 CLI 默认 dry-run，必须显式 `--execute` 才删除，可按组织精确收窄范围；stdout 固定为单行聚合 JSON，不输出 Run ID、游标或临床内容。

> 2026-08-22 更正：本阶段当时关于“`DEBUG=true` 时 SQLAlchemy echo 已关闭”的表述不完整。当前代码审计发现 `database.py` 仍把 `DEBUG` 直接用于 `echo`，本地 Compose 因此可能记录完整绑定参数。该缺口已在数据库日志隐私阶段真正关闭：SQL echo 与 DEBUG 解耦、默认关闭、Cloud 禁止，且应用引擎始终 `hide_parameters=true`。
4. Cloud 模式的保留期配置改为失败关闭：必须为正整数，且 trace 保留期不得长于 RunHistory 保留期。本地模式对非法值回退并将过长 trace TTL 收敛到 history TTL。
5. Run status、trace-token renewal 和 SSE 响应暴露保留天数及清理墓碑；成功 SSE 返回 `X-iCoDer-Trace-Retention-Days`。普通未知游标仍返回 409；存在清理墓碑时，缺失游标返回 `SSE_CURSOR_EXPIRED` 410，空 trace 返回 `SSE_TRACE_EXPIRED`/`TRACE_EXPIRED` 410。
6. 410 响应只包含安全代码、保留天数、清理时间和聚合数量，不回显游标。OpenAPI 已导出并通过 `--check`。
7. JavaScript `1.0.0-beta.10`、Python `1.0.0b9`、.NET `1.0.0-beta.10` 均加入专用 retention exception，并保证 410 不重试、异常不保存原始响应体或临床字段。
8. 跨进程 E2E 首轮发现 Python/httpx 对未缓冲流式错误响应直接调用 `response.json()` 会抛出 `ResponseNotRead`。现改为最多读取 64 KiB 后只投影安全字段，并新增未缓冲 body 回归；修复后整套 E2E 通过。
9. OAuth 初始化日志不再输出一次性生成的明文 client secret，只提示操作者通过显式创建流程接收一次性 secret。

## 验证证据

- 后端 Run/Trace/OAuth/配置/部署组合回归：**127 passed, 1 skipped**。唯一跳过项是本机没有 PostgreSQL 服务的条件合同，不计作 PostgreSQL 通过证据。
- 新增核心目标组合：**65/65 passed**。
- JavaScript SDK：**19/19 passed**，`npm pack --dry-run` 成功，包版本 `1.0.0-beta.10`。
- Python SDK：**27/27 passed**，`pip wheel --no-deps` 成功，包版本 `1.0.0b9`。
- .NET SDK：net8.0、net10.0 各 **31/31 passed**，双目标 pack 成功，包版本 `1.0.0-beta.10`。
- 三 SDK 双 API 进程真实本地 E2E：[local_e2e_20260815_sse_retention.json](../../reports/sdk/local_e2e_20260815_sse_retention.json) 为 `passed`。26 个 Agent 可见；三端均完成“过期 token → bearer 续签 → 两次 TCP 断流 → 跨独立进程游标续传 → 权威终态”。`real_llm_used=false`。
- 静态部署预检：[development_preflight_20260815_sse_retention](../../reports/deployment/development_preflight_20260815_sse_retention/) 为 **30/30 checks pass**，并显式声明没有安装或执行生产 retention scheduler/CronJob。
- 本轮未加载 Torch、FAISS、PyArrow 或 sentence-transformers，未触发已知 Windows 原生 ML 崩溃链。

## 与 Corti 的当前能力差距

| 能力 | iCoDer 当前证据 | 尚未关闭的差距 |
|---|---|---|
| Trace 保留与过期语义 | 真实清理、墓碑、审计、CLI、409/410、三 SDK 专用异常均有测试和 E2E | Corti 实际租户保留政策、归档能力和 SLA 不可由控制台只读信息反推 |
| 生产调度 | CLI 可安全 dry-run/execute，云配置失败关闭 | 尚无目标云 CronJob/调度器运行记录、告警、重试和失败演练 |
| 持久化与反向代理 | 双独立 uvicorn + 共享 SQLite + 轮询故障代理通过 | 真实 PostgreSQL 16、Nginx/Ingress、滚动升级、强杀、慢消费者和连接耗尽未实跑 |
| SDK 运维体验 | 三语言支持续签、断线续传、过期终态异常和安全错误投影 | 未在公开 registry/正式签名渠道发布，未验证 Corti 托管限流与长期连接策略 |
| 数据治理 | 终态限定、组织作用域、聚合审计、不回显游标/PHI | 医院及法务批准的保留期限、备份删除、诉讼保全和跨系统删除证明未完成 |
| Agent/临床质量 | 26/26 可见 Agent 工程路径可运行并失败关闭 | 仍缺新临时 LLM 凭证下的统一病例金标准、医院 reviewer、Corti 同病例质量/成本/延迟对比 |
| 中国场景 | ICD-10-CN、ICD-9-CM-3、DRG/DIP、中文病历和合规边界已有工程基础 | 地方规则合法版本、真实医院集成、国产云/等保/数据驻留与真实中文 ASR 仍是外部门禁 |

## 下一阶段优先级

1. 在 Linux CI 或预发布环境运行 PostgreSQL 16 跨进程合同，并以真实 Nginx/Ingress 做强杀、滚动升级、慢消费者、背压和连接耗尽测试。
2. 为目标云增加 retention CronJob/调度器、指标、告警和失败演练；由法务与医院确定 trace、RunHistory、备份和审计的正式保留政策。
3. 增加去 PHI 的 SSE 指标：连接尝试、断流原因、续签结果、410 数量、游标推进、恢复耗时、P50/P95/P99 和最终失败率。
4. 使用新的、可撤销的临时 LLM 凭证和统一去标识病例，生成 26 Agent 多轮稳定性与质量报告；不得复用此前暴露的密钥。
5. 继续推进真实医疗 ASR、隔离 Linux BGE/FAISS worker、地方医保规则包、独立临床审核、云安全和认证门禁。

总目标继续保持进行中；本阶段不能把 `production_ready`、Corti 等价、医院可上线或 SLA 达标标记为通过。
