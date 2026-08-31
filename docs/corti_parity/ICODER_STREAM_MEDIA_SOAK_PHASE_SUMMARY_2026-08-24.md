# iCoDer Streams 解码并发与格式/变异 Soak 阶段总结（2026-08-24）

## 阶段结论

Streams 的隔离媒体解码门已补齐进程级并发预算、排队超时、取消清理和无内容健康计数，
并通过五种真实容器与确定性畸形/变异样本的 100-case soak。合法媒体仍须在独立 ffmpeg
子进程内至少解码一帧，才能进入 ASR 或加密留存；容量用尽、超时、解码器缺失和畸形媒体
均使用固定错误失败关闭，不携带音频、转写或患者正文。

本阶段只使用合成静音，不使用真实患者音频、真实 STT 或真实 LLM。它证明 Windows 开发
环境中的合同、资源释放和可重复负向行为，不等于 Linux 容器沙箱、长期 fuzz、临床质量
或 Corti 托管环境的内部实现等价。

## 新增运行边界

| 能力 | 已验证行为 |
|---|---|
| 全局并发 | 每个 API 进程共享有界 semaphore；默认 2，可配置 1–16；测试证明最大活动数不越界 |
| 排队预算 | 默认 0.5 秒，可配置 0.05–5 秒；无法及时取得容量时返回 `AUDIO_VALIDATION_BUSY`、HTTP 503 / WebSocket 1013 |
| 取消清理 | 调用任务被取消时 kill 并 shield-wait 回收 ffmpeg，最终释放容量；计入 content-free `cancelled` |
| 健康观测 | `/api/health` 只返回模式、解码器是否可用、资源上限和状态计数，不返回路径、参数、音频、摘要或错误正文 |
| 凭据隔离 | 子进程仍只继承运行必需环境，不继承 LLM、Connector 或应用凭据；协议仅允许 `pipe`，stdout/stderr 丢弃 |
| 下游保护 | invalid/busy/timeout/unavailable 均不触达 ASR、录音留存、transcript、Facts 或成功 usage/end 终态 |

## 真实格式与变异 Soak

ffmpeg 在临时目录生成 0.25 秒静音 Ogg/Opus、WebM/Opus、MP3、FLAC、MP4/AAC。五种
基线均同时通过容器头检查与真实一帧解码；另有五个“首部看似合理但不可解码”的固定负向
样本，以及以种子 `20260824` 生成的 90 个确定性变异。

- 总计：**100/100** case 完成。
- 结果：69 valid、31 invalid、0 busy、0 timeout、0 unavailable。
- 并发：配置 4，观测最大活动数 4；结束时 active 0、ffmpeg 残留进程 0。
- 延迟：最大 419.405 ms，p95 343.563 ms（本机开发证据，不是生产 SLA）。
- 输出证据只包含格式名、字节数、SHA-256、状态、延迟和聚合计数，不保存生成的音频内容。

## 端到端与回归

| 验证面 | 结果 |
|---|---:|
| 后端 Streams/格式/decoder/租约/留存/云配置联合矩阵 | 137 passed |
| JavaScript SDK | 87 passed |
| Python SDK | 91 passed |
| .NET net8.0 / net10.0 | 72 / 72 passed |
| 迁移、升级/降级、shadow rebuild 与 ORM 漂移 | 19 passed |
| 发布候选验证器 | 5 passed |
| 静态部署预检 | 88 / 88 passed |

单 worker 真实 loopback WebSocket 证据包含三套 SDK 的合法 Ogg/Opus 会话及一个伪
`OggS/OpusHead` 负向会话；解码健康计数为 attempts 4、valid 3、invalid 1、active 0，
负向会话未触达 ASR 或留存。双 worker E2E 再次证明活跃冲突拒绝、主 worker 强制终止、
租约到期后的新 fence 接管和最终租约清零。测试结束后 Uvicorn 退出属于 runner 清理，
不是 `ROLLBACK` 或该 E2E 中途数据库崩溃。

三 SDK 已归一到 `1.0.0-beta.34`（Python `1.0.0b34`）。npm tgz、Python wheel、
.NET nupkg/snupkg 四个本地候选工件已生成 SHA-256 清单，`source_tree_state=dirty` 且
`publication.performed=false`，不得冒充由干净提交复现或已经发布的正式版本。

机器证据：[`reports/sdk_stream_media_soak_phase_20260824`](../../reports/sdk_stream_media_soak_phase_20260824/)。
候选清单：`C:\codex-artifacts\release-b34-stream-media-soak-final\release-candidate-b34-stream-media-soak-final.json`。

## 安全与外部门禁

- 受保护开发库保持 8,536,064 bytes、SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；源码 Alembic
  单 head 为 `056`。收尾审计中 Python/Uvicorn/ffmpeg、阶段临时目录和进程级 LLM key 均为 0。
- Docker CLI 在本机不可用，因而没有构建或扫描 Linux 镜像；ffmpeg 版本固定、SBOM、CVE、
  许可证、seccomp/AppArmor、cgroup CPU/内存/PID 配额仍需真实基础设施与安全/法务审批。
- 当前是 100-case 可重复回归，不是覆盖未知输入空间的模糊测试，也不是数小时/数日容量 soak。
- 未对 Corti 托管 Streams 发送同一五格式/畸形矩阵；公开文档合同对齐不能替代托管互操作。
- 真实中文医疗 ASR、方言/多人/噪声、多声道、diarization、audio events、Facts、计费、
  延迟和临床准确率仍需真实 Provider、合规医院数据和独立临床 reviewer。
