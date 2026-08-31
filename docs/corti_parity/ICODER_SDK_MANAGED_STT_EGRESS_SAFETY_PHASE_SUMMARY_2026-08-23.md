# iCoDer SDK 托管 STT 与音频外发安全阶段总结（2026-08-23）

> 本阶段证明 iCoDer JavaScript/Python SDK 对当前 iCoDer 实时 STT 协议具备可测试的托管连接生命周期，并关闭隐式音频外发与自由文本错误泄漏。它不证明与 Corti WebSocket wire protocol 互操作，也不证明真实临床语音质量或生产可用性。

## Corti 官方基线

Corti SDK Overview 将 WebSocket 描述为带自动重连和类型化事件的 managed connection，并把鉴权刷新、分页、重试和错误处理纳入 SDK：<https://docs.corti.ai/sdk/overview>。JavaScript WebSocket Guide 明确说明 `connect()` 默认等待 `CONFIG_ACCEPTED`，`awaitConfiguration: false` 可提前取得 socket，并公开 `sendAudio`、flush、end、typed message 与生命周期事件：<https://docs.corti.ai/sdk/js/websockets>。JavaScript/.NET 参考分别见 <https://docs.corti.ai/sdk/js/reference> 与 <https://docs.corti.ai/sdk/dotnet/websockets>。

本阶段只对标这些生命周期属性。iCoDer 当前 wire protocol 使用 `start → ready → interim/final → end`，不伪装成 Corti 的 `CONFIG_ACCEPTED`、Stream/Facts、usage 或 flush 合同。

## 已实现

- JavaScript `ManagedSttSession` 与 Python `ManagedSttSession` 均提供 ready handshake、类型化 message/open/ready/close/error/reconnecting 事件、等待 ready、发送音频、请求 interim、结束和关闭方法。
- 首次连接和每次重连前都调用现有自动鉴权刷新；token 只进入经过 URL 编码的连接地址，异常对象不保留 URL、Authorization、原始响应或服务端自由文本。
- 重连次数、初始延迟、最大延迟和 setup timeout 均有边界；重连耗尽后 `waitForReady` / `wait_for_ready` 现在会抛出终止错误，不再错误地正常返回。
- 当前服务端没有音频 resume cursor。SDK 因此只在尚未发送音频时自动重连；任意音频发送后断线固定返回 `audio_resume_unsupported`，避免把缺失前段的临床转写当成完整结果。
- 后端 WebSocket 继续强制 tenant-bound access/delegation/client-credentials token；机器 token 必须带 `streams` 或 `transcribe` scope；中文和媒体类型白名单、32 MiB 会话内存上限保持有效。
- 删除了隐式 `speech_recognition.recognize_google` 公共 Provider fallback。API 配置新增 `ICODER_ENABLE_LOCAL_STT=false` 默认值，实时路径在创建临床音频临时文件或加载 FunASR/Whisper/说话人分离前失败关闭；受控 DeepSeek runner 也显式保持该值为 false。
- 转写、后台任务和说话人分离不再记录原始异常文本或转写 preview；公共错误只返回稳定 code/固定 message。说话人分离临时音频在成功或异常路径均执行删除，客户端正常 disconnect 不再误记为内部错误。

## 验证

| 门禁 | 结果 |
|---|---:|
| JavaScript SDK 全量与 TypeScript build | 68/68，0 failed |
| Python SDK 全量 | 69/69，0 failed |
| managed STT + typed error/pager + resilience 专项 | JS 14/14、Python 14/14 |
| 后端 STT lifecycle/security/telemetry/jobs/ambient/preflight 扩大回归 | 40/40 |
| 后端新增安全 + telemetry + preflight 专项 | 18/18 |
| 静态部署候选预检 | 83/83，失败项 0 |
| JavaScript 发布包检查 | 56 files；managed JS 与声明均包含 |
| Python wheel 检查 | 27 files；managed Python 模块包含 |
| 后端单体全量 | 5260 passed、20 skipped、11 deselected、0 failed；1670.45s |

负向用例覆盖配置拒绝自由文本丢弃、pre-audio 重连、post-audio 终止、重连预算耗尽、无音频结束、原生转写异常脱敏、说话人分离失败临时文件清理、默认本机 STT 在落盘前拒绝，以及源代码/部署预检双重禁止隐式公共 Google STT。

## 与 Corti 的剩余差距

- iCoDer 只实现自身 STT wire protocol；尚未与 Corti 托管 Stream/Transcribe socket 做双向互操作。
- Corti 暴露 Stream 与 Transcribe 的统一 managed surface，以及 richer transcript/facts/usage/flushed/ended/command 消息；iCoDer 当前只有 ready/interim/final/buffering/pong/error。
- iCoDer 服务端没有可恢复音频 cursor、客户端重放确认或多副本 session ownership，因此不能安全承诺 mid-audio 自动恢复。
- JavaScript/Python 已实现 managed lifecycle；.NET 仍只有既有资源源码，且本机没有 dotnet/csc/msbuild，未获得同等构建与运行证据。
- 默认开发/生产候选 API 不加载本机原生 STT，但当前也没有接入经过中国区域、数据处理协议、容量和医院批准的真实 STT Provider；所以实时转写仍不是可上线临床能力。
- 方言、噪声、多人重叠、长音频、说话人身份映射、医学术语准确率、P95 延迟、断网恢复、成本、容量和临床验收必须由真实语料、区域基础设施与独立 reviewer 完成。

因此，Corti 式“托管连接生命周期”的本机工程差距已经在 JavaScript/Python 上关闭；Corti wire compatibility、真实区域 STT、mid-audio resume、.NET、长连接基础设施和临床质量继续保留为上线门禁。
