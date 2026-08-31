# iCoDer Python SDK

面向中国医院场景的 iCoDer API Python 客户端。当前开发候选版覆盖 Agent Hub、统一 Agent Run、A2A 多轮 Context、事实提取、编码审核、Compliance/Runtime、HIS/EMR Patient Context，以及可持久化的 v2 录音与转写生命周期。

## Corti-compatible Streams

```python
session = await client.streams.connect_async(
    interaction_id=str(uuid.uuid4()),
    tenant_name=organization_slug,
    environment="cn",
    configuration={
        "transcription": {"primaryLanguage": "zh-CN"},
        "mode": {"type": "transcription"},
        "retentionPolicy": "none",
        "audioFormat": "audio/ogg; codecs=opus",
    },
)
await session.send_audio(ogg_opus_chunk)
await session.flush()
await session.end()
await session.wait_ended()
```

单块音频最多 64,000 bytes、单会话最多 32 MiB。当前候选支持中文单声道以及 2–8 声道
16 kHz signed 16-bit PCM 的最终转写、参与者声道归属、`fixed`/`fast_init` Facts 调度、
flush/usage/end 和可选加密留存。keyterms 支持最多 1,000 个按顺序、大小写敏感的词项并
进入 FunASR hotword；diarization 仍失败关闭，音频发送后的连接
中断也不会隐式重放。

`retentionPolicy: "retain"` 会把未结束交互的状态加密持久化。客户端收到 `flushed` 后若连接
中断，会以可重试的 `stream_resume_required` 失败；调用
`client.streams.resume_async(...)` 后，服务端必须明确返回 `resumed: true`，并给出已恢复的
audio/transcript/Facts 计数，否则 SDK 以 `stream_checkpoint_not_found` 失败关闭。未收到
`flushed` 的音频仍返回 `audio_resume_unsupported`，SDK 不会猜测或重复发送。

流式输入可使用可识别的编码容器（Ogg、WebM、Opus/Vorbis、MP3、FLAC 或 MP4/M4A），
或受治理的 raw PCM 配置：
`audio/pcm; rate=16000; channels=<1..8>; bits=16; endian=little; encoding=sint`。
PCM 的 `endian`/`encoding` 可省略并采用上述默认值，帧必须完整对齐；其他 PCM 配置返回
`raw_pcm_profile_not_available`。多声道必须显式启用并让 participants 精确覆盖每个声道；
服务端不会推断说话人。WAV 仍只用于预录音上传，不是 Streams 输入。

仅上述 PCM 配置可启用 `audioEvents: {"enabled": True}`。SDK 将四类
`speechQualityIssue*`/`longSilence*` 事件解析为受控结构，未知或带私有扩展的事件失败关闭为
`unknown`。当前检测是确定性的工程信号质量启发式，不是临床结论；编码容器上的音频事件
返回 `audio_events_require_pcm`。

容器头通过后，服务端还必须在隔离、单线程、限时且无输出的解码器子进程中成功解码一帧，
才允许进入 ASR 或加密留存。畸形媒体、解码超时或解码器缺失分别以稳定错误码失败关闭，
SDK 不会把它们转换为转写成功。

每个 API Worker 对 decoder 子进程设置独立并发与有界排队；容量耗尽返回
`AUDIO_VALIDATION_BUSY`，连接取消会终止并回收子进程。SDK 应把这些 1013/503 状态视为
可重试的临时能力失败，且不得自动重放已经无法确认服务端状态的临床音频。

## A2A 多轮 Context

```python
first = client.a2a.message_send("note-completeness-agent", "第一轮")
second = client.a2a.message_send(
    "note-completeness-agent", "继续上一轮", context_id=first["contextId"]
)
history = client.a2a.get_context(
    "note-completeness-agent", second["contextId"]
)
client.a2a.delete_context(history["id"])
```

## A2A v1 持久化异步 Task

```python
submitted = client.a2a.message_send_v1(
    "note-completeness-agent",
    "去标识病历文本",
    return_immediately=True,
)
task_id = submitted["task"]["id"]

for event in client.a2a.subscribe_task_v1(
    "note-completeness-agent", task_id, after_sequence=0
):
    print(event["eventId"], event["eventType"])

settled = client.a2a.wait_task_v1("note-completeness-agent", task_id)
if settled["status"]["state"] == "TASK_STATE_INPUT_REQUIRED":
    client.a2a.message_send_v1(
        "note-completeness-agent",
        "已确认主要诊断",
        context_id=settled["contextId"],
        task_id=settled["id"],
    )
```

`wait_task_v1()` 会在终态或 input-required/auth-required 中断态返回；中断态必须携带原
`context_id`/`task_id` 续跑，rejected/completed/failed/canceled 不可恢复。

## Feedback 训练用途独立授权

Feedback 提交不等于训练许可。组织 owner/admin 只能对精确反馈快照授予最长 30 天的
`quality_improvement` / `feedback_metadata_only` 资格；Task、Message、模型正文与 feedback
reason 均不在授权范围，反馈变更或删除会撤销资格。

```python
grant = client.a2a.authorize_feedback_for_training(
    context_id, task_id, feedback_id,
    {
        "purposeOfUse": "quality_improvement",
        "dataScope": "feedback_metadata_only",
        "expiresAt": "2026-08-29T00:00:00+08:00",
        "approvalReference": "qi-review-opaque-001",
        "acknowledgement": True,
    },
)
client.a2a.revoke_feedback_training_authorization(context_id, task_id, feedback_id)
```

## 安装

发布到 PyPI 前，请从仓库源码安装：

```bash
python -m pip install ./packages/icoder-python
```

要求 Python 3.9 或更高版本。

## 托管认证与有界重试

服务端应用可配置 `client_id`/`client_secret`；SDK 会在首个请求前换取 token、在到期前刷新，并通过线程锁把并发换 token 合并为一次请求。401 只允许一次鉴权刷新重放。408/429/5xx 默认最多重试 2 次，遵守并限制 `Retry-After`；GET/HEAD/OPTIONS/PUT/DELETE 可重试，POST/PATCH 只有携带 `Idempotency-Key` 才会重试。

```python
import os
from icoder_sdk import iCoDerClient, iCoDerConfig

client = iCoDerClient(iCoDerConfig(
    base_url="https://api.example.cn",
    client_id=os.environ["ICODER_CLIENT_ID"],
    client_secret=os.environ["ICODER_CLIENT_SECRET"],
    max_retries=2,
    retry_initial_delay=0.25,
    retry_max_delay=2.0,
))
```

token 交换失败抛出不保留请求正文、Authorization 或 client secret 的 `iCoDerAuthenticationError`。普通 API 错误按 400/401/403/404/409/422/500/502/504 分型，统一继承 `iCoDerAPIError`；只保留 status、request ID 和白名单 code/reason/字段位置，不保留可能含 PHI 的原始 body。浏览器端不得配置 client secret，应使用服务端签发的最小 scope 短期 bearer token。

Agentic Task、Context、Context Task 和 Trace 支持惰性自动翻页；重复/非法 cursor 或超出 `max_pages` 会失败关闭：

```python
for context in client.a2a.iterate_contexts_v2(page_size=50):
    print(context["id"])
```

## Compliance、Runtime 与 Patient Context

这些高层资源只映射当前 OpenAPI 中存在的路由，并接受统一 `RequestOptions`。Runtime 的
分页/统计边界与服务端一致；Patient Context 的标识符会按同源路径编码，创建可携带
`Idempotency-Key`，延期限定为 60–86400 秒且仍受服务端 24 小时总寿命上限约束。

```python
status = client.compliance.rule_engine_status()
rules = client.runtime.rule_engine_rules()
context = client.patient_context.create(
    {
        "tenant_id": "tenant-opaque",
        "source_system": "HIS",
        "patient_id": "patient-token",
        "visit_type": "outpatient",
        "department_id": "dept-opaque",
        "clinician_id": "clinician-opaque",
        "purpose_of_use": "treatment",
        "consent_legal_basis": "treatment-necessity",
    },
    idempotency_key="request-opaque",
)
client.patient_context.delete(context["id"])
```

## 快速开始

```python
from icoder_sdk import iCoDerClient, iCoDerConfig

client = iCoDerClient(iCoDerConfig(
    base_url="https://api.example.cn",
    access_token="<tenant-bound-access-token>",
))

hub = client.agent_hub.list()
tenant_readiness = client.agent_hub.readiness()
coding = next(
    (
        item for item in tenant_readiness["agents"]
        if item["agent_id"] == "medical-coding-agent"
    ),
    None,
)
if coding is None or not coding["runtime_readiness"]["run_action_enabled"]:
    raise RuntimeError(
        coding["runtime_readiness"]["reason"] if coding else "Agent is unavailable"
    )
project_agent = client.agents.clone(
    "medical-coding-agent",
    name="住院病案编码项目 Agent",
)
run = client.runs.run_text(
    project_agent["runtime_agent_id"],
    "患者因胸痛入院……",
    idempotency_key="encounter-001",
)
print(hub["total"], run.get("trace_id"))

status = client.runs.get(run["run_id"])
cancellation = client.runs.cancel(run["run_id"], "operator request")
```

`runtime_agent_id` 必须等于 `project_agent_id`；`source_runtime_agent_id` 仅供服务端固定源实现，
SDK 会拒绝把源 ID 当作公开运行身份的响应，避免绕过项目定制、租户归属和审计。

## Agent Connector Graph

Connector 资源和执行图由 owner/admin 管理，运行时只能从受审计的 Agent Run 触发。节点
显式固定操作、输入字段、数据分类及用途，模型不能生成 URL、凭据或自由节点参数。

```python
connector = client.agents.create_connector(
    "custom-agent",
    connector_type="registry",
    name="Approved semantic memory",
    config={
        "registry_key": "memory",
        "capabilities": ["remember", "recall", "forget"],
    },
)
consent = client.agents.grant_memory_consent(
    "custom-agent",
    acknowledgement=True,
    purpose_of_use="treatment",
    retention_days=30,
    expires_in_days=30,
)
assert consent["patient_authority_verified"] is False
assert consent["phi_storage_allowed"] is False
client.agents.put_connector_graph(
    "custom-agent",
    expected_revision=0,
    enabled=True,
    nodes=[{
        "id": "recall",
        "connector_id": connector["id"],
        "operation": "recall",
        "required": True,
        "input_keys": ["query", "top_k"],
        "data_classification": "deidentified",
        "purpose_of_use": "treatment",
    }],
)
```

该 consent 仅是已认证用户对本人去标识化偏好/上下文的自助授权，不是患者、监护人或医院授权；服务端不允许据此持久化患者 PHI。调用 `revoke_memory_consent` 会硬删除对应 Memory 内容和语义向量。

认证信息只能通过 `bind_connector_credential` 提交外部 secret-manager 引用，不能把真实
API Key 放进 Connector `config`。必需节点失败或输出安全检查失败时，服务端禁止模型调用和结果发布。

内置的 `drugbank`/`lookup`、`posos`/`guide` 和 `web-search`/`search` 走服务端固定的
企业适配网关，只允许 `deidentified` 查询。DrugBank/POSOS 需要合法许可证；Web Search
还要求平台和当前租户双重 opt-in。SDK 不接受或转发网关 URL、Authorization header 或真实密钥。

For long-running consumers, the bounded resilient iterator preserves the last
event cursor and renews an expired signed trace token through the configured
bearer identity. It does not hide cursor, tenant, authorization or protocol
errors:

```python
for event in client.runs.stream_events_resilient(
    run["run_id"], trace_token,
    max_attempts=4, initial_delay=0.25, max_delay=4.0,
):
    print(event.get("meta", {}).get("event_id"), event["name"])
```

If the retained trace or resume cursor has expired, both stream methods raise
`RunEventRetentionError` with a safe `error_code` and `retention_days`. This
HTTP 410 condition is terminal, is not retried, and does not retain the raw
response body.

取消结果必须读取 `cancellation["outcome"]`：`RECORDED_ONLY` 表示请求已审计但 Provider
仍在运行，不能当作已取消。`client.runs.stream_events(run_id, trace_token)` 提供签名、去 PHI
的 SSE 生命周期事件；`trace_token` 来自 Agent Run `trace_url` 的 `token` 查询参数。
断线后可把最后一个 envelope 的 `meta.event_id` 作为
`last_event_id=` 再次调用，从下一条 trace 恢复。

## Medical Coding 过滤

```python
coding = client.medical_coding.predict(
    "患者有2型糖尿病史。",
    coding_systems=["icd10cn", "icd9cm3"],
    include_codes=["E11"],
    exclude_codes=["E11.0"],
    expand_categories=True,
)
print(coding["codes"])
```

中国编码入口支持单独或同时请求 `icd10cn` 诊断和 `icd9cm3` 手术操作。类别展开开启时
按前缀匹配叶子编码，关闭时只做完整编码匹配；服务端会再次确定性强制过滤。

## Models 受控实网 Canary

```python
catalog = client.models.get_catalog()
if catalog["live_canary_available"]:
    canary = client.models.live_canary(
        catalog["effective_deployment_id"],
        max_cost_cny=catalog["live_canary_policy"]["max_cost_cny"],
    )
    print(canary["status"], canary["latency_ms"], canary["cost"]["amount"])
```

该方法不接受提示词或病例文本，只发送服务端固定无患者数据载荷，且不返回模型正文。
owner/admin、显式开关、区域外发许可、费用上限和冷却时间全部通过后才会调用一次 Provider；
结果只证明当次连通性。

开发环境可使用 `http://127.0.0.1:8000`。生产环境应使用 HTTPS，并使用绑定组织租户的短期访问令牌。

## v2 录音与转写

```python
recording = client.speech_to_text.upload_recording(
    "interaction-001",
    b"synthetic-audio-for-development",
    "audio/wav",
)
transcript = client.speech_to_text.create_transcript(
    "interaction-001",
    recording["recordingId"],
    primary_language="zh-CN",
    spoken_punctuation=True,
    keyterms={"terms": [{"term": "房颤"}, {"term": "Corti Health"}]},
    async_=True,
)
print(transcript.status_code, transcript.location)
```

`spoken_punctuation=True` 会在已验证的中文路径中把显式口述的“逗号、句号、问号”等转换为
中文标点；默认关闭，并在同步、异步及重启恢复路径保持相同语义。旧 `is_dictation=True`
仅在两个当前标点字段都未提供时作为兼容回退。`keyterms["terms"]` 按顺序、大小写敏感地传给
识别器，最多 1,000 项且每项最多 50 字符；它只做识别偏置，不做结果替换。SDK 在上传前执行
150 MB 客户端限制；服务端仍是最终的鉴权、租户隔离和大小校验边界。

预录音远程问诊多声道当前接受时间对齐的 stereo 16 kHz/16-bit PCM WAV，以及声明正确的
Ogg、WebM、Opus、Vorbis、MP3、FLAC、M4A/AAC 双声道容器；每个声道只包含一位参与者。
调用 `create_transcript(..., is_multichannel=True,
participants=[{"channel": 0, "role": "doctor"}, {"channel": 1, "role": "patient"}])`。
服务端在隔离且有界的 ffprobe/ffmpeg 子进程中验证、解码，再分别识别并加密保存结构化行。
识别提供方返回有效短语时间戳时，`start`/`end` 为毫秒；否则诚实退化为每声道整段范围。
声道数不匹配、容器声明不符和 diarization 会失败关闭。

## 实时语音转写

```python
session = await client.speech_to_text.connect_managed_session_async(
    language="zh-CN",
    reconnect_attempts=3,
)
session.on("message", lambda event: print(event))
await session.send_audio(audio_chunk)
await session.request_interim()
await session.send_end()
```

`connect_managed_session_async()` 默认等待服务端 `ready`，提供类型化事件、token 刷新和
有界指数重连。双方协商 `icoder.stt-resume.v1` 后，每个音频块携带单调序号并获得
`audio_ack`；SDK 在服务端声明的上限内保存不可变内存副本，断线后从
`nextAudioSequence` 重放音频及结束指令。音频不由 SDK 落盘，也不在服务端跨进程保存；
当前 `client_replay` 模式重连时通常从序号 1 重放。旧服务端未确认恢复能力时，发送音频后
仍以 `audio_resume_unsupported` 失败关闭。客户端只应使用短期、租户绑定且带
`transcribe`/`streams` scope 的 token。

`create_session_async()` 保留为原始 WebSocket 兼容入口。WebSocket 依赖按需安装：
`python -m pip install websockets`。当前验证范围仅含中文、自动标点和 WebM/Opus start，
32 MiB 会话总量仍由服务端强制；服务端默认禁止在 API 进程隐式加载 FunASR/Whisper/
说话人分离原生栈，必须由受治理的区域 STT 服务或显式批准的本地部署提供真实转写能力。

## Documents 与 Templates

```python
sections = client.templates.list_sections(
    lang=["zh-CN"], region=["CHN"]
)
preview = client.documents.preview(
    "11111111-1111-4111-8111-111111111111",
    {
        "context": [{"type": "string", "data": "去标识临床样例文本"}],
        "template": {
            "sections": [
                {"key": section["id"], "nameOverride": section["name"]}
                for section in sections[:2]
            ]
        },
        "outputLanguage": "zh-CN",
        "documentationMode": "global_sequential",
    },
)
print(preview["sections"], preview["usageInfo"]["creditsConsumed"])
```

`documents.preview()` 强制使用零保留策略，并在服务端未返回 `acknowledged` 时失败关闭。生成内容必须由临床人员复核。

## Facts 与 Text Generation 兼容入口

```python
facts = client.facts.extract("患者主诉胸痛。", output_language="zh-CN")
generated = client.textgen.generate(
    "去标识临床文本", template="出院小结", output_language="zh-CN"
)
print(facts.usage_info.credits_consumed, generated["credits_consumed"])
```

`textgen.generate()` 是旧调用面的兼容 facade，实际使用 Guided Documents `dynamicTemplate`。它强制生成文书零留存确认；动态模板与 Section 元数据仍会登记在当前租户，因此模板名称不得包含患者标识。`doc_name`、非默认 `max_tokens` 和非默认 `temperature` 当前不受 Guided 合同支持，会在发送前失败关闭。新集成应优先直接使用 Guided Documents 请求。

## 资源

| 属性 | 能力 |
| --- | --- |
| `client.agent_hub` | 列出面向用户的 Agent 卡片并读取单卡 |
| `client.a2a` | A2A v1 Task/Context/Artifact 与托管对象生命周期 |
| `client.runs` | 统一 Agent Run 与 trace 元数据 |
| `client.speech_to_text` | v2 录音/转写生命周期与鉴权实时 WebSocket |
| `client.documents` | Classic 文档生成、零保留预览及加密生命周期 |
| `client.templates` | Guided Template/Section 发现及租户 Section 管理 |
| `client.facts` | 临床事实提取 |
| `client.textgen` | Guided Documents 动态模板兼容生成（文书零留存） |
| `client.medical_coding` | 中国医学编码预测、Corti 风格代码过滤与预估费用 |
| `client.agents` / `client.experts` | Agent 与 Expert 管理 |
| `client.billing` / `client.usage` | 计费和用量查询 |
| `client.oauth` | OAuth 客户端管理接口 |
| `client.models` / `client.platform` | 模型目录与平台访问控制 |

历史 `client.reviews` facade 已移除：后端没有对应公开路由。编码审核使用 `client.agents` / `client.a2a` / `client.medical_coding`；Agent 发现使用 `client.agent_hub`。

## Task Artifact 托管对象

```python
import base64

obj = client.a2a.upload_task_artifact_object_v2(
    context_id,
    task_id,
    artifact_id,
    raw=base64.b64encode(b'{"type":"deidentified"}').decode("ascii"),
    filename="summary.json",
    media_type="application/json",
    data_classification="deidentified",
)
if obj["status"] != "available":
    raise RuntimeError(obj.get("rejectionCode") or "scan failed")

authorization = client.a2a.authorize_task_artifact_object_download_v2(
    context_id,
    task_id,
    artifact_id,
    obj["objectId"],
    purpose_of_use="treatment",
    expires_in_seconds=60,
)
content = client.a2a.download_authorized_artifact_object_v2(authorization)
```

下载授权最多 300 秒且只可消费一次。URL 只含不可单独使用的 grant 定位符，服务端还会复核当前 Bearer 的租户、actor 类型和 actor 指纹必须与授权者一致。`download_authorized_artifact_object_v2()` 故意不自动重试；调用方仍不得记录授权 URL 或把失败下载当作可重放操作。

## 当前发布状态

`1.0.0b30` 新增协商式实时 STT 序号 ACK、去重和有界客户端重放，并与 JavaScript/.NET 通过真实 loopback WebSocket 强制断线恢复。公开 Agent Hub 只负责浏览；生产区域 STT Provider、真实中文临床语音质量、Corti 托管租户、生产对象存储、独立 AV/OCR/DLP、KMS、容量和医院验收仍是外部门禁。该版本尚未发布到 PyPI，也不代表临床上线批准。
