# iCoDer 托管 Artifact 对象阶段总结（2026-08-22）

> 声明：开发环境工程验证，不代表临床生产批准，也不宣称 Corti 私有实现等价。
>
> 日期：2026-08-22
>
> 阶段：Agentic v2 / A2A v1 托管 Artifact 对象
>
> 状态：开发切片通过；生产对象存储、独立安全扫描和外部上线门禁开放

## 结论

本阶段关闭了上一阶段“只有内联 FilePart/URI，没有可治理对象生命周期”的开发环境缺口。iCoDer 现在可以在 Context、Task、Artifact 三重归属下上传最多 5 MiB 的文本、JSON 或 passive PDF；对象先以密文进入隔离区，再执行格式、恶意内容和 DLP 检查，只有通过策略的对象才能获得短时、用途绑定、一次性下载授权。

这是数据库承载的开发模拟，不是生产对象存储。Corti 的公开 Core Concepts 仍注明 FilePart 尚未完全支持，公开材料也没有证明 Corti 提供同等托管 AV/DLP 流水线。因此，本阶段应记为 iCoDer 的安全加固与中国医疗场景适配，不能宣称与 Corti 私有托管实现一比一等价。

## 已实现

- Alembic `053` 新增 `a2a_artifact_objects` 与 `a2a_artifact_download_grants`，对象通过复合外键精确绑定组织、Context、Task 和 Artifact。
- 文件名、载荷和可识别元数据均受约束；载荷以独立派生的 Fernet key 加密，数据库不保存明文文件。
- 上传采用“先提交隔离态，再扫描，再原子记录终态和审计”的顺序；审计不可写时保持安全隔离或失败关闭。
- 每个 Artifact 最多 16 个对象；单对象解码后最多 5 MiB；Base64 必须规范化并含正确 padding。
- 只接受 `text/plain`、`application/json`、`application/pdf`，并验证声明类型、扩展名和内容 sniffing 一致。
- EICAR 摘要、PE/ELF、ZIP/RAR/7z、媒体伪造和路径穿越式文件名均拒绝。
- PDF 使用严格解析，拒绝加密 PDF、超过 100 页、超大提取文本，以及 JavaScript、Launch、OpenAction、EmbeddedFiles、AA、AcroForm 等主动内容。
- DLP 识别中国居民身份证号、手机号、邮箱和姓名/住院号/病案号/医保卡号等显式患者标识；只保存发现类型和数量，不保存命中值。
- `deidentified` 声明出现直接标识时拒绝并擦除密文；`clinical-sensitive` 命中时可保持受限可用，但下载必须声明 `treatment`、`payment` 或 `healthcare_operations` 用途。
- 下载 URL 只含不可猜的 grant ID，不含 query secret；消费必须由授权时同一 tenant 和精确 actor 完成。actor ID 只保存 HMAC fingerprint，OAuth/runtime actor 使用精确 `client_id`，同一 owner 下另一 Client 不能复用；授权 1–300 秒且一次性消费，伪造、跨 actor、过期、重放均失败关闭。
- 下载响应使用 `private, no-store`、`attachment`、`nosniff` 和 sandbox CSP；消费与审计在返回字节前提交。
- 删除会硬删除对象和授权；Context 删除会先删除所有相关 grant/object，不依赖隐式级联。
- Artifact 投影公开安全的 `managedObjects` 摘要和扩展 URI，不公开 ciphertext、actor fingerprint、token 或 DLP 命中值。
- TypeScript、Python、.NET SDK 均提供上传、列表、授权、一次下载和删除入口；下载方法明确禁用自动重试。

## API 合同

- `POST/GET /api/v2/agentic/contexts/{context}/tasks/{task}/artifacts/{artifact}/objects`
- `POST /api/v2/agentic/contexts/{context}/tasks/{task}/artifacts/{artifact}/objects/{object}:authorize-download`
- `DELETE /api/v2/agentic/contexts/{context}/tasks/{task}/artifacts/{artifact}/objects/{object}`
- `GET /api/v2/agentic/artifact-objects/download/{grant_id}`

上传要求活跃且未过期的 Context、持久 Task-owned Artifact 和写 scope；读取、授权和删除要求精确租户归属与相应 scope。API 请求体上限针对该路径单独限制，避免扩大其它接口攻击面。

## 验证

- 完整 A2A、Artifact、Agent Runtime、迁移和 schema 回归：**384/384**；24 条均为依赖或既有 `utcnow()` 弃用警告。
- JavaScript SDK：**43/43**，TypeScript build 通过。
- Python SDK：**50/50**。
- `.NET` 源码与合同测试已更新；本机没有 `dotnet` CLI，未声称编译或测试通过。
- OpenAPI：**269 paths**、**288 schemas**、842,053 bytes，重新导出并通过 drift check。
- 静态部署预检：**64/64**。
- 密钥扫描：使用 token 边界约束的工作区扫描未发现 credential-shaped `sk-` 长令牌，未发现硬编码 LLM 凭据赋值。
- 本阶段所有后端测试均清空 LLM 凭据、使用 mock provider，并禁用外部 LLM 与 Windows 原生 MedCodER；没有调用真实 LLM、Corti 写接口或浏览器自动化。

## 迁移安全

当前开发源库仍保持 Alembic `041`，本阶段没有迁移、切换或重启该后端。独立影子候选已升级到单 head `053`：

- 58 张既有表、6,090 行源数据全部复制并保持指纹一致；
- 候选 69 张表、68 张 ORM 表和 992 列零 schema 漂移；
- 候选完整性为 `ok`，外键违规为 0；
- 源库前后 SHA-256 均为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
- 6 个停用隔离租户只承载源库 827 条历史孤儿引用，不证明真实医院或租户归属；
- `cutover_performed=false`。

## 与 Corti/A2A 的边界

- A2A v1 Part 可表示 Base64 `raw` 或 `url`，并携带 `filename`、`mediaType`；iCoDer 的下载授权投影保持标准 URL Part 形状。
- Corti 公开 Core Concepts 描述 Task 归属 Artifact 和流式 Artifact，但同时标注 FilePart 尚未完全支持。
- 未发现 Corti 公开文档对托管上传、病毒扫描、DLP、一次性下载或删除链作出可验证承诺。因此这些能力不进入“已验证 Corti 等价”计数。

公开参考：

- [Corti Agentic Core Concepts](https://docs.corti.ai/agentic/core-concepts)
- [A2A v1 specification](https://a2a-protocol.org/dev/specification/)
- [A2A v1 changes](https://a2a-protocol.org/latest/whats-new-v1/)

## 仍开放的差距

1. 当前使用数据库密文模拟对象存储；生产需要区域化对象存储、KMS/HSM、独立 AV/OCR/DLP、隔离 worker、容量/保留/恢复和灾备验证。
2. 托管下载已改为 query-secret-free、同 actor 认证的 grant 路径；Uvicorn 和两份 Nginx 配置已静态验证不记录 query，下载 location 关闭访问日志。真实生产反向代理、APM、WAF、SIEM 和支持工具仍须执行日志隐私验收。
3. 只有 text/JSON/passive PDF；图像、音频、DICOM、Office、OCR 和压缩包均未作为安全可下载格式开放。
4. 扫描器为开发内置规则，不替代独立恶意软件引擎、规则更新、隔离重扫、威胁情报和专业 DLP。
5. `.NET` CI、PostgreSQL 多副本下的一次性消费竞争、对象存储一致性和生产队列仍需外部环境。
6. Corti 私有租户或独立第三方 A2A v1 客户端互操作、26-Agent 真实模型质量、医院接口、患者权威授权、云、法务、认证和独立临床验收仍未通过。
7. 当前开发数据库仍在 `041`；只有完成 6 个隔离租户归属复核、维护窗口、备份恢复演练和审批后，才能受控切换到 `053`。

基础对象链证据目录：`reports/agent_hub/managed_artifact_object_phase_20260822/`。下载授权隐私加固的当前证据见 `reports/agent_hub/artifact_download_grant_privacy_phase_20260822/` 和 [`ICODER_ARTIFACT_DOWNLOAD_GRANT_PRIVACY_PHASE_SUMMARY_2026-08-22.md`](ICODER_ARTIFACT_DOWNLOAD_GRANT_PRIVACY_PHASE_SUMMARY_2026-08-22.md)。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-22 | 下载改为 query-secret-free、同 actor 认证 grant；访问日志最小化；修复 A2A 游标非规范 Base64URL 别名 | 下载授权隐私与协议规范化审计 |
| 2026-08-22 | 记录托管 Artifact 对象、扫描、DLP、一次性下载、SDK、迁移和外部门禁证据 | Agentic v2 / A2A v1 对象生命周期差距整改 |
