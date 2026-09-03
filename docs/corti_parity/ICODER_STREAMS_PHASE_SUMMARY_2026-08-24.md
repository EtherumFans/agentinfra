# iCoDer Corti-compatible Streams 阶段总结（2026-08-24）

## 阶段结论

iCoDer `/api/v2/tools/streams/{interactionId}` 已从过时、可误报能力的开发实现收敛为可审计的上线候选切片：真实租户与 scope 鉴权、严格配置、中文单声道最终转写、受治理 Facts、flush/delta usage/end、可选加密留存和三语言 SDK 均已落地，并用真实 loopback WebSocket 完成端到端验证。

本阶段没有使用真实患者数据、真实音频、真实 ASR 或真实 LLM，因此只证明协议、鉴权、隔离、留存和失败真实性；不能据此宣称与 Corti 临床质量或生产 SLA 等价。

## 当前合同与安全边界

| 能力 | 当前实现 |
|---|---|
| 身份与租户 | access token 或 `client_credentials`；机器 token 必须有 `streams` scope；`tenant-name` 必须匹配组织 ID/slug；环境必须是 `cn/eu/us` 并与部署环境一致 |
| 配置 | 10 秒内提交；Pydantic `extra=forbid`；`CONFIG_ACCEPTED` 返回 UUID `sessionId` 和解析后的 `configuration` |
| 音频 | 单块最多 64,000 bytes、单会话最多 32 MiB；buffer 在退出时覆盖；交互 UUID 在同租户/主体内防重 |
| 转写 | 只输出真实 ASR 的 final transcript；单声道未分离 speaker 为 `-1`；时间单位为秒；ASR 不可用时返回稳定错误，不生成假文本 |
| Facts | 只通过平台受治理 gateway；mock/degraded 响应失败关闭；输出 UUID、去重并可与持久化记录保持同一 ID |
| flush/end | flush 依次输出剩余 transcript/Facts、`flushed`、`delta_usage`；end 依次输出剩余结果、`usage`、`ENDED` 并关闭 |
| usage | 本地当前实际扣费 credits 为 0；Provider token/cost 只进入审计遥测，不使用虚构换算公式 |
| 留存 | `retain` 写入加密录音与 interaction artifact，`none` 不落盘；E2E 通过租户 REST API 读取留存结果 |
| 失败闭合 | diarization、multichannel、非 0 participant channel、audio events、`fast_init`、keyterms、非中文及发送音频后重连均明确拒绝 |

## 验证证据

- Streams/ambient 定向合同：**21/21**。
- Streams + STT 扩大后端回归：**62/62**。
- JavaScript SDK 全量：**86/86**。
- Python SDK 全量：**90/90**。
- .NET SDK：net8.0 **71/71**，net10.0 **71/71**。
- 静态部署预检：**85/85**，新增 Streams 真实鉴权、严格配置、容量、受治理 Facts、三 SDK 与隔离 E2E 门禁。
- 三语言真实 loopback WebSocket：JavaScript、Python、.NET 各 1 个租户会话；共 3 次 configured/ended 审计；JavaScript `retain` 生成 1 个 interaction 和 1 条加密录音并通过租户 API 读取，Python/.NET `none` 未生成额外 artifact。
- 机器证据：[`e2e_evidence.json`](../../reports/sdk_streams_phase_20260824/e2e_evidence.json)、[`deployment-preflight.json`](../../reports/sdk_streams_phase_20260824/deployment-preflight.json) 和 [`phase_evidence.json`](../../reports/sdk_streams_phase_20260824/phase_evidence.json)。

E2E 在全新临时 SQLite 上执行 Alembic head，使用临时签名密钥和真实注册/租户 token；显式清除 LLM key，关闭 mock LLM、外部 Provider、本机 STT 和原生 MedCoder。测试结束后 Uvicorn 与临时目录被回收；受保护开发库保持 8,536,064 bytes 和原 SHA-256。

## 候选制品

三套 SDK 已统一为 `1.0.0-beta.31`（Python `1.0.0b31`）。本机候选清单为 `C:\codex-artifacts\release-candidate-b31-streams-final.json`，如实记录源码 revision `4fc31b3c012c49d09c6b3b01d3c67e25049efe98`、工作区 `dirty` 且 `publication.performed=false`。

| 制品 | 字节 | SHA-256 |
|---|---:|---|
| `icoder-sdk-1.0.0-beta.31.tgz` | 69,693 | `0a9a17ec4f127e089c14f36287ab38ce8c8bbbb4f30995280ec1dbc8a95e4fa4` |
| `icoder_sdk-1.0.0b31-py3-none-any.whl` | 56,121 | `53fcd7763c2b34d9f0e6369ca1765a8637cd1f487915f6378d849b46fc5974d0` |
| `iCoDer.Sdk.1.0.0-beta.31.nupkg` | 414,552 | `31f6297e1aa83ed1617bc97ec9007189f1b582823bba8552f1f755cc5c93c225` |
| `iCoDer.Sdk.1.0.0-beta.31.snupkg` | 88,244 | `abee8529447684d92a8aef4b61e172c901ac202f57241947fcee1064a1c26de0` |

## 对 Corti 当前公开能力的差距

Corti 当前公开的 [Streams API](https://docs.corti.ai/api-reference/streams) 要求带 interaction UUID、环境、tenant 和 token 的 WSS 会话，并公开了当前配置、transcript/Facts、flush、usage/end、audio events 与留存语义；[Streams STT 指南](https://docs.corti.ai/stt/streams) 和 [STT release notes](https://docs.corti.ai/release-notes/stt) 还描述了多人、多声道、diarization、语言和持续演进的行为。

当前仍未关闭：

- 真实中国区域医疗 ASR/LLM 的识别与 Facts 准确率、方言/噪声/远场/长音频、首结果延迟、成本、并发容量和 SLA；
- diarization、multichannel、多 participant channel、audio events、`fast_init`、session keyterms 和 Corti 多语言层级；
- Corti credits/provider billing 的真实对账；当前 0 credits 是 iCoDer 本地实际扣费，不是 Corti 计价仿真；
- 未完成 interaction 的音频/转写状态持久恢复和生产消息/对象存储；跨 API Worker 的 active-session 唯一性、租约 fencing 与崩溃后新会话接管已由后续 [`ICODER_STREAMS_MULTIWORKER_LEASE_PHASE_SUMMARY_2026-08-24.md`](ICODER_STREAMS_MULTIWORKER_LEASE_PHASE_SUMMARY_2026-08-24.md) 关闭；
- Corti 托管租户及其官方 SDK 的双向互操作与协议漂移监控；
- 医院授权数据集、法务合规、独立临床 reviewer、安全认证、生产网络与云区域验收。

这些项目需要真实 Provider、医院、云基础设施或独立 reviewer，不能用合成字节和本地 mock 提升为“已上线”。
