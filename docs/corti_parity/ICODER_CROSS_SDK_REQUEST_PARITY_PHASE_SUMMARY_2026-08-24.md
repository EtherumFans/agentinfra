# iCoDer 跨语言 SDK 请求控制与真实 E2E 阶段总结（2026-08-24）

## 阶段结论

本阶段关闭了上一轮仍开放的 Python 高层资源和 .NET 本机请求控制/实跑/打包差距，并用同一个临时后端完成 JavaScript、Python、.NET 三语言真实 HTTP 端到端。26 个 Hub 可见 Agent 均被读取并验证为可运行的开发上线候选；`note-completeness-agent` 在无真实 LLM、禁止外部模型和禁用原生 MedCoder 的条件下，以确定性中国病历章节规则成功运行。Facts 保持无凭据 503 失败关闭，Medical Coding 只返回明确 degraded/error，不产生伪临床成功。

该结论仍是开发环境工程候选，不代表 Corti 托管租户等价、临床质量通过或生产上线批准。

## 已完成实现

- Python `1.0.0b29` 新增 `compliance`、`runtime`、`patient_context` 高层资源，参数边界与当前 OpenAPI 对齐；公开入口、类型和 README 已同步。
- .NET `1.0.0-beta.29` 为所有公开 HTTP 资源方法增加 `ICoDerRequestOptions`：逐请求 timeout、0–10 次 retry、额外 headers/query，并保留现有 `CancellationToken`。
- .NET 普通 JSON、A2A v0.3/v1、A2A SSE、Run SSE、上传、字节下载、无正文和匿名认证请求使用同一控制管线；408/429/5xx 有界重试，401 刷新独立计数。
- 请求目标强制同源；Authorization、Cookie、Host、租户/组织、Content-Length/Type、协议头、幂等键及资源自有 query 冲突均失败关闭。签名或 bearer 单次下载不自动重试。
- JavaScript/Python/.NET smoke 统一验证确定性本地 Note Completeness 成功，而不是沿用旧的“无 LLM 必须失败”断言；Facts 和模型依赖路径的失败关闭不变。

## E2E 捕获并关闭的真实回归

1. 临时 OAuth client 缺少精确 Agent/用途委托，Agent Run 返回 403；脚本现只授权 `note-completeness-agent` + `treatment`。
2. 后端/OpenAPI 允许开发计费关闭时返回 `billing: {}`，.NET 错把 `billing.status` 声明为必填；现保留强类型结算字段，并允许空 billing 对象。
3. Note Completeness 已迁移为零网络确定性规则引擎，三语言 smoke 仍期待失败；现验证 `review_conclusion` 与 `completeness_score`。
4. Python SDK 已迁移到 PHI-safe `iCoDerAPIError`，示例仍捕获 `httpx.HTTPStatusError`；现按公开异常类型验证 503。

## 验证结果

| 验证 | 结果 |
|---|---:|
| JavaScript SDK | 74/74 |
| Python SDK | 78/78 |
| .NET net8.0 | 61/61 |
| .NET net10.0 | 61/61 |
| SDK 路由真实性 + 配置失败关闭 + 部署预检测试 | 54/54 |
| 发布候选校验器 | 5/5 |
| OpenAPI `--check` | current |
| 静态部署预检 | 83/83 |
| 单 API 进程三语言 E2E | passed |
| 双 API 进程 round-robin SSE 三语言 E2E | passed |

双进程 E2E 记录 15 次 SSE 连接尝试、12 次接受、6 次恢复、3 次 token 续期和 27 个事件；三语言均完成 OAuth client credentials、Hub 26/26、Agent Run、终态轮询、已完成 Run 的诚实取消、断线续传、A2A Context 脱敏 roundtrip、录音上传/读取/下载/删除和不发送音频的实时 STT ready/close。测试使用随机 loopback 端口和临时 SQLite，结束后关闭进程并删除临时运行目录。

## 发布候选产物

版本归一化为 `1.0.0-beta.29`，清单明确记录工作树为 `dirty` 且 `publication.performed=false`。

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `icoder-sdk-1.0.0-beta.29.tgz` | 65,288 | `ec8ad8653db68332954f7a3bcc204d12e1b83e0ed2a3bf22337788fdda4d164b` |
| `icoder_sdk-1.0.0b29-py3-none-any.whl` | 51,027 | `a9425672a589c039b86a4b51da322b01d275771ed6182a419ef38f8c7ed45604` |
| `iCoDer.Sdk.1.0.0-beta.29.nupkg` | 376,882 | `43a4bae024bfcd827f7d5e94d39c8cde4f749665adf197b5ed3a12196b6ded97` |
| `iCoDer.Sdk.1.0.0-beta.29.snupkg` | 80,776 | `3da85dcdbb8c08e01c33bf508d924cf9c49e0dee772936210a10c7413eb8c9a6` |

Python wheel 为 30 个条目且包含 Compliance/Runtime/Patient Context；NuGet 为 net8.0/net10.0 双目标且不含源码、`bin` 或 `obj`；npm tarball 为 54 个发布文件。所有产物仅保存在 `C:\codex-artifacts`，未发布到外部 registry。

## 与 Corti 当前公开 SDK 的差距

Corti 官方 [.NET 概览](https://docs.corti.ai/sdk/dotnet/overview) 和 [.NET API Reference](https://docs.corti.ai/sdk/dotnet/reference) 表明其每个 HTTP 方法均接受 RequestOptions，支持 408/429/5xx retry、timeout、headers/query，并额外允许逐请求 `BaseUrl`、`HttpClient` 和 `AdditionalBodyProperties`。iCoDer 已对齐可安全复用的 timeout/retry/headers/query/cancellation 与全 HTTP 方法覆盖，但有意不开放逐请求跨源 BaseUrl、自定义 HttpClient 或任意 body merge：医疗 tenant、身份、协议和签名字段必须由资源层拥有，不能由调用方覆盖。

仍开放的 SDK/托管差距：

- 服务端没有可恢复音频 cursor；发送音频后断线只能失败关闭。
- 尚未与 Corti 托管租户做双向 SDK/Agent/A2A 互操作。
- Corti 私有预览 Agent SDK composition 无公开可复测入口。
- Corti .NET 覆盖 .NET Framework 4.6.2+/NET Standard 2.0；iCoDer 当前候选只验证 net8.0/net10.0。
- Linux CI、真实代理/自定义网络栈、PostgreSQL 多副本和生产 WebSocket/SSE 仍需外部环境验证。

## 不得提升的外部门禁

本阶段没有使用真实 LLM、真实患者数据或真实音频，也没有启动浏览器。真实区域 LLM/STT、临床正确性、合法 ICD/DRG-DIP 资产、医院 HIS/EMR、患者授权、对象存储/AV/OCR/DLP/KMS、Docker/SBOM/漏洞扫描、容量/SLA、法务/等保/认证和独立临床 reviewer 仍保持未通过。

最终检查无 E2E/Uvicorn 子进程和 Python 监听，`ICODER_CREDENTIAL_LLM`/`DEEPSEEK_API_KEY` 在进程、用户和机器环境中的长度均为 0；受保护开发库 `backend/data/icoder.db` 仍为 8,536,064 bytes，SHA-256 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

机器可读证据：[`phase_evidence.json`](../../reports/sdk_cross_language_request_parity_phase_20260824/phase_evidence.json)。
