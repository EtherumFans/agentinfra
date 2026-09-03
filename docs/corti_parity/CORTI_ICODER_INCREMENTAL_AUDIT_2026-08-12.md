# Corti × iCoDer 开发环境增量审计（2026-08-12）

> 本文是对 2026-08-10 实时差距矩阵的增量复核，不覆盖历史审计。  
> 本轮为避免 Windows 原生访问冲突，未再次自动操作 Corti 浏览器控制台，也未加载本机 BGE / sentence-transformers；Corti 侧能力采用已留存的登录态观察证据和冻结基准，iCoDer 侧采用本轮仓库与低内存测试实证。

## 1. 当前结论

- Agent Hub 用户可见 Agent：**26/26 executable，26/26 maturity=runnable，26/26 engineering launch candidate，26/26 具备真实 A2A URL**。
- `production_ready` 仍为 **0**。工程上线候选不等于生产、临床或合规批准；所有 Agent 仍保留独立临床验证、医院互操作验证、安全隐私审查、生产基础设施批准四类外部门禁。
- Hub 到运行时的真实死链已清零：本轮动态读取 Hub 后逐个调用 26 个 A2A URL，全部得到协议成功响应或明确的安全失败，没有 404、未注册路由或伪造临床成功。
- Corti 核心产品能力复刻**尚未完成**。冻结 CDI 对标仍为 `partial`，生产 Experts/MCP 生态、语音产品深度、语义记忆、全球编码体系、托管云运维、计费、认证和医院实证仍有差距。

## 2. 本轮修复的真实缺陷

1. Hub 为展示日期注入 `_pack_mtime_iso`，却把该运行时字段计入完整性哈希，导致 15 个 Agent 在 Hub 投影中被错误判为非上线候选。新旧校验器现均排除该派生字段。
2. 8 个已经满足可执行、审计、输出契约、人工复核和测试证据要求的 Pack 仍使用 `mvp` 标签。已收敛为工程语义的 `runnable`，但未改变 `production_ready=false`。
3. Hub 对未显式写 `a2a.endpoint` 的可运行 Agent 返回 `null`，与 discovery 自动生成 URL 的行为不一致。现统一采用规范路径 `/api/icoder/agents/{agent_id}/v1/message:send`。
4. `code-validation-agent` 声明了不存在的 `/v2/message:send`，动态全目录测试发现 404；已改为实际挂载的 v1 路径并重算哈希。
5. `denial-appeals` 使用旧注册器不接受的字符串型 `required_models`，启动时 26 个 Pack 实际只注册 25 个；已改为对象契约并通过 v1.1 旧校验器。
6. 全目录 A2A 测试首次运行暴露测试环境可能连接外部 DeepSeek。回归测试现直接替换 LLM 单例为离线失败桩，保证未来测试不会发出外部模型请求。

## 3. 本轮开发环境验证

| 验证项 | 结果 |
|---|---:|
| Hub 强门禁与运行时展示字段 | 2 passed |
| 数据库自定义 Agent → 合成 Pack → Agent Run | passed |
| A2A discovery → message:send → 响应契约 | passed |
| 多轮 Context 复用与跨租户不透明 | passed |
| Task 跨租户查询/取消 404 + 同租户取消 | 3 passed |
| 26 个 Hub Agent 动态 A2A URL 顺序调用 | 26/26 passed |
| Pack 最终盘点 | 26 executable / 26 launch candidates / 26 runnable / 26 A2A URLs |
| v1.1 旧注册器兼容性 | 0 failures |
| 临时 SQLite 迁移 `head → 031 → 032` | passed |
| CDI rewrite queue 迁移 `032 → 033 → 032 → 033` | passed，最终 033 / 0 cases |
| OpenAPI 导出与 `--check` | passed |
| JavaScript SDK TypeScript build | passed，0 errors |
| Python A2A SDK | 3 passed |
| Frontend production build | passed |

测试均采用独立小批次执行。结束时无 Python 或 .NET 残留进程，可用物理内存约 7 GB，未出现本轮所述“内存不可读/不可写”弹窗。

## 4. Corti 冻结 CDI 基准差距

离线校验确认 4 个汇总工件和 40 个唯一去标识病例完整，未使用网络、未加载模型。严格对齐仍有 4 项未达标：

| 指标 | iCoDer 当前值 | 目标 | 状态 |
|---|---:|---:|---:|
| 查询数量差不超过 1 的一致率 | 0.75 | ≥ 0.80 | 未达标 |
| 平均绝对查询数量差 | 1.00 | ≤ 0.50 | 未达标 |
| 明确缺口漏询率 | 0.10 | 0 | 未达标 |
| 无依据询问率 | 0.025 | 0 | 未达标 |

已达标项包括：iCoDer 查询数量范围符合率 0.93、完整病历过度询问率 0、跨维度合并询问率 0、证据原文引用率 0.975、四个以上回答选项率 1.0、非诱导式询问率 1.0。

因此，Agent 目录与工程运行链路已经收敛，不代表 CDI 临床行为已经与 Corti 等价。

逐例根因复核进一步确认：

- 10/40 个病例的绝对查询数差不小于 2，既有少问也有多问，不能用统一增减查询数的方法整改。
- `G8-CDI-GAP-004` 的候选询问同时涉及严重程度和病因，被 single-dimension gate 正确禁止发送，但旧实现将其静默删除。现已新增持久化 `query_rewrite_queue`：保留 gap、原始证据、检测轴和拒绝原因，交由 CDI 人员拆分；它不进入可发送给医生的 Query 表，也不伪造自动拆分结果。
- 唯一“无依据询问”代理项来自 `G8-CDI-CONFLICT-034`。病历中分别存在入院和出院诊断，但生成器把两个不连续片段拼成一个 evidence quote；单一连续 EvidenceSpan 无法诚实表示它。不能通过降低 fuzzy 阈值掩盖，后续应增加多 EvidenceSpan 契约并保持逐段原文校验。

## 5. 中国场景适配判断

当前已有明确工程优势：ICD-10-CN、ICD-9-CM-3、本地 DRG/DIP、医保结算/拒付、中文病历与中文 ASR 路径、禁止自动写回、证据约束与人工复核。

仍需开发或外部协作的重点：

- 地方医保及 DRG/DIP 规则包的来源、版本、有效期、地区隔离和回滚机制；
- 真实医院 HIS/EMR/FHIR/医保平台字段映射、证书、网络和验收；
- 医院脱敏数据集、独立 CDI/编码专家标注及分层质量基准；
- 中文方言、多人说话、噪声、科室词表和长音频的真实语音验证；
- 中国数据本地化、等保、个保法/数安法/网安法及医院制度审查。

## 6. 当前环境限制与外部门禁

- 当前机器没有 `dotnet.exe`，本轮不能复验 .NET SDK；仓库源码存在不等于本机已验证。
- 当前机器没有 Docker，不能执行 Compose 容器启动、镜像扫描和容器级健康检查。
- Windows 上 `torch 2.11.0 + sentence-transformers 3.2.1` 已知会触发 `torch_cpu.dll` 的 `0xc0000005` 访问冲突；本轮继续失败关闭，不能通过不安全开关恢复。
- 浏览器自动化暂缓，以避免再次触发宿主访问冲突。Corti 登录态已由用户确认，但本轮没有产生新的浏览器实测结论。
- `backend/data/codex_migration_032_roundtrip_20260812.db` 是本轮迁移往返产生的空临时数据库。受当前环境的破坏性操作策略限制未删除，不能把它误认为业务数据或正式工件。
- 真实医院验证、临床签字、独立渗透测试、外部认证、生产云账号、密钥托管、灾备演练、支付结算和数据许可均不能仅靠本开发机闭环。

## 7. 下一优先级

1. 针对冻结 CDI 基准的 4 个失败指标做逐例根因分析和规则/提示词整改，保持评测集只读和防过拟合审计。
2. 补齐 26 个 Agent 的结构化输出属性测试、缺失证据测试、提示注入测试和中文临床边界测试。
3. 扩展语义记忆的安全隔离服务方案，禁止在当前不安全 Windows 原生栈内加载 BGE。
4. 在具备 Docker、.NET 和隔离 Linux 依赖环境后复跑 SDK、容器、检索与部署门禁。
5. 由医院、法务、安全、认证和独立临床 reviewer 完成外部门禁后，才允许评估 `production_ready`。

## 8. 2026-08-12 查询安全与数量偏差增量

- Provider Query 已支持多个相互独立的 `evidence_spans`，每段独立做原文锚定；任一片段无效即整条 fail-closed，旧 `evidence_span` 客户端和历史记录继续兼容。
- 所有查询丢弃门禁现保留结构化审计工作项；无存活 Query 的文档缺口会产生不可发送的 `NEEDS_QUERY_DRAFT`，避免缺口静默消失。
- NLQ `BLOCK` 问题不再属于可发送候选，而进入 `NEEDS_NON_LEADING_REWRITE`。病历已经明确记载糖尿病分型时，重复分型追问进入 `REJECTED_AS_UNNECESSARY`。
- 审计队列执行后端 RBAC 投影；临床医生视图不暴露被拦截问题，A2A 只返回计数与状态汇总。
- 低内存串行定向回归 `21 passed`，前端生产构建通过；本轮未启用 Corti 浏览器自动化、Torch、BGE 或 sentence-transformers。
- CDI API 边界回归另发现 SQLite 无时区 UTC 时间与有时区当前时间相减会导致审计面板 500；现已在 SLA 计算入口统一为 UTC。相关服务/API 回归 `66 passed`，多证据、A2A、隐私、临床视图与 API 组合回归 `50 passed`。
- 冻结全量指标仍是：数量差不超过 1 的一致率 `0.75`、平均绝对数量差 `1.00`、明确缺口漏问率 `0.10`、无依据询问率 `0.025`。任何新规则只有在生成新的只读候选并完成同一 40 例冻结流程后，才可更新这些值。
- 诊断性切片（仅 Corti 数量落入预期范围的 20 例）为：平均绝对差 `0.30`、差值不超过 1 的一致率 `1.00`。该切片不得替代全量原始对标结果。
