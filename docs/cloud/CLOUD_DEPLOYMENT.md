# iCoDer Cloud Deployment Architecture (2026-06-27)

> **Status**: Design intent (Phase 1 cloud-flip). Production deployment targets
> `https://{tenant}.{region}.icoder.cloud`. Local development remains
> `python -m uvicorn app.main:app --port 8000` + `docker compose -f
> docker-compose.local-dev.yml up`. See also: [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md),
> [MULTI_REGION.md](MULTI_REGION.md), [CLOUD_INTAKE_TEMPLATE.md](CLOUD_INTAKE_TEMPLATE.md).

This document is an architecture target, not evidence of a live production
environment. A cloud process fails closed unless the hosted URL, region,
tenant/API-client identity, strong `ICODER_SECRET_KEY`,
`ICODER_PHI_ENCRYPTION_KEY`, and DB-backed RunTrace profile are supplied.
LLM credentials enter only through `ICODER_CREDENTIAL_LLM`/CredentialVault;
`LLM_API_KEY` is not a supported deployment secret ingress.

MedCodER 的 BGE/FAISS 原生栈也不得进入主 API 进程。Cloud 模式必须提供独立检索服务的 `MEDCODER_RETRIEVER_URL` 与 32–512 字符的 `MEDCODER_RETRIEVER_TOKEN`，URL 必须为无内嵌凭证、query 或 fragment 的绝对 HTTPS 地址，并保持 `MEDCODER_RETRIEVER_ALLOW_HTTP=false`。缺少上述任一项、索引/模型版本不匹配、readiness 降级或响应契约异常时，应用失败关闭，不能静默回退到 API 进程内加载原生模型。服务凭证必须由 KMS/Secret Manager 注入，不能提交到 `.env`、镜像或报告。

DrugBank、POSOS 和 Web Search 同样不得由 Agent 自由直连。它们只通过固定 HTTPS 企业适配网关、Vault 凭证、精确 egress allowlist 和去标识化 Connector 执行；Web Search 另需平台/租户双重 opt-in。部署合同见 [EXTERNAL_REGISTRY_GATEWAYS.md](./EXTERNAL_REGISTRY_GATEWAYS.md)。开发环境真实 TCP fixture 只证明 iCoDer 合同与安全门禁，不代表已取得商业许可、供应商 DPA 或临床质量证据。

持久 Memory 的语义检索同样在隔离服务中运行。Cloud 必须配置 `ICODER_MEMORY_SEMANTIC_URL`、32–512 字符的 `ICODER_CREDENTIAL_MEMORY_SEMANTIC`，并设置 `ICODER_MEMORY_SEMANTIC_REQUIRED=true`；服务主机必须在精确 egress allowlist 内。请求只含再次脱敏的文本，不含租户、用户、患者或 consent 标识，向量随 Memory 行加密。当前 consent 仅为登录用户自助授权，不是患者权威授权，患者 PHI 存储保持失败关闭。完整合同见 [SEMANTIC_MEMORY_SERVICE.md](./SEMANTIC_MEMORY_SERVICE.md)。

## 1. Strategic Positioning

iCoDer v1 ships as **托管云 SaaS (Corti-style)**, 不是医院私有化部署:

| Layer | Concept | Mapping |
|---|---|---|
| **Environment** | 地理 / 合规区域 | EU / US / CN |
| **Tenant** | 客户 (医院 / ISV) | 一个医院 = 一个 Tenant |
| **API Client** | 接入凭证 | backend-service (server-to-server) vs ROPC embedded (browser) |

三层对应 Corti 的 environment / tenant / API client 模型。医院 HIS/EMR 通过 API Client
集成,不直接接触底层控制面。

## 2. Three-Layer Model

### 2.1 Environment (地理 / 合规区域)

每个 Environment 是一个独立的控制面 + 数据驻留边界:

| Environment | Regions (初始) | Compliance framework | 启用日期 |
|---|---|---|---|
| `eu` | `eu-frankfurt`, `eu-stockholm` | GDPR + EHDS | TBD |
| `us` | `us-virginia`, `us-oregon` | HIPAA + HITECH | TBD |
| `cn` | `cn-hangzhou`, `cn-beijing` | 数据安全法 + 个人信息保护法 + 医疗数据规定 | TBD |

Environment 配置 declarative 在 [regions.yaml](../../deploy/cloud/regions.yaml)。

### 2.2 Tenant (医院 / ISV)

- **Tenant 创建**: 通过 `CLOUD_INTAKE_TEMPLATE.md` onboarding 流程,经 iCoDer
  平台运维团队审批。
- **Tenant 隔离**: 每个 Tenant 拥有独立 database schema + LLM credential vault +
  audit log partition。
- **现有 `Organization` schema** (在 `backend/app/api/organizations.py`) 升级为
  `Tenant` 的实现细节之一;Phase 1 文档口径用 Tenant,代码继续用 Organization
  直到 Phase 2 重命名。

### 2.3 API Client (接入凭证)

两类 client,与 Corti 同款:

| 类型 | 用途 | 凭证 | 典型用户 |
|---|---|---|---|
| **backend-service** | HIS / EMR 后端集成 | `client_id` + `client_secret` (server 持有) | 医院信息科自研集成 |
| **ROPC embedded** | Web Component / 浏览器嵌入 | ROPC flow (username/password → short-lived token) | Web 端医生工作站 |

详细规范见 [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md)。

## 3. Region Routing & Data Residency

详细 region → data-residency 映射、failover 语义、audit-log 复制规则见
[MULTI_REGION.md](MULTI_REGION.md)。

**核心约束**: Tenant 数据 (encounters / reviews / gold_cases / m2a traces) 物理驻留在
Tenant 所属 Environment 的 region 内,**绝不跨 Environment 复制**。LLM 调用路由
到同 region 的 inference endpoint,token + 推理都不出 region。

## 4. PHI Redaction-at-Edge Contract

iCoDer **不**承诺"数据不出院" (那是私有化时代的叙事)。新承诺:

> 原始 PHI (姓名 / 身份证号 / 联系方式 / 地址) 在 iCoDer Agent 处理前**强制脱敏**;
> 脱敏样本进入云审计通道;只有脱敏后的 diagnosis / procedure / evidence 字段上送
> 至 LLM Inference。原始 PHI 留存在医院 HIS/EMR 内,iCoDer 不持有原始 PHI。

- `ICODER_PHI_REDACTION_MODE=edge` (cloud default) — 强制
- `ICODER_PHI_REDACTION_MODE=disabled` — 仅 local dev 允许
- Redaction 引擎实现位置: `backend/app/services/phi_redaction/` (M3 spec, 已实装,
  本次 cloud-flip 仅 reframe 用途)
- Audit log 仅记录 "this encounter had X PHI tokens redacted",不记录原始 PHI

## 5. SLA & Reliability

| Metric | Target (GA) | 备注 |
|---|---|---|
| Availability | 99.5% (single region) / 99.9% (active-active, future) | Phase 1 单 region |
| P50 latency (coding run) | ≤ 8s (BGE-M3 cached) / ≤ 60s (cold) | MedCodER 5-stage full |
| P99 latency (coding run) | ≤ 120s | 含 LLM call timeout |
| Data durability | 99.999999% (S3-compatible) | 11 9s |
| Recovery time (RTO) | ≤ 4h (single region) / ≤ 30min (active-active) | |
| Recovery point (RPO) | ≤ 1h (single region) / ≤ 1min (active-active) | |

## 6. Local Development (唯一受测开发路径)

### 6.1 RunTrace retention and resume cursors

- `ICODER_RUN_TRACE_EVENTS_TTL_DAYS` defines the public SSE replay/cursor
  window; the deployment template defaults to 90 days.
- `ICODER_RUN_HISTORY_TTL_DAYS` must be greater than or equal to the trace
  window. Cloud startup/purge tooling fails closed when the relationship or
  either value is invalid.
- The purge only targets terminal Runs, records `trace_events_purged_at` and a
  cumulative count on RunHistory, and writes a `retention.purge` audit event.
- A cursor absent before any purge returns 409. After a recorded purge, an
  unavailable cursor or trace returns 410 with a sanitized error code,
  retention days and purge timestamp. SDKs must not retry 410.
- The operator entry point is dry-run by default:

```bash
cd backend
python -m scripts.purge_retention
python -m scripts.purge_retention --execute
```

Production must schedule the execute form as a singleton CronJob (or an
equivalent managed scheduler) after a successful dry run. The scheduler,
database backup, alerting and execution evidence remain deployment-owned;
this repository does not claim that a production CronJob is running.

### 6.2 Run SSE operational metrics

`GET /api/metrics` returns a JSON snapshot for exactly one API process. Cloud
deployments must inject a 32–512 character `ICODER_METRICS_BEARER_TOKEN` from
KMS/Secret Manager and scrape every worker/pod directly; querying through a
round-robin service does not produce an aggregate. A platform-admin JWT is an
interactive fallback, not the recommended monitoring credential. Responses
are `Cache-Control: no-store`.

The `run_sse` object contains only fixed-enum or numeric values: connection
attempts/accepts, active and resumed connections, emitted data events and
heartbeats, rejection and close reasons, trace-token renewal outcomes, bounded
P50/P95/P99 resume recovery and stream duration windows. It never accepts or
exports run, organization, user, cursor, token, event-name or clinical labels.
Unknown labels collapse to `other`/`other_failure`.

The snapshot evaluates three deployment-tunable alert candidates with the
current reference thresholds: unexpected-close ratio above 10% after 20
accepted streams, renewal-failure ratio above 5% after 20 renewals, and resume
recovery P95 above 2 seconds after 10 resumed streams. These are local
evaluations only; no production Prometheus collector, alert delivery route or
SLA is claimed until the target platform installs and exercises them.

### 6.3 First platform administrator and access changes

Public registration always creates the least-privileged platform role
`coder`; an organization creator receives organization `owner`, which is not
a platform administrator. `SEED_ON_STARTUP=false` is mandatory in Cloud, so a
new environment must establish its first platform administrator through the
passwordless operator command below. The command is dry-run by default,
requires an approved ticket ID, refuses to run when any active platform admin
already exists, increments `token_version`, and writes a `MODERN_SYSTEM`
audit event.

```bash
cd backend
python scripts/bootstrap_platform_admin.py \
  --identifier ops@example.cn \
  --ticket-id IAM-0001

# Execute only after reviewing the dry-run and change ticket:
python scripts/bootstrap_platform_admin.py \
  --identifier ops@example.cn \
  --ticket-id IAM-0001 \
  --execute
```

Subsequent changes use `PATCH /api/admin/users/{user_id}` from the
platform-admin-only Console. Requests carry the user's current
`expected_token_version`, a fixed reason code and an optional safe ticket ID.
Administrators cannot modify themselves or remove the last active platform
administrator. Successful role/account changes revoke the user's JWT,
refresh and owned OAuth tokens; account suspension also disables owned API
Clients. Organization suspension similarly revokes member sessions and
disables/revokes organization API Clients.

This is a development deployment candidate, not a complete enterprise IAM
system. Production still requires MFA/step-up authentication, dual approval
for privileged grants, SSO/SCIM lifecycle, periodic access review and an
independent audit/security review.

iCoDer v1 **不**支持生产环境 Docker compose 部署。Compose 仅供本地开发:

```bash
# Local dev path (唯一)
git clone <repo> && cd <repo>
cp .env.cloud.example .env.cloud  # 复制后改 ICODER_DEPLOYMENT_MODE=local 即可
docker compose -f docker-compose.local-dev.yml up -d --build

# 或纯 uvicorn (推荐用于 Agent 开发)
cd backend && python -m uvicorn app.main:app --port 8000
# 前端单独跑: cd frontend && npm run dev
```

需要真实 BGE/FAISS 语义检索时，使用隔离 worker profile：

```bash
export MEDCODER_RETRIEVER_TOKEN='<32-512 字符随机服务凭证>'
docker compose \
  -f docker-compose.local-dev.yml \
  -f docker-compose.medcoder.yml \
  up -d --build medcoder-retriever backend
```

overlay 会把 Backend 明确接到 `http://medcoder-retriever:8100`、只对这条 Compose 内网链路允许 HTTP、禁用 API 进程内原生检索，并等待 Worker `/readyz` 健康后再启动 Backend；缺少独立服务凭证时 Compose 在配置阶段失败。worker 只在 Compose 内网暴露 8100，启动时对固定 BGE revision、索引版本和资产 SHA-256 做完整校验，并通过完整推理预热后才就绪。Windows 已知不安全的 Torch/FAISS 组合不得作为本路径的替代实现。

`docker-compose.local-dev.yml` 不带 TLS 证书 / production secret / 跨实例 networking,
**绝不允许**部署到任何医院内网或公有云生产环境。

## 7. Migration Path (Phase 1 → Phase 2+)

本 cloud-flip 范围 (Phase 1):
- ✅ 文档翻转 (CLAUDE.md / README.md / 22 篇 docs)
- ✅ 部署 artifact 翻转 (config.py / docker-compose → local-dev / .env.cloud.example)
- ✅ 5 个 platform API stub 端点 (返 501 + doc-link)

Phase 2+ (out-of-scope, 已记录):
- ❌ `team.py` 加 org_id filter
- ❌ `ICODER_ENVIRONMENT` 真路由逻辑 (LLMGateway / DataPolicy 按 env branch)
- ❌ Stripe / 计费接线
- ❌ Env-region active-active failover
- ❌ Edge node PHI redaction 引擎 (in-hospital edge node)
- ❌ Platform API stub 端点的真实实现

独立 MedCodER 检索服务当前仅为开发部署候选：契约、失败关闭、资产来源、依赖漏洞、真实 TCP 跨进程 API→Worker 合同 E2E 和静态 Compose overlay 预检已有自动化证据；该 TCP E2E 使用无原生依赖的固定检索器验证网络/认证/版本/编码系统/Backend MCP 接线，不代表真实 BGE/FAISS 质量。本机缺少 Docker CLI，尚未完成镜像构建、SBOM/镜像扫描、Linux 原生索引运行、容量、故障注入或云部署验证。

## 8. References

- [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md) — backend-service vs ROPC embedded flow
- [MULTI_REGION.md](MULTI_REGION.md) — region routing / failover / replication
- [CLOUD_INTAKE_TEMPLATE.md](CLOUD_INTAKE_TEMPLATE.md) — Tenant onboarding intake
- [SEMANTIC_MEMORY_SERVICE.md](SEMANTIC_MEMORY_SERVICE.md) — 隔离语义 Memory、加密向量与授权边界
- [deploy/cloud/regions.yaml](../../deploy/cloud/regions.yaml) — declarative region config
- Corti reference: [project_corti_product_design_strategy.md](file://C:/Users/huawei/.claude/projects/E--Corti4C/memory/project_corti_product_design_strategy.md)
  (CLAUDE.md 已 lock pivot 至近 1:1 复刻 Corti)
- Internal: [CLAUDE.md](../../CLAUDE.md) — 当前产品定位 / 部署模型 / 启动命令
