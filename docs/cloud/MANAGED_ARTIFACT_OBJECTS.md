# Agentic 托管 Artifact 对象安全合同

## 当前开发候选边界

迁移 `053` 为 A2A v1 Task-owned Artifact 增加两类持久资源：

- `a2a_artifact_objects`：租户、Context、Task、Artifact 四重归属的加密隔离对象；
- `a2a_artifact_download_grants`：最多 300 秒、单次消费、可随对象或 Context 删除的下载授权。

对象上传使用 A2A v1 `raw` 的规范 Base64 表达，解码后限制为 1 byte–5 MiB。当前完整扫描媒体白名单只有 `text/plain`、`application/json` 和 `application/pdf`；图片、音频、Office、压缩包、可执行文件及无法完整解析的内容失败关闭，不能被标为 clean。

## 状态机

```text
upload -> encrypted quarantine commit -> malware/content/DLP scan
                                     -> available
                                     -> rejected (encrypted payload erased)
```

隔离提交先于扫描，因此进程中断只会留下不可下载的 `quarantined` 对象。扫描决策与强制审计在同一事务提交；审计暂停或持久化失败时，对象不会转为可下载状态。

每个可用对象都满足：

1. 密文使用由服务端强密钥派生的独立 Fernet key；
2. 下载前重新解密并校验明文长度和 SHA-256；
3. 文件名是规范化 basename，禁止路径、控制字符和直接患者标识；
4. 声明 MIME、内容嗅探和扩展名一致；
5. EICAR 测试签名、PE/ELF、压缩包、PDF JavaScript/Launch/EmbeddedFile/OpenAction 等主动内容失败关闭；
6. PDF 必须可由严格解析器完整读取，禁止加密 PDF、超过 100 页或提取文本超过 1,000,000 字符；
7. DLP 检查中国居民身份证号、手机号、邮箱及显式姓名/住院号/病案号/医保卡号字段。

`deidentified` 对象发现直接标识符即 `rejected/blocked`。`clinical-sensitive` 可保存为 `available/restricted`，但每次下载都必须明确声明 `treatment`、`payment` 或 `healthcare_operations`；用途、授权和消费均写入最小必要审计，正文、文件名和下载 grant ID 不进入审计详情。

## API 生命周期

基路径：

```text
/api/v2/agentic/contexts/{contextId}/tasks/{taskId}/artifacts/{artifactId}/objects
```

- `POST`：上传并同步获得隔离/扫描终态；
- `GET`：列举安全元数据；
- `POST /{objectId}:authorize-download`：生成最多 300 秒的一次性授权及标准 A2A URL Part；
- `DELETE /{objectId}`：硬删除密文和全部未消费/已消费授权；
- `GET /api/v2/agentic/artifact-objects/download/{grantId}`：同一已认证 actor 原子消费授权后返回附件。

grant ID 是不可猜的一次性定位符，不是 bearer credential。下载请求必须携带正常的 Bearer 身份，并与授权时的精确 tenant、actor type 和 actor HMAC fingerprint 一致；OAuth/runtime actor 使用精确 `client_id`，不能由同一 owner 下的另一 Client 复用。下载响应强制 `no-store, private`、`Pragma: no-cache`、`Expires: 0`、`Referrer-Policy: no-referrer`、`nosniff`、`sandbox`、same-origin 资源策略和 attachment disposition。grant/object/tenant/actor/expiry 绑定、重放、过期和伪造 ID 均失败关闭。Context 不可逆删除显式先删授权和对象，再删 Artifact/Task/Context，不依赖 SQLite 是否开启 FK cascade。

Task/Artifact 读取不会生成长期或隐式授权 URL，只在 Artifact `metadata.managedObjects` 中投影对象状态，并增加 `urn:icoder:a2a:managed-artifact-object:v1` extension。调用方必须显式授权；授权响应中的 `part.url` 才是短期一次性 A2A File/URL Part。

## 运维要求

- Cloud 必须提供稳定、强随机的 `ICODER_SECRET_KEY`；密钥变化会使现存密文和 actor fingerprint 失效。
- 托管下载 URL 禁止携带 query secret。Uvicorn 访问日志删除所有 query/fragment 并遮盖 grant ID；Nginx 安全日志只记录 `$uri`，不记录可能含上一页面 query 的 Referer，且托管下载 location 关闭访问日志、缓存和响应缓冲。生产 APM/WAF/SIEM/支持工具仍必须验证同一隐私合同。
- 不得对 download GET 自动重试。三套 SDK 的专用下载方法只发送一次；应用重试必须先重新授权。
- 告警至少覆盖：隔离积压、scan error、infected/blocked 比率、完整性失败、授权重放、审计不可用和异常下载量。
- 清理任务必须删除过期 grant；对象生命周期继续由 Context retention 和显式删除控制。

## 仍未关闭的生产门禁

本实现是数据库对象存储和确定性扫描的开发模拟，不是生产 AV/DLP 认证：

- 真实区域对象存储、KMS/HSM、分片上传、断点续传、跨区复制和不可变备份；
- 独立维护的商业 AV、多引擎沙箱、OCR/图像/音频 DLP、Office/压缩包递归扫描；
- PostgreSQL 多副本下的一次性消费竞争、真实代理/APM 日志隐私验证、容量/P95/故障注入；
- 医院数据分级、用途授权、法务保留/删除政策和独立渗透测试；
- 供应商 SLA、病毒定义更新、误报处置及安全运营值守。

上述门禁必须在真实云、医院和独立 reviewer 环境完成，不能由本机绿色测试替代。
