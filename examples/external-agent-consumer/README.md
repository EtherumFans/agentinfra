# iCoDer External Agent Consumer — Sprint 2 Goal F

> **目的** — 以**外部消费者**身份调用 iCoDer，证明 Developer Golden Path 真实可用。

这个示例只通过 **公开 REST API** + **官方 SDK** 调用 iCoDer：
- ✗ 不 import 任何 iCoDer 内部模块（`app.*`、`icoder_runtime.*`、`backend.*`）
- ✗ 不访问数据库（不读 SQLite、不连 ORM）
- ✗ 不依赖任何"特权"路径（管理后门、内部测试 endpoint）

## 文件结构

```
examples/external-agent-consumer/
├── package.json       # 无运行时依赖 (Node 18+ 自带 fetch)
├── run-agent.mjs      # 消费者脚本 (REST + SDK 双路径)
├── .env.example       # 环境变量模板
└── README.md          # 本文件
```

## 前置条件

1. **后端在跑** — `cd backend && python -m uvicorn app.main:app --port 8000`
2. **OAuth Client 已创建** — 在 Console → API Clients 创建一个 OAuth Client
   （会显示一次 client_secret，**必须立刻复制保存**）
3. **Generic Agent 已存在** — 任选其一：
   - 用 Console → Agents → "通用翻译智能体 (translator-blank)" 模板创建一个 Agent
   - 或直接用任何预置 Generic Agent 的 id（`translator-blank` / `summarizer-blank`）

## 使用方法

```bash
cd examples/external-agent-consumer
cp .env.example .env
# 编辑 .env 填入 ICODER_API_CLIENT_ID / ICODER_API_CLIENT_SECRET

# 自动模式：SDK 优先，没装就降级 REST
node run-agent.mjs

# 强制纯 REST 路径（最干净的"外部消费者"证据）
node run-agent.mjs --mode rest

# 强制 SDK 路径
node run-agent.mjs --mode sdk
```

## 成功输出

```
══════════════════════════════════════════════════════════════════════════
  iCoDer External Agent Consumer — Sprint 2 Goal F Verification
  backend  : http://localhost:8000
  agent    : translator-blank
  mode     : rest
══════════════════════════════════════════════════════════════════════════
→ POST http://localhost:8000/api/oauth/token
✓ access token received (expires_in=3600s, token_type=Bearer)
→ POST http://localhost:8000/api/v1/agents/translator-blank/run
──────────────────────────────────────────────────────────────────────────
{
  "run_id": "...",
  "trace_id": "...",
  "status": "completed",
  "latency_ms": 4231,
  "cost": { "amount": 0.012, "currency": "CNY" },
  "runtime_mode": "corti_like_fast",
  "error": false,
  "output_preview": "你好，世界..."
}
──────────────────────────────────────────────────────────────────────────
✓ Goal F verified: external consumer received a structured response from iCoDer.
```

## Sprint 2 验证清单

| Goal F 子项 | 验证方式 |
|---|---|
| Create Agent | Console → Agents → 用 `translator-blank` 模板创建一个 Generic Agent |
| Get credentials | Console → API Clients → 创建 OAuth Client，复制 client_id + client_secret |
| External call | `node run-agent.mjs` 走完 token + agent run 两步 |
| Receive response | 脚本输出 `run_id` + `output` + `cost`，`error=false` |

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `token exchange failed: HTTP 401` | client_secret 错或已 rotate | Console 重新生成 secret |
| `agent run failed: HTTP 404` | AGENT_ID 拼错或 Agent 在另一个 tenant 下 | 用 `GET /api/rest/v1/agent_definitions` 确认 |
| `agent run failed: HTTP 403` | OAuth scope 不含 `api:write` | 重建 client，scope=`api:read api:write` |
| `SDK path failed: Cannot find package '@icoder/sdk'` | SDK 未发布到 npm | 用 `--mode rest` 或本地 workspace 路径（脚本会自动 fallback） |
| `error=true`, `error_reason=unknown_agent` | DB-stored Agent 但版本不匹配 | 检查 Agent 是否在当前 tenant 下、是否被 disable |
