# @icoder/sdk

iCoDer JavaScript SDK — 面向中国医院的医疗 AI 智能体平台。

## 安装

```bash
npm install @icoder/sdk
```

## 快速开始

```js
import iCoDer from '@icoder/sdk';

const icoder = new iCoDer({
  baseURL: 'http://localhost:8000',
  auth: {
    accessToken: '<your-access-token>',
    refreshToken: '<your-refresh-token>',
  },
});

// 事实提取
const facts = await icoder.facts.extract('患者因腰痛伴左下肢放射痛3月就诊...', 'zh-CN');
console.log(facts.facts.diagnosis_facts);

// Agent 流式对话
const stream = await icoder.agents.stream('agent-id', '请分析以下病例...');
const reader = stream.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(new TextDecoder().decode(value));
}

// 用量查询
const usage = await icoder.usage.summary(30);
console.log(`近30天消耗积分: ${usage.credits_used}`);
```

## Phase 6 Gate 4 — 统一 Agent Run + Trace 资源 (v1.0.0-beta.2)

```js
// 统一 agent run 入口 (Phase 4-F2 + Phase 6 Gate 5)
const { data: run } = await icoder.runs.runText('medical-coding-agent',
  '患者男，65岁，因胸痛入院...',
  { runtime_mode: 'corti_like_fast', idempotencyKey: 'my-key-001' });
console.log(run.run_id, run.trace_id, run.trace_url);
console.log(run.cost);  // { amount: 0.0123, currency: 'CNY' }
console.log(run.latency_ms);

// 运行历史 (alembic 010)
const { data: history } = await icoder.runHistory.list({
  agent_id: 'medical-coding-agent', days: 7, limit: 50,
});

// Trace 时间线 (alembic 009) — 9-step timeline viewer 数据源
const { data: trace } = await icoder.runTrace.timeline(run.run_id);
console.log(trace.timeline);  // [{step, status, duration_ms, ...}, ...]
```

### Phase 6 Gate 4 注意事项

- **不发布到 npm** — `1.0.0-beta.2` 仅作为 dist-tag，通过 git/source 消费 (PACKAGE_BUILD_VERIFIED, REGISTRY_PUBLISH_DEFERRED)。
- **A2A v0.3 类型** — SDK 暴露 `A2AEnvelope`/`A2AMessage`/`A2AMessagePart` 类型 (mirror of `app/icoder/agent_runtime/a2a_facade.py`)。这些类型当前没有客户端消费者 (Python A2A 入口在 server 端)，仅用于未来 SDK 直接发 A2A 消息。
- **SSE 客户端** — 当前 agent_run 是 request/response 模式。Phase 7 候选: 增加 `EventSource`-based stream 客户端。

## 资源

| 资源 | 说明 |
|------|------|
| `icoder.facts` | 事实提取 |
| `icoder.agents` | 智能体管理 + 流式对话 |
| `icoder.experts` | 专家管理 |
| `icoder.reviews` | 医学编码审核 |
| `icoder.speechToText` | 语音转录 |
| `icoder.textGen` | 文书生成 |
| `icoder.billing` | 计费余额 |
| `icoder.usage` | 用量统计 |
| `icoder.oauth` | OAuth 客户端管理 |

## License

MIT
