> 声明：本文件记录开发环境阶段证据，不构成临床生产批准或 Corti 等效性声明。  
> 日期：2026-08-22  
> 阶段：完整后端默认测试门与 26-Agent 运行矩阵复验  
> 状态：开发门禁通过；外部上线门禁保持开放

# iCoDer 完整后端发布门阶段总结

> 2026-08-23 增量：本文件记录的 573 条告警已在后续严格阶段降至 1 条第三方 Starlette 迁移提示；完整套件更新为 5001 passed。见 `ICODER_STRICT_WARNING_NATIVE_WORKER_PHASE_SUMMARY_2026-08-23.md`。

## 结论

本轮首次完成不间断的完整默认后端测试：**4996 passed、20 skipped、11 deselected、0 failed、573 warnings**，耗时 **1435.09 秒（23 分 55 秒）**。部署候选静态预检为 **78/78**，Agent Hub 运行矩阵为 **26/26 launch-candidate-ready**。测试期间未使用真实 LLM 密钥、未允许外部 LLM、未加载原生 MedCodER、未启动独立后端；开发数据库 SHA-256 前后未变化，8000/18022 端口最终均无监听。

这证明当前代码在本机可执行的默认后端工程门上已闭环，但不证明与 Corti 私有模型效果等同，也不授予临床生产上线资格。

## 本轮关闭的问题

1. 机器客户端的幂等键现在同时绑定委托用户身份和 `purpose_of_use`。同一 OAuth 客户端变更患者或用途后复用旧键会冲突，不会错误重放旧结果；数据库只保存派生摘要，不保存原始委托标识。
2. SSRF 防护对非法 authority/port 的解析异常改为明确 fail-closed，不再把恶意或畸形 URL 传播成未处理异常。
3. 反馈训练授权的 grant/revoke 审计动作补入历史租户归因分类器，运行期和历史重分类口径一致。
4. 云启动、Provider、原生检索器、Recorder、Note Completeness 等测试改为显式隔离环境状态，同时保留“依赖缺失即失败关闭”的产品语义。
5. 依赖本机 `localhost:8000` 的并发烟测归入 `infra`，不再混入 hermetic 默认套件。
6. Provider 区域驻留测试移除不必要的共享模块 reload，关闭了后续模型目录测试的类身份污染。
7. 部署预检新增 `machine_idempotency_is_bound_to_delegated_subject_and_purpose`，防止上述安全边界在后续改动中静默回退。

## 完整验证证据

| 验证 | 结果 |
|---|---:|
| 最终不间断默认后端测试 | 4996 passed、20 skipped、11 deselected、0 failed |
| 最终默认测试耗时 | 1435.09 秒 |
| 模块污染定向回归 | 19 passed |
| 幂等、SSRF、系统审计安全回归 | 47 passed |
| 部署预检单测 | 1 passed |
| 部署候选静态预检 | 78/78 |
| 运行矩阵单测 | 8 passed |
| Hub 可见 Agent 运行矩阵 | 26/26 ready；21 条 Provider Registry 路由、5 条 dedicated 路由、0 条 legacy default |
| 开发数据库 | SHA-256 与基线一致 |
| 最终监听 | 8000=0，18022=0 |

第一次完整运行结果为 4995 passed、1 failed。唯一失败来自测试主动 reload 共享模块后造成的 Pydantic 类身份污染，不是模型目录产品逻辑失败；移除该 reload 后，19 项污染回归和随后完整套件均通过。

## 关于此前 `uvicorn exited with code -1`

本轮约 24 分钟不间断完整测试未复现内存不可读/不可写崩溃，也未复现 `uvicorn -1`。现有日志只表明 Uvicorn 进程以 `-1` 结束，而此前紧邻请求已经返回 `200 OK`；这更符合进程被外部终止的表现，但缺少 Windows 异常码、事件查看器或转储，**不能据此断言根因**。因此本轮结论是“未复现、稳定性显著改善”，不是“已证明原崩溃根因并彻底消除”。

## 与 Corti 的当前差距

开发环境内已经能证明：26 个用户可见 Agent 均有可解析路由、严格输出合同、安全失败关闭、审计和 Pack 自有参考语义门；完整默认后端测试也已闭环。

仍未关闭的开发/Provider 差距：

- 当前真实 Provider 的 26-Agent 快乐、对抗和重复稳定性尚未用新的未暴露临时密钥重跑；
- 2026-08-15 历史真实响应按当前语义门回放仍为 **22/26**，Diagnosis Extractor、DRG Analyzer、Evidence Extractor、Surgical Registry 四项需要当前 Provider 新实跑确认；
- 完整套件仍有 573 条非失败告警，主要是依赖弃用、`datetime.utcnow`、测试 JWT 密钥强度及少量 pytest marker/runtime 告警。

必须由外部环境或独立人员完成：

- Corti/iCoDer 同病例、同评分标准的双边盲测和独立临床金标准；
- 中国医院 ICD-10-CN、ICD-9-CM-3、CHS-DRG/DIP 本地版本及 HIS/EMR/PACS 联调；
- Docker/Kubernetes 构建、SBOM、漏洞扫描、镜像签名、KMS、PostgreSQL HA、容量、灾备和 SLA；
- 渗透测试、法务、许可、认证和独立 reviewer 审批。

因此 26 个 Agent 继续保持“开发上线候选”，不能改写为 `production_ready=true`，总目标尚未完成。

## 证据位置

- 机器证据：`reports/agent_hub/full_backend_release_gate_phase_20260822/phase_evidence.json`
- 运行矩阵：`reports/agent_hub/full_backend_release_gate_phase_20260822/runtime_matrix/`
- 部署预检：`reports/deployment/full_backend_release_gate_20260822/`
- 上一阶段参考语义总结：`docs/corti_parity/ICODER_AGENT_HUB_REFERENCE_QUALITY_GATE_PHASE_SUMMARY_2026-08-22.md`

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-22 | 首次记录完整默认后端发布门、78 项预检和 26-Agent 运行矩阵复验 | 本轮阶段性总结 |
