# iCoDer.Sdk for .NET

面向中国医院场景的 iCoDer 官方 .NET 客户端。当前包覆盖统一 Agent Run、Agent Hub、A2A 多轮 Context、医学编码预测、Corti-compatible v2 预录音/实时转写、Facts、Documents、Templates/Sections、开发账本/Agent Run 结算和 OAuth token refresh。

## Corti-compatible Streams

```csharp
await using var stream = await icoder.Streams.CreateSessionAsync(
    new StreamsSessionOptions
    {
        InteractionId = Guid.NewGuid(),
        TenantName = organizationSlug,
        Environment = "cn",
        Configuration = new StreamsConfiguration
        {
            Transcription = new() { PrimaryLanguage = "zh-CN" },
            Mode = new() { Type = "transcription" },
            RetentionPolicy = "none",
            AudioFormat = "audio/ogg; codecs=opus",
        },
    });
await stream.SendAudioAsync(oggOpusChunk);
await stream.FlushAsync();
await stream.CompleteAsync();
```

单块音频最多 64,000 bytes、单会话最多 32 MiB。当前候选支持中文单声道以及 2–8 声道
16 kHz signed 16-bit PCM 的最终转写、参与者声道归属、`fixed`/`fast_init` Facts 调度、
flush/usage/end 与可选加密留存。keyterms 支持最多 1,000 个按顺序、大小写敏感的词项并
进入 FunASR hotword；diarization 仍会明确拒绝；音频发送后断线会
失败关闭，不会隐式重放临床音频。

`RetentionPolicy = "retain"` 会把未结束交互的状态加密持久化。客户端收到 `flushed` 后若连接
中断，会以可重试的 `stream_resume_required` 失败；调用
`icoder.Streams.ResumeSessionAsync(options)` 后，服务端必须明确返回 `Resumed = true`，并给出
已恢复的 audio/transcript/Facts 计数，否则 SDK 以 `stream_checkpoint_not_found` 失败关闭。
未收到 `flushed` 的音频仍返回 `audio_resume_unsupported`，SDK 不会猜测或重复发送。

流式输入可使用可识别的编码容器（Ogg、WebM、Opus/Vorbis、MP3、FLAC 或 MP4/M4A），
或受治理的 raw PCM 配置：
`audio/pcm; rate=16000; channels=<1..8>; bits=16; endian=little; encoding=sint`。
PCM 的 `endian`/`encoding` 可省略并采用上述默认值，帧必须完整对齐；其他 PCM 配置返回
`raw_pcm_profile_not_available`。多声道必须显式启用且 participants 精确覆盖每个声道；
服务端不推断说话人。WAV 仍只用于预录音上传，不是 Streams 输入。

仅上述 PCM 配置可启用 `AudioEvents.Enabled = true`。SDK 将四类
`speechQualityIssue*`/`longSilence*` 事件解析为 `StreamsAudioEventData`；未知或带私有扩展的
事件失败关闭为 `unknown`。当前检测是确定性的工程信号质量启发式，不是临床结论；编码
容器上的音频事件返回 `audio_events_require_pcm`。

容器头通过后，服务端还必须在隔离、单线程、限时且无输出的解码器子进程中成功解码一帧，
才允许进入 ASR 或加密留存。畸形媒体、解码超时或解码器缺失分别以稳定错误码失败关闭，
SDK 不会把它们转换为转写成功。

每个 API Worker 对 decoder 子进程设置独立并发与有界排队；容量耗尽返回
`AUDIO_VALIDATION_BUSY`，连接取消会终止并回收子进程。SDK 应把这些 1013/503 状态视为
可重试的临时能力失败，且不得自动重放已经无法确认服务端状态的临床音频。

## Agent Hub 运行就绪

```csharp
var hub = await icoder.AgentHub.ListAsync();
var tenantReadiness = await icoder.AgentHub.GetReadinessAsync();
var coding = tenantReadiness.Agents.Single(
    item => item.AgentId == "medical-coding-agent");
if (!coding.RuntimeReadiness.RunActionEnabled)
    throw new InvalidOperationException(
        coding.RuntimeReadiness.Reason);
var projectAgent = await icoder.AgentHub.CloneAsync(
    "medical-coding-agent",
    new AgentCloneRequest { Name = "住院病案编码项目 Agent" });
var run = await icoder.AgentRuns.RunTextAsync(
    projectAgent.RuntimeAgentId,
    "患者因胸痛入院……");
```

公开 schema 1.3 Hub 仅用于浏览并保持运行禁用；`GetReadinessAsync` 返回鉴权后的租户绑定配置与有时效的连通性证据。SDK 会拒绝重复、缺失或“当前不可用却允许运行”的矛盾响应。`CloneAsync` 返回的 `RuntimeAgentId` 必须等于 `ProjectAgentId`，源实现 ID 不能绕过项目定制、租户归属或审计。`GetCardAsync` 返回的是独立的 A2A v0.3 发现卡，不是 Hub 卡片。

## A2A 多轮 Context

```csharp
var first = await icoder.A2A.MessageSendTextAsync(
    "note-completeness-agent", "第一轮");
var second = await icoder.A2A.MessageSendTextAsync(
    "note-completeness-agent", "继续上一轮", first.ContextId);
var history = await icoder.A2A.GetContextAsync(
    "note-completeness-agent", second.ContextId);
await icoder.A2A.DeleteContextAsync(history.Id);
```

## A2A v1 持久化异步 Task

```csharp
var submitted = await icoder.A2A.MessageSendV1TextAsync(
    "note-completeness-agent",
    "去标识病历文本",
    returnImmediately: true);
var taskId = submitted.Task?.Id
    ?? throw new InvalidOperationException("Server did not return a Task.");

await foreach (var item in icoder.A2A.SubscribeTaskV1Async(
    "note-completeness-agent", taskId, afterSequence: 0))
{
    Console.WriteLine($"{item.Id}: {item.Data}");
}
var settled = await icoder.A2A.WaitTaskV1Async(
    "note-completeness-agent", taskId);
if (settled.Status.State == "TASK_STATE_INPUT_REQUIRED")
{
    await icoder.A2A.MessageSendV1TextAsync(
        "note-completeness-agent",
        "已确认主要诊断",
        contextId: settled.ContextId,
        taskId: settled.Id);
}
```

`WaitTaskV1Async` 会在终态或 input-required/auth-required 中断态返回；中断态必须携带
原 ContextId/TaskId 续跑，rejected/completed/failed/canceled 不可恢复。

## Feedback 训练用途独立授权

Feedback 提交不会自动产生训练许可。组织 owner/admin 只能授权精确反馈快照的
`quality_improvement` / `feedback_metadata_only` 资格，最长 30 天；Task、Message、模型
输入/输出和 feedback reason 均不在范围内，反馈更新或删除会撤销资格。

```csharp
var grant = await icoder.A2A.AuthorizeFeedbackForTrainingAsync(
    contextId, taskId, feedbackId,
    new FeedbackTrainingAuthorizationInput
    {
        ExpiresAt = DateTimeOffset.UtcNow.AddDays(7),
        ApprovalReference = "qi-review-opaque-001",
    });
await icoder.A2A.RevokeFeedbackTrainingAuthorizationAsync(
    contextId, taskId, feedbackId);
```

## Agent Connector 与并行图

```csharp
var connectors = await icoder.AgentConnectors.ListAsync("agent-id");
var graph = await icoder.AgentConnectors.PutGraphAsync(
    "agent-id",
    new ConnectorGraphPutRequest
    {
        ExpectedRevision = 0,
        Enabled = true,
        ExecutionMode = "parallel",
        MaxConcurrency = 2,
        Nodes = [],
    });

var consent = await icoder.AgentConnectors.GrantMemoryConsentAsync(
    "agent-id",
    new MemoryConsentGrantRequest
    {
        Acknowledgement = true,
        PurposeOfUse = "treatment",
        RetentionDays = 30,
        ExpiresInDays = 30,
    });
if (consent.PatientAuthorityVerified || consent.PhiStorageAllowed)
    throw new InvalidOperationException("Unexpected patient-PHI authority.");
```

MCP/A2A Connector 的 URL、凭据引用、重定向、出站区域和 PHI 策略由服务端治理；SDK 不接收或记录原始患者数据凭据。
Memory consent 只代表当前登录用户对本人去标识化偏好/上下文的自助授权，不是患者或医院授权；撤销 consent 会硬删除对应内容与语义向量。

## 运行要求

- `.NET Standard 2.0`（可由 .NET Framework 4.6.2+ 消费）、仍在维护期的 .NET 8，或 .NET 10 LTS（推荐）；NuGet 同时提供 `netstandard2.0`/`net8.0`/`net10.0` 资产
- 生产环境使用 HTTPS
- 服务端 OAuth access token；SDK 可用 refresh token 在一次 `401` 后自动刷新并重试一次

## 安装

发布到 NuGet 后：

```powershell
dotnet add package iCoDer.Sdk --version 1.0.0-beta.50
```

仓库源码引用：

```xml
<ProjectReference Include="..\packages\icoder-dotnet\src\Icoder.Sdk\Icoder.Sdk.csproj" />
```

## 逐请求控制

所有公开 HTTP 资源方法都接受命名参数 `requestOptions`；已有的
`CancellationToken` 仍负责调用方主动取消。默认对 408、429 和 5xx 最多重试 2 次，
每次调用可覆盖为 0–10 次；超时必须大于 0 且不超过 1 小时。

```csharp
var options = new ICoDerRequestOptions
{
    Timeout = TimeSpan.FromSeconds(30),
    MaxRetries = 3,
    AdditionalHeaders = new Dictionary<string, string?>
    {
        ["X-Request-Id"] = Guid.NewGuid().ToString("N"),
    },
    AdditionalQueryParameters = new Dictionary<string, string>
    {
        ["trace_mode"] = "safe",
    },
};

using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(35));
var hub = await icoder.AgentHub.ListAsync(
    cancellationToken: cancellation.Token,
    requestOptions: options);
```

请求选项不能覆盖 Authorization、Cookie、Host、消息分帧头、租户/组织头、
Idempotency-Key、A2A 协议版本或资源方法已经声明的查询参数。SDK 不提供逐请求跨源
Base URL、替换 HttpClient 或任意 JSON body 合并；这些 Corti 通用扩展点在医院多租户
场景会扩大凭据外泄或临床字段覆盖面，因此只允许构造客户端时注入同源 HttpClient。
一次性 Artifact 下载始终禁用自动重试，并拒绝服务端返回的跨源下载 URL。

## Agent Run

```csharp
using Icoder.Sdk;

using var icoder = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = new Uri("https://api.cn.icoder.cloud"),
    AccessToken = Environment.GetEnvironmentVariable("ICODER_ACCESS_TOKEN"),
    RefreshToken = Environment.GetEnvironmentVariable("ICODER_REFRESH_TOKEN"),
});

var run = await icoder.AgentRuns.RunTextAsync(
    "medical-coding-agent",
    "患者男，65岁，因胸痛入院……",
    runtimeMode: "corti_like_fast",
    idempotencyKey: Guid.NewGuid().ToString("N"));

Console.WriteLine($"{run.RunId} {run.TraceUrl} {run.ManualReviewRequired}");

var status = await icoder.AgentRuns.GetAsync(run.RunId);
var cancellation = await icoder.AgentRuns.CancelAsync(run.RunId, "operator request");
```

For long-running consumers, use the bounded resilient iterator. It preserves
the last SSE ID, renews an expired signed trace token with the bearer identity,
and leaves cursor, tenant, authorization and protocol failures visible:

```csharp
await foreach (var item in icoder.AgentRuns.StreamEventsResilientAsync(
    run.RunId,
    traceToken,
    new RunStreamRetryOptions { MaxAttempts = 4 }))
{
    Console.WriteLine($"{item.Id} {item.Event}");
}
```

If the retained trace or resume cursor has expired, both stream methods throw
`RunEventRetentionException`. Its `ErrorCode` and `RetentionDays` properties
are safe for operator handling; HTTP 410 is terminal and is not retried.

取消结果必须读取 `cancellation.Outcome`：`RECORDED_ONLY` 表示请求已审计但 Provider
仍在运行，不能当作已取消。`AgentRuns.StreamEventsAsync(runId, traceToken)` 提供签名、去 PHI
的 SSE 生命周期事件；`traceToken` 来自 Agent Run `TraceUrl` 的 `token` 查询参数。
收到事件的 `Id` 后，可调用 `StreamEventsAsync(runId, traceToken, lastEventId)` 从下一条事件恢复，
避免断线后重复处理已确认的 trace。

## 开发账本与 Agent Run 结算

```csharp
var balance = await icoder.Billing.GetBalanceAsync();
var settlements = await icoder.Billing.ListRunSettlementsAsync(limit: 20);
var reconciled = await icoder.Billing.ReconcileStaleRunSettlementsAsync(
    olderThanSeconds: 3600);

if (settlements.Items.FirstOrDefault()?.Status == "SETTLEMENT_FAILED")
{
    var retried = await icoder.Billing.RetryRunSettlementAsync(
        settlements.Items[0].RunId);
    Console.WriteLine($"{retried.Status} {retried.SettledAmount}");
}
```

这些接口是服务端显式启用的本地/开发模拟合同，不代表支付、发票、退款或财务对账。
启用强制结算时，余额不足会在 Provider 调用前失败关闭；同一幂等 Run 的重放不会重复扣费。
陈旧协调会跳过活跃 Run，只释放孤立预授权；陈旧结算中的真实成本会保留并转成可重试状态。

## Medical Coding 过滤

```csharp
var coding = await icoder.MedicalCoding.PredictAsync(new CodingPredictRequest
{
    Text = "患者有2型糖尿病史。",
    CodingSystems = ["icd10cn", "icd9cm3"],
    Filter = new CodingCodeFilter
    {
        Include = ["E11"],
        Exclude = ["E11.0"],
        Expand = true,
    },
});
Console.WriteLine(coding.Codes.Count);
```

中国编码入口支持单独或同时请求 `icd10cn` 诊断和 `icd9cm3` 手术操作。类别展开开启时
按前缀匹配叶子编码，关闭时只匹配完整编码；服务端会再次确定性强制过滤。

## DRG/DIP 开发风险审查

```csharp
var risk = await icoder.DrgDipRiskReview.AnalyzeAsync(new DrgDipAnalyzeRequest
{
    PrimaryDiagnosis = new DrgDipCode { Code = "I10" },
    PatientAge = 58,
});
Console.WriteLine($"{risk.ReviewConclusion} {risk.ManualReviewRequired}");
```

该资源不是官方分组器。SDK 会拒绝非零 DRG 权重、DIP 分值、支付估算、
`BillingAuthoritative=true` 或 `ManualReviewRequired=false`；`PredictedDrg` 只是
向后兼容的开发候选字段，不得用于医保分组、结算或临床自动决策。

## Models 受控实网 Canary

```csharp
var catalog = await icoder.Models.GetCatalogAsync();
if (catalog.LiveCanaryAvailable)
{
    var canary = await icoder.Models.LiveCanaryAsync(
        catalog.EffectiveDeploymentId,
        catalog.LiveCanaryPolicy.MaxCostCny);
    Console.WriteLine($"{canary.Status} {canary.LatencyMs}ms");
}
```

Canary 只发送服务端固定的无患者数据载荷。SDK 不接受提示词或自由文本，并会显式确认
外部调用；服务端不会返回或记录模型正文。一次成功仅表示该时刻的连接观察，不证明模型
质量、持续在线健康、SLA 或权威账单。

## OAuth client credentials 与 FactsR

```csharp
using var auth = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = new Uri("https://api.cn.icoder.cloud"),
});
var token = await auth.AuthenticateClientCredentialsAsync(
    Environment.GetEnvironmentVariable("ICODER_CLIENT_ID")!,
    Environment.GetEnvironmentVariable("ICODER_CLIENT_SECRET")!);

using var icoder = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = auth.Options.BaseUri,
    AccessToken = token.AccessToken,
});
var facts = await icoder.Facts.ExtractAsync(new FactExtractionRequest
{
    Context = [new FactExtractionContext { Text = "去标识临床文本" }],
    OutputLanguage = "zh-CN",
});
Console.WriteLine($"{facts.Facts.Count} facts, {facts.UsageInfo.CreditsConsumed} credits");
```

OAuth token 请求使用 RFC 6749 form encoding；client-credentials 响应不要求
refresh token 或 Console user 字段。

## 异步预录音转写

```csharp
var audio = await File.ReadAllBytesAsync("consultation.flac");
var recording = await icoder.SpeechToText.UploadRecordingAsync(
    "interaction-001", audio, "audio/flac");

var accepted = await icoder.SpeechToText.CreateTranscriptAsync(
    "interaction-001",
    new TranscriptCreateRequest
    {
        RecordingId = recording.RecordingId,
        PrimaryLanguage = "zh-CN",
        SpokenPunctuation = true,
        IsMultichannel = true,
        Participants =
        [
            new TranscriptParticipant { Channel = 0, Role = "doctor" },
            new TranscriptParticipant { Channel = 1, Role = "patient" },
        ],
        Keyterms = new TranscriptKeyterms
        {
            Terms =
            [
                new TranscriptKeyterm { Term = "房颤" },
                new TranscriptKeyterm { Term = "Corti Health" },
            ],
        },
        Async = true,
    });

Console.WriteLine($"HTTP {(int)accepted.StatusCode}: {accepted.Location}");
```

`SpokenPunctuation = true` 会在已验证的中文路径中把显式口述的“逗号、句号、问号”等转换为
中文标点；默认关闭，并在同步、异步及重启恢复路径保持相同语义。旧 `IsDictation = true`
仅在两个当前标点字段都未提供时作为兼容回退。`Keyterms.Terms` 按顺序、大小写敏感地传给
识别器，最多 1,000 项且每项最多 50 字符；它只做识别偏置，不做结果替换。
预录音多声道接受时间对齐的 stereo 16 kHz/16-bit PCM WAV，以及声明正确的 Ogg、WebM、
Opus、Vorbis、MP3、FLAC、M4A/AAC 双声道容器；participants 必须精确覆盖声道 0 和 1。
服务端隔离、有界地探测和解码，再分别识别并加密保存两个声道。识别提供方返回有效短语
时间戳时，`start`/`end` 为毫秒；否则退化为每声道整段范围。声道数或容器声明不匹配以及
diarization 均失败关闭。

## 实时语音转写

```csharp
await using var session = await icoder.SpeechToText.CreateRealtimeSessionAsync(
    new RealtimeSttSessionOptions
    {
        Language = "zh-CN",
        MediaType = "audio/webm;codecs=opus",
        ReconnectAttempts = 3,
    });

Console.WriteLine($"ready: {session.Ready?.MaxSessionBytes} bytes");
await session.SendAudioAsync(audioChunk);
await session.RequestInterimAsync();
var evt = await session.ReceiveAsync();
await session.CompleteAsync();
```

实时连接使用当前 tenant-bound access token；创建方法仅在服务端返回 `ready` 后成功，并在客户端强制
32 MiB 音频会话上限和 1 MiB 服务端事件上限。协商 `icoder.stt-resume.v1` 后，SDK 会按序号
封帧并验证 `audio_ack`，在有界内存中保留不可变音频副本；断线后重新鉴权、握手，并从服务端
请求的序号重放音频和结束指令。音频不会由 SDK 落盘；旧服务端未确认恢复能力时，发送音频后的
断线以 `audio_resume_unsupported` 失败关闭。当前已验证运行时只支持中文、自动标点和单路受支持
音频；其他语言、spoken punctuation 或未知媒体类型会在建立连接前失败关闭。

## Documents 零保留预览

```csharp
var document = await icoder.Documents.PreviewAsync(
    "interaction-001",
    new DocumentCreateRequest
    {
        Context = [DocumentContext.Facts([
            new DocumentFact { Text = "患者主诉胸痛", Group = "clinical" },
        ])],
        OutputLanguage = "zh-CN",
        DocumentationMode = DocumentationModes.RoutedParallel,
        Template = new DocumentTemplate
        {
            SectionKeys = ["chief-complaint", "assessment", "plan"],
        },
    });

Console.WriteLine($"{document.Id}: {document.Sections.Count} sections");
```

`PreviewAsync` 会发送 `X-Corti-Retention-Policy: none`，只有服务端明确返回
`X-Corti-Retention-Policy: acknowledged` 才交付结果；否则失败关闭。普通保存生成使用
`CreateAsync`，并可通过 `ListAsync/GetAsync/UpdateAsync/DeleteAsync` 管理生命周期。

## Templates 与 Sections

```csharp
var sections = await icoder.Templates.ListSectionsAsync(
    new GuidedDiscoveryFilters
    {
        Languages = ["zh-CN"],
        Regions = ["CHN"],
        Published = true,
    });

var custom = await icoder.Templates.CreateSectionAsync(
    new SectionCreateRequest
    {
        Name = "专科评估",
        Language = "zh-CN",
        Specialties = ["cardiology"],
    });
```

## Task Artifact 托管对象

```csharp
var obj = await icoder.A2A.UploadTaskArtifactObjectV2Async(
    contextId,
    taskId,
    artifactId,
    Encoding.UTF8.GetBytes("{\"type\":\"deidentified\"}"),
    "summary.json",
    "application/json",
    "deidentified");

if (obj.Status != "available")
    throw new InvalidOperationException(obj.RejectionCode ?? "scan failed");

var authorization = await icoder.A2A.AuthorizeTaskArtifactObjectDownloadV2Async(
    contextId,
    taskId,
    artifactId,
    obj.ObjectId,
    "treatment",
    expiresInSeconds: 60);
var content = await icoder.A2A.DownloadAuthorizedArtifactObjectV2Async(authorization);
```

下载授权最多 300 秒且只可消费一次。URL 只含不可单独使用的 grant 定位符，服务端还会复核当前 Bearer 的租户、actor 类型和 actor 指纹必须与授权者一致。`DownloadAuthorizedArtifactObjectV2Async` 故意不自动重试；调用方仍不得记录授权 URL 或把失败下载当作可重放操作。

## 安全边界

- 非 loopback 的明文 HTTP 默认拒绝；仅隔离开发网可显式设置 `AllowInsecureHttp=true`。
- 异常对象只保留服务端的安全 `detail/type/requestid`，不保存原始响应体，避免把可能含 PHI 的正文带入日志。
- SDK 不自动提交编码、分诊、转诊、医保或病历写回；所有临床输出仍服从服务端的人工复核门禁。
- 实时 STT 建连异常会移除可能包含 query token 的底层异常，不把 access token 保留在公开异常链。
- 逐请求附加头不能覆盖认证、租户、消息分帧或资源固定头；附加查询参数不能覆盖资源字段；绝对下载 URL 必须与配置 API 同源。
- NuGet 发布、签名和真实托管 API 验证属于独立发布步骤；源码存在不等于包已发布。

## 验证

```powershell
dotnet test tests/Icoder.Sdk.Tests/Icoder.Sdk.Tests.csproj
dotnet build tests/Icoder.Sdk.NetStandard20Consumer/Icoder.Sdk.NetStandard20Consumer.csproj -c Release
dotnet build tests/Icoder.Sdk.Net462Consumer/Icoder.Sdk.Net462Consumer.csproj -c Release
dotnet pack src/Icoder.Sdk/Icoder.Sdk.csproj -c Release
```

PR CI 会同时安装 .NET 8 与 .NET 10，分别运行同一套合同测试，并编译
`netstandard2.0` 与 `.NET Framework 4.6.2` 最低版本消费者；它会拒绝不同时包含
`lib/netstandard2.0`、`lib/net8.0` 和 `lib/net10.0` 资产的 NuGet 包。通过后的
`.nupkg`/`.snupkg` 作为短期 CI 工件保留。原生双运行时验证不能用主版本
roll-forward 替代；最低版本消费者是编译兼容门禁，不代表已在每个 Framework
补丁版本上运行集成测试。

真实 API consumer smoke（token 通过环境变量传递，不进入命令行或日志）：

```powershell
$env:ICODER_E2E_BASE_URL='http://127.0.0.1:8000'
$env:ICODER_E2E_ACCESS_TOKEN='<local-development-token>'
dotnet run --project examples/Icoder.Sdk.Smoke/Icoder.Sdk.Smoke.csproj -c Release
```

该 smoke 要求 Hub 恰有 26 个可运行发布候选，调用统一 Agent Run，并完成加密持久化录音的 upload/list/download/delete 生命周期。它使用合成非临床文本，不能替代真实医院质量验证。

仓库提供 `scripts/run-local-e2e.ps1` 自动创建临时 SQLite、隐藏启动 uvicorn、注册一次性 tenant-bound 用户，并让 .NET、JavaScript 与 Python SDK 依次消费同一个服务后精确回收；不会读取或修改开发数据库，也会强制关闭真实 LLM 凭据和不安全 Windows BGE override。服务端以 JWT `org_id` 为租户权威，脚本不会用 `Tenant-Name`/`X-Tenant` 伪造租户范围。
