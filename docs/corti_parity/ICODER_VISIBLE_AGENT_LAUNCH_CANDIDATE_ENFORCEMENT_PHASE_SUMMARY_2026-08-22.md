# iCoDer 用户可见 Agent 上线候选强制阶段总结（2026-08-22）

> 声明：本报告证明开发环境中的可执行、可审计、可测试和失败关闭属性，不代表临床质量、医院生产批准或 Corti 私有实现等价。

## 结论

当前磁盘共有 32 个官方 Agent Pack。26 个声明面向 Agent Hub 的 Pack 全部为 executable、Provider-resolvable、launch-candidate-ready；21 个通过显式 Provider Registry 路由，5 个通过专用适配器，0 个依赖 legacy default fallback。其余 6 个 Pack 均不面向用户，其中 5 个为 metadata-only/stub 兼容或内部 Pack，1 个为内部可执行引擎。

本阶段关闭的缺口不是当前清单数量，而是未来回归策略：旧 Hub 代码允许 `hidden_from_hub=false` 的 metadata-only Pack以 Coming Soon 卡片出现，也允许 `mvp` 生命周期进入 runnable 判断。现在 `hidden_from_hub=false` 只表示“希望公开”；真正公开还必须同时满足规范 runnable maturity、Pack executable、开发上线候选门禁和实际 Provider 解析。

## 后端可见性合同

- `metadata-only`、`stub`、`mvp`、deprecated、invalid、internal engine、expert stub、未知 Provider 和无执行路径 Pack 均不能进入公共 Hub。
- 允许的用户可见 maturity 只有 `runnable`、`production-ready` 和 `production`；其中生产状态仍必须服从 `production_ready` 的诚实投影。
- 公共 Hub 在请求时使用权威 Pack loader，并验证 `launch_candidate_ready`；21 个通用 Pack 必须被 Provider Registry 实际解析，5 个专用 Pack 必须在权威执行路径目录中登记。
- Hub schema version 提升为 `1.2`；OpenAPI 描述明确只返回 executable、Provider-resolvable development launch candidates。
- 运行矩阵同时记录“声明可见”和“实际发布”。未来坏 Pack 即使被 API 安全排除，也会进入 `hub_declared_visible_excluded` 并使 `--assert-visible-ready` 和部署预检失败，不能靠静默少卡片取得绿色。

## 前端失败关闭

前端在 API 响应进入页面状态前再次过滤：只有 executable、runnable、非 MVP、`launch_candidate_ready=true`、blocker 为空，并具备 agent ID、A2A endpoint、run URL 和 clone URL 的卡片才可显示。旧后端、代理缓存或畸形响应返回的 placeholder、blocked 或 actionless 卡片不会重新暴露为 Coming Soon。

纯过滤器位于无浏览器副作用模块，可在 Node 测试环境独立验证，不依赖全局 store 或 `localStorage`。

## 原生栈测试隔离

扩大回归发现一个既有测试顺序问题：同一 pytest 进程更早的测试已加载 Torch，cache-only Agent E2E 单元测试误把“进程此前已加载”归因于 runner。生产 runner 的严格保护没有放宽：干净 E2E 进程中只要发现 Torch/PyArrow 仍立即拒绝。单元测试改为比较调用前后原生模块集合，证明 cache-only 路径没有新增原生模块，并增加 guard 对预加载模块的直接拒绝测试。

## 验证结果

- 权威运行矩阵：32 Pack；声明可见 26；实际发布 26；被门禁排除 0；不可用清单 0。
- 路由：Provider Registry 21；专用适配器 5；legacy default 0。
- 合同：26/26 完整类型、嵌套 schema、严格输出白名单、不可变登记、字段关系、evidence binding 和跨 Agent 关系门禁。
- Hub/Pack/发现/显示/运行矩阵扩大回归：**285/285**，22 条依赖或既有 `utcnow()` 弃用警告。
- 聚焦后端回归：**32/32**；最终矩阵/预检聚焦：**9/9**。
- 前端：**138/138**；TypeScript + Vite 生产构建通过。
- JavaScript SDK `1.0.0-beta.24`：**43/43**，TypeScript build 通过。
- Python SDK `1.0.0b24`：**50/50**。
- .NET SDK `1.0.0-beta.24`：本机无 `dotnet`，未声称编译或测试通过。
- OpenAPI：269 paths、288 schemas、842,015 bytes，重新导出且 drift check 通过。
- 静态部署候选预检：**65/65**。

## 数据和运行边界

- 所有后端测试均清空 LLM 凭据、使用 mock provider、禁止外部 LLM，并禁用 Windows 原生 MedCodER。
- 没有启动 8000 端口、没有调用 Corti 写接口或浏览器自动化。
- 当前开发主库 `backend/data/icoder.db` SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`，本阶段无 schema 变更、迁移或切换。

## 仍开放的 Corti/生产差距

1. 当前 26/26 只证明开发执行路由、公共合同、安全边界和可审计性，不证明 26-Agent 真实模型语义质量、P50/P95、成本或临床准确性。
2. 除 Compliance Guardrail 的确定性 mock 能力外，模型依赖 Agent 在无凭据环境中的正确结果仍是安全失败关闭；完整真实模型快乐/对抗/重复矩阵需要轮换凭据、明确预算和独立临床复核。
3. Corti 托管模型、计费、私有运行时、租户互操作及 Agent SDK 私有预览不能由本地矩阵证明。
4. 真实医院接口、患者授权、权威中国编码/DRG-DIP 数据、云基础设施、KMS、PostgreSQL 多副本、法务、认证、渗透测试和独立 reviewer 仍是外部门禁。

机器证据目录：`reports/agent_hub/visible_launch_candidate_enforcement_phase_20260822/`。
