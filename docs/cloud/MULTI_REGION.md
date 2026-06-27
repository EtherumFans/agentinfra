# iCoDer Multi-Region Architecture (2026-06-27)

> **Status**: Design intent (Phase 1 cloud-flip). 详细三层架构见
> [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)。API Client token 隔离见
> [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md)。

## 1. Region Catalog (Initial)

| Environment | Region code | Location | Compliance | 启用日期 |
|---|---|---|---|---|
| `eu` | `eu-frankfurt` | Frankfurt, DE | GDPR + EHDS | Phase 2 |
| `eu` | `eu-stockholm` | Stockholm, SE | GDPR + EHDS | Phase 3 |
| `us` | `us-virginia` | Virginia, US | HIPAA + HITECH | Phase 2 |
| `us` | `us-oregon` | Oregon, US | HIPAA + HITECH | Phase 3 |
| `cn` | `cn-hangzhou` | Hangzhou, CN | 数据安全法 + 个人信息保护法 | Phase 2 |
| `cn` | `cn-beijing` | Beijing, CN | 数据安全法 + 个人信息保护法 | Phase 3 |

环境配置在 [deploy/cloud/regions.yaml](../../deploy/cloud/regions.yaml)。

## 2. Data Residency Constraints

**核心约束**: Tenant 数据 **绝不跨 Environment 复制**。

| 数据类型 | 存储位置 | 跨 region 复制 | 备注 |
|---|---|---|---|
| Encounter / Review / Code | 同 region Postgres | 否 (单 region 主备) | Tenant 数据 |
| Gold case | 同 region Postgres | 否 | Tenant 数据 |
| Audit log | 同 region Postgres + 同 region object storage | 否 (write-once) | 合规 |
| LLM API key (per-tenant) | 同 region secret vault | 否 | KEK 从 KMS 注入 |
| FAISS 索引 (BGE-M3 / ICD-10) | region-shared object storage (只读) | 跨 region 镜像 (read-only) | 模型权重公共 |
| Code dicts (ICD-10-CN catalog) | region-shared object storage (只读) | 跨 region 镜像 | 公共资产 |
| PHI 脱敏缓存 | 仅内存,不落盘 | 否 | edge only |
| PHI 原始 | **不存储** | N/A | 留 HIS/EMR |

## 3. Routing Logic

```
Request → CDN/Edge → TLS terminate →
  ┌─ If X-Tenant-Id header present: route by tenant_id
  │     - Lookup tenant.environment + tenant.region
  │     - Forward to control-plane in that region
  │
  ├─ Else: rejected (401 Unauthorized)
  │
  └─ Region control-plane:
      - Validate JWT (tenant_id + env + region claims)
      - Forward to in-region services:
          ├─ API service (FastAPI + tenant-scoped middleware)
          ├─ Inference pool (LLMGateway → in-region DeepSeek endpoint)
          ├─ Retrieval service (BGE-M3 + FAISS in-region)
          └─ Audit log (write-once object storage)
```

## 4. Failover & Disaster Recovery

### 4.1 Phase 1 (single-region, no failover)

- 单 region 内主备 (Postgres streaming replication + 自动 failover)
- RTO ≤ 4h, RPO ≤ 1h
- 跨 region 不复制 Tenant 数据

### 4.2 Phase 3 (active-active, future)

- Tenant 可选 active-active 跨 2 个 region (同 Environment)
- Active-active 用 CRDT-style merge for 冲突 resolution (audit log append-only
  → 无冲突;encounter data → last-write-wins by updated_at)
- RTO ≤ 30min, RPO ≤ 1min
- 跨 Environment 不允许 active-active (合规隔离)

## 5. Audit Log Replication

- **同 region**: Audit log 写主库 + 异步复制到 S3-compatible object storage
  (write-once, immutable)
- **跨 region**: Audit log **不复制**到其他 region (合规约束)
- **Tenant 自查**: Tenant admin 可在同 region 控制面读自己的 audit log
- **监管机构**: 走独立 encrypted channel (out of scope for this phase)

## 6. LLM Inference Routing

LLM 调用路由到 **同 region** 的 inference endpoint,token + 推理都不出 region:

| Environment | LLM Provider (default) | Endpoint |
|---|---|---|
| `eu` | DeepSeek EU (or Anthropic EU if contracted) | `https://api-eu.deepseek.com/v1` |
| `us` | DeepSeek US / Anthropic | `https://api-us.deepseek.com/v1` |
| `cn` | DeepSeek V4 (deepseek-v4-flash) | `https://api.deepseek.com/v1` |

Tenant 可在 Console → Settings → LLM Provider 选 (4 env var per-tenant:
`LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL`)。**LLM API key 必须
在同 region 内**,跨 region 的 key 不被接受 (防止数据出 region)。

## 7. Cross-Region Latency Expectations

| 链路 | Target P50 | Target P99 |
|---|---|---|
| Client → same region CDN/edge | ≤ 50ms | ≤ 200ms |
| Edge → control-plane (同 region) | ≤ 30ms | ≤ 100ms |
| Control-plane → LLM inference (同 region) | ≤ 80ms | ≤ 250ms |
| MedCodER full pipeline (同 region, BGE-M3 warm) | ≤ 8s | ≤ 30s |
| MedCodER full pipeline (同 region, BGE-M3 cold) | ≤ 60s | ≤ 120s |

跨 region 调用 **不允许** (除 read-only public assets 如 FAISS 索引镜像)。

## 8. Migration Path (Phase 1 → Phase 3)

Phase 1 (本 cloud-flip):
- ✅ 文档化三层架构 + region 目录
- ✅ `regions.yaml` declarative config
- ✅ `ICODER_ENVIRONMENT` / `ICODER_REGION` env vars 接入 config.py (未路由)

Phase 2 (Environment 真路由):
- API service 按 `tenant.environment` 路由
- LLMGateway 按 `ICODER_ENVIRONMENT` 选 base_url
- DataPolicy 按 env 加 region-specific redaction rules

Phase 3 (active-active):
- 跨 region read replica
- CRDT-style conflict resolution
- 自动 failover with health check

## 9. References

- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) — 三层架构总览
- [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md) — token claims 含 env/region
- [deploy/cloud/regions.yaml](../../deploy/cloud/regions.yaml) — declarative config