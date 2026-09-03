# iCoDer Streams 隔离媒体解码阶段总结（2026-08-24）

## 阶段结论

Streams 的“容器头真实”已提升为“至少一帧可解码”。通过 MIME 与首部校验的音频，必须先
在独立 ffmpeg 子进程中成功解码一帧，才允许进入 ASR 或加密留存。缺失解码器、超时和
畸形媒体均使用固定、无正文的错误失败关闭；云模式禁止退回 `header_only`。

该阶段避免在 API 进程加载 FunASR、Whisper、Torch 等原生 ML 栈。ffmpeg 只从 stdin
读取已受 32 MiB 会话上限约束的媒体，stdout/stderr 均丢弃，单线程，probe 1 MiB，
analyze 1 秒，只解码一帧，单次分配上限 64 MiB，默认墙钟超时 3 秒；协议白名单仅允许
`pipe`，子进程环境不继承 iCoDer 凭据，超时进程会被 kill 并回收。

## Corti 对齐依据

Corti [Audio input](https://docs.corti.ai/stt/audio) 明确要求声明格式与实际音频匹配、首块
足以识别容器，并区分流式编码容器与仅供上传的 WAV；[Streams API](https://docs.corti.ai/api-reference/streams)
规定单块最大 64,000 bytes。公开文档没有披露 Corti 的具体解码沙箱实现，因此本阶段只能
证明 iCoDer 在公开输入合同之上增加了可执行安全门，不能声称内部实现等价。

## 实现合同

| 能力 | 当前行为 |
|---|---|
| 执行隔离 | `asyncio.create_subprocess_exec` 启动固定服务端路径；参数数组执行，不接受客户端命令或路径 |
| 内容最小化 | 音频仅通过 stdin；stdout/stderr 为 DEVNULL；协议仅 `pipe`；子进程环境只保留 OS 运行必需字段，不继承 LLM/Connector 等应用凭据 |
| 资源边界 | 1 thread、1 MiB probe、1 秒 analyze、1 frame、64 MiB 单次分配、0.25–10 秒配置边界，默认 3 秒 |
| 失败语义 | 畸形 `AUDIO_DECODE_INVALID`/4400；超时 `AUDIO_VALIDATION_TIMEOUT`/1013；缺失能力 `AUDIO_VALIDATION_UNAVAILABLE`/1013 |
| 下游保护 | 解码失败不调用 ASR、不生成 transcript、不执行录音留存、不发 usage/ENDED 成功终态 |
| 云门禁 | `ICODER_STREAM_MEDIA_VALIDATION_MODE=decoder` 必需；Docker API 镜像声明安装 ffmpeg；仅头模式只允许本地诊断 |

## 端到端证据

同一临时租户和临时 Alembic `056` 数据库完成四条真实 WebSocket 场景：

1. JavaScript、Python、.NET 分别发送 ffmpeg 生成的 215-byte 静音 Ogg/Opus；三者通过
   独立 decoder 后，由于真实 STT 明确关闭，仅收到一次 `STT_UNAVAILABLE`，随后按合同
   完成 flush/usage/end；仅 retain 会话生成一条加密录音。
2. 第四条会话发送具有 `OggS` 与 `OpusHead` 外观、但不可解码的合成字节；头门通过，
   decoder 返回 `AUDIO_DECODE_INVALID` 并以 4400 关闭。最终仍只有前三条中的一条录音、
   0 transcript、0 Facts、0 租约残留，证明 ASR 和留存未被触达。
3. 双 Worker 租约故障 E2E 继续通过：活跃冲突拒绝、主 Worker 强制终止、6 秒后新 fence
   接管，最终租约 0。

## 验证结果

- 后端 Streams、格式、decoder、租约、留存与云配置联合矩阵：**119/119**。
- JavaScript：**87/87**；Python：**91/91**；.NET net8/net10：各 **72/72**。
- 迁移、升级/降级与 ORM 漂移：**19/19**；发布验证器：**5/5**。
- 静态部署预检：**88/88**；Docker CLI 在本机不可用，因此没有把静态 Dockerfile 检查
  误报为实际镜像构建/扫描通过。
- `1.0.0-beta.33` 四个候选包已生成哈希清单，未发布。
- 受保护开发库仍为 8,536,064 bytes、SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
  Alembic 单 head `056`。审计结束时后端进程、阶段临时目录与 LLM key 进程环境均为 0。

机器证据：[`reports/sdk_stream_media_decoder_phase_20260824`](../../reports/sdk_stream_media_decoder_phase_20260824/)。
候选清单：`C:\codex-artifacts\release-b33-stream-media-decoder-final\release-candidate-b33-stream-media-decoder-final.json`。

## 仍未关闭的差距

- 未在 Docker/Linux 运行和扫描 API 镜像；ffmpeg 版本固定、CVE/许可证、seccomp/AppArmor、
  容器级 CPU/内存/进程配额仍需云安全与法务批准。
- ffmpeg 子进程隔离强于进程内解码，但不等于独立微虚机/sidecar 沙箱；Windows 没有等价
  的 OS 级内存硬限制，恶意媒体模糊测试集与长期 soak 仍需补充。
- 未对 Corti 托管 Streams 执行同一合法/畸形媒体的双向互操作；当前只对齐公开合同。
- 真实中文医疗 ASR、diarization、多声道、audio events、Facts、延迟、计费与临床准确率
  仍需真实 Provider、医院数据治理和独立临床 reviewer。
