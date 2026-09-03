# Phase 6 Gate 8 — API Client + Usage 产品化

**Date**: 2026-07-13
**Tier**: `GATE8_PASS_USAGE_MULTIDIM_FILTERS_API_CLIENT_STUB_DOCUMENTED`
**Estimate vs actual**: ~1h estimate / ~20min actual
**Code changes**: `backend/app/api/usage.py` (multi-dim filters + new `/by-agent` endpoint) + `backend/app/api/platform_api_clients.py` (Phase 6 verdict labels on stubs)

## What landed

### 1. Usage multi-dim filters — `agent_id` + `runtime_mode` 维度

`GET /api/usage/summary` 现在支持可选 query params:

```
GET /api/usage/summary?days=30                          # 全部
GET /api/usage/summary?days=7&agent_id=medical-coding-agent  # 仅 medical-coding
GET /api/usage/summary?days=30&runtime_mode=medcoder_deep     # 仅 medcoder_deep
GET /api/usage/summary?days=7&agent_id=cdi&runtime_mode=corti_like_fast  # 双过滤
```

Response 增加回显字段:
```json
{
  "total_requests": 142,
  "credits_used": 1.234,
  "currency": "CNY",
  "daily_breakdown": [...],
  "filters": {
    "agent_id": "medical-coding-agent",
    "runtime_mode": "corti_like_fast"
  },
  ...
}
```

让前端可以显示 "filtered by agent_id=X / runtime_mode=Y"。

### 2. 新 endpoint — `GET /api/usage/by-agent`

```python
@router.get("/by-agent")
async def get_usage_by_agent(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase 6 Gate 8 — per-agent cost breakdown."""
```

返回每个 `agent_id` 一行 (按 cost 降序):
```json
{
  "items": [
    {"agent_id": "medical-coding-agent", "cost": 0.8421, "run_count": 87, "avg_latency_ms": 9234},
    {"agent_id": "cdi", "cost": 0.2310, "run_count": 14, "avg_latency_ms": 6789},
    {"agent_id": "drg-analyzer", "cost": 0.1609, "run_count": 6, "avg_latency_ms": 4521}
  ],
  "total_cost": 1.234,
  "currency": "CNY",
  "period_days": 30
}
```

用途: Usage 页面的 "哪个 agent 最贵" 图表。

### 3. API Client stub — 显式 Phase 6 Gate 8 verdict

`backend/app/api/platform_api_clients.py` 文件头注释 + 5 个 501 endpoint 的 `detail` 都加:

```python
_PHASE6_GATE8_VERDICT = "API_CLIENT_PRODUCTIZATION_DEFERRED_TO_PHASE_2_CLOUD"

# 文件头注释解释为什么 deferred:
# - iCoDer 托管云 SaaS 路线要求 ICODER_DEPLOYMENT_MODE=cloud + 三层架构
# - 当前 local 模式仍使用单一 JWT (HS256)
# - 完整实装需要 alembic 迁移 (api_clients 表) + 密钥生成 + Keycloak/Authelia 接入
# - 超出 Phase 6 (consolidation) 范围
# - 501 stub 明确保留, 不假装可用 (per Phase 6 §4.3 "No fake npm publish" 精神)
```

每个 501 响应现在带 `phase6_gate8_verdict` 字段, 让前端可以基于 verdict code 做决策:
```json
{
  "message": "Platform API Clients API 是 Phase 1 cloud-flip ...",
  "design_doc": "https://github.com/iCoDer/docs/blob/cloud/API_CLIENT_MODEL.md",
  "phase": "Phase 2",
  "phase6_gate8_verdict": "API_CLIENT_PRODUCTIZATION_DEFERRED_TO_PHASE_2_CLOUD"
}
```

## Verification

```bash
# 1. Routes registered
python -c "
from app.api.usage import router
print('usage routes:', [r.path for r in router.routes])
from app.api.platform_api_clients import router as p
print('clients routes:', [r.path for r in p.routes])
"
# → usage routes: ['/api/usage/tokens', '/api/usage/summary', '/api/usage/by-agent', '/api/usage/history']
# → clients routes: ['/api/clients', '/api/clients/{client_id}/scopes', ...]

# 2. Regression — 12 tests pass (2 usage + 10 agent_run)
python -m pytest tests/test_api/test_phase5_a3_usage_run_history_cost.py tests/test_api/test_phase4f_agent_run.py -x
# → 12 passed in 37s
```

## Files written / modified

| Path | Change |
|---|---|
| `backend/app/api/usage.py` | +`agent_id` +`runtime_mode` filters on `/summary`; +new `/by-agent` endpoint (per-agent breakdown); +`filters` echo field in response |
| `backend/app/api/platform_api_clients.py` | +Phase 6 Gate 8 verdict docstring; +`_PHASE6_GATE8_VERDICT` constant; +`phase6_gate8_verdict` field in all 5 501 responses |

## Phase 6 §4.3 compliance — "No fake publish"

- API Client stubs remain 501 — explicitly deferred to Phase 2 cloud, **not** faked as working.
- Each 501 carries a `phase6_gate8_verdict` code so partners reading the API spec understand the deferral rationale.
- Usage endpoints are real and backed by `run_history` table (alembic 010) — no fakes.

## Not done (out of Gate 8 scope)

- **`api_client_id` filter on Usage** — Would require adding `api_client_id` column to `run_history` (alembic 012 migration). The trace_events DO carry `api_client_id` (Phase 4-G fix), but rollup-cost queries would need it on run_history. Phase 7 candidate.
- **API Client CRUD implementation** — Requires:
  - alembic 012 (api_clients table: client_id, client_secret_hash, tenant_id, scopes, created_at, revoked_at)
  - Secret generation (one-time display + bcrypt hash)
  - Keycloak / Authelia integration for OAuth 2.1 token endpoint
  - Frontend API Client management UI
  - Audit log entries on create/revoke
  
  This is multi-week work — explicitly Phase 2 cloud-flip per CLAUDE.md §部署模型.

- **Usage chart on frontend** — Backend ships the data; frontend could add a "Cost by Agent" donut chart. Existing UsagePage already shows daily breakdown; multi-agent breakdown is additive. Out of Phase 6 scope.

- **Live browser walkthrough** — Deferred to partner validation.

## Carry-forward to Final

- Final report will record verdict: `API_CLIENT_PRODUCTIZATION_DEFERRED_TO_PHASE_2_CLOUD` + `USAGE_MULTIDIM_FILTERS_SHIPPED`.

## Verdict

`GATE8_PASS_USAGE_MULTIDIM_FILTERS_SHIPPED_API_CLIENT_STUB_DOCUMENTED` — Usage 端加了 `agent_id` / `runtime_mode` 多维过滤 + 新 `/by-agent` 端点; API Client stub 保留 501 但用 `phase6_gate8_verdict` 显式标注 "deferred to Phase 2 cloud", 遵守 Phase 6 §4.3 不假装可用。12 backend regression tests pass.

Carry-forward: api_client_id column on run_history + full API Client CRUD = Phase 2 cloud-flip.
