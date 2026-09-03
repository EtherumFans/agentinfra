# Run SSE 可观测性与注册安全阶段总结（2026-08-15）

## 阶段结论

本阶段把 Run SSE 从“可恢复但缺少安全运维指标”推进为可按 API 进程抓取、可跨进程聚合、可计算 P50/P95/P99 并具有参考告警判断的开发上线候选能力。指标合同只接受固定枚举和数值，不接受 Run、组织、用户、游标、token、事件名或临床内容标签。

双独立 uvicorn + 轮询故障代理 + 三套真实 SDK consumer 的 E2E 同时验证了断流恢复行为和两个进程的指标抓取。该证据不等同于生产 Prometheus、告警交付或 Corti 托管 SLA；目标平台仍须安装并演练采集器、聚合器、告警路由和响应流程。

## 完成内容

1. 新增线程安全、2048 样本有界的 Run SSE 进程指标：连接尝试/接受/活跃、恢复连接、数据事件、心跳、固定枚举拒绝/关闭原因、trace-token 续签结果、恢复耗时与流持续时间 P50/P95/P99/max。
2. 未知原因强制折叠为 `other`/`other_failure`，禁止将任意请求值转换为标签，避免 PHI 泄漏和高基数失控。
3. 增加三个参考告警判断：20 个样本后意外关闭率大于 10%，20 次续签后失败率大于 5%，10 次恢复后 P95 大于 2 秒。当前只是进程快照中的判断，不宣称生产告警已接通。
4. `/api/metrics` 明确改为 `single_api_process` JSON 快照，响应 `Cache-Control: no-store`。访问仅允许平台 admin JWT 或 KMS 注入的 32–512 字符专用 monitoring bearer；普通租户 coder 返回 403，无凭证返回 401。
5. Cloud 配置与本地 Compose 加入 `ICODER_METRICS_BEARER_TOKEN`，Cloud 模式对缺失/过短凭证失败关闭。运维必须逐 worker/pod 直连抓取，不能把负载均衡后的单次响应误当聚合值。
6. SSE 成功响应增加 `X-iCoDer-SSE-Resumed`，Partner CORS 显式暴露该头；事件保留期头继续保留。
7. 修复旧通用请求指标的潜在高基数问题：如果未来启用中间件，只使用 FastAPI route template，不再用包含资源 ID 的原始 URL；计数器访问增加线程锁。
8. 安全审计发现公共注册直接信任请求 `role`，调用者可自报 `admin`。现公共注册仅允许最低平台角色 `coder`，组织创建者仍是组织 owner；提权尝试返回 `SELF_ASSIGNED_ROLE_FORBIDDEN`，不创建用户并写入 `MODERN_SYSTEM` 安全审计。
9. 密码重置一次性原始凭证不再写入应用日志；同时补上该模块原先缺失的 logger 定义。

## 验证证据

- 扩大后端回归：**171 passed, 1 skipped**。跳过项仍是本机无 PostgreSQL 的条件合同，不能计作 PostgreSQL 通过证据。
- 指标、SSE、鉴权和注册核心目标回归：**43/43** 与 **30/30** 分组均通过。
- 三 SDK 双进程故障 E2E：[local_e2e_20260815_sse_observability.json](../../reports/sdk/local_e2e_20260815_sse_observability.json) 为 `passed`。
- E2E 从两个独立 API 进程直接抓取并聚合：连接尝试 **15**、成功流 **12**、游标恢复 **6**、数据事件 **27**、续签成功 **3**；三套 SDK 均完成过期 token 续签、两次 TCP 断流和终态恢复。
- E2E 报告明确记录固定枚举标签策略，`real_llm_used=false`，未使用真实 LLM 密钥，未加载 Windows 原生 ML 栈。
- OpenAPI 重新导出并通过 `--check`。
- 静态部署预检：[development_preflight_20260815_sse_observability](../../reports/deployment/development_preflight_20260815_sse_observability/) 为 **32/32 checks pass**，并明确声明未安装生产采集器、跨进程聚合器、告警投递或 SLA。

## 与 Corti 的当前差距

| 能力 | iCoDer 当前证据 | 尚未关闭的差距 |
|---|---|---|
| SSE 断流/恢复指标 | 双进程三 SDK E2E 与固定枚举指标均通过 | Corti 的内部指标、阈值和 SLA 不公开，无法逆向证明等价 |
| 指标安全 | 无业务 ID/PHI 标签、有界样本、专用监控凭证、no-store | 仍需独立安全团队验证采集链、日志链和监控系统权限 |
| 跨进程聚合 | E2E 明确逐进程抓取并在测试协调器聚合 | 尚无生产 Prometheus/OTel collector、长期存储和 dashboard |
| 告警 | 三项参考告警状态可计算且有单元测试 | 尚无 PagerDuty/短信/企业微信等投递、静默、升级和演练证据 |
| 认证与注册 | 公共注册自助提权已失败关闭并审计 | 企业 SSO、邀请制角色分配、审批和定期权限复核仍需产品/医院流程 |
| 生产可靠性 | SQLite 双进程故障代理验证恢复 | 真实 PostgreSQL/Nginx、滚动发布、强杀、背压、连接耗尽和跨区未实跑 |
| Agent 临床质量 | 26/26 Hub Agent 工程链继续可运行、可审计 | 仍缺新安全 LLM 凭证下的统一病例金标准、医院 reviewer 和 Corti 同病例对比 |

## 下一阶段优先级

1. 继续审计公开鉴权/邀请/角色变更路径，确保平台角色与组织角色不混淆，补齐管理员赋权的受审计最小权限流程。
2. 在开发环境生成 Prometheus/OTel collector 与 dashboard/alert rule 部署候选，但保持未在真实云运行的诚实标记。
3. 在 Linux CI/预发布环境运行 PostgreSQL 16、真实 Nginx/Ingress、强杀、滚动升级、慢消费者、连接耗尽和恢复耗时验证。
4. 使用新的可撤销临时 LLM 凭证与统一去标识病例，执行 26 Agent 多轮质量、成本和延迟基准；不得复用此前暴露的密钥。
5. 推进真实中文医疗 ASR、隔离 Linux BGE/FAISS、地方医保规则包、医院审核与中国云合规门禁。

总目标继续进行中；本阶段不能标记 `production_ready`、Corti 等价、医院可上线或 SLA 达标。
