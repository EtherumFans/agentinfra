# iCoDer 实时 STT 断线恢复阶段总结（2026-08-24）

## 阶段结论

实时 STT 的“发送音频后断线只能失败关闭”开发缺口已经关闭。服务端与 JavaScript、Python、.NET 三套 SDK 现在协商 `icoder.stt-resume.v1`，使用单调音频序号、服务端 ACK/去重和客户端有界内存重放；旧服务端未确认恢复能力时继续以 `audio_resume_unsupported` 失败关闭，不会把缺少前段的临床转写当作完整结果。

该结论只证明传输恢复合同，不证明真实语音识别质量。测试使用 6 字节合成非音频数据，明确关闭本机 STT 和外部 LLM。

## 协议与安全边界

| 能力 | 当前合同 |
|---|---|
| 协商 | `start.protocol=icoder.stt-resume.v1`，服务端必须回显 `resumeSupported=true`、`resumeMode=client_replay`、同一 opaque `sessionId` 与 `nextAudioSequence` |
| 音频帧 | `ICR1` 魔数 + 4 字节大端无符号序号 + 非空音频载荷；32 MiB 上限只计算音频载荷 |
| 确认与去重 | 每个已接收序号返回 `audio_ack`；连接内重复序号只返回 ACK，不重复追加；序号缺口失败关闭 |
| 完成 | `end.lastAudioSequence` 必须等于服务端期望的末序号，否则返回 `audio_sequence_incomplete` |
| 恢复 | SDK 重新取得当前 token、建连并握手，然后从 `nextAudioSequence` 重放不可变音频副本；若已经发送 `end`，最后重放结束指令 |
| PHI | SDK 缓存有界且只在内存中；服务端不为恢复协议持久化原始音频；.NET 释放会话时覆盖缓存帧；错误只公开稳定代码 |
| 多 Worker | `client_replay` 不依赖进程本地 cursor；两个独立 Uvicorn 进程通过 round-robin 故障代理完成首次连接与恢复连接切换 |

当前服务端每次恢复通常返回 `nextAudioSequence=1`，因此会重放整段缓存。它不是持久化的服务端恢复 cursor，也不宣称跨客户端/重启恢复尚未上传完成的录音。

## 验证证据

- 后端实时 STT 安全与协议：**20/20**。
- JavaScript SDK：**78/78**。
- Python SDK：**82/82**。
- .NET SDK：net8.0 **65/65**，net10.0 **65/65**。
- 静态部署预检：**84/84**，包含服务端/三 SDK 恢复合同、缓存覆盖和双 Worker 故障脚本检查。
- 真实 loopback WebSocket 故障注入：JavaScript、Python、.NET 各 1 个会话；两个独立 API 进程；每个会话在序号 1 ACK 后被强制断开一次；共 **3 个会话、3 次强制断线、6 次连接、3 个跨进程恢复**，三套 SDK 均收到首次和重放 ACK。
- 机器证据：[`e2e_evidence.json`](../../reports/sdk_realtime_stt_resume_phase_20260824/e2e_evidence.json)。
- 阶段汇总证据：[`phase_evidence.json`](../../reports/sdk_realtime_stt_resume_phase_20260824/phase_evidence.json)。

E2E 使用全新临时 SQLite、临时签名密钥和真实租户绑定 access token；结束后删除临时数据库并终止两个 Uvicorn 与故障代理。没有使用真实患者数据、真实音频、真实 STT Provider 或真实 LLM。

## 候选制品

三套 SDK 已生成 `1.0.0-beta.30` 候选包，清单位于 `C:\codex-artifacts\release-candidate-b30-stt-final2.json`。候选源码 revision 为 `4fc31b3c012c49d09c6b3b01d3c67e25049efe98`，清单如实标记现有工作区为 `dirty`；所有制品均未发布。

| 制品 | 字节 | SHA-256 |
|---|---:|---|
| `icoder-sdk-1.0.0-beta.30.tgz` | 66,785 | `5a15a65d4c64291ebf3f6bcc6f46ab50631e94b280ac3d9b7f77f8f15178254c` |
| `icoder_sdk-1.0.0b30-py3-none-any.whl` | 52,050 | `59f3039cae1cb7cb897dd910d16b0667ed819f6e6623941de01cfcf468064357` |
| `iCoDer.Sdk.1.0.0-beta.30.nupkg` | 394,934 | `defd68cbcad0a02653da4a6c5ed102469362818a5e8c7a76c10f339d902576d2` |
| `iCoDer.Sdk.1.0.0-beta.30.snupkg` | 84,001 | `3930f0de15a7f03e0630d1f4853e3332498cdcc3af14c9525414fe363e8a0211` |

## 对 Corti 当前公开能力的差距

Corti 公开的 [`/transcribe`](https://docs.corti.ai/api-reference/transcribe) 是实时无状态听写 WebSocket，配置确认后接收音频并返回 transcript/command；[`/streams`](https://docs.corti.ai/api-reference/streams) 是面向交互的有状态实时会话，可输出转写和 Facts。官方 [STT 概览](https://docs.corti.ai/stt/overview)、[Streams 说明](https://docs.corti.ai/stt/streams) 与 [2026 STT release notes](https://docs.corti.ai/release-notes/stt) 还公开了多语言层级、interim、格式化、命令、音频健康事件、多人/多声道、diarization、持久交互和 usage 等能力。

iCoDer 本阶段只关闭了断线后音频完整性与三 SDK 托管恢复差距，仍没有证明以下 Corti 级能力：

- 真实区域医疗 ASR 的转写、interim、延迟、成本、usage 和 SLA；
- 方言、噪声、静音、远场、长音频、多声道、参与者角色及说话人分离质量；
- Corti `/transcribe` 的命令与格式化、音频健康事件；
- Corti `/streams` 的实时 transcript + Facts、flush/ended/usage 和持久 interaction 语义；
- Corti 托管租户与官方 JavaScript/.NET SDK 的双向互操作。

这些差距不能用协议模拟或合成字节测试提升为已完成。真实中文医疗语音集、区域 Provider、医院授权、生产网络、容量和独立临床 reviewer 仍是外部门禁。
