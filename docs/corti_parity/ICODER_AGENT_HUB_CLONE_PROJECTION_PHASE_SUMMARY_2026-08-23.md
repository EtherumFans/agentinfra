# iCoDer Agent Hub Clone 与预置投影一致性阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床、生产、医院上线或监管批准。
>
> 阶段：Hub-visible Pack clone identity and Registry-to-DB projection consistency
>
> 状态：Clone 创建与投影一致性门禁通过；项目副本的定制执行语义仍为 P0 开放差距

## 阶段结论

本阶段关闭了一个真实的 Hub 断链：`medical-coding-agent` 在 Pack-mastered Hub 中可见且可运行，但 `POST /api/icoder/agents/medical-coding-agent/clone` 只查询派生数据库行；测试/非 development 启动跳过 Pack seed 后，旧 Registry 修复又没有写入 `is_prebuilt=true` 和 `config.agent_ref`，因此 Clone 固定返回 404。

Clone 现在从与 Hub 完全相同的“可见、可执行、Provider 可解析、launch-candidate”Pack 边界解析源 Agent。隐藏、metadata-only、stub、internal 或不可解析 Pack 即使存在管理面数据库行也不可克隆。首次克隆返回组织内项目 Agent，重复请求按 `(organization, source_agent_ref)` 返回已有副本。

Registry→DB 同步现在生成完整的全局预置 Agent 投影，包含 Pack identity、版本、Expert、A2A、输出合同、权限、要求、LLM 能力、运行绑定和治理边界；已存在行发生字段漂移时会报告 `field_mismatch` 并原地修复。自定义 Agent、租户克隆和未被 Runtime Registry 安装的隐藏 metadata seed 行不再被误报为 Registry orphan。

development 启动的两个历史投影器也已明确分工：`seed_agents` 只维护广义 REST/管理面 Pack 行，并跳过 `registry_projection_managed=true` 的 27 个可执行投影；Registry 同步只管理其实际安装的可执行 Pack。首次采用后，重复 lifespan 的实测日志为 `5 updated, 27 skipped`，随后 `Registry→DB sync: 0 repaired, 0 failed`，不再固定出现 48 项不一致和 27 行重写。

## 已关闭的开发缺口

- Hub 卡片与 Clone 使用同一可见 Pack 权威源，不再依赖 development seed。
- 真实隐藏的 `medcoder-coding-review-agent` 短 ID返回 404，不能通过派生 DB 行绕过 Hub 边界。
- 旧同步创建的 clone-like 残缺行可按原 ID 升级为完整预置投影。
- Registry 记录不再按两个别名重复计数；自定义克隆不参与预置一致性检查。
- Pack-mastered 字段漂移可检测、可修复；运行计数和时间戳保持 DB 自有状态。
- 广义 Pack seed 与 Runtime Registry 投影有显式 ownership 标记，重复启动幂等。
- 租户使用量测试改为断言自身增量，不再依赖全仓测试文件顺序。
- Evidence Extractor 已有本地治理 Provider 后，三处旧“mock 必须失败”断言已更新为当前 v11 合同，不再把正确本地成功当回归。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| Clone/同步聚焦测试 | 15/15 | 可见 Pack 克隆、真实隐藏 Pack 拒绝、幂等、组织行、旧行升级、字段漂移、非 Registry seed 排除 |
| Hub/发现/租户/真实启动跨面回归 | 96/96 | Hub 可见性、统一 discovery、Clone、readiness、display、真实 lifespan/Uvicorn smoke |
| 最终默认安全后端全量 | 5168 passed | 20 skipped、11 deselected、0 failed；项目默认排除 heavy/retrieval/infra |
| 前端 Agent Hub 合同 | 17/17 | Hub API 类型与导航合同 |
| 前端生产构建 | 通过 | TypeScript + Vite；仅保留既有动态/静态 import chunk 提示 |
| OpenAPI 漂移 | 通过 | `docs/openapi/openapi.json` 为最新 |
| 运行矩阵 | 26/26 | visible、executable、Provider-resolvable、launch-candidate-ready |
| 静态部署预检 | 81/81 | 失败项 0；不替代 Docker/Cloud/PostgreSQL 外部门禁 |

机器证据位于 `reports/agent_hub/agent_hub_clone_projection_phase_20260823/`。全部测试使用空 LLM 凭据、mock Provider、禁止外部 LLM并禁用原生 MedCodER；没有操作 Corti 登录控制台或启动常驻浏览器。

## 对 Corti 的能力差距

Corti 官方公开 Agent Library 表述为：预置 Agent 可以直接部署，也可以按场景配置；公开 FAQ 进一步列出可修改 system prompt、可用 Experts，并扩展自定义逻辑、工具和集成。官方 Agentic Quickstart 还公开了 Project 内创建 Agent 并发送消息的 API 流程。来源：[Corti Agent Library](https://corti.ai/agents)、[Corti Agentic Quickstart](https://docs.corti.ai/agentic/quickstart)。

| 能力 | iCoDer 当前状态 | 差距判断 |
|---|---|---|
| 预置模板发现 | 26 个可见 Pack 与 Clone 边界统一；隐藏/不可执行 Pack 失败关闭 | 开发目录与可克隆性边界已闭环 |
| 项目副本创建 | 组织内持久化、源引用、名称/描述覆盖和重复请求复用已有副本 | 关闭原 404；尚缺并发多 worker 唯一性实压 |
| 副本配置 | DB 可修改 name、description、system prompt、Expert bindings 和 config | 有配置面，但配置是否作用于每类源 Runtime 尚未闭环 |
| 副本执行 | 当前 Chat 从 `source_agent_ref` 派生源 Agent ID并运行源 Runtime；直接以项目 ID运行会合成通用 DB Agent Pack | **P0 差距**：不能声称克隆后的 prompt/Experts/custom logic 已按副本执行，也不能声称与 Corti 定制语义等价 |
| 审计与租户边界 | 源引用、创建者、组织、Run/Trace 与失败关闭已有开发合同 | 缺真实 PostgreSQL 多 worker、Console 同题、生产身份和外部安全验证 |

因此，本阶段只关闭 Clone 可达性和派生投影一致性，不关闭“可配置副本的真实执行”等价。下一阶段必须让项目副本通过同一租户绑定 Run/A2A 主线执行其实际配置，同时为专用路由和 Provider Registry定义明确的继承/覆盖规则，再补并发、跨租户和定制效果 E2E。

## 安全与外部门禁

- 未读取或使用用户曾暴露的 DeepSeek 密钥；该密钥仍应在供应商控制台注销。
- 未打开 Corti 登录控制台；本机已有浏览器/原生测试内存崩溃风险。
- 保护数据库最终 SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 最终两个 LLM 密钥环境变量长度均为 0；8000/18022 监听数为 0；Python/Uvicorn 进程数为 0。
- 未执行真实模型、真实医院数据、HIS/EMR、医保结算、Docker、Cloud、真实 PostgreSQL 多副本或生产容量测试。
- 法务、数据授权、等保/个保/数安、渗透测试、医院验收、云基础设施和生产运维仍为外部上线门禁。

## 下一步

P0 是项目副本执行闭环：以 `project_agent_id` 进入租户隔离的 Run/A2A，继承源 Pack 的 Provider、输出合同、工具和专用运行能力，同时应用允许覆盖的 prompt/Experts/配置；不支持安全覆盖的字段必须在 API/前端明确只读或失败关闭。随后补并发克隆唯一性、跨组织不可见、删除/版本升级和 Clone→Customize→Run→Trace 端到端回归，再继续 `diagnosis-extractor` 能力收敛。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-23 | 建立 Hub-visible Pack 克隆权威源、完整 Registry 投影、字段漂移修复、双投影 ownership 和全量回归证据 | Clone 404 与启动固定漂移 |
