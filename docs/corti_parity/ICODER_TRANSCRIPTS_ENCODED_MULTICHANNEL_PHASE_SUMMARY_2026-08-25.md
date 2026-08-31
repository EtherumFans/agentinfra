# iCoDer Transcripts 编码多声道与逐句时间戳阶段总结（2026-08-25）

## 阶段结论

本阶段关闭了开发环境内可完成的预录音 `/transcripts` 编码双声道隔离解码合同，并把有效 ASR Provider 的逐句时间信息统一为 Corti 返回合同使用的整数毫秒。同步、持久异步 Job 与重启恢复路径共用同一验证、解码、转写和加密持久化边界。

根据 Corti 当前公开文档，预录音接口接受 WAV、Ogg、WebM、Opus、Vorbis、MP3、FLAC、M4A/AAC 等容器或编码；远程医疗双单声道场景可用 `isMultichannel` 分别转写声道，通过 `participants[].channel` 绑定角色，返回行包含 `channel`、`participant`、`speakerId`、`text`、`start`、`end`，其中开始和结束时间为毫秒。参考：[Audio Configuration](https://docs.corti.ai/stt/audio)、[Create Transcript](https://docs.corti.ai/api-reference/transcripts/create-transcript)、[Transcripts](https://docs.corti.ai/stt/transcripts)。

iCoDer 当前实现边界为：

- 公开接受与 Corti 文档一致的上述 MIME/container 合同，并对内容、声明 MIME、容器和 codec 做一致性校验；损坏、错标、超长、超大或非双声道文件在 ASR 前失败关闭。
- 编码媒体只经受控的外部 `ffprobe`/`ffmpeg` 子进程处理，限制输入大小、时长、探测输出、解码时间、并发和排队时间；不使用 shell，限制 pipe 协议，成功、失败和取消均清理临时文件。
- `isMultichannel=true` 仍要求恰好两个 participant，channel 精确覆盖 0 和 1。解码结果为两个隔离的 16 kHz、16-bit mono PCM WAV，再分别进入 ASR，避免声道串扰。
- FunASR 的有效 `sentence_info` 毫秒段直接形成逐句行；Whisper 秒单位段转换为整数毫秒。无效、越界、逆序或非有限时间段不会被信任。
- Provider 未返回有效分段时保留兼容回退：每个非静音声道只产生一条整段结果，时间边界为零值。该回退不冒充真实逐句或词级时间戳。
- JavaScript、Python、.NET SDK 的容器集合、双声道 participant 校验和 API 合同保持一致，版本升至 `beta.42/b42`。

## 端到端与回归证据

- 真实 Uvicorn、真实租户注册/鉴权、真实录音上传、同步请求、持久异步轮询与真实 FFmpeg 编解码均通过。
- 首个 E2E 同时覆盖 PCM WAV 与 FLAC stereo；两个声道使用相反合成样本，ASR 测试边界逐声道校验，证明同步和异步路径均无串扰，并返回 doctor/channel 0、patient/channel 1。
- 补充的逐格式矩阵以 440 Hz/880 Hz 两个合成声道完成 `audio/ogg`、`audio/webm`、`audio/opus`、`audio/vorbis`、`audio/mpeg`、`audio/mp3`、`audio/mpeg3`、`audio/flac`、`audio/mp4`、`audio/m4a` 共 10 个 MIME 情形；实际 payload 覆盖 Ogg/Opus、WebM/Opus、Ogg/Vorbis、MP3、FLAC、MP4/AAC。每项均完成上传、同步 201、异步 202→completed、持久结果读取、四条毫秒行和频率隔离检查；两个独立临时数据库完整运行均为 **10/10**，合计 **20/20**。
- Provider 测试段精确验证 `0–40 ms`、`50–90 ms`、`0–45 ms`、`50–95 ms` 等逐句边界未被误当作秒。
- 首次编码同步 E2E 在 15 秒客户端超时；随后完整运行一次及稳定性重复两次均通过，即 **3 次完整成功、1 次初始瞬时超时**。该事件保留在阶段结论中，不将稳定性扩大表述为长期 soak。
- 机器证据均为 `true`：`prerecorded_encoded_stereo_decoded_without_crosstalk`、`prerecorded_stereo_pcm_split_without_crosstalk`、`prerecorded_multichannel_attribution_sync_async`、`prerecorded_phrase_timestamps_are_milliseconds`。
- 聚焦 STT/API/预检回归：**206/206**。
- 后端四分片最终结果：**5,604 passed、20 skipped、11 deselected、0 failed**；另有根级发布测试 **13/13**，合计 **5,617 passed**。
- JavaScript SDK：**95/95**；Python SDK：**101/101**；.NET net8.0/net10.0：各 **82/82**。
- 静态部署预检：**101/101**；发布候选验证器：**5/5**；OpenAPI `--check` 通过。
- OpenAPI：877,158 bytes、271 paths、299 schemas，SHA-256 `2c4763c073a6ffafaec6c52e433af7903bb4aa9146c32c32e26307b2e6371d57`。

全量后端必须把 `DATABASE_URL` 与 `ICODER_DATABASE_URL` 指向同一个唯一临时 SQLite URL。早期诊断运行只设置其中一个变量，导致 Streams 写入与测试读取落到不同数据库；该运行不作为发布证据。按正确不变量重跑的四个分片全部通过，且 `PytestUnhandledThreadExceptionWarning` 被提升为错误后仍为 0。

## SDK 与候选工件

JavaScript/.NET 版本为 `1.0.0-beta.42`，Python 为 `1.0.0b42`。5 个安装包与 1 个内层 manifest 已构建，逐项 SHA-256 与候选清单一致，未发布到任何外部仓库。候选目录为 `C:\codex-artifacts\release-b42-transcripts-encoded-multichannel`。

## 安全与数据边界

- E2E 只使用合成音频和合成 ASR 边界：`patient_audio_used=false`、`real_stt_used=false`、`real_llm_used=false`。
- 最终验证使用 bundled Python，并关闭本地 STT、原生 MedCoder 与外部 LLM；没有加载不稳定的本机 PyArrow 原生链。
- 受保护数据库保持 8,536,064 bytes、最后写入 `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`，未迁移、未写入。
- 工作区与候选目录均未检出 `sk-` 加 32 位十六进制的 DeepSeek Key 形态；候选目录的一般密钥样式匹配为 0。
- 逐格式矩阵的两个 Uvicorn 进程均已停止。主机策略拒绝删除其两个明确的合成测试临时目录，因此保留了临时 SQLite 和无敏感数据日志；它们不含患者数据或真实 Key，也未进入候选工件。
- 最终核验时 8000 端口没有监听，也没有项目 Uvicorn 进程，因此本阶段没有执行新的真实 DeepSeek 回归。此前对话中暴露的 Key 仍必须在 DeepSeek 控制台撤销并轮换。

## 相对 Corti 的剩余能力差距

1. 未实现单声道多人 diarization、自动 participant 推断和 speaker identity；`speakerId=-1` 仍明确表示未做说话人分离。
2. Provider 逐句时间戳已经传递和校验，但尚无词级时间戳，也没有用真实中国医疗音频验证分句质量。
3. 逐格式真实 FFmpeg E2E 已关闭格式兼容性差距，但只使用短合成音调与合成 ASR 边界；它不证明有损编码后的真实临床识别准确率、长音频稳定性或资源容量。
4. 尚未用真实 FunASR/区域 STT 和合规中国医疗双声道音频验证方言、噪声、重叠语音、长音频及医学术语准确率。
5. 尚未用同一批授权音频与 Corti 做盲测，因此没有质量、延迟、成本、并发容量或 SLA 等价证据。
6. Agent Hub 的严格真实 Provider 语义和临床生产批准仍为 0/26；本阶段只关闭 STT 合同切片，不能改变该结论。
7. Linux/PostgreSQL 多副本、Docker 镜像/SBOM/漏洞扫描、KMS、对象存储与 AV/DLP、监控告警、渗透测试、数据驻留、法务认证和医院验收仍是外部上线门禁。

机器证据见 [`reports/transcripts_encoded_multichannel_phase_20260825/phase_evidence.json`](../../reports/transcripts_encoded_multichannel_phase_20260825/phase_evidence.json)，逐格式首轮与稳定性复跑见 [`encoded_format_matrix_e2e.json`](../../reports/transcripts_encoded_multichannel_phase_20260825/encoded_format_matrix_e2e.json) 和 [`encoded_format_matrix_e2e_stability_1.json`](../../reports/transcripts_encoded_multichannel_phase_20260825/encoded_format_matrix_e2e_stability_1.json)，部署预检见 [`deployment_preflight.json`](../../reports/transcripts_encoded_multichannel_phase_20260825/preflight/deployment_preflight.json)，发布物清单见 [`release_candidate_validation.json`](../../reports/transcripts_encoded_multichannel_phase_20260825/release_candidate_validation.json)。
