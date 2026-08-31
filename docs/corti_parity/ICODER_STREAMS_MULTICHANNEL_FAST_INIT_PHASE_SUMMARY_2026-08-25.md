# iCoDer Streams 多声道 PCM 与 fast_init 阶段总结（2026-08-25）

> 后续状态：本报告记录的 session keyterms 开放项已由 [`ICODER_STREAMS_KEYTERMS_CURRENT_CONTRACT_PHASE_SUMMARY_2026-08-25.md`](ICODER_STREAMS_KEYTERMS_CURRENT_CONTRACT_PHASE_SUMMARY_2026-08-25.md) 关闭开发合同缺口；diarization 与真实语音质量仍开放。

## 阶段结论

本阶段关闭了 Corti Streams 公开合同中“声明式多声道 PCM”和 `factExtraction.mode=fast_init` 的开发环境缺口。iCoDer 现在接受 1–8 声道的 16 kHz、signed 16-bit、little-endian 原始 PCM；多声道会按交错帧拆分，且每个声道必须与唯一 participant 的 `channel` 精确对应。transcript segment、音频健康事件、持久化 transcript 和恢复 checkpoint 均保留声道归属。`fast_init` 使用约 10、20、26、38 秒后逐步增长、最高 60 秒的调度；`fixed` 继续使用 60 秒。

这只表示协议、归属、状态机、安全边界和三 SDK 开发候选已实现并通过本地 E2E，不表示真实中文医疗 ASR、真实 Facts/LLM、临床准确率、Corti 私有服务端实现、计费、容量或生产 SLA 已达到等价。

## 对标依据

- Corti Streams API 公开 `primaryLanguage`、`isDiarization`、`isMultichannel`、participant `channel/role`、segment `speakerId`/participant channel，以及 `fixed`/`fast_init` Facts 模式。
- Corti STT Audio 公开说明 multichannel 适用于每个说话人独占一个对齐声道的场景，并推荐 16-bit/16 kHz PCM。
- Corti Text Generation 发布说明描述 `fast_init` 先快速产生 Facts、随后逐步放宽间隔的行为。

官方资料：<https://docs.corti.ai/api-reference/streams>、<https://docs.corti.ai/stt/streams>、<https://docs.corti.ai/stt/audio>、<https://docs.corti.ai/release-notes/textgen>。

## 已完成的能力

1. Streams 配置接受 1–8 声道原始 PCM；非多声道配置必须为单声道，多声道配置必须至少双声道。
2. 多声道 participant 映射要求声道集合恰好为 `0..channels-1`，拒绝缺失、重复、越界或多余映射。
3. 纯 Python PCM s16le 解交错不会加载不稳定的本机 native ML 栈，并对非完整交错帧失败关闭。
4. 每声道独立执行音频健康监控与转写适配；事件和 transcript segment 携带精确 participant channel。
5. `retain` checkpoint 保存并恢复各声道 transcript 状态、消息序号和 Facts 尝试进度；租约与 session fencing 语义不变。
6. `fast_init` 与 `fixed` 均进入服务端审计和三 SDK 类型化配置；JavaScript、Python、.NET 使用同一组客户端失败关闭规则。
7. Corti JSON 字段统一为 `isDiarization`；兼容输入仍接受历史别名 `diarize`。
8. 发布候选升至 JavaScript/.NET `1.0.0-beta.37`、Python `1.0.0b37`，仅在本机生成并校验，未发布。

## 同阶段发现并修复的独立缺陷

Agent Run 幂等重放过去会重新签发 attestation，违背“持久化响应原样重放”的合同。现在重放前验证已保存 token 与 run、agent、schema、organization 和 result 的绑定，并返回原 token；无效或过期证明失败关闭。该修复通过整个幂等测试文件及最终全量回归。

## 验证结果

- Streams 聚焦后端：54 passed。
- 最终后端全量：5,565 passed、20 skipped、11 deselected、0 failed；耗时 1,889.04 秒。
- JavaScript SDK：93/93。
- Python SDK：97/97。
- .NET SDK：net8.0 78/78，net10.0 78/78。
- 部署候选预检：94/94。
- 真实 loopback WebSocket：JavaScript、Python、.NET 三套 SDK 通过；另含 malformed media、单声道 audio events 与双声道 fast_init 场景。
- 多声道场景使用 10 秒合成 stereo PCM（声道 0 静音、声道 1 合成音），验证 participant channel、声道健康事件、decoder 到 STT adapter、`STT_UNAVAILABLE`、usage 与 `ENDED`；未使用患者音频、真实 ASR 或真实 LLM。
- 受保护开发数据库未被测试迁移或写入：8,536,064 bytes，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- 两轮全量回归都未复现此前 Windows native/PyArrow 访问冲突；这降低了本阶段路径的崩溃风险，但不能证明原生栈缺陷已修复。

机器可读证据：

- `reports/streams_multichannel_phase_20260825/phase_evidence.json`
- `reports/streams_multichannel_phase_20260825/loopback_e2e.json`
- `reports/streams_multichannel_phase_20260825/full_backend_remediated_junit.xml`
- `reports/deployment/streams_multichannel_phase_20260825/deployment_preflight.json`
- `reports/streams_multichannel_phase_20260825/release_candidate_validation.json`

## 仍未关闭的 Corti 差距

1. Diarization 仍失败关闭：现有启发式/本机 native diarizer 没有临床级权威证据，不应伪装为可上线能力。
2. 未验证真实中国区域医疗 ASR，包括普通话、方言、口音、噪声、串音、打断、长音频、时间戳、实时纠错、延迟和并发容量。
3. 未验证真实 Facts/LLM 的 `fast_init` 内容质量、费用、稳定性或与 Corti 同音频 head-to-head 等价。
4. 编码容器的多声道语义、Corti 支持的其余 PCM profile、真实音频事件准确率、生产 PostgreSQL 多副本、KMS 轮换与清理调度仍开放。
5. Corti 公共 Streams 文档未公开 session checkpoint/fencing 的内部字段与恢复计数；当前不能宣称私有重连实现等价。
6. Agent Hub 严格 live-provider 仍为 0/26，CDI/Medical Coding 多病例真实执行仍为 0/50，临床与生产验收仍为 0/26。

## 凭证与运行边界

本阶段没有使用用户曾在对话中暴露的 DeepSeek Key；Process/User/Machine 三层相关环境变量检查均为空。该 Key 已视为泄露，仍须在 DeepSeek 控制台撤销并换发。测试固定关闭 native medcoder、本地 STT 和外部 LLM，并使用临时 SQLite；受主机删除策略限制而残留的历史临时数据库不作为产品数据或通过证据。
