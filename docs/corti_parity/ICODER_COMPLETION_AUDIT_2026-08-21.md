# iCoDer × Corti 总目标完成性审计（2026-08-21）

本审计按总目标逐项核验证据，不以“测试未发现问题”代替完成证明，也不把开发候选、
单次连通性或历史真实调用扩大解释为临床生产等价。

## 要求—证据—结论

| 总目标要求 | 当前权威证据 | 结论 |
|---|---|---|
| Agent Hub 所有用户可见 Agent 不再是 metadata-only/stub/MVP | 最新运行矩阵为 32 个磁盘 Pack、26 个 Hub 可见 Agent；可见面 26/26 executable、provider-resolvable、launch-candidate-ready，0 个可见 stub；6 个隐藏 Pack 中 5 个 metadata-only | **开发环境已证明** |
| 用户可见 Agent 可审计、可测试 | 26/26 具备严格输出白名单、递归 schema、值/关系/证据/跨 Agent 门禁、Run/Trace 和人工复核策略；最新扩大回归 194/194 | **开发环境已证明** |
| Agent 可作为上线候选 | 26/26 满足开发发布候选静态门；部署预检 51/51 | **仅开发候选已证明**；不等于临床或生产批准 |
| Corti 预构建能力目录对齐 | 历史 `corti_prebuilt_agent_catalog.json` 为 20/20 mapped；2026-08-21 官方公开文档显示当前 v2 已统一为五类 connector，并增加 A2A v1.0、context/task、OpenInference 和 feedback | **历史目录映射已证明**；当前 Agentic v2 协议等价未证明，不能继续用 20/20 关闭该要求 |
| 完整端到端测试 | 两套 26-Agent mock HTTP 矩阵证明成功/失败关闭和审计链；历史 DeepSeek 证明 Diagnosis、Medical Coding、Note Completeness、Code Validation 的部分真实链路；本轮 diagnosis 修复后唯一一次真实复测通过 v6 并签名，但 `search_icd` 不可用使 Provider incomplete 且必须人工复核 | **部分证明**；缺受治理 ICD 检索闭环和 26-Agent 真实模型快乐/对抗/重复矩阵 |
| 依据 Corti 当前可访问产品逐项输出差距 | 已登录 Corti Console 的只读目录、Models、Medical Coding、Embedded、Templates、Usage/API Client 证据已归档；当前差距矩阵逐层区分开发、环境和外部门禁 | **产品面差距已记录**；没有同病例双边预测或 Corti 私有 SLA/模型证据 |
| 三语言 SDK | JavaScript beta.17 31/31 且生成 `.tgz`；Python b17 38/38 且生成 `.whl`；两个本地工件均写入 SHA-256 manifest；.NET beta.17 源码/反例/CI 合同已补齐；release validator 5/5，manifest 为 `source_tree_state=dirty` 且明确未发布 | **JS/Python 本机工件已证明；当前工件不是干净提交的可复现正式发布物；.NET 未编译，registry 发布未发生** |
| Models/真实网络安全 | secret-free 目录、租户精确路由、出境门禁、默认关闭的固定无患者数据 Canary、预算/token/超时/单次/冷却/审计和三 SDK 门禁；后端组合 116/116 | **工程合同已证明**；真实 Canary 尚未执行，持续健康/SLA 未证明 |
| Corti Agentic v2 | OpenAPI 已由 241 paths 增至 252 paths：7 个 A2A v1 路径和 4 个 Connector 资源/graph 路径；A2A Send/Stream/Get/List/Cancel、五类 Connector 持久化/安全 CRUD、失败关闭执行器、通用 Provider HTTP Run 及同步 A2A v0.3/v1 管理员受控顺序 graph 已实现；已有 v1 Task 会落成功/失败终态且无失败 Artifact，A2A Run/Trace 和 Connector task 审计可查；Graph 文件 10/10，联合回归 364/364，JS SDK 32/32、Python SDK 39/39 | **部分实现**；`returnImmediately`/Subscribe/持久事件、动态/标准 well-known card、专用 Agent graph、条件/并行 Planner、生产 transport/provider adapter、.NET SDK、OpenInference 和 feedback 仍未完成，见 [`ICODER_AGENTIC_V2_MIGRATION_DESIGN_2026-08-21.md`](ICODER_AGENTIC_V2_MIGRATION_DESIGN_2026-08-21.md) |
| 中国医疗场景适配 | ICD-10-CN、ICD-9-CM-3、编码过滤、CDI、中国编码签名主链、CN 严格出境、DRG/DIP 非权威失败关闭治理 | **工程适配已证明**；合法官方/地区/医院规则、许可和结算验收未证明 |
| 真实上线 | 无医院接口验收、独立临床盲评、法务/等保/认证、云容量/灾备/SLA、真实支付结算 | **未完成，且不得由开发机关闭** |

## 当前主机可执行性

2026-08-21 本机只读探测：

| 能力 | 状态 | 影响 |
|---|---|---|
| Python / Node / npm | 可用 | 后端、前端、JavaScript/Python SDK 和静态发布门已执行 |
| .NET CLI | 不可用 | net8.0/net10.0 与 NuGet 必须由 CI 或安装了 SDK 的环境执行 |
| Docker CLI | 不可用 | 镜像启动、Compose、SBOM、漏洞和 Nginx 容器 E2E 未执行 |
| PostgreSQL/`psql` / 5432 | 不可用 | 行锁 SQL 合同已测，真实多进程并发未证明 |
| Redis / 6379 | 未监听 | 本机未做真实队列/跨进程状态验证 |
| iCoDer / 8000 | 当前未监听 | 修复后单次 DeepSeek 回归已完成；临时后端已停止 |
| 浏览器重型 E2E | 主机已有内存访问崩溃风险 | 保留 API/组件/生产构建证据，不强行启动 Chromium |

## 尚可在当前开发机完成

1. 停止本轮临时后端，立即注销/轮换已经暴露于会话的临时凭据。
2. 把已完成的通用 Provider HTTP Run/同步 A2A 顺序 graph 共享到专用 Agent，完成 `returnImmediately` 异步 Task、条件/并行 Planner、动态 Agent Card、A2A v1.0 Subscribe/持久事件和 .NET SDK，并实现 OpenInference 脱敏投影及 task/message feedback。
3. 修复本地 Compose/文档/CI 的远端检索接线：当前 `ml` profile 可声明 Worker，但后端 URL 默认为空；无原生合同 31/31、Cloud 配置 40/40、静态预检 51/51 和索引哈希已通过，仍须在具备 Docker 的 Linux 环境启动 Worker/API 并执行真实检索 E2E。
4. 若要继续 26-Agent 真实模型矩阵，必须重新取得明确的调用数量/预算授权；一次连通或
   单 Agent 成功不能自动扩大为全量付费测试授权。

## 必须保留的环境或外部门禁

- Linux/.NET 双框架 CI、真实 PostgreSQL 多副本、Docker/Nginx、SBOM、镜像漏洞与签名。
- Corti 与 iCoDer 使用同一去标识金标准病例的双边预测、盲评、准确率/严重错误率、
  P50/P95、成本和稳定性。
- 国家/省市/医院合法授权的编码、医保、DRG/DIP 规则及生效期、回滚和结算对照。
- 医院 HIS/EMR/FHIR、身份、网络隔离、数据治理、临床流程和上线验收。
- 中国法务、个保/数安/网安、等保、备案/认证、必要的数据出境评估。
- 独立临床 reviewer、医院编码员、双盲金标准、偏差/安全评估。
- 云 KMS、容量、监控告警、灾备、值守和 SLA 演练。

## 审计结论

当前可以证明的是“26 个用户可见 Agent 的开发环境工程上线候选”，不能证明“完整复刻
Corti 托管/临床生产能力”。总目标保持未完成；单次修复后 DeepSeek 回归已经完成，A2A
v1 首个兼容切片、五类 Connector 安全 CRUD、本地失败关闭执行器和通用 Provider HTTP Run/同步 A2A 顺序 graph 也已落地。最近的可执行工程步骤是补专用 Agent graph、真实异步 Task、条件/并行 Planner、动态 Card 和 Subscribe/持久事件，
同时闭环受治理 ICD 检索；真实模型矩阵仍须另行取得明确预算授权。
