# Run SSE 自动恢复阶段总结（2026-08-15）

## 阶段结论

本阶段关闭了上一阶段保留的 SDK 自动重连与 trace-token 续签缺口。JavaScript、Python、.NET 三套 SDK 现在使用相同的失败语义：保存最后确认的 SSE 游标，只对网络中断或终态前 EOF 做有界指数退避；签名 trace token 明确返回 401 时，通过当前 bearer 身份续签；400、403、404、409、协议错误和临床错误均立即暴露，不会被重试掩盖。

该结论是开发环境中的运行合同和真实环回故障证据，不代表已取得 Corti 托管环境的可用性、容量、跨区容灾或支持 SLA。

## 实现内容

1. 新增 `POST /api/v1/runs/{run_id}/trace-token`。端点要求用户或 OAuth bearer 身份，按权威 Run 组织隔离，不存在、跨组织和不可见 Run 统一返回 404。
2. 新 token 继续绑定 Run、组织和 OAuth client（如适用），响应使用 `Cache-Control: no-store`。凭证只有在 `run.trace_token.renew` 审计事务成功后才返回；审计暂停或提交失败时以 503 失败关闭。
3. JavaScript `streamEventsResilient`、Python `stream_events_resilient` 和 .NET `StreamEventsResilientAsync` 均提供总连接次数上限、初始/最大延迟、指数退避、抖动、初始游标和取消/生成器终止语义。
4. 三套 SDK 均保留原有一次性流与手动 `Last-Event-ID` API，自动恢复是新增能力，不破坏旧调用。
5. 新增仅供本地 E2E 使用的环回故障代理。它不记录含签名 token 的查询字符串，并对每个测试 Run 的前两次成功 SSE 连接各截断一个完整事件帧；该脚本不被生产 API 导入。

## 版本与验证

- 后端 Run/trace-token/SSE/租户隔离/orphan/audit/API Client 安全组合回归：**97/97**。
- JavaScript `1.0.0-beta.9`：**18/18**，TypeScript 构建及 `npm pack --dry-run` 通过。
- Python `1.0.0b8`：**25/25**，wheel `icoder_sdk-1.0.0b8-py3-none-any.whl` 构建通过。
- .NET `1.0.0-beta.9`：net8.0 与 net10.0 各 **30/30**；NuGet/Symbol 包生成成功，主包同时包含两套框架资产。
- OpenAPI 已重新导出并通过 `--check`，大小 **627,658 bytes**；续签端点公开 200/401/404/503/422、`Cache-Control` 响应头和 `TraceTokenRenewResponse`。
- 静态部署候选预检通过，证据在 [`development_preflight_20260815_sse_resilient`](../../reports/deployment/development_preflight_20260815_sse_resilient/)。

## 真实端到端证据

[`local_e2e_20260815_sse_resilient.json`](../../reports/sdk/local_e2e_20260815_sse_resilient.json) 记录三套外部 consumer 均通过以下真实链路：

1. 启动随机环回端口的临时 uvicorn、临时 SQLite 数据库和 DB TraceStore；
2. 注册一次性组织用户并创建组织绑定 OAuth Client；
3. 为独立 Run 发放已过期 trace token；
4. SDK 首次连接收到真实 401，并通过 bearer 续签；
5. 环回代理在 `run.ingest` 后第一次断流；SDK 携带该 UUID 自动恢复；
6. 代理在 `run.completion` 后第二次断流；SDK 再次推进游标；
7. 最后一条连接只接收 `stream.completed`，终态为 `COMPLETED`，总业务事件数为 2；
8. 临时 API、代理、数据库、JWT、OAuth secret 和随机端口均由脚本回收。

E2E 使用 mock/degraded LLM 边界，没有调用真实 LLM/ASR、没有发送音频，也没有加载 Torch、PyArrow、FAISS 或 sentence-transformers。

## 与 Corti 的当前能力差距

| 能力 | 本阶段 iCoDer 状态 | 与 Corti 的判断 |
|---|---|---|
| SDK 长连接自动恢复 | 三语言有界重连、游标推进、401 续签、取消与失败分类，真实双断流 E2E 通过 | **开发环境合同基本对齐**；没有 Corti 托管网络、限流和 SLA 的同口径数据 |
| Run/Trace 授权与审计 | Run/组织/OAuth client 绑定，续签禁止缓存，审计失败关闭 | **工程控制较完整**；尚无独立安全审计或生产渗透结论 |
| 游标生命周期 | UUID 稳定恢复，未知/已清理游标目前统一 409 | **仍有差距**；缺明确保留期、过期错误码和清理策略公开合同 |
| 多 worker/反向代理 | 单进程 uvicorn + SQLite + 环回 TCP 故障已验证 | **Corti 优势**；缺 PostgreSQL 多 worker、负载均衡、代理超时、背压与容量证据 |
| SDK 交付 | npm/Python/NuGet 可构建，三语言真实 consumer 通过 | **开发候选**；尚未正式发布、签名、生成 SBOM/供应链证明或验证公网托管 API |
| Agent/临床质量 | 26/26 Hub Agent 仍为工程发布候选，输出/安全合同存在 | **未达到生产等价**；缺同一金标准数据集、独立临床 reviewer 和真实医院结果 |
| STT/Ambient | 中文安全主线、持久化和任务生命周期已有 | **Corti 仍明显领先**；缺多语种、说话人分离、多通道、生产对象存储和现场质量证据 |
| Billing/多区域/认证 | 只有开发接口、配置和静态预检 | **Corti 明显领先**；真实计费、跨区容灾、ISO/SOC/等保及医院合规均不是本机可闭环项 |
| 中国场景适配 | ICD-10-CN、ICD-9-CM-3、DRG/DIP、中文病历 Section 和失败关闭边界 | **方向性优势**；仍需地方医保规则版本治理和真实医院验收 |

## 下一阶段优先级

1. 在开发环境补 PostgreSQL 多 worker + 反向代理故障矩阵，验证顺序、去重、代理缓冲、连接上限、慢消费者和重启恢复。
2. 定义 trace 游标保留期、过期错误码和清理/审计合同，并加入三 SDK 明确异常类型。
3. 给自动恢复增加连接尝试、续签、断流原因和最终耗时的去 PHI 可观测指标，建立容量与混沌基线。
4. 继续 Agent 同输入/同量表离线评测、STT 多语/说话人能力、语义 Memory、真实 Experts/MCP 和地方医保规则包。

生产审批仍必须由真实医院、临床/编码专家、法务、独立安全 reviewer、云运维和认证机构完成。因此总目标保持进行中，不能把 `production_ready` 人为改为通过。
