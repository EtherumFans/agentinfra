# Agent Hub E2E 鉴权与原生运行安全阶段总结（2026-08-15）

> **声明**：本文记录开发环境鉴权、运行归因和 Windows 原生依赖失败关闭证据，不构成临床上线或 Corti 临床等价声明。
> **日期**：2026-08-15
> **阶段**：Agent Hub E2E authentication and native-runtime safety
> **状态**：DEVELOPMENT GATE PASSED；FULL LIVE-LLM AND EXTERNAL GATES OPEN

## 阶段结论

本阶段关闭了三个会妨碍 Agent Hub 全量 E2E 和 Windows 稳定性的真实缺口：Agent Chat 切换 API Client 后可能使用旧选择；快乐/对抗/稳定性 runner 依赖源码硬编码测试密码；`ICODER_DISABLE_NATIVE_MEDCODER=true` 虽已声明，但 ICD-9-CM-3 健康检查仍会导入 FAISS。

修复后，Agent Chat 的统一 Run 请求会使用当前所选 API Client；E2E runner 只接受环境 bearer、成对环境账号密码，或显式 `--allow-self-register`；自注册严格限制在 loopback 隔离服务。显式禁用原生 MedCodER 时，ICD-10 与 ICD-9 两条健康检查均不导入 FAISS，BGE/subprocess 路径保持关闭。

## 本阶段完成

1. `AgentChatPage` 的提交回调加入 `selectedApiClient` 和 `refreshRunHistory` 依赖，Medical Coding 与其余 Agent 两条统一 Run 分支均继续传递 `api_client_id`；移除“placeholder selector”过时标记。
2. 26-Agent 快乐、对抗和稳定性 runner 的鉴权统一为：
   - 优先读取 `ICODER_E2E_BEARER`，兼容既有 `ICODER_BEARER`；
   - 或读取成对的 `ICODER_E2E_USERNAME`/`ICODER_E2E_PASSWORD`，缺一即失败关闭；
   - 未提供凭证时默认拒绝执行，不再轮询源码中的演示密码；
   - 只有显式 `--allow-self-register` 才创建随机用户、密码、组织和租户 token，且目标必须是 `localhost`、`127.0.0.1` 或其他 loopback 地址。
3. Live Agent Hub CI 的快乐、对抗和稳定性三条命令均显式使用 loopback 自注册，解决干净 PostgreSQL runner 没有预置 admin 导致登录失败的问题；没有向工作流写入固定密码。工作流现在使用应用实际读取的 `DATABASE_URL`，并在启动 API 前执行 `python -m alembic upgrade head`；集成测试作业继续同时保留 pytest fixture 所需的 `ICODER_DATABASE_URL`。
4. `ICODER_DISABLE_NATIVE_MEDCODER` 现在是实际运行时门禁，并优先于 Windows BGE 风险 override；设置后返回 `operator_disabled_native_medcoder`。
5. ICD-9-CM-3 检索健康 helper 新增 `allow_native` 与禁用原因参数，启动代码把与 ICD-10 相同的安全判定传入，消除第二条绕过门禁的 FAISS 导入路径。

## 真实开发环境证据

- 早期本地验证错误使用了 `ICODER_DATABASE_URL`，而应用实际读取 `DATABASE_URL`，因此随机 E2E 主体及其 Run/审计记录曾写入开发 SQLite。发现后按已审计的精确主体 ID 在单个事务中删除 2 条审计、1 条 Run、9 条组织内置模板、1 条组织成员、1 个组织和 1 个用户；随后复核开发库中 `agent-e2e-*` 主体及相关记录均为 **0**。这一事件同时促成 CI 数据库变量和迁移步骤修复。
- 最终权威验证使用 `DATABASE_URL=sqlite+aiosqlite:///./data/e2e_auth_isolated_final.db` 启动 `127.0.0.1:8014`。runner 未配置 bearer/账号密码，通过 `--allow-self-register` 创建随机租户主体；`compliance-guardrail-agent` 完成 HTTP 200、Run/trace、输出合同、类型/schema、内容安全、人工复核和禁止生产写回检查，结果 **1/1 passed**。同一最终启动日志中 `faiss.loader`、Torch、sentence-transformers 导入行均为 **0**，`operator_disabled_native_medcoder` 为 **2**。权威证据位于 `reports/agent_hub/e2e_auth_native_isolated_final_20260815/`。
- 最终临时服务已按精确 PID 终止，隔离数据库文件已删除；8012/8013/8014 端口均已清空，开发库复核无残留 E2E 主体。

## 回归与门禁

- E2E 鉴权、对抗矩阵、稳定性基准定向：**27/27 passed**。
- 原生运行安全与双编码索引健康：**25/25 passed**。
- API Client 归因、E2E、运行安全、运行矩阵与部署组合：**86/86 passed**；仅保留第三方 TestClient、旧测试时间 API 和测试短 HMAC key 警告。
- 前端全量：**116/116 passed**，18 个测试文件；TypeScript/Vite 生产构建通过。
- OpenAPI `--check`：通过。
- Agent Hub 矩阵：磁盘 Pack 32、可见 26、隐藏 6；可见 **26/26** executable、provider-resolvable、launch-candidate-ready、contract-complete。
- 部署候选静态预检：通过，无失败检查。
- CI YAML 可解析，`git diff --check` 无新增空白错误。

本阶段所有命令均删除真实 LLM 凭证并固定 `LLM_PROVIDER=mock`、`ICODER_ALLOW_EXTERNAL_LLM=false`、`ICODER_DISABLE_NATIVE_MEDCODER=true`。没有调用真实 LLM/ASR、没有访问 Corti 或消耗 credits。

## 相对 Corti 的剩余差距

1. 本阶段只对规则型 Compliance Agent 做了新的隔离 HTTP 正向实跑。其余 25 个 LLM Agent 在无密钥时继续正确失败关闭；仍需新的安全临时凭证运行 26 happy、26 adversarial 和两轮 104 条稳定性观测。
2. API Client 归因现已从 Console 当前选择贯穿统一 Run、trace 和 RunHistory，但真实合作方 OAuth Client 的限流、配额、账单和托管环境调用仍需外部部署验证。
3. 原生禁用门禁消除了 Windows API 进程加载 FAISS 的风险，但不提供语义检索能力；上线候选仍需要隔离 Linux worker、冻结索引、容器故障注入、性能、SBOM、扫描和签名证据。
4. Corti 的同病例临床输出、准确率、严重错误率、STT 质量、托管 SLA 和企业支持仍未被本阶段证明。
5. 医院 HIS/EMR、真实 PostgreSQL 多副本、KMS、对象存储、灾备、等保/隐私/法律与独立 reviewer 验收仍是外部门禁。

## 凭证安全

此前在对话中暴露过的 DeepSeek 密钥不得复用，仍应在 Provider 控制台注销或轮换。后续真实 E2E 应把新临时密钥和 bearer 仅放在启动进程环境中；runner 不打印、不持久化 Authorization header 或密码。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-15 | 修复 Agent Chat 客户端状态陈旧、E2E 源码密码与 ICD-9 原生门禁绕过；新增 loopback 自注册和进程级证据 | Agent Hub 全量 E2E 可执行性与 Windows 崩溃防护审计 |
