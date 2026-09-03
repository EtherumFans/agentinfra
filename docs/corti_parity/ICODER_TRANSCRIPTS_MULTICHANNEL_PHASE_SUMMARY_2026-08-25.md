# iCoDer Transcripts 多声道阶段总结（2026-08-25）

## 阶段结论

本阶段关闭了开发环境内可完成的预录音 `/transcripts` 双声道 PCM WAV 拆分和参与者归属合同差距。根据 Corti 当前公开合同，远程医疗场景可把每位参与者放在独立且时间对齐的声道中，`isMultichannel` 使各声道分别转写，`participants[].channel` 决定返回 transcript 的 participant/channel 归属。iCoDer 当前实现边界为：

- 接受且仅接受时间对齐的 stereo、16 kHz、16-bit、未压缩 PCM WAV；其他采样率、位深、声道数、压缩编码或损坏容器均在 ASR 前以 422 失败关闭。
- `isMultichannel=true` 时要求恰好两个 participant，channel 必须精确覆盖 0 和 1；不推断、不补全、不交换参与者。
- 以有界分块方式把交错 PCM 拆成两个临时 mono WAV，并串行送入现有 ASR 边界，避免同时加载原生模型和大音频副本；成功或失败都会清理临时文件。
- 同步、持久异步 Job 和进程恢复路径使用同一合同，并保留 keyterms、中文口述标点和 replacements 的既有语义。
- 返回及加密持久化的 transcript 行保留 `channel`、`participant`、`speakerId`、`text`、`start`、`end`；旧单文本密文仍可读取，无数据库迁移。
- JavaScript、Python、.NET SDK 均公开 `isMultichannel` 与两个声道 participant 的同一客户端校验。

参考合同：[Corti Audio Configuration](https://docs.corti.ai/stt/audio)、[Corti Create Transcript](https://docs.corti.ai/api-reference/transcripts/create-transcript)、[Corti Speech-to-Text Overview](https://docs.corti.ai/stt/overview)。

## 精确能力边界

本阶段没有实现或暗示 diarization。每个非静音声道当前形成一条整段结果，`start=0`、`end=音频时长`；`speakerId=-1` 表示未执行说话人分离。因此，当前证据只证明“显式双声道 participant attribution”，不证明单声道多人识别、逐句分段或词级时间戳。

静音声道可以不产生文本；真正的推理错误会使整次多声道任务失败，而不会用另一声道结果伪造完整成功。日志和遥测只汇总时长、声道数、模型状态等无内容字段，不记录转写正文或 keyterms。

## 端到端与回归证据

- 真实 Uvicorn、真实注册/租户鉴权、真实录音上传、同步和异步轮询 loopback：通过。
- 合成 stereo WAV 的 channel 0 固定为正样本、channel 1 固定为负样本；ASR 测试边界逐一检查 mono 样本，证明无声道串扰，并精确返回 doctor/channel 0 与 patient/channel 1。
- 机器证据：`prerecorded_stereo_pcm_split_without_crosstalk=true`、`prerecorded_multichannel_attribution_sync_async=true`。
- 音频与 ASR：只使用合成 WAV 和合成 ASR 边界；`patient_audio_used=false`、`real_stt_used=false`、`real_llm_used=false`。
- STT 聚焦回归：**44/44**；STT/OpenAPI 扩大回归：**141/141**。
- 最终后端全量：**5,586 passed、20 skipped、11 deselected、0 failed**，JUnit 1797.542 秒。
- JavaScript SDK：**95/95**；Python SDK：**101/101**；.NET net8.0/net10.0：各 **82/82**。
- 部署预检：**100/100**；最终发布验证器/OpenAPI 回归：**13/13**。
- OpenAPI：877,158 bytes、271 paths、299 schemas。

首次后端全量运行暴露了一次 `aiosqlite` 后台 reader 在线程结束后访问已关闭 event loop 的警告。测试夹具现显式关闭 `TestClient`、关闭 WebSocket 后 join reader thread，并把 `PytestUnhandledThreadExceptionWarning` 提升为错误；目标文件 **40/40**、重复收集 **200/200** 和上述最终全量均无警告。

## SDK 与候选工件

JavaScript/.NET 版本为 `1.0.0-beta.41`，Python 为 `1.0.0b41`。5 个安装包与 1 个内层 manifest 已重新构建并校验 SHA-256，未发布到任何外部仓库。候选目录为 `C:\codex-artifacts\release-b41-transcripts-multichannel`。

## 环境稳定性事件

本机系统 Python 曾在 `pyarrow\arrow.dll` 中触发 Windows `0xc0000005` 原生访问冲突，表现为 Uvicorn `exit code -1`；SQLAlchemy 查询后的 `ROLLBACK` 不是根因。Windows 事件只能确认访问冲突，不能判断读越界或写越界。最终验证改用隔离的 bundled Python，并关闭本地 STT、原生 MedCoder 与外部 LLM；本阶段没有声称修复系统级 PyArrow 安装，也没有继续通过该不稳定路径执行高负载测试。

## 尚未关闭的 Corti 能力差距

1. 预录音只验证 stereo PCM WAV；MP3、AAC、Opus、FLAC 等编码或压缩多声道的可靠解码尚未实现。
2. 单声道 diarization、自动 speaker/participant 推断、逐句分段及准确逐句/词级时间戳尚未实现。
3. 尚未用真实 FunASR 和合规中国医疗双声道音频验证方言、噪声、重叠语音、长音频和医学术语准确率。
4. 尚未用同一批授权音频与 Corti 做盲测，因此没有质量、延迟、成本、并发容量或 SLA 等价证据。
5. Docker/Linux/PostgreSQL 多副本、KMS、监控告警、渗透测试、数据驻留和医院验收仍是外部上线门禁。
6. Agent Hub 的严格真实 Provider 语义和临床生产批准仍为 0/26；本阶段只关闭 STT 合同切片，不能改变该结论。

## 安全与数据边界

最终验证显式清空 DeepSeek/OpenAI/项目 LLM 凭证，关闭外部 LLM、本地 STT 和原生 MedCoder，使用临时 SQLite；受保护开发数据库未迁移、未写入。用户曾在对话中暴露的 DeepSeek Key 未被本阶段使用，仍必须在 DeepSeek 控制台撤销并轮换。

机器证据见 `reports/transcripts_multichannel_phase_20260825/phase_evidence.json`，发布物清单见 `reports/transcripts_multichannel_phase_20260825/release_candidate_validation.json`。
