# iCoDer Product Roadmap v2
## Medical Revenue Compliance AI Runtime Platform

Runtime 是底座，HIS 厂商是分发通道，Agent 包是分发单元。Marketplace 是 ISV 的"Agent 包注册表"，不是云端应用商店。

---

## 架构目标

```
icoder-runtime (Apache 2.0, pip install, 零外部依赖)
├── contract_engine      ── 合同强制验证
├── permissions          ── Deny-First 权限
├── guardrails           ── 输入/输出护栏
├── symbolic_state       ── 决策链 SHA-256 哈希
├── agent_runner         ── Agent 执行引擎
├── tool_registry        ── 工具注册表
├── agent_pack           ── Agent 包导入/导出（含自定义 Expert/Tool 完整定义）
├── http_server          ── 本地 HTTP API 模式（icoder-runtime serve --port 8765）
└── local_sqlite         ── 本地持久化

icoder-platform (SaaS, 闭源)
├── marketplace          ── Agent 包注册表
├── auth / billing       ── 认证 + 计费
└── dashboard            ── Web 管理界面
```

数据流 (Corti-style 托管云):

```
ISV 开发 Agent → 本地 icoder-cli 调试 (本地 dev)
    → 打包 .icoder-agent → 上传到 Marketplace (托管云 Console)

医院 / ISV Tenant → 浏览 Marketplace → 安装 Agent
    → Agent 注册到 Tenant 命名空间 → 按需 invoke via API Client (backend-service 或 ROPC embedded)

托管云 Runtime → 接收 API Client 请求 → 执行 Agent → 返回结果 (PHI 脱敏后入审计通道)
```

---

## Phase 1: Runtime 独立（Weeks 1-3）

目标：HIS 厂商可以 `pip install icoder-runtime`，5 分钟内在本地跑通编码审核 Agent。Runtime 不依赖 auth/billing/dashboard/cloud。

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 1.1 | 从 `orchestrator.py` 中抽出 symbolic_state 为独立模块 | 1 周 | `icoder-runtime/symbolic_state.py` |
| 1.2 | 移除 Runtime 核心对 auth 的依赖 | 3 天 | `agent_runner.py` 不再依赖 `get_current_user` |
| 1.3 | Runtime 本地 HTTP 服务模式 | 3 天 | `icoder-runtime serve --port 8765`。HIS 后端通过 localhost HTTP 调用，不要求引入 Python 依赖 |
| 1.4 | 包化：`setup.py` + `pyproject.toml` | 2 天 | `pip install icoder-runtime` 可用 |
| 1.5 | Runtime 本地部署文档 | 2 天 | HIS 厂商集成指南：安装→启动 HTTP 服务→加载 Agent→调用→导出证据包 |
| 1.6 | 后端测试适配新包结构 | 3 天 | 579 个测试在新包结构下全绿 |

**Phase 1 exit criteria：**
- `pip install icoder-runtime` 成功
- 导入 `from icoder_runtime import AgentRunner` 可用
- 无 auth/billing/dashboard 依赖
- 579 测试全绿

---

## Phase 2: Agent 包（Weeks 4-5）

目标：Agent 可以被打包成一个 `.icoder-agent` 文件，在有 Runtime 的任何地方导入运行。

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 2.1 | `.icoder-agent` 包格式定义 | 2 天 | 自包含格式：`manifest`, `system_prompt`, `experts`（含 ISV 自定义 Expert 完整定义）, `tools`（自定义 Tool specs 含合同）, `permissions`, `requirements`。包内引用完全自描述，不依赖外部注册表 |
| 2.2 | `icoder_runtime.agent_pack` 模块 | 3 天 | `export(agent_id) → .icoder-agent`；`import(path) → Agent definition`。导入时自动注册包内自定义 Tool/Expert 到本地 Runtime |
| 2.3 | Agent 模板 → 一键导出 | 1 天 | 20 个预置模板可以一键导出为 `.icoder-agent` 包 |
| 2.4 | 导入验证 | 2 天 | 校验：manifest 完整性、Runtime 版本兼容性、Tool 合同字段合法性、Expert 引用完整性 |
| 2.5 | HIS 厂商集成示例 | 2 天 | 完整示例：`pip install` → `icoder-runtime serve` → `agent import` → HTTP 调用 |

**Phase 2 exit criteria：**
- 从 Agent 模板导出一个 `.icoder-agent` 文件
- 在另一台机器上 `pip install icoder-runtime` → `import agent` → 成功运行
- HIS 集成示例可在本地完整跑通

---

## Phase 3: 开发者工具（Weeks 6-7）

目标：ISV 可以 self-service 构建、测试、打包、发布 Agent。Runtime 自带本地 Dashboard。

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 3.1 | CLI 工具 | 1 周 | `icoder init my-agent`（脚手架 → 生成 system_prompt + tools + permissions 模板）; `icoder test`（本地 Runtime 测试）; `icoder pack`（导出 .icoder-agent） |
| 3.2 | 本地 Dashboard | 2 周 | `icoder dashboard` — 本地 Web UI：Agent 列表、运行历史、证据链查看、Agent 包导入/导出。不需要登录 |
| 3.3 | SDK 参考文档（从 docstring 自动生成） | 1 周 | 完整 API 参考：Runtime, AgentRunner, ToolRegistry, SymbolicState, AgentPack |
| 3.4 | ISV 开发指南 | 3 天 | 从零到发布：创建 Agent → 写 Tool 合同 → 配置权限 → 本地测试 → 打包 → 发布到 Marketplace |

**Phase 3 exit criteria：**
- `icoder init → icoder test → icoder pack` 全流程走通
- 本地 Dashboard 可查看运行历史和证据链
- ISV 指南完整覆盖开发→打包→发布流程

---

## Phase 4: Marketplace 注册表（Weeks 8-9）

目标：ISV 有地方发布 Agent 包，HIS 厂商有地方发现和下载 Agent 包。

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 4.1 | Agent 包上传/发布端点 | 3 天 | `POST /api/marketplace/publish` — 上传 .icoder-agent + 描述 + 截图。自动解析 manifest 并索引 |
| 4.2 | 浏览/搜索/下载 | 3 天 | 分类浏览 + 全文搜索 + 版本列表 + 下载计数 + 一键下载 |
| 4.3 | 发布者 Dashboard | 3 天 | 发布者看自己 Agent 的下载量趋势 |
| 4.4 | Agent 包签名（可选） | 2 天 | SHA-256 签名 + 发布者公钥。导入时可选验证。首次发布跳过，Phase 4 后期加入 |

**Phase 4 exit criteria：**
- ISV 可以通过 CLI 或 Web 上传 Agent 包到 Marketplace
- HIS 厂商可以在 Marketplace 浏览、搜索、下载 Agent 包
- 下载的 Agent 包可以在本地 Runtime 中导入并运行

---

## 不再做的事（相比 v1 Roadmap）

| 原计划 | 原因 |
|--------|------|
| 在线"安装"Agent 到云端 Workspace | Agent 不运行在云端。分发单元是文件，不是在线激活 |
| 版本 diff 视图 + 回滚 UI | 版本管理 = 文件级。diff 是 CLI 工具的事，不在 MVP |
| ISV 云端用量分析 Dashboard | 没有云端调用就没有云端用量。改为本地统计 |
| Agent Playground（Web UI 在线测试） | 本地 Dashboard 已经覆盖。在线 Playground 无实际需求 |

---

## 不做 Marketplace 的 SaaS 怎么赚钱

| 收入来源 | 说明 |
|---------|------|
| iCoDer Platform（SaaS）订阅 | ISV/HIS 厂商使用云端 Dashboard、Marketplace 发布、多租户管理的订阅费 |
| Runtime 企业支持 | HIS 厂商 Runtime 集成技术支持、定制化 Tool 开发 |
| 医疗合规解决方案 | 医院/医保/商保的 POC → 年度授权 → 托管云 Tenant 订阅（项目制，但与 Runtime 分离） |

---

## 关键指标

| Phase | 指标 |
|-------|------|
| Phase 1 | `pip install icoder-runtime` 成功且 579 测试全绿 |
| Phase 2 | 一个 HIS 厂商用 .icoder-agent 包在本地 Runtime 跑通编码审核 |
| Phase 3 | 一个 ISV 用 CLI 全流程（init → test → pack）创建自己的 Agent |
| Phase 4 | 一个 ISV 的 Agent 包在 Marketplace 上被另一个 HIS 厂商下载并使用 |
