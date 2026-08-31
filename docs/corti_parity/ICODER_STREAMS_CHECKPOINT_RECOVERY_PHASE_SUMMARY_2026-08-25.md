# iCoDer Streams 未结束交互断点恢复阶段总结（2026-08-25）

## 阶段结论

iCoDer 已在开发环境关闭“`retain` Streams 交互因 Worker 异常退出而丢失未结束音频、
transcript/Facts 进度”的工程缺口。恢复状态和音频分块必须加密落库，以组织、主体和
interaction 复合边界隔离，并由新的 session UUID fencing；配置不一致、密文或摘要损坏、
旧 Writer 写入、缺加密能力和缺 checkpoint 均失败关闭。

这不是 Corti 托管服务等价或临床上线证明。本轮只使用合成 16 kHz mono PCM、临时 SQLite
和关闭的本地 STT/外部 LLM。真实中文医疗 ASR、FactsR 质量、生产 PostgreSQL 多副本、
KMS、容量/SLA、医院验收及监管认证仍未验证。

## 已完成的实现

- Alembic `057` 新增 `stt_stream_checkpoints` 与 append-only
  `stt_stream_checkpoint_chunks`；状态和每个音频块均加密，并分别绑定 SHA-256、序号、长度
  和总量记账。
- `StreamCheckpointRepository` 对 64,000-byte chunk、32 MiB 会话、1 MiB 状态设置硬上限；
  `retain` 在未配置 PHI 加密密钥时拒绝启动，不能退化为明文。
- checkpoint session 与持久租约共同 fencing。接管者在租约过期后轮换 session，旧 Worker
  不能继续追加、更新或删除新会话状态；恢复配置必须与原配置完全一致。
- 每个已接受音频块、transcript/Facts 进度、provider usage、媒体探测状态和计数都以事务
  保存；崩溃后以已持久化 transcript/Facts 为权威重新对账，避免“业务写成功、checkpoint
  尚未更新”的窗口产生重复结果。
- 正常 `end` 只持久化一份相同录音，完成审计后删除 checkpoint/chunks；不可恢复媒体错误
  也删除 checkpoint，暂时性断线或 Worker 异常退出保留它。
- `CONFIG_ACCEPTED` 新增 `resumed`、`restoredAudioBytes`、
  `restoredTranscriptMessages`、`restoredFactMessages`。JavaScript、Python 与 .NET SDK
  提供显式 `resume` 入口；只有服务端确认 `resumed=true` 才成功。
- SDK 只在收到 `flushed` 回执后把当前音频标记为可安全恢复。已发送但未收到该回执的音频
  继续返回 `audio_resume_unsupported`，不会猜测或隐式重放。恢复后的 transcript/Facts
  通过计数和既有 REST artifact 生命周期对账，不在新 WebSocket 上伪造历史消息重放。

## 验证结果

| 验证 | 结果 |
|---|---:|
| checkpoint repository、租约与 Streams API | 44/44 |
| 完整后端回归（修复后） | 5,559 passed、20 skipped、11 deselected、0 failed |
| fresh migration、downgrade `056`、re-upgrade `057`、schema drift/portability | 10/10，direct round-trip exit 0 |
| STT/Recording/Transcript/Facts API 生命周期 | 114/114 |
| 26-Agent 离线示例、克隆与对抗安全 | 78/78 |
| 临床校准计划、语义证据与部署专项 | 24/24 |
| JavaScript SDK | 91/91 |
| Python SDK | 95/95 |
| .NET SDK net8.0 / net10.0 | 77/77 / 77/77 |
| 发布验证器 | 5/5 |
| 静态部署预检 | 93/93 |
| PowerShell AST | 0 errors |

首次完整后端回归为 5,537 passed、22 failed。逐项复核确认：21 项来自 Agent 已迁移为受治理
本地执行后遗留的旧运行模式、旧输出夹具或旧契约计数；另 1 项是 MCP 网络异常在部分
`httpx` 异常类型下会形成空错误字符串。整改没有恢复旧外部 LLM 路径或放宽输出契约：
tenant readiness 现锁定 24 个本地基线和 2 个外部模型必需 Agent；triage 流式夹具补齐
运行时 trace 与逐字证据；DRG 按嵌套治理结构验证；证据绑定和跨字段对抗回放分别覆盖
30/60 与 110/340；MCP 离线失败始终返回非空且不含凭据的错误类型。相关 12 个文件先以
139/139 定向通过，再完成上述全量回归。JUnit 证据为
`reports/streams_checkpoint_phase_20260825/full_backend_remediated_junit.xml`，SHA-256
`c255e511e7f4d63babbf44af725f1dbdf2c3445c987329cab93db3da9004842f`。

真实 loopback WebSocket 使用两个独立 Uvicorn 和一个共享临时 SQLite WAL：第二 Worker 在
主 Worker 活跃时拒绝重复 interaction；主 Worker 在 640-byte 音频 `flush` 后被强制终止；
租约过期后第二 Worker 以新 session fence 恢复并结束。最终数据库为一份 640-byte 录音、
两条 configured audit、一条 ended audit，lease/checkpoint/chunk 均为 0。机器证据位于
`reports/streams_checkpoint_phase_20260825/multiworker_e2e_evidence.json`。

三 SDK 已统一为 JavaScript/.NET `1.0.0-beta.36` 与 Python `1.0.0b36`。5 个候选工件
已生成但未发布，版本/内容/哈希清单位于
`C:\codex-artifacts\release-b36-streams-checkpoint-recovery\release-candidate-b36-streams-checkpoint-recovery.json`。

## 与 Corti 当前公开能力的差距

Corti 当前公开的 [Streams API](https://docs.corti.ai/api-reference/streams) 支持实时双向
transcript/Facts、10 秒配置、64,000-byte chunk、`retain|none`、audio events、
`flush → flushed/delta_usage`、`end → usage/ENDED`，并说明 WebSocket 可以重新打开。
公开页也提到 reconnect failure，但没有公开未结束音频 checkpoint 的恢复协议、恢复计数或
跨 Worker fencing。因此本阶段只能证明 iCoDer 的本地恢复加固，不能声称已与 Corti 私有
恢复语义做过 head-to-head。

iCoDer 仍缺 Corti 已公开而本地候选未覆盖的 diarization、multichannel、`fast_init`、
session keyterms、完整语言/音频 profile、编码容器 audio events、真实 credit/billing 和
真实 FactsR/ASR 质量。Corti 文档也没有公开证明其实现了与 iCoDer 完全相同的加密
checkpoint schema、digest 或 session fence；这些只能标为 iCoDer 安全设计，不能反向当作
Corti 等价证据。

## 安全边界与下一门禁

- 受保护数据库保持 8,536,064 bytes、最后写入 `2026-08-22 17:16:22`、SHA-256
  `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- Windows 事件日志仍证明系统 Python 的 `pyarrow/arrow.dll` 曾以 `0xc0000005` 原生崩溃；
  本轮全量回归使用隔离临时数据库，并显式关闭 native MedCoder、本地 STT 和外部 LLM，
  30 分 23 秒内未复现原生崩溃。这证明安全测试路径稳定，不代表不安全 PyArrow 组合已修复。
- 验证结束后 Python/Uvicorn 进程与常用后端监听均为 0；三个 LLM 凭据变量在
  Process/User/Machine 范围均不存在。
- 未配置生产 checkpoint 清理调度器；目标平台仍须把现有 retention purge 机制接入计划
  任务，并完成 KMS 密钥轮换/灾备演练。
- 下一开发门禁仍是使用一枚新临时 Key 串行运行严格 26-Agent live-provider E2E 与 50 次
  CDI/Medical Coding 校准。即使通过，真实医院数据、独立临床 reviewer、许可/脱敏证明、
  Corti 同输入对照、云容量/SLA、法务、等保/监管与认证仍是外部门禁。
