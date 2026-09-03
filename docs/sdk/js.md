# JavaScript SDK

```bash
npm install @icoder/sdk @a2a-js/sdk ai
```

生产服务应先用 OAuth client credentials 换取短期、租户绑定的 access token；不要把
client secret 放进浏览器包或业务源码。

```javascript
import iCoDer, { iCoDerClient } from '@icoder/sdk';

const baseURL = process.env.ICODER_BASE_URL ?? 'http://127.0.0.1:8000';
const auth = new iCoDerClient({ baseURL, auth: { accessToken: '' } });
const token = await auth.authenticate(
  process.env.ICODER_CLIENT_ID,
  process.env.ICODER_CLIENT_SECRET,
);
const client = new iCoDer({
  baseURL,
  auth: { accessToken: token.access_token },
});

const facts = await client.facts.extract({
  context: [{ type: 'text', text: '去标识病历文本' }],
  outputLanguage: 'zh-CN',
});
console.log(facts.facts, facts.usageInfo.creditsConsumed);

const coding = await client.medicalCoding.predict({
  text: '患者有2型糖尿病史。',
  coding_systems: ['icd10cn', 'icd9cm3'],
  filter: {
    include: ['E11'],
    exclude: ['E11.0'],
    expand: true,
  },
});
console.log(coding.codes, coding.filter_applied);

// Development risk review only: this rejects authoritative/payment-bearing results.
const drgRisk = await client.drgDipRiskReview.analyze({
  primary_diagnosis: { code: 'I10' },
  patient_age: 58,
});
console.log(drgRisk.review_conclusion, drgRisk.manual_review_required);

const { data: run } = await client.runs.runText(
  'note-completeness-agent',
  '去标识病历文本',
  { idempotencyKey: crypto.randomUUID() },
);
console.log(run.run_id, run.result, run.trace_url);
const status = await client.runs.get(run.run_id);
const cancellation = await client.runs.cancel(run.run_id, 'operator request');
const traceToken = new URL(run.trace_url, 'https://api.example.cn')
  .searchParams.get('token');
if (traceToken) {
  const lifecycleEvents = await client.runs.streamEvents(run.run_id, traceToken);
}
```

For resilient consumers, use `streamEventsResilient()`. A purged trace or
cursor produces the terminal, non-retryable `RunEventRetentionError`; only its
safe code and `retentionDays` are retained, never the raw clinical response.

A2A v1 长任务使用持久化 Task；订阅返回原始 SSE `ReadableStream`，可带
`afterSequence`/`lastEventId` 续传：

```ts
const submitted = await client.a2a.messageSendV1(
  'note-completeness-agent',
  '去标识病历文本',
  { returnImmediately: true },
);
const taskId = submitted.task!.id;
const stream = await client.a2a.subscribeTaskV1(
  'note-completeness-agent',
  taskId,
  { afterSequence: 0 },
);
const settled = await client.a2a.waitTaskV1(
  'note-completeness-agent',
  taskId,
);
```

`waitTaskV1()` 会如实返回 completed、failed、canceled、rejected，以及可续跑的
input-required/auth-required。后两项不是终态；续跑必须再次调用 `messageSendV1()` 并同时
携带服务端返回的 `contextId` 和 `taskId`。SDK 不会把失败或无法中途取消的 Provider 调用包装成成功。

### Vercel AI SDK Adapter

`@icoder/sdk/ai-sdk-adapter` 导出 `convertToParams()`、`toUIMessageStream()`、
`createA2AClientFactory()` 与 `createFetchImplementation()`，并提供 Corti-compatible
UI message、JSON/text/status part 和 MCP credential 类型。当前候选要求
`@a2a-js/sdk >=1.0.0 <2` 与 `ai >=6 <8` peer；工厂返回官方异步
`ClientFactory`，使用其 ProtoJSON codec、JSON-RPC request-ID 校验和 SSE parser。适配器从最后一条 assistant
消息推断 `contextId`，只有 `state: 'input-required'` 时携带 `taskId`，凭据只在没有
`taskId` 的首轮作为 DataPart 发送。鉴权 fetch 固定同源、禁止重定向跟随并覆盖调用方伪造的 Authorization。

```ts
const a2a = await createA2AClientFactory(client).createFromUrl(
  `${baseURL}/api/v2/agentic/agents/note-completeness-agent/.well-known/agent-card.json`,
  '',
);
return createUIMessageStreamResponse({
  stream: toUIMessageStream(a2a.sendMessageStream(convertToParams(messages))),
});
```

OAuth exchange 使用 `application/x-www-form-urlencoded`。client-credentials token 默认有效期
较短，响应不保证包含 refresh token；长期服务应在到期时重新换取 token。

中国编码入口可单独或同时接受 `icd10cn` 诊断和 `icd9cm3` 手术操作。`expand:true`
使 include/exclude 类别按前缀匹配叶子编码；`expand:false` 只匹配完整编码。过滤同时由
服务端在模型返回后确定性执行，不应把它当作模型提示词约定。

`drgDipRiskReview` 只公开非权威风险审查、规则和治理信息。SDK 会拒绝非零 DRG 权重、
DIP 分值、支付估算、`billing_authoritative:true` 或 `manual_review_required:false`；
`predicted_drg` 是兼容字段中的开发候选，不得用于医保分组、结算或临床自动决策。

受控实网连通性检查必须先读取租户目录声明的策略，并且只有目录明确允许时才调用：

```ts
const catalog = await client.models.getCatalog();
if (catalog.live_canary_available) {
  const canary = await client.models.liveCanary(
    catalog.effective_deployment_id,
    catalog.live_canary_policy.max_cost_cny,
  );
  console.log(canary.status, canary.latency_ms);
}
```

`liveCanary()` 不接受提示词或自由文本，只发送服务端固定的无患者数据载荷；完成正文不会
返回或写入审计。一次成功仅是连接观察，不等于模型质量、持续在线健康、SLA 或权威账单。

机器客户端的签名 `trace_url` 才包含事件 token。取消必须读取 `outcome`；HTTP 202 +
`RECORDED_ONLY` 表示 Provider 仍在运行，应继续轮询 `get()`，不能显示“已取消”。
