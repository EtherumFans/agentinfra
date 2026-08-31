# iCoDer Streams 推荐 PCM 与音频健康事件阶段总结（2026-08-24）

## 阶段结论

iCoDer Streams 已支持 Corti 当前官方推荐的 raw PCM 配置：16 kHz、单声道、16-bit、
little-endian、signed integer，并在服务端和 JavaScript/Python/.NET SDK 中形成一致的配置、
失败码和类型合同。PCM 数据在 ASR/留存前必须满足完整帧对齐，通过固定且不可由客户端
控制的 ffmpeg 参数完成隔离解码；进入本地 ASR 适配器时转换为内存 WAV。其他 Corti
允许的 PCM profile 继续以 `raw_pcm_profile_not_available` 失败关闭，不冒充完整支持。

当该 PCM profile 启用 `audioEvents` 时，服务端以 250 ms 窗口发出四类严格事件：
`speechQualityIssueDetected`、`speechQualityIssueRecovered`、`longSilenceDetected`、
`longSilenceRecovered`。事件与审计只包含事件名、channel、时间和计数，不包含音频、转写、
患者文本或模型输出。当前算法是确定性的工程信号质量启发式，不是临床判断，也没有宣称
复刻 Corti 未公开的检测阈值或模型。

## Corti 当前公开合同基线

- Corti [Audio Configuration](https://docs.corti.ai/stt/audio) 当前声明 `/transcribe` 和
  `/streams` 支持 `audio/pcm`；`rate` 允许 8000–48000、`channels` 允许 1–8、`bits`
  允许 8/16/24/32，另有 little/big endian 和 sint/uint；官方推荐 16 kHz、16-bit、
  little-endian、mono。
- Corti [Transcribe API](https://docs.corti.ai/api-reference/transcribe) 要求连接后 10 秒内
  发 config、收到 `CONFIG_ACCEPTED` 后再发音频，并定义四类 `audioEvent` 的
  `event/channel/startTimeMs` 结构；`audioEvents` 默认关闭。该页也定义 interim、spoken/
  automatic punctuation、commands、formatting、flush、usage 和 ended。
- Corti [Commands](https://docs.corti.ai/stt/commands) 支持 enum/wildcard 变量与客户端执行的
  工作流命令；[Transcript Text Handling](https://docs.corti.ai/stt/best-practices-transcribe)
  还规定 `text/rawTranscriptText`、interim 替换、插入边界和 locale spacing 语义。

因此，本阶段只关闭“推荐 PCM + 四类严格事件 + 安全处理”的开发切片，不关闭 Corti
完整 dictation、所有 PCM profile、编码格式 audio events 或编辑器语义差距。

## 实现与安全边界

| 能力 | 已验证行为 |
|---|---|
| PCM 配置 | 参数必填、范围和重复/未知参数严格校验；只接受推荐 profile，缺参数或其他 profile 在配置阶段失败 |
| 帧与 decoder | 非空且完整 sample frame；ffmpeg 固定使用 `s16le/16000/mono`，输入只经 stdin，stdout/stderr 丢弃 |
| ASR 适配 | PCM 在内存中封装为 1-channel、16-bit、16 kHz WAV；测试环境关闭真实 STT 时返回 `STT_UNAVAILABLE`，不伪造 transcript |
| 音频事件 | 10 秒长静音、恢复、持续 clipping/高 zero-crossing quality issue 与恢复均为确定性状态转换；chunk 边界不改变结果 |
| 审计 | `stt.stream.audio_event` 为 content-free allowlist；四个 E2E 事件对应四条审计，无音频或正文 |
| SDK | 三 SDK 接受推荐 PCM、拒绝其他 profile/编码格式 audio events，并把四种事件解析为受控类型；未知事件失败关闭 |

## 真实端到端和回归

单 worker E2E 使用临时迁移数据库、真实租户 token、真实 loopback WebSocket、合成 PCM 和
隔离 ffmpeg。它依次发出 10 秒静音、250 ms 正常音、1 秒 clipping、1 秒正常音，得到：

1. `longSilenceDetected`，`startTimeMs=0`；
2. `longSilenceRecovered`，`startTimeMs=10000`；
3. `speechQualityIssueDetected`，`startTimeMs=10250`；
4. `speechQualityIssueRecovered`，`startTimeMs=11250`。

随后 `end` 证明 PCM 通过 decoder 并到达 ASR adapter；由于真实 STT 被明确关闭，服务端
按预期返回 `STT_UNAVAILABLE`，再返回 `usage` 和 `ENDED`。五次解码尝试为 valid 4、
invalid 1、active 0；五个配置会话中 ended audit 为 4，四个 audio-event audit 均无内容，
租约最终为 0。双 worker 强制终止/过期接管 E2E 也再次通过。运行器在 finally 中强制停止
Uvicorn；该清理可表现为退出码 `-1`，不是本轮访问冲突或数据库崩溃。

| 验证面 | 结果 |
|---|---:|
| 后端 Streams/STT/留存/配置/预检联合矩阵 | 255 passed |
| JavaScript SDK | 89 passed |
| Python SDK | 93 passed |
| .NET net8.0 / net10.0 | 74 / 74 passed |
| 迁移、升级/降级、shadow rebuild 与 ORM 漂移 | 19 passed |
| 发布候选验证器 | 5 passed |
| 静态部署预检 | 89 / 89 passed |

三 SDK 已归一到 `1.0.0-beta.35`（Python `1.0.0b35`）。npm tgz、Python wheel、
.NET nupkg/snupkg 四个本地候选工件已生成 SHA-256 清单；清单明确
`source_tree_state=dirty`、`publication.performed=false`，没有发布到外部 registry。

机器证据：[`reports/sdk_stream_pcm_audio_events_phase_20260824`](../../reports/sdk_stream_pcm_audio_events_phase_20260824/)。
候选清单：`C:\codex-artifacts\release-b35-stream-pcm-audio-events-final\release-candidate-b35-stream-pcm-audio-events-final.json`。

## 尚未关闭的差距与外部门禁

- Corti 允许 8–48 kHz、1–8 channel、8/16/24/32-bit、big/little、sint/uint；iCoDer 仅支持
  官方推荐 profile。multichannel、diarization 与其余 raw PCM profile 尚未实现。
- Corti 文档示例允许编码音频同时启用 audio events；iCoDer 当前只在推荐 PCM 上提供事件。
- Corti 未公开 audio-health 检测实现和阈值。本地启发式尚未用中国医院麦克风、环境噪声、
  方言、多人对话或真实设备校准，也未由独立临床/声学 reviewer 验收。
- `/transcribe` 的 interim、commands、spoken/automatic punctuation、formatting、
  `text/rawTranscriptText` 和编辑器插入语义仍有明确差距。
- 本阶段没有调用真实 STT 或 LLM，不证明中文医疗 ASR 准确率、延迟、计费、稳定性或 SLA；
  真实 Provider、医院授权数据与独立临床验收仍是外部门禁。
- Docker CLI 在本机不可用，因此没有构建/扫描 Linux 镜像；ffmpeg SBOM/CVE/许可证、
  seccomp/AppArmor/cgroup、Linux 多进程容量和 PostgreSQL 多副本仍未验证。
- 受保护开发库未迁移，仍为 8,536,064 bytes、SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；源码 Alembic
  单 head 为 `056`。
