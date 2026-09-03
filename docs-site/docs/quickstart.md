---
sidebar_position: 2
title: 5 分钟 Quickstart
description: 从 0 到第一次 Agent Run — 5 步搞定你的第一个 iCoDer 调用。
---

# 5 分钟 Quickstart

本指南走完一遍 iCoDer 平台的 **核心闭环**: 注册账号 → 创建 API Client → 安装 SDK →
换取 access token → 调用 Medical Coding Agent。完成后, 你将拥有第一个带 trace_url 的
真实 Agent 运行结果。

预计耗时: **5–10 分钟** (不包含等待人工审核)。

---

## 前置条件

- iCoDer Console 账号 (联系你的 iCoDer Customer Success 或申请 trial)
- Node.js ≥ 18.x (SDK + Docusaurus 文档站需要)
- 一个真实病例文本 (用作 Agent 输入; 详见下面的示例)

## Step 1 — 登录 iCoDer Console

iCoDer 是**云托管 SaaS** (R6 ADR 决策), 入口:

```
https://console.icoder.cloud    # 生产 (Sprint 2 上线)
http://localhost:8000           # 本地开发 (ICODER_DEPLOYMENT_MODE=local)
```

使用 Console 管理员账号登录。如果你是设计合作伙伴 (design partner), 你会收到租户
slug + 初始 admin 邮箱; 首次登录后请立即修改密码。

## Step 2 — 创建 API Client

进入 **Console → "API Clients"** 页面 (`/console/api-clients`):

1. 切换到 **OAuth Clients** 标签
2. 点击 **"+"** 创建新客户端
3. 填写:
   - **Name**: `my-first-integration`
   - **Description**: `Quickstart 试跑`
   - **Scopes**: `api:read api:write` (默认即可)
4. 提交后, 弹窗会显示 **client_id** 和 **client_secret**

> ⚠️ **client_secret 仅此一次可见** — 立即复制保存。关闭弹窗后无法再次查看, 只能
> 轮换 (重新生成)。这是 charter §GATE4 强制约束。

## Step 3 — 安装 SDK

### JavaScript / TypeScript (推荐)

```bash
npm install @icoder/sdk
# 或者
pnpm add @icoder/sdk
yarn add @icoder/sdk
```

> 当前 `@icoder/sdk@1.0.0-beta.2` 通过 git/source 消费; 1.0.0 stable 将发布到 npm
> (见 [PUBLISH.md](https://github.com/icoder-cloud/icoder/blob/main/packages/icoder-sdk/PUBLISH.md))。

### Python (Sprint 2 计划)

```bash
pip install icoder-python  # 待发布, 详见 Sprint 2 依赖清单
```

### curl (无 SDK)

无需安装, 直接用 curl。下面的示例同时给出 curl 和 SDK 两种写法。

## Step 4 — 换取 access token

### curl

```bash
curl -X POST https://api.cn.icoder.cloud/api/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=$YOUR_CLIENT_ID" \
  -d "client_secret=$YOUR_CLIENT_SECRET" \
  -d "scope=api:read api:write"
```

返回 (RFC 6749 标准):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 300,
  "scope": "api:read api:write"
}
```

> **Realm-based endpoint** 也支持: `POST /api/oauth/realms/{realm}/token` — 与
> Corti 风格的 `auth.{env}.corti.app/realms/{tenant}` 兼容。Realm 仅作为租户提示,
> 实际租户解析以 JWT 的 `org_id` claim 为准。

### JavaScript SDK

```js
import iCoDer from '@icoder/sdk';

const icoder = new iCoDer({
  baseURL: 'https://api.cn.icoder.cloud',
  auth: {
    accessToken: process.env.ICODER_ACCESS_TOKEN!,
    refreshToken: process.env.ICODER_REFRESH_TOKEN!,
  },
});
```

SDK 会在 access_token 过期时自动调 `/api/auth/refresh` 续签。如果走 M2M
(`client_credentials`) 流程, 建议自己在服务端用 axios 拦截器续签 (SDK 不内置
M2M 自动续签, 因为 client_secret 不能落到客户端)。

## Step 5 — 调用 Medical Coding Agent

### curl

```bash
curl -X POST https://api.cn.icoder.cloud/api/v1/agents/medical-coding-agent/run \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "患者男性, 78岁, MRI 显示 T12 椎体压缩性骨折。",
    "runtime_mode": "corti_like_fast",
    "idempotency_key": "quickstart-001"
  }'
```

### JavaScript SDK

```js
const { data: run } = await icoder.runs.runText(
  'medical-coding-agent',
  '患者男性, 78岁, MRI 显示 T12 椎体压缩性骨折。',
  {
    runtime_mode: 'corti_like_fast',
    idempotencyKey: 'quickstart-001',
  }
);

console.log(run.run_id);          // "run_abc123..."
console.log(run.trace_id);        // "trace_def456..."
console.log(run.trace_url);       // https://api.cn.icoder.cloud/api/v1/runs/run_abc123/trace?token=...
console.log(run.cost);            // { amount: 0.0123, currency: 'CNY' }
console.log(run.latency_ms);      // 5462
console.log(run.output.primary_diagnosis);
// { code: 'S22.000', name: 'T12 椎体压缩性骨折', confidence: 0.82, ... }
```

### 返回结构 (节选)

```json
{
  "run_id": "run_abc123",
  "trace_id": "trace_def456",
  "trace_url": "https://api.cn.icoder.cloud/api/v1/runs/run_abc123/trace?token=...",
  "cost": { "amount": 0.0123, "currency": "CNY" },
  "latency_ms": 5462,
  "output": {
    "primary_diagnosis": {
      "code": "S22.000",
      "name": "T12 椎体压缩性骨折",
      "confidence": 0.82,
      "evidence": ["MRI 显示 T12 椎体压缩性骨折"]
    },
    "secondary_diagnoses": [],
    "procedures": [],
    "manual_review_required": true,
    "review_conclusion": "WARNING"
  }
}
```

`manual_review_required: true` 是 iCoDer 的设计强约束 — **AI 不替代编码员**, 所有
编码建议需经人工确认。详见 [Medical Coding 红线](https://github.com/icoder-cloud/icoder/blob/main/backend/official_agents/medical_coding/agent_pack.json)。

---

## 下一步

- 📚 [SDK 完整文档](./sdk) (Sprint 2)
- 🏥 [Console API Clients 操作指南](./api-clients) (Sprint 2)
- 🔌 [A2A v0.3 协议](https://github.com/icoder-cloud/icoder/blob/main/docs/ICODER_V1_A2A_SPEC.md)
- 🚀 [部署到云](https://github.com/icoder-cloud/icoder/blob/main/docs/cloud/CLOUD_DEPLOYMENT.md)
- 🧪 查看 trace_url: 把它直接贴到浏览器, 看到 9-step timeline

## 故障排查

| 错误 | 原因 | 解决 |
|------|------|------|
| `401 invalid_client` | client_secret 错误或客户端已停用 | 在 Console 重新生成 secret |
| `401 tenant_header_mismatch` | `Tenant-Name` header 与 JWT org_id 不一致 | 检查请求 header 或不传 Tenant-Name (用 JWT 默认) |
| `404 unknown_agent_id` | agent_id 不存在 | 用 `GET /api/rest/v1/agent_definitions` 列出可用 agent |
| `200 error=true error_reason=llm_degraded` | LLM provider 不健康 | 检查 Console → Status, 重试或切换 runtime_mode |
| `200 manual_review_required=true` | 这是**预期行为**, 不是错误 | iCoDer 设计强约束 — 见 Medical Coding 红线 |

## 货币说明

所有金额以 **CNY (人民币 ¥)** 计价, 不用 USD。详见
[CLAUDE.md 货币约定](https://github.com/icoder-cloud/icoder/blob/main/CLAUDE.md#货币约定-phase-5-a2--2026-07-10)。
