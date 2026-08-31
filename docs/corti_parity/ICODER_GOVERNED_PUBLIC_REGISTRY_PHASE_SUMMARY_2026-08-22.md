# 受治理公共 Registry Provider 阶段总结（2026-08-22）

本阶段将 `clinical-trials` 与 `pubmed` 从“稳定失败关闭的外部 key”推进为可执行的固定官方 Provider。结论仍限定为开发上线候选：ClinicalTrials.gov 已完成一次无患者数据实网最小验证；PubMed 的完整离线合同通过，但没有合规的 NCBI 运营联系邮箱，因此没有伪造邮箱执行实网调用。

实现依据为 NCBI 官方 E-utilities ESearch/ESummary 合同和 ClinicalTrials.gov API v2。NCBI 使用指南说明软件请求应标识 `tool` 与联系人 `email`，无 API Key 时应保持低请求速率；ClinicalTrials.gov 的 `/api/v2/studies` 支持 `query.term`、分页和 `fields` 投影。来源：

- [NCBI E-utilities In-Depth](https://www.ncbi.nlm.nih.gov/sites/books/NBK25499/)
- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api)
- [ClinicalTrials.gov API migration](https://clinicaltrials.gov/data-api/about-api/api-migration)

## 完成内容

- 新增公共 Registry Provider，支持：
  - PubMed：固定 `eutils.ncbi.nlm.nih.gov`，执行 ESearch → ESummary，只返回 PMID、标题、期刊、发布日期、有限作者与固定 PubMed URL；
  - ClinicalTrials.gov：固定 `clinicaltrials.gov/api/v2/studies`，显式 `fields` 最小投影，只返回 NCT ID、标题、状态、阶段、研究类型、疾病、干预和固定记录 URL。
- Agent 只能提交 `query` 与 `max_results`，不能提交 URL、host、header、API Key、分页 token 或任意 Provider 参数。
- 两类查询均要求 `data_classification=deidentified`，并在出站前再次运行 PHI detector；检测到姓名、电话、地址、病案号、邮箱等内容时失败关闭，而不是将脱敏占位符发送到外部。
- 查询最长 500 字符、结果最多 20 条；Provider 响应按 256 KiB/512 KiB/1 MiB 边界读取，输出还要经过 Connector 自身最大字节合同。
- 复用受治理 transport：DNS 审核地址钉住 socket、精确 host、HTTPS/443、拒绝 redirect、不继承操作系统/Clash 代理、整体 timeout、Content-Type 校验和稳定错误码。
- NCBI 联系邮箱是非密钥部署配置 `ICODER_NCBI_CONTACT_EMAIL`；缺失或格式非法时 PubMed 返回 `CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED`，健康信息不回显邮箱。
- Cloud/CN 仍要求把 `eutils.ncbi.nlm.nih.gov`、`clinicaltrials.gov` 分别加入 `ICODER_CONNECTOR_EGRESS_ALLOWLIST`；否则 Provider 与健康状态均失败关闭。
- 输出明确标记非权威、需要临床人员复核；ClinicalTrials.gov 结果明确说明“登记不等于政府批准或安全/有效性证明”。

## 实网阶段发现并修复的问题

第一次 ClinicalTrials.gov 最小调用在打开连接前发现 pinned pool 启用了可选 HTTP/2，但本机没有 `h2`，会抛出 `ModuleNotFoundError`。当前 transport 明确使用两家 API 均支持的 HTTP/1.1，不再隐式依赖 `h2`。

第二次调用到达官方边缘但返回 403。对比同一 IP、host、HTTP/1.1 请求后，根因是自定义 transport 使用 Windows 系统证书上下文；改为 httpx 的隔离 Certifi 信任上下文并继续 `trust_env=False` 后，同一 pinned IP/SNI 请求返回 200。最终最小验证得到 1 条记录、正数总量和合法 `NCT########` 标识，正文未写入证据。

这次实网成功只证明 2026-08-22 当时的最小可达性和解析合同，不证明持续 SLA、数据完整性、临床质量或中国医院准入。

## 验证结果

| 范围 | 结果 |
|---|---:|
| 后端单元/安全/Corti 合同 | 197/197 |
| 共享数据库串行集成 | 77/77 |
| 应用启动 E2E | 6/6 |
| ClinicalTrials.gov 无患者数据实网最小验证 | 1/1 |
| JavaScript SDK `beta.22` | 41/41 |
| Python SDK `b22` | 48/48 |
| OpenAPI 漂移 | 通过，258 paths |

数据库集成覆盖持久 Connector → Executor → 公共 Registry → 固定 host HTTP → 输出投影 → 成功审计；HTTP 使用确定性 MockTransport，因此不把网络偶然性混入共享 SQLite 回归。实网验证独立使用真实 pinned transport，但没有写入数据库审计。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/governed_public_registry_phase_20260822/phase_evidence.json)。

## 仍未完成

- PubMed 尚缺有效运营联系邮箱后的真实最小验证；代码、解析、速率限制、失败关闭与两次 HTTP pipeline 已离线覆盖。
- DrugBank、POSOS 仍需要合法许可证和服务合同；Web Search 仍需要隐私 Provider、租户/平台双重 opt-in 和中国区域评估。
- 两个公共 Provider 的限速、熔断与状态仍为单进程；生产多 worker 需要 Redis 或等价共享状态。
- 该能力是文献/试验登记检索，不是临床诊断、治疗推荐、试验入组判断或权威编码依据。
- 医院安全、隐私、法务、临床 reviewer、云出口、等保/个保及认证门禁仍未通过。

## 下一开发优先级

下一项开发 P0 是把持久 Memory Connector 的 actor、用途、同意、retention 与 tenant 加密合同闭环；随后实现最小 delegated machine scope，使声明 `required_scopes` 的 Medical Coding 操作不再只能默认拒绝。PubMed 实网复测等待合法运营联系邮箱，不阻塞这些可在本地继续完成的工作。
