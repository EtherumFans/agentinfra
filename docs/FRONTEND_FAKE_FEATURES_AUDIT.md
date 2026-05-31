# Frontend Fake Features Audit

**日期**: 2026-05-12
**范围**: 后端 API → 前端消费者对照

## 1. 后端有 API 但前端无消费者

| 后端路由 | 端点数量 | 前端 API 客户端 | 前端调用页面 | 状态 |
|----------|---------|----------------|-------------|------|
| `/api/runtime/*` | 6 | **无** (未在 api.ts 中定义) | 0 | ❌ 完全无调用 |
| `/api/health` | 1 | `healthApi` 已定义 | 0 | ❌ 无页面调用 |
| `/api/websocket` (STT) | 1 | `sttApi` 已定义 | 0 | ❌ 前端使用浏览器 Web Speech API，不用后端 STT |
| `/api/a2a/*` | 3 | `a2aApi` 已定义 | 1 (SettingsPage 仅 toggle) | ⚠️ 仅配置开关，未真实调用 coordinate/chain |
| `/api/memory/*` | 3 | `memoryApi` 已定义 | 1 | ⚠️ 调用极少 |

### Runtime API 详情

以下 6 个端点**完全未连接前端**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/runtime/status/{case_id}` | GET | 获取案例运行时状态 |
| `/api/runtime/audit/{case_id}` | GET | 获取审计追踪 |
| `/api/runtime/review/{case_id}` | POST | 人工复核决策（DUC 门控） |
| `/api/runtime/duc/actions` | GET | 列出所有 DUC 操作 |
| `/api/runtime/stale` | GET | 列出卡住的案例 |
| `/api/runtime/active` | GET | 列出活跃案例 |
| `/api/runtime/states` | GET | 列出所有状态及其许可操作 |

### A2A API 详情

| 端点 | 方法 | 前端调用情况 |
|------|------|-------------|
| `/.well-known/agent.json` | GET | 无 |
| `/api/a2a/agents` | GET | SettingsPage 加载 Agent 列表 |
| `/api/a2a/coordinate` | POST | 无 |
| `/api/a2a/chain` | POST | 无 |

## 2. 前端页面但功能不完整

| 页面 | 问题 | 严重度 |
|------|------|--------|
| **TicketsPage** | 纯占位，`href="http://localhost:3000/tickets"` 自引用死循环 | P1 |
| **CodingWorkbenchPage:149** | 导出按钮无 onClick 处理函数 | P1 |
| **CaseReviewPage:49,64** | 错误处理用 `console.error` 而非用户可见 toast | P2 |
| **EvaluationPage** | API `evaluationApi.run()` 依赖 GoldCase 数据，数据不足时返回空 | P2 |

## 3. 后端有端点但前端未使用特定操作

| API 客户端 | 已调用的方法 | 未调用的方法 |
|-----------|-------------|-------------|
| `reviewsApi` | `create`, `get`, `reviewCandidate`, `complete`, `list` | `getReportMarkdown`, `getReportHtml` |
| `expertsApi` | `list`, `get`, `call` | `search` |

## 4. 总结

- **Runtime API**: 6 个端点完全无前端消费者 — 记录了修复后的 Runtime 绕行问题中新增的 audit/guard 数据，但前端无法查看
- **A2A API**: 仅 SettingsPage 用于 toggle 开关，核心的 coordinate/chain 从未被真实业务调用
- **STT**: 前端使用浏览器 Web Speech API，后端 `/ws` STT 端点从未被前端使用
- **导出功能**: CodingWorkbench 导出按钮至今无实现
- **健康检查**: healthApi 定义了但从未被任何页面调用
