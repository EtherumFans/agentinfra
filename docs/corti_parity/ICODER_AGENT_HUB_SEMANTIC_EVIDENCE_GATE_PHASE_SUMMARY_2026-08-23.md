# iCoDer Agent Hub 真实语义证据门禁阶段总结（2026-08-23）

> 本阶段证明的是开发环境中的证据完整性、抗伪造、可追溯和失败关闭，不是临床准确率、Corti 同病例质量对等或生产批准。

## 阶段结论

Agent Hub 的 26 个用户可见 Agent 继续保持 26/26 executable、Provider-resolvable、非 MVP 和结构性 launch-candidate-ready；运行矩阵升级为 v3，当前分类为 19 个外部 LLM 必需、1 个外部 LLM 可选、6 个纯本地执行、7 个具备本地基线。由于本阶段没有使用真实 LLM 密钥，也没有生成新鲜的 26-Agent 实网证据，`semantic_live_e2e_verified` 和 `production_ready_verified` 均诚实保持 **0/26**。

本阶段新增了可审计的证据链：示例、对抗和稳定性运行报告记录 Agent Pack 快照、输出 schema、HTTP 执行动作、响应与 Trace 文件哈希、Provider/model/usage 遥测和结果证明；运行 Trace 端点新增独立 HMAC attestation，将组织、Run、规范化安全事件摘要与有效期绑定。语义 bundle 生成器会重新读取源文件并校验签名、哈希、时效、Agent 集合、Pack/schema、参考用例、稳定性种子来源和真实 Provider 遥测。任何 mock、degraded、fallback、resume、陈旧、缺失、伪造或漂移证据都不能提高矩阵分数。

历史 2026-08-13/15 报告按当前门禁重放后被明确拒绝：0/26 验证、140 项原因，bundle SHA-256 为 `dcaa236d84a350ecede72de4d55d8d7bf0555a0e04616386aedc94a799157476`。这证明旧报告、历史响应和缺失稳定性数据不会被重新包装成当前上线证据。

## 主要实现

- `agent_hub_live_evidence.py` 统一采集 PHI-safe 执行 provenance、Pack 快照、响应/Trace 哈希、真实 Provider/model/usage 和 HMAC 结果/Trace 证明。
- 示例、对抗、稳定性报告分别升级为 v3、v3、v2；稳定性首轮种子必须逐字节绑定到同一 bundle 的新鲜示例/对抗源报告，第二轮必须独立 HTTP 执行。
- `build_agent_hub_semantic_evidence_bundle.py` 建立严格聚合门禁；`build_agent_hub_runtime_matrix.py` 只有在完整重新验证 bundle 后才能从 0/26 提升。
- CI 在有真实 LLM 凭据时生成 job-scoped 随机 `ICODER_SECRET_KEY`，同一作业内完成示例、对抗、参考回放、稳定性、bundle 和矩阵；凭据缺失时不伪造语义通过。
- 本地运行手册要求后端和测试 runner 继承同一临时 attestation key；真实 LLM key 只进入专用后端窗口，运行结束即清除。
- 测试基础设施修复了显式 `ICODER_DATABASE_URL` 与旧 SQLite 迁移断言读取不同数据库的问题，并更新 Surgical Registry 已转为受治理本地确定性 Agent 后的 Hub 分类合同。

## 验证结果

| 门禁 | 结果 | 解释 |
|---|---:|---|
| 语义 bundle、矩阵、runner、Trace attestation 与 Trace API | 68/68 | 包含伪造/过期签名、mock Trace、陈旧证据、Pack 漂移、safe-fail 冒充成功、种子来源篡改等负向用例 |
| 首次全量回归 | 5238 passed / 16 failed / 20 skipped / 11 deselected | 16 项分为旧 SQLite 路径、Surgical Registry 旧分类、API 归因硬编码路径和 OpenAPI 快照；均已修复并隔离通过 |
| 修复后全量回归 | 5250 passed / 4 failed / 20 skipped / 11 deselected | 4 项均为全量负载下的有界等待超时：3 个 Alembic 子进程 60 秒、1 个 fake worker 5 秒探针；没有迁移或业务断言失败 |
| 最终 4 项相关文件复测 | 12/12 | Alembic 上限调整为仍有界的 120 秒，fake worker 探针为 15 秒；全部通过 |
| 最终干净单体全量回归 | 5254 passed / 0 failed / 20 skipped / 11 deselected | 使用 C 盘隔离 SQLite、空密钥、mock Provider、禁止外部 LLM；36 分 30 秒，所有负载敏感节点均通过 |
| 前端与 SDK | 前端 142/142；JS SDK 63/63；Python SDK 64/64 | SDK 后续阶段补齐自动 client-credentials、并发安全刷新、408/429/5xx 幂等重试、统一 PHI-safe API 错误与 Agentic cursor 自动分页；前端生产构建和 JS SDK 构建通过；.NET 因本机无 dotnet/csc/msbuild 未执行 |
| 合同兼容 | 通过 | 26 个可见合同、109 个注册合同；0 新引用、0 漂移、0 非法、0 重复 |
| OpenAPI | 通过 | 运行时导出与提交快照一致 |
| 静态部署预检 | 82/82 | `static_without_docker_cli`，失败项 0 |
| 编译、Workflow YAML、阶段 JSON、diff check | 通过 | diff check 仅输出既有行尾转换警告，无空白错误 |

最终单体全量运行已经取得一次 `0 failed`，关闭了此前 4 个负载敏感超时门禁。机器证据位于 `reports/agent_hub/semantic_evidence_gate_phase_20260823/phase_evidence.json`。

## 后台退出复核

用户提供的日志中 Trace 查询返回 200，SQLAlchemy 的只读事务 `ROLLBACK` 属正常清理；随后 `uvicorn exited with code -1` 只证明进程已终止。系统事件中没有找到对应时段的 Windows Application Error/WER，无法据此认定“内存不可读/不可写”。本阶段两次长时全量回归均未出现 Uvicorn 或 Python 原生崩溃。收尾时 8000/18022 无监听、无项目 Python/Uvicorn/pytest/Alembic 残留进程。

## 对 Corti 的当前差距

| 能力面 | 当前 iCoDer 开发证据 | 未关闭差距 |
|---|---|---|
| Agent Hub/运行治理 | 26 个用户可见 Agent 的 Pack、Provider、schema、项目克隆、A2A、Trace、租户就绪和失败关闭已形成工程闭环 | 19 个 Agent 仍需外部 LLM；缺新鲜 26-Agent 真实 Provider 语义与稳定性 bundle |
| Agentic/A2A | v1 双 binding、持久 Task/Context、取消/恢复、Connector Graph、OpenInference 投影和三 SDK 合同已有开发实现 | Corti 托管租户双向实测、生产多副本、完整 SDK/私有 Agent SDK 互操作仍缺；本机 .NET 未实编译 |
| Medical Coding | 中国 ICD-10-CN/ICD-9-CM-3 的本地目录与受治理基线、证据/候选/schema 安全边界已覆盖 | Corti 多国体系、全病历模型推理、真实检索质量、权威编码资料许可、同病例盲测和编码员验收未完成 |
| STT/Embedded | REST、流式、Artifact 和 Embedded 基础合同已有 | Corti Dictation/Ambient 正式组件的方言、多人、噪声、长音频、diarization、词级时间戳、延迟/成本和浏览器可靠性无对等证据 |
| Models/平台 | 租户 Provider 选择、路由、Canary、审计和中国区域默认拒绝外发已有 | 无 Corti 式托管模型池、EU/中国主权基础设施、embedding 容量、计费与 SLA |
| 中国场景 | 中文手术登记、编码目录、DRG/DIP 风险边界、PHI 最小化和人工复核规则已有 | 国家/地方/医院权威版本化数据、结算引擎对照、医院接口、个保/数安/等保、法务和临床 reviewer 门禁仍需外部完成 |

## 下一阶段

开发环境内可继续完成的首要任务是：使用新建的临时 DeepSeek 密钥和随机 attestation key，通过不启动浏览器的 HTTP runner 生成 26 个示例、26 个对抗、26 个参考回放和至少两轮稳定性证据；只有 bundle 完整通过后，矩阵才允许提升对应 Agent。任何失败应按具体 Agent 的 schema/semantic/Provider telemetry 修复后重跑，不允许用 resume、旧响应或 safe-fail 替代。

真实医院病例盲评、编码资料授权、国家/地方 DRG-DIP 规则、医院 HIS/EMR/结算接口、云多副本与灾备、渗透测试、法务/认证和临床上线签字不属于单机开发环境可完成事项，必须继续保留为外部门禁。

## 安全收尾

- 本阶段未读取或使用真实 DeepSeek key；`ICODER_CREDENTIAL_LLM` 与 `DEEPSEEK_API_KEY` 收尾长度均为 0。
- 受保护数据库 `backend/data/icoder.db` SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- E 盘剩余约 67.2 MB，仍不适合在 E 盘运行全量 SQLite 临时库；测试继续使用 C 盘专用临时目录。
- 曾在会话中公开过的 DeepSeek key 必须在供应商控制台注销/轮换；后续只能使用新临时 key。
