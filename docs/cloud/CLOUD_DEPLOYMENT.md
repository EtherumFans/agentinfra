# iCoDer Cloud Deployment Architecture (2026-06-27)

> **Status**: Design intent (Phase 1 cloud-flip). Production deployment targets
> `https://{tenant}.{region}.icoder.cloud`. Local development remains
> `python -m uvicorn app.main:app --port 8000` + `docker compose -f
> docker-compose.local-dev.yml up`. See also: [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md),
> [MULTI_REGION.md](MULTI_REGION.md), [CLOUD_INTAKE_TEMPLATE.md](CLOUD_INTAKE_TEMPLATE.md).

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

## 8. References

- [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md) — backend-service vs ROPC embedded flow
- [MULTI_REGION.md](MULTI_REGION.md) — region routing / failover / replication
- [CLOUD_INTAKE_TEMPLATE.md](CLOUD_INTAKE_TEMPLATE.md) — Tenant onboarding intake
- [deploy/cloud/regions.yaml](../../deploy/cloud/regions.yaml) — declarative region config
- Corti reference: [project_corti_product_design_strategy.md](file://C:/Users/huawei/.claude/projects/E--Corti4C/memory/project_corti_product_design_strategy.md)
  (CLAUDE.md 已 lock pivot 至近 1:1 复刻 Corti)
- Internal: [CLAUDE.md](../../CLAUDE.md) — 当前产品定位 / 部署模型 / 启动命令