# iCoDer Streams 编码音频真实性阶段总结（2026-08-24）

## 阶段结论

iCoDer Streams 不再把 WAV、raw PCM 或任意字节默认为 WebM。配置阶段只接受 Corti
当前公开列出的流式编码格式；首个音频窗口在临床处理和留存前执行有界容器探测，声明 MIME
与实际容器不一致、未知参数、无法识别或过短的终态输入均以结构化错误失败关闭。

三套 SDK 同步在建立 WebSocket 前拒绝不支持的声明。真实环回 E2E 已由 `ICODER` 伪字节
切换为 ffmpeg 生成的 0.25 秒静音 Ogg/Opus，仍不使用患者数据、真实 ASR 或真实 LLM。

## 对齐依据

Corti 的 [Streams API](https://docs.corti.ai/api-reference/streams) 规定单块最大 64,000
bytes；[Audio input](https://docs.corti.ai/stt/audio) 将 Ogg、WebM、Opus、Vorbis、MP3、
FLAC、MP4/M4A 列为流式编码输入，并说明 raw audio 不支持、WAV 仅用于预录音上传、声明
格式不匹配会触发音频校验错误，首块必须足以识别容器头。iCoDer 本阶段按这一公开合同实现，
没有把未公开的编码能力推断为已支持。

## 实现与安全边界

| 能力 | 当前合同 |
|---|---|
| 声明校验 | MIME 大小写/空白归一；仅允许 `codecs=flac|opus|vorbis`，且仅允许在 Ogg/WebM 上声明兼容 codec |
| 容器探测 | 最多读取首 512 bytes；识别 Ogg/Opus/Vorbis/FLAC marker、WebM EBML、FLAC、MP3 ID3/frame sync 与 MP4 `ftyp` |
| 一致性 | 声明 container/codec 与探测结果不一致返回 `AUDIO_FORMAT_MISMATCH`；无效终态返回 `AUDIO_FORMAT_INVALID` 并以 4400 关闭 |
| 下游约束 | ASR 与录音留存只接收已经验证的解析 MIME；不存在 WebM fallback |
| SDK | JavaScript/Python/.NET 在传输前拒绝 WAV、raw、未知 MIME 和非法参数 |
| 重复调用 | `flush` 已处理全部音频后，`end` 不再对相同 buffer 重复调用 ASR，避免重复 Provider 成本 |
| 隐私 | 探测器不记录、不保留音频正文；错误仅暴露稳定代码和固定描述 |

## 验证结果

- 后端 Streams、容器、跨 Worker 租约与留存仓储扩大回归：**54/54**。
- JavaScript SDK：**87/87**；Python SDK：**91/91**；.NET net8.0/net10.0：各
  **72/72**。
- 迁移、升级/降级与 ORM 漂移扩大矩阵：**19/19**；发布候选验证器：**5/5**。
- 静态部署预检：**87/87**，新增编码容器/三 SDK/E2E 联合门禁。
- 单 Worker 三 SDK 真实 loopback WebSocket：**3/3**；每个会话发送 215-byte
  静音 Ogg/Opus，明确收到一次 `STT_UNAVAILABLE`、随后 `flushed → delta_usage → usage
  → ENDED`，证明禁用 Provider 时不生成伪 transcript、Facts 或 credits。
- 双 Worker 故障接管：活跃冲突拒绝、主 Worker 强制终止、6 秒后新 fence 接管，最终
  租约 **0**。
- 受保护开发库保持 8,536,064 bytes，SHA-256 仍为
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；Alembic
  单 head 为 `056`。审计结束时后端进程、阶段临时目录和 LLM key 进程环境均为 0。

机器证据位于 [`reports/sdk_stream_audio_format_phase_20260824`](../../reports/sdk_stream_audio_format_phase_20260824/)。
三 SDK `1.0.0-beta.32` 候选包已生成哈希清单但未发布；清单位于
`C:\codex-artifacts\release-b32-stream-audio-final\release-candidate-b32-stream-audio-final.json`。

## 仍未关闭的差距

- 容器头校验不等于完整解码、声学质量、采样率/声道或恶意媒体安全验证；生产需独立媒体
  解码沙箱、资源限制、模糊测试和恶意样本库。
- 未完成 Corti 托管 Streams 的双向互操作；公开文档一致不等于服务端行为逐字节等价。
- 真实中文医疗 ASR、说话人分离、多声道、audio events、实时 Facts、延迟、计费和临床
  准确率仍未通过真实 Provider 与独立临床评测。
- SQLite 双进程证据不等于 PostgreSQL 多副本、跨区路由、网络分区与容量/SLA 验证。
- 真实医院、云基础设施、数据合规、法务、认证和独立 reviewer 门禁仍为外部开放项。
