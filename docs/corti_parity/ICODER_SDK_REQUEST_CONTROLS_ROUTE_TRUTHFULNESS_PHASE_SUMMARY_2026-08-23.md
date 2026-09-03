# iCoDer SDK 请求控制、真实路由与发布物收敛阶段总结

日期：2026-08-23  
范围：开发环境；不启动浏览器/Uvicorn，不启用真实 LLM、原生 MedCodER 或本地 STT，不使用用户披露的 DeepSeek Key。

## 本阶段结论

本阶段关闭了 Corti 官方 SDK 请求级控制、page-number 资源分页、SDK 公共路由真实性和发布物陈旧文件四类开发环境差距。JavaScript/Python SDK 的普通 REST、A2A v0.3/v1、Run SSE 和托管 Artifact 下载现在都能接受有界的逐请求超时、取消、附加请求头与附加查询参数；资源自有协议头、租户/身份头、签名 token 和分页字段不能被调用方覆盖。

这不是 Corti 托管服务或临床质量等价证明。.NET 本机工具链、Corti 托管租户互操作、真实模型/STT/医院质量、生产账单与云基础设施仍保持开放。

## 完成项

1. Billing `/transactions` 与 `/run-settlements` 改为真实 `page`/`page_size` 分页：作用域内 `count(*)`、稳定排序、offset/limit 和权威 `total`；旧 `limit` 调用继续映射为第一页。
2. Expert SDK 统一到真实只读 `/api/v1/experts`、单卡、MCP servers 和 registry reconcile；列表新增有界、不区分大小写的 name/description 搜索。
3. 删除没有后端公开路由的 JavaScript/Python `ReviewsResource`、JavaScript `MarketplaceResource` 和 STT `punctuate()`；增加 SDK 路径字面量与 FastAPI/OpenAPI/显式 lifespan 路由的自动对账测试。
4. JavaScript `iCoDerRequestOptions` 与 Python `RequestOptions` 覆盖 timeout、retry、caller cancellation、headers、query params。绝对 URL、路径内 query/fragment、身份/租户头覆盖、资源查询字段碰撞和 CR/LF 注入均失败关闭。
5. A2A/Run SSE 的流式 POST 不自动重放；非零逐请求 retry 明确拒绝。Task Subscribe 等 GET 流仍由显式 resilient API 管理重连，避免两套重试策略叠加。
6. 一次性 Artifact 下载只接受与 SDK base URL 同源、无凭据/fragment、固定 managed download 前缀的服务端授权 URL；下载强制 `maxRetries=0`。
7. README、操作手册、教程和两份 Postman collection 不再宣传 `/api/reviews`、旧 Marketplace 或 `/api/agents` 幽灵路由。两份 collection 共 9 个请求，均已与当前 OpenAPI 路径匹配。
8. JavaScript 构建现在先清理固定包内 `dist` 再运行 `tsc`，防止删除的资源被旧编译产物重新发布；Python wheel 在清理陈旧 `build/lib` 资源后重建并检查成员。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| JavaScript SDK 全量 | 74 passed / 0 failed |
| Python SDK 全量 | 75 passed / 0 failed |
| Backend Billing + Expert + SDK route truthfulness | 20 passed / 0 failed |
| SDK route truthfulness 独立复跑 | 2 passed / 0 failed |
| 部署静态预检 | 83 passed / 0 failed |
| Postman → OpenAPI 路由对账 | 9/9 + 9/9，0 missing |
| Backend 默认安全全量 | 5263 passed / 20 skipped / 11 deselected / 0 failed（1834.54s） |

发布物：

- JavaScript `icoder-sdk-1.0.0-beta.28.tgz`：54 files，Reviews/Marketplace members 0，SHA-256 `99d61330761a513cf34e3db18c3edf2b10ddcb784a1fb409733c6ceafb7ef13c`。
- Python `icoder_sdk-1.0.0b28-py3-none-any.whl`：27 files，Reviews/Marketplace members 0，SHA-256 `35c60ee955ccff17e9c3863b369f7741d01f3f361258fb278f60ccec51e2edde`。
- 部署预检 JSON：83/83，SHA-256 `8129095aa9c43b633aca3e7ccb907e9de2c6bfa2ac3aa8d44ff9a2ea09df67b8`。

## 相对 Corti 的剩余差距

- Python SDK 尚无 JavaScript 已有的 Compliance、Runtime 和 Patient Context 高层资源；.NET 的同轮逐请求控制与本机打包/运行证据未完成。
- Corti 托管 API/SDK 的真实租户双向互操作、错误兼容细节、流式断线/超时行为仍需外部租户测试。
- iCoDer Billing 仍是开发账本与 Run settlement，不是 Corti 项目级余额、真实支付、发票、退款或财务对账。
- Agent Hub 的 26/26 是结构性上线候选，不是 26/26 真实模型语义或临床质量通过；新鲜、非 mock、签名的多 Agent 质量 bundle 仍未完成。
- 真实中国区域 LLM/STT、医院 HIS/EMR、权威 ICD/DRG/DIP 数据许可、独立临床 reviewer、等保/法务/云多副本/SLA 均属于外部门禁。
