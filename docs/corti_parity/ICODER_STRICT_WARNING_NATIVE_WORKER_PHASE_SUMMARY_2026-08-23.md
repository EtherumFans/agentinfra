> 声明：本文件记录开发环境严格测试与稳定性证据，不构成临床生产批准或 Corti 等效性声明。  
> 日期：2026-08-23  
> 阶段：严格告警门、Windows 原生 Worker 握手与置信度边界  
> 状态：开发门禁通过；真实 Provider、医院、云与独立评审门禁保持开放

# iCoDer 严格告警与原生 Worker 稳定性阶段总结

## 结论

本阶段最终完成不间断严格后端回归：**5001 passed、20 skipped、11 deselected、0 failed、1 warning**，耗时 **1115.11 秒（18 分 35 秒）**。`RuntimeWarning`、普通 `DeprecationWarning` 和 JWT 短密钥警告均被升级为失败门；唯一保留告警来自第三方 Starlette TestClient，提示后续迁移到 `httpx2`。

> 后续增量：该第三方提示已通过官方 HTTPX2 TestClient 后端迁移关闭；当前完整严格门为 5002 passed、0 warnings，预检为 80/80。见 `ICODER_HTTPX2_TESTCLIENT_ZERO_WARNING_PHASE_SUMMARY_2026-08-23.md`。

部署静态预检升至 **79/79**，Agent Hub 运行矩阵继续保持 **26/26 launch-candidate-ready**。测试未使用真实 LLM、未加载原生 MedCodER 模型、未改动开发数据库，8000/18022 最终均无监听。

## 本阶段关闭的问题

1. CDI 同步桥原先会先构造协程，再由 `asyncio.run` 发现活动事件循环；异常路径会留下“coroutine was never awaited”。现在先检测事件循环，在工作线程内构造并运行协程。
2. Coding Expert 的同步入口也改为在构造协程前拒绝活动事件循环，避免双重错误与对象延迟回收。
3. 项目中的 `datetime.utcnow()` 已从 Python 运行路径清除。运行合同使用 aware UTC；历史 naive SQL DateTime 则由 aware UTC 时钟显式去除时区后写入，保持兼容。
4. Python 3.12 SQLite 隐式 datetime adapter 被显式 ISO-8601 adapter 替代。
5. Pytest 在导入应用前强制使用进程内、非生产、满足 HS256 最小长度的测试密钥，不再继承开发机 `.env` 或真实环境密钥。
6. 畸形 JSON 测试从 httpx 已弃用的 `data="raw"` 改为 `content="raw"`，严格弃用门下仍验证相同解析错误合同。
7. Windows MedCodER Worker 新增 `STARTUP_READY` / `STARTUP_ERROR` 握手。索引加载和子解释器启动使用独立 60 秒启动边界，业务请求超时只在 Worker ready 后开始。
8. FAISS inner-product 继续作为排序信号，但不再直接作为临床置信度。所有进入公开诊断、操作和 rerank 输出的 confidence 都被限制在 `[0,1]`；NaN/Infinity 归零。

## 长跑发现而定向测试未发现的问题

| 完整序列暴露点 | 问题 | 处置 |
|---|---|---|
| 288 项后 | raw text 使用 httpx 弃用参数 | 改为 `content=` |
| 2525 项后 | Worker 启动耗时被算进 5 秒请求超时 | 增加明确启动握手 |
| 2294 项后 | 旧测试助手绕过正式握手 | 所有直接客户端先消费 ready |
| 2493 项后 | 随机 FAISS 分数产生 `-0.0092` 置信度 | 统一有限数检查与 `[0,1]` 边界 |

这些失败说明完整、不间断且严格的长跑不是形式化重复；它实际发现了定向测试和普通绿测无法稳定暴露的问题。

## 验证证据

| 验证 | 结果 |
|---|---:|
| 最终不间断严格默认后端测试 | 5001 passed、20 skipped、11 deselected、0 failed |
| 最终告警 | 1 条第三方 Starlette/httpx2 迁移提示 |
| RuntimeWarning 严格定向矩阵 | 48 passed |
| UTC/SQLite/JWT 严格矩阵 | 441 passed、1 skipped |
| Worker 相关矩阵 | 20 passed、1 skipped |
| Worker 协议 5 轮重复 | 40/40 passed |
| 旧测试助手 3 轮重复 | 18 passed、3 skipped |
| MedCodER 检索/策略/置信度矩阵 | 100 passed |
| 部署候选静态预检 | 79/79 |
| Agent Hub 运行矩阵 | 26/26 ready |
| 开发数据库 | SHA-256 与基线一致 |
| 最终监听 | 8000=0，18022=0 |

## 对 Corti 总目标的影响

本阶段提高的是 iCoDer 的运行确定性、Windows 稳定性、测试真实性和临床数值合同质量。它证明 26 个用户可见 Agent 的开发候选路由没有因底层修复回退，但不产生新的 Corti 私有模型质量证据。

仍未关闭：

- 使用新、未暴露临时凭证完成当前真实 Provider 的 26-Agent 快乐、对抗和重复稳定性；
- 历史真实 Provider 语义回放的 4 项差距：Diagnosis Extractor、DRG Analyzer、Evidence Extractor、Surgical Registry；
- Corti/iCoDer 同病例双盲评估及独立临床金标准；
- 中国医院 ICD-10-CN、ICD-9-CM-3、CHS-DRG/DIP 本地版本和 HIS/EMR/PACS 联调；
- Docker/Kubernetes、SBOM、漏洞扫描、签名、KMS、PostgreSQL HA、容量、灾备、SLA、渗透、法务与认证。

因此状态仍是“开发上线候选”，不是 `production_ready=true`，总目标保持进行中。

## 证据位置

- 机器证据：`reports/agent_hub/strict_warning_native_worker_phase_20260823/phase_evidence.json`
- 运行矩阵：`reports/agent_hub/strict_warning_native_worker_phase_20260823/runtime_matrix/`
- 79 项预检：`reports/deployment/full_backend_release_gate_20260823/`
- 上一完整后端阶段：`docs/corti_parity/ICODER_FULL_BACKEND_RELEASE_GATE_PHASE_SUMMARY_2026-08-22.md`

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 记录严格 5001 项完整回归、告警归零、Worker 握手与置信度边界 | 持续开发门禁收敛 |
