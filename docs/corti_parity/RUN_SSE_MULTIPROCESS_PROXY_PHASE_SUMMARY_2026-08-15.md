# Run SSE 多进程与代理可靠性阶段总结（2026-08-15）

## 阶段结论

本阶段把上一轮单进程自动重连合同推进到两个独立 API 进程、共享持久化 TraceStore 与轮询故障代理。JavaScript、Python、.NET 三套真实 SDK consumer 均完成“过期 token → bearer 续签 → 两次 TCP 提前断流 → UUID 游标续传 → 权威终态”，且请求在两个独立 uvicorn 进程间轮询。该证据证明开发环境中的客户端恢复、跨进程可见性和游标连续性，不等同于 Corti 托管可用性或生产 SLA。

本机没有 Docker CLI、`psql`、可连接的 PostgreSQL 服务或独立 Nginx 运行时，因此真实 PostgreSQL 16、容器 Nginx、慢消费者容量、进程中途重启、连接上限和跨区故障不能标记为已实跑。相应配置与条件测试已经接入门禁，但仍需 Linux CI/预发布环境产生运行结果。

## 本阶段完成内容

1. 生产与本地 Nginx 配置为三类 SSE 路径声明独立流式代理规则：HTTP/1.1、空 `Connection`、关闭响应/请求缓冲、缓存和 gzip，读写超时 75 秒，并返回 `X-Accel-Buffering: no`。应用 15 秒心跳，因此边缘允许四次心跳间隔后再关闭停滞上游。
2. 本地故障代理支持多个上游并逐请求轮询；它不记录包含签名 trace token 的 URL。每个 Run 的前两次成功 SSE 连接均在一个完整事件帧后主动截断。
3. SDK 本地 E2E 可启动两个独立 uvicorn 进程，二者共享同一临时 SQLite DB 和临时签名材料；代理让重连落到不同进程。三套 SDK 都通过续签、两次断流、两次游标推进和终态收敛。
4. 修复 DB TraceStore 的 PostgreSQL 驱动缺口：异步 API URL `postgresql+asyncpg://` 现在显式转换为同步 `postgresql+psycopg://`，默认 API 镜像加入固定版本 `psycopg[binary]==3.3.4`，不再隐式依赖未安装的 psycopg2。
5. 本地 Compose 连接 PostgreSQL 时现在默认 `RUNTRACE_STORE=db`、`RUNTRACE_FAIL_CLOSED=0`，避免“配置了 PostgreSQL但 trace 仍在进程内存”的重启丢失。云模板也显式选择 DB store；默认保持既有 `BEST_EFFORT_DB` 可用性策略，要求“无审计不运行”的合规部署应改为 `REQUIRED_DB` 与 fail-closed。
6. 新增真实 PostgreSQL 跨进程合同：进程 A 写入后退出，进程 B 从同一 PostgreSQL 读取并追加，父进程验证顺序、稳定事件 ID 与组织隔离。测试在本机明确跳过，已接入提供 PostgreSQL 16 的 Linux CI；CI 先运行 Alembic，再单独执行该门禁。
7. 部署候选预检新增持久化 TraceStore、Psycopg 3 同步驱动、云模板一致性和 Nginx SSE 规则检查。

## 验证证据

- 三 SDK 两进程真实 E2E：[`local_e2e_20260815_sse_multiworker.json`](../../reports/sdk/local_e2e_20260815_sse_multiworker.json)，状态 `passed`，`sse_api_processes=2`，代理策略为 `round_robin_across_independent_api_processes`。
- E2E 明确记录：Agent Hub 可见项 26/26；三 SDK 完成 token 续签、双断流续传与终态；未使用真实 LLM，未发送实时音频；Windows 原生 ML 栈保持关闭。
- 后端配置、RunTrace 与部署门禁组合：**40 passed, 1 skipped**。跳过项仅为本机没有 PostgreSQL 服务的条件测试，不计作 PostgreSQL 通过证据。
- 最终静态部署预检：[`development_preflight_20260815_sse_multiprocess_final`](../../reports/deployment/development_preflight_20260815_sse_multiprocess_final/)，**29/29 checks pass**，并在限制项中明确声明未运行 PostgreSQL、镜像、容量、灾备或 SLA 测试。
- `pip install --dry-run "psycopg[binary]==3.3.4"` 已确认 Linux/Windows 当前依赖可解析；本轮没有向父环境安装或注入新包。

## 与 Corti 的当前能力差距

| 能力 | iCoDer 当前证据 | 对 Corti 的阶段判断 |
|---|---|---|
| SDK 断流恢复 | 三语言 SDK、401 续签、双断流、UUID 游标和终态 E2E | 开发合同接近；缺 Corti 托管网络、限流、长期连接与 SLA 同口径数据 |
| 多进程连续性 | 两个独立 API 进程共享 DB 并轮询重连 | 已关闭单进程假设；当前实跑使用 SQLite，不是生产 PostgreSQL/负载均衡证据 |
| PostgreSQL 持久化 | 驱动、配置、迁移前置与跨进程 CI 合同已实现 | 代码候选已具备；必须等 Linux CI 或预发布真实运行结果后才能升级结论 |
| 反向代理 | Nginx SSE 关闭缓冲/压缩、声明心跳兼容超时 | 仅静态配置通过；缺真实 Nginx 容器抓包、慢消费者、上游重启和连接耗尽测试 |
| 重启恢复 | DB 设计与条件测试覆盖“写进程退出、另一进程续读”；双 API E2E跨进程续传 | 尚无正在流式传输时强杀/重启容器的实跑证据，Corti 托管可靠性仍领先 |
| 容量与可观测性 | 有界 SDK 重试与审计事件 | 缺连接数、积压、P50/P95/P99、重试原因、续签率、丢帧率和告警基线 |
| Agent/临床质量 | 26/26 Hub Agent 工程路径仍可运行并失败关闭 | 仍缺统一金标准、真实模型复验、医院 reviewer 与 Corti 同病例质量对照 |
| 中国场景 | ICD-10-CN、ICD-9-CM-3、DRG/DIP、中文病历与合规边界已有工程基础 | 仍需地方规则合法版本、真实医院验收、国产云/等保/数据驻留运行证据 |

## 下一阶段优先级

1. 在 Linux CI 或预发布环境运行新增 PostgreSQL 16 跨进程合同，保存工作流 URL、迁移日志和测试产物；失败时不得以 SQLite 结果替代。
2. 使用真实 Nginx/容器编排做强杀一个 API 实例、重启、滚动升级、慢消费者、连接耗尽与背压测试，核验不重复、不漏事件、终态唯一和恢复耗时。
3. 定义 trace 游标保留期、过期错误类型、清理审计和 SDK 专用异常；当前未知/已清理游标统一 409，不足以支撑长期运维。
4. 增加去 PHI 的 SSE 指标：连接尝试、断流原因、续签结果、游标推进、重试耗时和最终失败，并建立 P50/P95/P99 与告警阈值。
5. 使用新的、可撤销的临时 LLM 凭证和统一去标识病例运行 26 Agent 多轮质量/成本/延迟基准；不得复用此前已暴露的密钥。
6. 继续推进真实医疗 ASR、Linux BGE/FAISS worker、地方医保规则包、独立临床审核、云安全与认证门禁。

总目标继续保持进行中。本阶段不能把 `production_ready`、Corti 等价、医院可上线或 SLA 达标标记为通过。
