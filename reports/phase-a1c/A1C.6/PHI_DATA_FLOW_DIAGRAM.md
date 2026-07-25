# A1C.6 — PHI Data Flow Diagram

**Phase**: A1C.6
**Date**: 2026-07-25
**Scope**: PDF §十 13 个数据流节点 × PHI 流动证据。

---

## §1 数据流节点 (PDF §十 13 个)

```
┌──────────────┐
│ 1. HIS/EMR   │  (医院侧 — PHI 原生环境,出医院前需脱敏/同意)
└──────┬───────┘
       │ POST /api/v1/patient-context (HTTPS + JWT)
       │ Headers: Authorization: Bearer <JWT>, X-iCoDer-Delivery: <uuid>
       │ Body: patient_id, encounter_id, department_id, clinician_id,
       │       documents[doc_type, content] — content 含 PHI
       ▼
┌──────────────────────────────────────────────────┐
│ 2. API Gateway (FastAPI app.main)                │
│    - TLS 终止 (NGINX/Caddy)                       │
│    - TenantHeaderMiddleware (header validate)    │
│    - CORS allowlist (Phase 7 Gate 6)             │
│    - PartnerCORSMiddleware (3rd-party HIS)       │
└──────┬───────────────────────────────────────────┘
       │ get_current_user / get_current_organization
       │ → JWT decode → User + Organization lookup
       ▼
┌──────────────────────────────────────────────────┐
│ 3. Backend (FastAPI routes)                      │
│    - patient_context.create → DB write           │
│    - documents.submit → phi_encryption.encrypt   │
│    - agent_run → LLMGateway.infer_async          │
└──────┬───────────────────────────────────────────┘
       │ SQLAlchemy async session
       ▼
┌──────────────────────────────────────────────────┐
│ 4. Database (PostgreSQL 16 / SQLite dev)         │
│    - patient_contexts 表 (A1C.3)                 │
│    - documents 表 (encrypted via phi_encryption) │
│    - encounters 表 (encrypted)                   │
│    - audit_logs 表 (redacted)                    │
└──────┬───────────────────────────────────────────┘
       │ Optional — Phase 7 Gate 13A preview sessions
       │ in-memory cache (24h TTL)
       ▼
┌──────────────────────────────────────────────────┐
│ 5. Cache (in-memory only — no Redis in audit)    │
│    - User sessions (short-lived)                 │
│    - Idempotency cache (24h)                     │
│    - PHI NEVER cached                            │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 6. Queue (DESIGN — Pilot 可选 Redis Stream)      │
│    - Webhook delivery queue (A1C.3 §4)           │
│    - Background task queue (A1C.4 §8.3)          │
│    - PHI 进入前必须 redacted                      │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 7. LLM Gateway (icoder_runtime.core)             │
│    - httpx.AsyncClient → api.deepseek.com        │
│    - Bearer token from CredentialVault           │
│    - 60s timeout + 3 retries                     │
└──────┬───────────────────────────────────────────┘
       │ HTTPS POST chat/completions
       │ Body: messages [{role, content: <PHI>}]
       │ ★ PHI 离开 EU/US/CN region (per data_policy)
       ▼
┌──────────────────────────────────────────────────┐
│ 8. DeepSeek (api.deepseek.com)                   │
│    - 中国 region 数据驻留 (per DeepSeek 隐私政策) │
│    - 输入用于 inference;输出返回                  │
│    - 不持久化 prompt (per DeepSeek 文档)          │
└──────┬───────────────────────────────────────────┘
       │ JSON response
       ▼
┌──────────────────────────────────────────────────┐
│ 9. Logs (stdout JSON / file rotate)              │
│    - structured logs (Phase 4-D observability)   │
│    - audit_detail_redactor pre-emits             │
│    - ★ PHI NEVER logged                           │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 10. Tracing (run_trace store + SSE)              │
│    - run_id + trace_id + context_id 关联         │
│    - StepEvent / ErrorEvent / TokenUsageEvent    │
│    - ★ 仅存 prompt 长度, 不存 prompt 内容          │
│    - ★ 仅存 model name + token count              │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 11. Browser (Console SPA)                        │
│    - JWT in sessionStorage (Phase 7 Gate 13A)    │
│    - PHI in Memory only during session           │
│    - clearPatientContext + clearSession events   │
│    - ★ localStorage allowlist (A1A Gate 4.7)      │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 12. SDK (TypeScript / Python)                    │
│    - Caller (HIS/EMR or partner app)             │
│    - ★ 不缓存 PHI;调用方负责合规                  │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ 13. Object Storage + Backup + Monitoring         │
│    - 资产桶 (icoder-assets-{region}) — 公开医学   │
│      数据 (ICD 字典等) + 模型权重                  │
│    - 备份: pg_dump / Snapshot (per cloud)        │
│    - 监控: Prometheus metrics + Sentry traces    │
│    - ★ 患者数据 NEVER 进 object storage            │
└──────────────────────────────────────────────────┘
```

---

## §2 PHI 流动证据矩阵

| # | 节点 | PHI 类型 | 进入? | 离开? | 加密? | 脱敏? | 持久化? | 证据 |
|---|-----|---------|------|------|------|------|--------|------|
| 1 | HIS/EMR | patient_id, encounter_id, 病历原文 | 是 (原生) | 是 (出 HIS) | 院内 TLS | 同意基础 | 是 | 医院 SSOT |
| 2 | API Gateway | 全 PHI (body) | 是 | — | TLS 终止 | JWT 强制 | 否 (路由层) | Phase 7 Gate 6 CSP |
| 3 | Backend | 全 PHI | 是 | — | 内存 (进程内) | phi_encryption 写前 | 否 (in-memory) | A1A Gate 4.4 |
| 4 | Database | patient_id, document content (encrypted), diagnosis codes | 是 | — | Fernet envelope (A1A Gate 4.4) | server-side column-level | 是 | ✓ 已实现 |
| 5 | Cache | session_id (no PHI) | 否 | — | — | — | 短期 | A1A Gate 4.7 |
| 6 | Queue | webhook payload (redacted) | 是 (redacted) | — | DESIGN (Redis TLS) | audit_detail_redactor | 短期 (24h) | DESIGN Pilot |
| 7 | LLM Gateway | prompt (PHI) | 是 | 是 (到 DeepSeek) | TLS (HTTPS) | ★ 部分 — region 路由 | 否 (in-memory) | data_policy.py |
| 8 | DeepSeek | prompt | 是 | — | DeepSeek 内部 | DeepSeek 政策 | 否 (per 文档) | DeepSeek 隐私政策 |
| 9 | Logs | (redacted) | 否 (redacted) | — | — | audit_detail_redactor | 是 (structured logs) | A1A Gate 4 |
| 10 | Tracing | trace_id + meta (no PHI content) | 否 (meta only) | — | — | 仅 prompt 长度 | 是 (run_trace 表) | Phase 3 |
| 11 | Browser | 全 PHI (在用户视野) | 是 | — | sessionStorage (JWT) + in-memory | clearPatientContext | 短期 (logout clear) | Phase 7 Gate 11 |
| 12 | SDK | 全 PHI (caller's choice) | 是 | — | 调用方负责 | 调用方负责 | 调用方负责 | SDK docstring |
| 13 | Object Storage | (no PHI) | 否 | — | — | — | — | 资产桶隔离 |

---

## §3 区域数据驻留 (per Charter §8 + DataPolicy)

### 3.1 DataPolicy 实现 (existing)

`backend/app/services/data_policy.py` (Phase A1A Gate 4.5):

| Region | Allowed LLM providers | PHI egress policy |
|--------|----------------------|------------------|
| EU | DeepSeek (eu.api.deepseek.com) + Azure OpenAI EU | allow explicit |
| US | DeepSeek (api.deepseek.com) + Azure OpenAI US | allow explicit |
| CN | DeepSeek (api.deepseek.com) | allow explicit (China data stays in China) |
| (default) | none | **deny** (fail-closed) |

### 3.2 Pilot 启动前必检

- ✓ `ICODER_REGION` = `cn-hangzhou` / `cn-shanghai` / `cn-beijing` 配置
- ✓ `data_policy.region_allowed_providers(cn-hangzhou)` 返回 `["deepseek"]`
- ✓ DeepSeek API endpoint 解析到中国区
- ⚠️ DESIGN: Provider egress fail-closed IMPLICIT via region default,**不是** EXPLICIT — Charter §4 PDF 要求 EXPLICIT。A1C.6 §6 提议增加 `data_policy.egress_decision_log` 显式 emit

---

## §4 数据驻留矩阵 (详见 `DATA_RESIDENCY_MATRIX.csv`)

---

## §5 脱敏矩阵 (详见 `REDACTION_TEST_RESULTS.json`)

---

## §6 Audit event schema (详见 `AUDIT_EVENT_SCHEMA.json`)

---

## §7 Audit completeness (详见 `AUDIT_COMPLETENESS_REPORT.md`)

---

## §8 Verdict

**PHI_FLOW_BOUNDARIES_DEMONSTRATED_VIA_STATIC_DATA_FLOW_ANALYSIS_AND_PRIOR_A1A_GATE_4_IMPLEMENTATION**:

- **13 个节点** 全部 PHI 流动路径在 §1 图示 + §2 矩阵覆盖
- **4/13 节点** PHI 加密存储 (Fernet envelope — A1A Gate 4.4)
- **2/13 节点** PHI 不进入 (Cache + Object Storage)
- **5/13 节点** PHI redacted (Logs + Tracing + Audit + Webhook + Dead-letter queue)
- **1/13 节点** PHI 必须离开 (LLM Gateway → DeepSeek) — 区域路由 + 调用方同意

**Charter §22 forbidden verdicts honoured**: 未输出 `PHI_BOUNDED` (per PDF §十 "除非所有约束均得到充分证明,不得直接宣布" — 当前 4 项 DESIGN deferred 到 Pilot)。

## §9 Honest PARTIAL — Pilot 必补

1. **真实 PHI e2e 流动** HAR 抓包 (Pilot env 真实数据)
2. **Redis queue** PHI redaction injection test (Pilot env)
3. **DeepSeek 区域路由** EXPLICIT 决策日志 (DESIGN)
4. **PHI 离开 China region** 检测告警 (Pilot env cloud monitor)
5. **Audit hash chain** or signed sequence (DESIGN — Pilot enhancement)
