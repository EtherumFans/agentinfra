# @icoder/sdk

面向中国医院场景的 iCoDer API JavaScript/TypeScript 客户端。当前开发候选版覆盖 Agent Hub、统一 Agent Run、A2A 多轮 Context、事实提取，以及可持久化的 v2 录音与转写生命周期。

## Corti-compatible Streams

```ts
const session = await client.streams.connect({
  interactionId: crypto.randomUUID(),
  tenantName: organizationSlug,
  environment: 'cn',
  configuration: {
    transcription: { primaryLanguage: 'zh-CN' },
    mode: { type: 'transcription' },
    retentionPolicy: 'none',
    audioFormat: 'audio/ogg; codecs=opus',
  },
});
session.on('message', event => console.log(event.type));
session.sendAudio(oggOpusChunk);
session.flush();
session.end();
await session.waitForEnded();
```

单块音频最多 64,000 bytes、单会话最多 32 MiB。当前中国开发候选支持中文单声道以及
2–8 声道 16 kHz signed 16-bit PCM 的最终转写、参与者声道归属、`fixed`/`fast_init` Facts
调度、`flush`/`usage`/`ENDED` 与可选加密留存。会话 keyterms 支持最多 1,000 个按顺序、
大小写敏感的词项并进入 FunASR hotword；diarization 仍会明确拒绝；
发送音频后断线不会进行可能重复临床音频的隐式重放。

`retentionPolicy: 'retain'` 会把未结束交互的状态加密持久化。客户端收到 `flushed` 后若连接
中断，会以可重试的 `stream_resume_required` 失败；调用
`client.streams.resume(options)` 后，服务端必须明确返回 `resumed: true`，并给出已恢复的
audio/transcript/Facts 计数，否则 SDK 以 `stream_checkpoint_not_found` 失败关闭。未收到
`flushed` 的音频仍返回 `audio_resume_unsupported`，SDK 不会猜测或重复发送。

流式输入可使用可识别的编码容器（Ogg、WebM、Opus/Vorbis、MP3、FLAC 或 MP4/M4A），
或受治理的 raw PCM 配置：
`audio/pcm; rate=16000; channels=<1..8>; bits=16; endian=little; encoding=sint`。
PCM 的 `endian`/`encoding` 可省略并采用上述默认值，帧必须完整对齐；其他 PCM 配置返回
`raw_pcm_profile_not_available`。多声道必须设置 `isMultichannel: true`，且 participants 必须
精确覆盖 `0..channels-1`；服务端不推断或合并说话人。WAV 仍只用于预录音上传。

仅上述 PCM 配置可启用 `audioEvents: { enabled: true }`。SDK 将
`speechQualityIssueDetected/Recovered` 和 `longSilenceDetected/Recovered` 解析为严格类型；
未知或带私有扩展的事件失败关闭为 `unknown`。当前检测是确定性的工程信号质量启发式，
不是临床结论；编码容器上的音频事件返回 `audio_events_require_pcm`。

容器头通过后，服务端还必须在隔离、单线程、限时且无输出的解码器子进程中成功解码一帧，
才允许进入 ASR 或加密留存。畸形媒体、解码超时或解码器缺失分别以稳定错误码失败关闭，
SDK 不会把它们转换为转写成功。

每个 API Worker 对 decoder 子进程设置独立并发与有界排队；容量耗尽返回
`AUDIO_VALIDATION_BUSY`，连接取消会终止并回收子进程。SDK 应把这些 1013/503 状态视为
可重试的临时能力失败，且不得自动重放已经无法确认服务端状态的临床音频。

## A2A 多轮 Context

```ts
const first = await client.a2a.messageSend('note-completeness-agent', '第一轮');
const second = await client.a2a.messageSend(
  'note-completeness-agent',
  '继续上一轮',
  { contextId: first.contextId },
);
const history = await client.a2a.getContext(
  'note-completeness-agent',
  second.contextId,
);
await client.a2a.deleteContext(history.id);
```

## A2A v1 持久化异步 Task

```ts
const submitted = await client.a2a.messageSendV1(
  'note-completeness-agent',
  '去标识病历文本',
  { returnImmediately: true },
);
if (!submitted.task) throw new Error('server did not return a Task');

// 可用 Last-Event-ID 恢复原始 SSE；轮询返回终态或可续跑中断态。
const events = await client.a2a.subscribeTaskV1(
  'note-completeness-agent',
  submitted.task.id,
  { afterSequence: 0 },
);
const terminal = await client.a2a.waitTaskV1(
  'note-completeness-agent',
  submitted.task.id,
);
if (terminal.status.state === 'TASK_STATE_INPUT_REQUIRED') {
  await client.a2a.messageSendV1(
    'note-completeness-agent',
    '已确认主要诊断',
    {
      contextId: terminal.contextId,
      taskId: terminal.id,
    },
  );
}
```

`waitTaskV1()` 在 completed、failed、canceled、rejected 或
input-required/auth-required 时返回；后两项是中断态，不是成功或失败，必须携带服务端
`contextId`/`taskId` 续跑。终态 Task 不允许恢复。

## Vercel AI SDK Adapter

适配器独立入口与 Corti 当前公开 0.4.0 函数/类型面一致，使用官方
`@a2a-js/sdk` 1.0.x ClientFactory 与 ProtoJSON/SSE codec。在 Next.js 服务端安装
`@a2a-js/sdk` 和 `ai` 后，可把 `useChat` 消息转换为 A2A，并把事件转换为
`createUIMessageStreamResponse` 可消费的结构化 chunks：

```ts
import {
  convertToParams,
  createA2AClientFactory,
  toUIMessageStream,
  type CortiUIMessage,
} from '@icoder/sdk/ai-sdk-adapter';
import { createUIMessageStreamResponse } from 'ai';

const params = convertToParams(messages as CortiUIMessage[]);
const a2a = await createA2AClientFactory(client).createFromUrl(
  `${baseURL}/api/v2/agentic/agents/note-completeness-agent/.well-known/agent-card.json`,
  '',
);
return createUIMessageStreamResponse({
  stream: toUIMessageStream(a2a.sendMessageStream(params)),
});
```

MCP `ExpertCredential` 只能在可信服务端从 Secret Manager/环境注入；适配器仅在没有
`taskId` 的首轮把它转换为 A2A DataPart，不写 metadata、URL、日志或浏览器状态。
工厂和低层 fetch 默认拒绝跨源 URL、URL 内凭据、重定向跟随以及缺失 access token。
`createFromUrl()` 是官方 SDK 的异步 Agent Card 发现调用，必须 `await`。

## Feedback 训练用途独立授权

普通 Task/message feedback 永远不自动授权训练。只有组织 owner/admin 能对一条反馈的精确
快照授予最长 30 天、仅 `quality_improvement` 且仅
`feedback_metadata_only` 的资格；修改或删除反馈会撤销资格。该合同不授权 Task、Message、
模型输入/输出或 feedback reason。

```ts
const grant = await client.a2a.authorizeFeedbackForTraining(
  contextId,
  taskId,
  feedbackId,
  {
    purposeOfUse: 'quality_improvement',
    dataScope: 'feedback_metadata_only',
    expiresAt: new Date(Date.now() + 7 * 86400_000).toISOString(),
    approvalReference: 'qi-review-opaque-001',
    acknowledgement: true,
  },
);
await client.a2a.revokeFeedbackTrainingAuthorization(contextId, taskId, feedbackId);
```

## 安装

发布到 npm registry 前，请从仓库构建并通过本地路径消费：

```bash
cd packages/icoder-sdk
npm install
npm run build
```

## 托管认证与有界重试

服务端应用可直接配置 OAuth client credentials；SDK 会在首个请求前换取 token、在到期前刷新，并把并发换 token 合并为一次请求。401 只允许一次鉴权刷新重放。408/429/5xx 默认最多重试 2 次，遵守并限制 `Retry-After`；GET/HEAD/OPTIONS/PUT/DELETE 可重试，POST/PATCH 只有携带 `Idempotency-Key` 才会重试。

```ts
const client = new iCoDer({
  baseURL: 'https://api.example.cn',
  auth: { clientId: process.env.ICODER_CLIENT_ID!, clientSecret: process.env.ICODER_CLIENT_SECRET! },
  retry: { maxRetries: 2, initialDelayMs: 250, maxDelayMs: 2000 },
});
```

token 交换失败抛出不保留请求正文、Authorization 或 client secret 的 `iCoDerAuthenticationError`。普通 API 错误按 400/401/403/404/409/422/500/502/504 分型，统一继承 `iCoDerAPIError`；只保留 status、request ID 和白名单 code/reason/字段位置，不保留可能含 PHI 的原始 body。浏览器端不得配置 client secret，应使用服务端签发的最小 scope 短期 bearer token。

Agentic Task、Context、Context Task 和 Trace 支持惰性自动翻页；重复/非法 cursor 或超出 `maxPages` 会失败关闭：

```ts
for await (const context of client.a2a.iterateContextsV2({ pageSize: 50 })) {
  console.log(context.id);
}
```

## 快速开始

```ts
import iCoDer from '@icoder/sdk';

const client = new iCoDer({
  baseURL: 'https://api.example.cn',
  auth: { accessToken: '<tenant-bound-access-token>' },
});

const hub = await client.agents.hub();
const tenantReadiness = await client.agents.hubReadiness();
const coding = tenantReadiness.agents.find(
  (item) => item.agent_id === 'medical-coding-agent',
);
if (!coding?.runtime_readiness.run_action_enabled) {
  throw new Error(coding?.runtime_readiness.reason ?? 'Agent is unavailable');
}
const projectAgent = await client.agents.clone('medical-coding-agent', {
  name: '住院病案编码项目 Agent',
});
const run = await client.runs.runText(
  projectAgent.runtime_agent_id,
  '患者因胸痛入院……',
  { idempotencyKey: 'encounter-001' },
);
console.log(hub.total, run.data.trace_id);

const status = await client.runs.get(run.data.run_id);
const cancellation = await client.runs.cancel(run.data.run_id, 'operator request');
const traceToken = new URL(run.data.trace_url).searchParams.get('token');
const events = await client.runs.streamEvents(run.data.run_id, traceToken!);
```

## Agent Connector Graph

Connector 由 owner/admin 配置，运行时只能通过受审计的 Agent Run 触发。图节点固定选择
Connector、操作、最小输入字段、数据分类和用途；模型不能自行提供 URL、凭据或节点参数。

```ts
const connector = await client.agents.createConnector('custom-agent', {
  type: 'registry',
  name: 'Approved semantic memory',
  config: { registry_key: 'memory', capabilities: ['remember', 'recall', 'forget'] },
});

const consent = await client.agents.grantMemoryConsent('custom-agent', {
  acknowledgement: true,
  purpose_of_use: 'treatment',
  retention_days: 30,
  expires_in_days: 30,
});
if (consent.patient_authority_verified || consent.phi_storage_allowed) {
  throw new Error('Unexpected patient-PHI authority');
}

await client.agents.putConnectorGraph('custom-agent', {
  version: '1.0',
  enabled: true,
  execution_mode: 'sequential',
  expected_revision: 0,
  nodes: [{
    id: 'recall', connector_id: connector.id, operation: 'recall',
    required: true, input_keys: ['query', 'top_k'],
    data_classification: 'deidentified', purpose_of_use: 'treatment',
  }],
});
```

Memory consent 只代表已认证用户对本人去标识化偏好/上下文的自助授权，不代表患者或医院授权；服务端始终拒绝通过该 consent 存储患者 PHI。撤销时调用 `revokeMemoryConsent`，对应内容和语义向量会被硬删除。

需要认证的 Connector 只接受 `vault://`、`kms://` 或 `secret://` 引用；不要把 API Key
写入 `config`、日志或源码。必需节点失败或输出安全检查失败时，服务端不会调用模型或发布结果。

内置 Registry key 还包括 `drugbank` (`lookup`)、`posos` (`guide`) 与
`web-search` (`search`)。前两项只有在运维配置合法商业许可证网关后才执行；Web Search
还要求平台与当前租户双重 opt-in。三者都只接受 `deidentified` 输入，网关 URL 和令牌
不能由 Agent 或 SDK 请求提供。

For long-running consumers, prefer the bounded resilient iterator. It resumes
from the last SSE ID, renews an expired signed trace token through the bearer
identity, and never retries 400/403/404/409 or malformed protocol data:

```ts
for await (const event of client.runs.streamEventsResilient(
  run.data.run_id,
  traceToken!,
  { maxAttempts: 4, initialDelayMs: 250, maxDelayMs: 4000 },
)) {
  console.log(event.id, event.event);
}
```

When the server has already purged the retained trace, both stream methods
throw `RunEventRetentionError` (`SSE_TRACE_EXPIRED` or
`SSE_CURSOR_EXPIRED`). The exception exposes only the safe error code and
`retentionDays`; it is terminal and is never retried automatically.

取消结果必须读取 `cancellation.data.outcome`：`RECORDED_ONLY` 表示请求已审计但 Provider
仍在运行，SDK 不会把它误报为已取消。`events` 是签名、去 PHI 的 SSE 生命周期流。
断线后将最后收到的 SSE `id:` 作为第四个 `lastEventId` 参数再次调用
`streamEvents(runId, traceToken, signal, lastEventId)`，服务端会从下一条 trace 恢复。

## Medical Coding 过滤

```ts
const coding = await client.medicalCoding.predict({
  text: '患者有2型糖尿病史。',
  coding_systems: ['icd10cn', 'icd9cm3'],
  filter: { include: ['E11'], exclude: ['E11.0'], expand: true },
});
console.log(coding.codes);
```

中国编码入口支持单独或同时请求 `icd10cn` 诊断和 `icd9cm3` 手术操作。`expand` 开启时
类别按前缀匹配叶子编码，关闭时只匹配完整编码；服务端会在模型返回后再次强制过滤。

## Models 受控实网 Canary

```ts
const catalog = await client.models.getCatalog();
if (catalog.live_canary_available) {
  const canary = await client.models.liveCanary(
    catalog.effective_deployment_id,
    catalog.live_canary_policy.max_cost_cny,
  );
  console.log(canary.status, canary.latency_ms, canary.cost.amount);
}
```

该方法只发送服务端固定的无患者数据载荷，不接受提示词或病例文本，也不返回模型正文。
它需要 owner/admin、显式服务端开关、区域外发许可、费用上限和冷却时间；一次成功只证明
当时的连通性，不证明临床质量、持续可用性或账单准确性。

开发环境可使用 `http://127.0.0.1:8000`。生产环境应使用 HTTPS，并使用绑定组织租户的短期访问令牌。

## v2 录音与转写

```ts
const recording = await client.speechToText.uploadRecording(
  'interaction-001',
  new TextEncoder().encode('synthetic-audio-for-development'),
  'audio/wav',
);
const transcript = await client.speechToText.createTranscript('interaction-001', {
  recordingId: recording.recordingId,
  primaryLanguage: 'zh-CN',
  spokenPunctuation: true,
  keyterms: { terms: [{ term: '房颤' }, { term: 'Corti Health' }] },
  async: true,
});
console.log(transcript.statusCode, transcript.location);
```

`spokenPunctuation: true` 会在已验证的中文路径中把显式口述的“逗号、句号、问号”等转换为
中文标点；默认关闭，并在同步、异步及重启恢复路径保持相同语义。旧 `isDictation: true`
仅在两个当前标点字段都未提供时作为兼容回退。`keyterms.terms` 按顺序、大小写敏感地传给
识别器，最多 1,000 项且每项最多 50 字符；它只做识别偏置，不做结果替换。SDK 在上传前执行
150 MB 客户端限制；服务端仍是最终的鉴权、租户隔离和大小校验边界。

预录音远程问诊多声道当前接受时间对齐的 stereo 16 kHz/16-bit PCM WAV，以及声明正确的
Ogg、WebM、Opus、Vorbis、MP3、FLAC、M4A/AAC 双声道容器；每个声道只包含一位参与者。
创建请求设置 `isMultichannel: true`，并传入
`participants: [{ channel: 0, role: 'doctor' }, { channel: 1, role: 'patient' }]`。
服务端在隔离且有界的 ffprobe/ffmpeg 子进程中验证、解码，再分别识别并加密保存结构化行。
识别提供方返回有效短语时间戳时，`start`/`end` 为毫秒；否则诚实退化为每声道整段范围。
声道数不匹配、容器声明不符和 diarization 会失败关闭。

## 实时语音转写

```ts
const session = await client.speechToText.connectManagedSession({
  language: 'zh-CN',
  reconnectAttempts: 3,
});
session.on('message', event => {
  if (event.type === 'interim' || event.type === 'final') console.log(event.text);
});
session.sendAudio(audioChunk); // WebM/Opus binary chunk
session.requestInterim();
session.sendEnd();
```

`connectManagedSession()` 默认等待服务端 `ready`，提供类型化事件、token 刷新和有界指数
重连。双方协商 `icoder.stt-resume.v1` 后，每个音频块携带单调序号并获得 `audio_ack`；SDK
在服务端声明的上限内保存不可变内存副本，断线后从 `nextAudioSequence` 重放音频及已发送的
结束指令。音频不由 SDK 落盘，也不在服务端跨进程保存；当前 `client_replay` 模式重连时通常
从序号 1 重放。若旧服务端未确认恢复能力，发送音频后的断线仍以
`audio_resume_unsupported` 失败关闭。浏览器只应使用短期、租户绑定且带
`transcribe`/`streams` scope 的 token，不能包含 client secret。

`createSession()` 保留为原始 WebSocket 兼容入口。当前验证范围仅含中文、自动标点和
WebM/Opus start，32 MiB 会话总量仍由服务端强制；服务端默认禁止在 API 进程隐式加载
FunASR/Whisper/说话人分离原生栈，必须由受治理的区域 STT 服务或显式批准的本地部署提供
真实转写能力。

## Documents 与 Templates

```ts
const sections = await client.templates.listSections({
  lang: ['zh-CN'],
  region: ['CHN'],
});

const preview = await client.documents.preview(crypto.randomUUID(), {
  context: [{ type: 'string', data: '去标识临床样例文本' }],
  template: {
    sections: sections.slice(0, 2).map(section => ({
      key: section.id,
      nameOverride: section.name,
    })),
  },
  outputLanguage: 'zh-CN',
  documentationMode: 'global_sequential',
});
console.log(preview.sections, preview.usageInfo.creditsConsumed);
```

`documents.preview()` 强制发送 `X-Corti-Retention-Policy: none`，且仅在服务端返回 `acknowledged` 时返回文档。生成内容必须由临床人员复核。

## Facts 与 Text Generation 兼容入口

```ts
const facts = await client.facts.extract({
  context: [{ type: 'text', text: '患者主诉胸痛。' }],
  outputLanguage: 'zh-CN',
});

const generated = await client.textGen.generate('去标识临床文本', {
  template: '出院小结',
  outputLanguage: 'zh-CN',
});
console.log(facts.usageInfo.creditsConsumed, generated.credits_consumed);
```

`textGen.generate()` 是旧调用面的兼容 facade，实际使用 Guided Documents `dynamicTemplate`。它强制生成文书零留存确认；动态模板与 Section 元数据仍会登记在当前租户，因此模板名称不得包含患者标识。`docName`、`maxTokens` 和 `temperature` 当前不受 Guided 合同支持，会在发送前失败关闭。新集成应优先直接使用 Guided Documents 类型。

## 主要资源

| 属性 | 能力 |
| --- | --- |
| `client.agents` | Agent 管理、Hub 卡片和流式调用 |
| `client.a2a` | A2A v1 Task/Context/Artifact 与托管对象生命周期 |
| `client.runs` | 统一 Agent Run 与 trace 元数据 |
| `client.speechToText` | v2 录音/转写生命周期与鉴权实时 WebSocket |
| `client.documents` | Classic 文档生成、零保留预览及加密生命周期 |
| `client.templates` | Guided Template/Section 发现及租户 Section 管理 |
| `client.facts` | 临床事实提取 |
| `client.textGen` | Guided Documents 动态模板兼容生成（文书零留存） |
| `client.medicalCoding` | 中国医学编码预测、Corti 风格代码过滤与预估费用 |
| `client.drgDipRiskReview` | 开发用途 DRG/DIP 风险审查（非官方分组、非结算） |
| `client.billing` / `client.usage` | 计费和用量查询 |
| `client.oauth` | OAuth 客户端管理接口 |
| `client.models` / `client.platform` | 模型目录与平台访问控制 |

历史 `client.reviews` 与 `client.marketplace` facade 已移除：后端没有对应公开路由。编码审核使用 `client.agents` / `client.a2a` / `client.medicalCoding`；Agent 发现使用 `client.agents.hub()`。

## Task Artifact 托管对象

```ts
const object = await client.a2a.uploadTaskArtifactObjectV2(
  contextId,
  taskId,
  artifactId,
  {
    raw: 'eyJ0eXBlIjoiZGVpZGVudGlmaWVkIn0=', // canonical padded Base64
    filename: 'summary.json',
    mediaType: 'application/json',
    dataClassification: 'deidentified',
  },
);

if (object.status !== 'available') throw new Error(object.rejectionCode ?? 'scan failed');
const authorization = await client.a2a.authorizeTaskArtifactObjectDownloadV2(
  contextId,
  taskId,
  artifactId,
  object.objectId,
  { purposeOfUse: 'treatment', expiresInSeconds: 60 },
);
const bytes = await client.a2a.downloadAuthorizedArtifactObjectV2(authorization);
```

下载授权最多 300 秒且只可消费一次。URL 只含不可单独使用的 grant 定位符，服务端还会复核当前 Bearer 的租户、actor 类型和 actor 指纹必须与授权者一致。`downloadAuthorizedArtifactObjectV2()` 故意不自动重试；调用方仍不得记录授权 URL 或把失败下载当作可重放操作。

## 当前发布状态

`1.0.0-beta.30` 是三 SDK 同步的开发发布候选版，尚未发布到 npm registry，也不代表临床上线批准。本版本新增协商式实时 STT 序号 ACK、去重和有界客户端重放；JavaScript、Python 与 .NET 均通过真实 loopback WebSocket 强制断线恢复。公开 Agent Hub 仅用于浏览并保持运行禁用；生产区域 STT Provider、真实中文临床语音质量、Corti 托管租户、生产对象存储、独立 AV/OCR/DLP、KMS、容量和医院验收仍是外部门禁。

发布准备清单见 [PUBLISH.md](./PUBLISH.md)，版本历史见 [CHANGELOG.md](./CHANGELOG.md)。

## License

MIT
