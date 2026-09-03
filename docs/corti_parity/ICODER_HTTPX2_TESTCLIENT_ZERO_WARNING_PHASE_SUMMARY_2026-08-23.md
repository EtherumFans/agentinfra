> 声明：本文件记录开发/CI 测试传输兼容性，不构成临床生产批准或 Corti 模型质量等效声明。  
> 日期：2026-08-23  
> 阶段：Starlette TestClient HTTPX2 迁移与零告警门  
> 状态：开发门禁通过；真实 Provider、医院、云与独立评审门禁保持开放

# iCoDer TestClient 零告警阶段总结

## 结论

Starlette 1.3 的 TestClient 已从兼容期旧 `httpx` 后端切换到官方推荐的 `httpx2==2.12.0`。生产 Provider/Connector 使用的 `httpx==0.27.2` 继续独立锁定，`httpx2` 不进入最小 API 运行镜像。

最终严格完整后端门为 **5002 passed、20 skipped、11 deselected、0 failed、0 warnings**，耗时 **1340.93 秒（22 分 20 秒）**。上一阶段唯一保留的第三方 `StarletteDeprecationWarning` 已关闭，而不是过滤。

## 实现与防回退

1. `backend/requirements.txt` 在测试依赖中锁定 `httpx2==2.12.0`。
2. `requirements-api.txt` 保持生产 `httpx==0.27.2`，避免把测试迁移扩张成 Provider 客户端升级。
3. 新增运行时测试，断言 Starlette TestClient 实际绑定 `httpx2` 且版本精确匹配。
4. 部署预检新增 `starlette_testclient_uses_pinned_httpx2_backend`，同时确认 `httpx2` 不进入 API 运行依赖。

## 验证

| 验证 | 结果 |
|---|---:|
| 98 个 TestClient 文件严格兼容矩阵 | 1050 passed、8 skipped、0 failed |
| 最终严格完整后端门 | 5002 passed、20 skipped、11 deselected、0 warning |
| Runtime/Preflight 定向单元矩阵 | 10/10 passed |
| 部署候选静态预检 | 80/80 passed |
| Agent Hub 运行矩阵 | 26/26 launch-candidate-ready |
| 开发数据库 | SHA-256 与基线一致 |
| 最终进程环境 | 8000/18022 无监听；无 spawn/uvicorn 残留 |

## 对 Corti 总目标的影响

本阶段关闭测试基础设施的最后一条已知弃用告警，提高 26-Agent HTTP/WebSocket、鉴权、A2A、SSE、STT、Facts、Guided Document 与 Coding 契约的长期可维护性。它不新增 Corti 私有模型质量证据，也不关闭真实医院和生产云门禁。

仍开放的主门禁包括真实 Provider 26-Agent 回放、Corti/iCoDer 同病例双盲临床评估、中国医院权威编码/DRG/DIP 资产与系统联调、生产镜像/SBOM/漏洞/签名/KMS/HA/容量/灾备，以及法务、隐私、认证和独立临床评审。

## 证据位置

- 机器证据：`reports/agent_hub/httpx2_testclient_phase_20260823/phase_evidence.json`
- 运行矩阵：`reports/agent_hub/httpx2_testclient_phase_20260823/runtime_matrix/`
- 80 项预检：`reports/deployment/httpx2_testclient_phase_20260823/`
- 前一稳定性阶段：`ICODER_STRICT_WARNING_NATIVE_WORKER_PHASE_SUMMARY_2026-08-23.md`

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 完成 HTTPX2 TestClient 迁移、5002 项严格零告警回归与 80/80 预检 | 关闭最后一条已知测试弃用告警 |
