# iCoDer 五阶段开发收口报告（2026-08-28）

## 结论

用户指定的五阶段内容已完成当前开发环境内可独立实现的部分，并形成可重复验证的证据链。该结论是“开发范围完成”，不是 Corti 全能力等价、临床准确性证明或生产上线批准。

## 已完成

### 1. 生产队列控制面、死信、告警与 Scheduler

- 数据库作为 durable queue 权威源；Redis 仅作无 PHI 唤醒信号，信号丢失时回退数据库轮询。
- 作业支持租约、续租、过期接管、generation/token fencing、幂等创建与取消。
- 尝试耗尽进入组织隔离 DLQ；重放校验不可变快照，幂等且阻断漂移。
- 持久化聚合告警支持触发和恢复；进程指标为低基数且不含患者标签。
- Scheduler 使用数据库时间和 generation fencing，避免主机时钟偏差及旧实例写入。
- Alembic 单链路扩展至 `063`；部署静态预检已纳入此控制面。

证据：`reports/deployment/clinical_shadow_control_plane_20260828_v2/clinical_shadow_control_plane.json`，8/8，通过；`production_broker_exercised=false`、`external_alert_delivery_exercised=false`。

### 2. 故障注入、恢复与有界长稳

- 强制终止 worker 子进程（退出码 91），新 worker 在租约到期后接管至 attempt 2，旧 fencing token 被拒绝。
- Scheduler generation 1→2，旧 Scheduler 写入被拒绝，恢复周期与终态周期完成。
- 16 路重复投递只有 1 个 claim winner。
- SQLite 写锁 0.5 秒后恢复，claim 恢复耗时 0.595 秒。
- 220 个循环、30.228 秒有界 soak：P50 130.649 ms、P95 153.028 ms、stuck active jobs 0、final health healthy。

证据：`reports/deployment/clinical_shadow_resilience_20260828_v1/clinical_shadow_resilience.json`，哈希与当前源文件一致。

### 3. 模型部署、对象存储、KMS 与安全扫描适配

- 建立可注入的 scanner、KMS、object store、deployment controller 协议。
- 扫描结果必须与 bundle digest 精确绑定且结论为 clean/clear。
- 使用 KMS data key + AES-GCM envelope，encryption context 绑定组织、包、证明和 digest。
- 对象存储采用 content-addressed key、`If-None-Match: *`、SHA-256 checksum 和 KMS SSE。
- 部署控制器只接收元数据，明确禁止 production traffic；扫描失败或 digest 漂移时停止后续外部调用。

验证：基础设施适配测试 3/3。真实云 KMS、S3/OSS、扫描器及部署控制器尚未联调。

### 4. 统一 26-Agent 离线评测平台

- 建立固定清单 `backend/evaluations/agent_hub_26_v1.json`，覆盖全部 26 个 Agent。
- 统一验证 required fields、类型、嵌套 schema、字段关系、证据 span/document 绑定、未声明字段与凭据泄露。
- 报告只保留聚合结果、case hash 和违规计数，不输出输入病例文本。
- 修复 CDI 官方示例中 3 处过期 evidence span，并刷新 Pack integrity。
- 参考包结果 26/26，contract pass rate 1.0；明确 `clinical_accuracy_proven=false`。

证据：`reports/roadmap/phases_3_to_5_20260828_v1/offline_evaluation.json`。

### 5. Memory、Experts/MCP、STT、SDK 与前端体验

- Memory 新增租户/用户/Agent/用途级聚合 readiness：同意状态、保留期限、加密、语义 Provider、词法降级和持久条数；不读取或返回记忆内容。
- Experts/MCP 新增聚合 readiness；MCP server 列表补上 Expert 组织所有权和 MCP 组织过滤。
- STT 新增内容无关 readiness，明确中文验证范围、加密数据库存储、重启恢复、单进程队列、非水平扩展和未完成 live health。
- JavaScript、Python、.NET SDK 均增加对应调用面；版本推进至 beta.50/b50。
- Experts、STT 和 Agent Detail 前端展示上述真实状态与生产阻断项。
- OpenAPI 已刷新：298 paths、327 schemas，`--check` 通过。

验证：readiness API 3/3；JavaScript SDK 97/97；Python SDK 14/14；前端生产构建通过。.NET 主机工具链不可用，因此源码已更新但发布前仍必须在装有 .NET SDK 的环境编译并跑测试。

## 汇总证据

- 阶段 3～5：`reports/roadmap/phases_3_to_5_20260828_v1/roadmap_phases_3_to_5.json`，`passed=true`，报告 SHA-256 `7fc879db09187e9cf218097f5c7dbf02a2095e09b5570af42329d9be5b91f029`。
- 部署静态预检：`reports/deployment/roadmap_preflight_20260828_v1/deployment_preflight.json`，全部检查通过。
- 整个验证过程未使用 LLM 凭据、患者数据或模型 Runtime。
- 受保护数据库保持 8,536,064 bytes、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- 授权工作簿保持 6,890,295 bytes、SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`。

## 尚未关闭的 Corti/生产差距

1. 在目标 PostgreSQL + Redis 多节点环境进行 broker、网络分区、主从切换和 24～72 小时长稳，并验证真实 PagerDuty/飞书/短信告警链路。
2. 使用目标云账号完成 KMS、对象存储、恶意文件扫描、镜像/依赖扫描、模型部署控制器与密钥轮换联调。
3. 用独立去标识临床金标准、盲法专科医生评审及真实 Provider 输出评估 26 Agent；当前 26/26 只证明契约与证据一致性。
4. 对外部 MCP、医院 HIS/EMR、医保/编码字典和区域网络策略做带凭据 E2E；完成中国数据出境、等保和院内安全验收。
5. 用真实中文临床音频验证 STT 准确率、噪声/口音、时间戳、并发容量；补对象存储和水平扩展队列。
6. 安装 .NET 工具链后编译测试 beta.50，并在 npm/PyPI/NuGet 发布前完成制品签名、SBOM、漏洞扫描和外部消费者 smoke。
7. 在已登录 Corti 控制台重新执行同输入、同约束的端到端对照，形成可审计的功能、延迟、输出结构和交互差距，而不能以本地测试替代 Corti 等价证明。
