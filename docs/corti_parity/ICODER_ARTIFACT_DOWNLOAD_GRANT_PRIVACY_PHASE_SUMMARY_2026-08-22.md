# iCoDer Artifact 下载授权隐私阶段总结（2026-08-22）

> 声明：开发环境工程与安全验证，不代表临床生产批准，也不宣称 Corti 私有实现等价。
>
> 状态：开发切片通过；真实边缘、APM/WAF、PostgreSQL 多副本和独立安全 reviewer 门禁开放。

## 结论

本阶段关闭了托管 Artifact 下载授权的两个开发缺口：授权不再作为 query bearer token 进入 URL；下载必须由授权时同一已认证 actor 完成。URL 只携带短期、单次、不可猜的 grant ID，定位符本身不能下载对象。

审计同时发现 A2A Task list 游标接受非规范 Base64URL 签名尾字符别名。攻击者虽不能伪造新签名，但可把同一签名字节表示成另一字符串，破坏严格 token 唯一性和篡改检测。解码器现要求 payload 与 signature 均为无 padding 的规范 Base64URL 表达，并有确定性回归覆盖。

## 下载授权安全合同

- 授权记录精确绑定 `organization_id`、object、actor type、actor HMAC fingerprint、用途和过期时间。
- 用户 actor 绑定用户 ID；OAuth/runtime actor 绑定精确 `client_id`，不再退化为 owner user ID。同一 owner 下不同 API Client 不能共享授权。
- 下载路径为 `GET /api/v2/agentic/artifact-objects/download/{grant_id}`，必须携带正常 Bearer 身份和读取 scope。
- grant ID 仅接受规范小写 UUIDv4 形状；未知 tenant/actor/ID 统一失败关闭，不泄露对象归属。
- 原子消费条件包含 grant ID、tenant、actor type、actor fingerprint 和未消费状态；重放、过期、并发丢失更新均失败关闭。
- 消费和强制审计在返回字节前提交；响应使用 `no-store, private`、`Pragma: no-cache`、`Expires: 0` 和 `Referrer-Policy: no-referrer`。
- TypeScript、Python、.NET SDK 保留调用方 Authorization，下载不自动重试；一次消费失败后必须重新授权。

## 日志与边缘隐私

- Uvicorn access filter 在格式化前删除所有 request target query/fragment，并把托管下载路径中的 grant ID 替换为 `[grant-redacted]`。
- 两份 Nginx 配置使用 `$request_method $uri $server_protocol` 的安全 access log format，不使用 `$request` 或 `$request_uri` 记录请求目标，也不记录可能带入上一页面 query 的 Referer。
- 托管下载有专用 Nginx location：关闭 access log、缓存和响应缓冲，显式转发 Authorization，并设置有界连接/读取超时。
- 该验证只覆盖应用与仓库内 Nginx 配置。真实 ingress、CDN、APM、WAF、SIEM、错误聚合和支持工具仍必须证明相同隐私属性。

## 验证结果

- A2A 游标聚焦回归：**12/12**。
- A2A、Artifact、Agent Runtime、OpenAPI、部署预检、迁移与 schema 相关回归：**384/384**，24 条依赖或既有 `utcnow()` 弃用警告。
- TypeScript SDK `1.0.0-beta.24`：**43/43**，TypeScript build 通过。
- Python SDK `1.0.0b24`：**50/50**。
- .NET SDK `1.0.0-beta.24`：源码和合同测试已同步；本机无 `dotnet`，未声称编译或测试通过。
- OpenAPI：**269 paths**、**288 schemas**、842,053 bytes，`--check` 通过；旧 query 下载路径不存在，新 `{grant_id}` 路径存在。
- 静态部署候选预检：**64/64**。
- credential-shaped `sk-` token 文件：**0**；硬编码 LLM 凭据赋值文件：**0**。
- 所有后端测试均清空 LLM 凭据，使用 mock provider，禁止外部 LLM，并禁用 Windows 原生 MedCodER。

## 数据与运行边界

- 当前开发主库 `backend/data/icoder.db` SHA-256 仍为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。
- 本阶段没有 schema 变更，沿用已通过的 `041`→`053` 独立影子迁移证据；没有迁移、切换或写入当前开发主库。
- 没有启动 8000 端口、没有重启开发后端、没有调用真实 LLM 或 Corti 写接口。
- 本机无 Nginx、Docker 和 .NET CLI；Nginx 只完成静态合同验证，镜像/语法/运行态和 .NET 双目标验证继续由 Linux CI/外部环境完成。

## 与 Corti 的能力差距

Corti 公开 Core Concepts 仍注明 FilePart 尚未完全支持，公开材料未证明其私有托管下载授权、AV/DLP 或日志处理机制。因此，本阶段只能证明 iCoDer 的开发安全加固与中国医疗数据最小化设计，不能计为 Corti 私有实现的一比一复刻。

仍开放：

1. 生产区域对象存储、KMS/HSM、独立 AV/OCR/DLP、隔离 worker、重扫、容量、备份与灾备。
2. PostgreSQL 多副本下单次消费竞争、事务隔离和故障恢复。
3. 真实 ingress/CDN/APM/WAF/SIEM/支持工具的 URL、header 和错误日志隐私验收。
4. .NET 双目标 CI、Nginx 配置语法/镜像运行、SBOM、漏洞和供应链签名。
5. Corti 租户/第三方 A2A v1 互操作、医院数据用途授权、法务、认证、渗透测试和独立临床/安全 reviewer。

公开参考：

- [Corti Agentic Core Concepts](https://docs.corti.ai/agentic/core-concepts)
- [A2A v1 specification](https://a2a-protocol.org/dev/specification/)
- [A2A v1 changes](https://a2a-protocol.org/latest/whats-new-v1/)

机器证据目录：`reports/agent_hub/artifact_download_grant_privacy_phase_20260822/`。
