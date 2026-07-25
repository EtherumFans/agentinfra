# HIS/EMR Integration Contract — iCoDer Pilot Entry Standard

**Phase**: A1C.3
**Date**: 2026-07-25
**Status**: CONTRACT_AUTHORIZED_FOR_PILOT (implementation PARTIAL — see §10)
**Auditor host caveat**: 主机无 docker / psql / 真实 HIS 测试床;本契约以**审计现有 iCoDer API** + **设计标准契约** 双路输出。Pilot 环境必须在第一次 HIS 对接前以本契约 MD5 (见 §11) 锁定版本。

---

## §0 目标与范围

**目标** (per PDF A1C.3): 建立真实医院集成前的标准契约,**不依赖某一家医院的临时接口**。

**范围**:
- Patient Context API (新建,关闭 RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT)
- Document Ingestion API (基于现有 `/api/encounters` 扩展,补文书类型枚举)
- Result Callback API (新建,Webhook 回写)
- Cross-tenant 约束 (基于 A1A Gate 2/3 tenant_read_policy)
- Idempotency (基于 Phase 7 Gate 3 IdempotencyKey pattern)
- Audit (基于 A1A Gate 3 system_audit allowlist + AuditLog)
- 数据来源标识 (基于 A1B-AE.3 origin/corti_alignment enum)
- 医院组织映射 (基于 A1A Gate 2 organizations.slug + tenant_id)

**不在范围** (deferred to Pilot 真实对接):
- HL7 v2.x / FHIR R4 wire format (iCoDer Pilot 2026 Q3 仅支持 JSON-over-HTTPS;HL7/FHIR 适配器由医院侧 HIS 厂商负责)
- 院内 HIS 私有协议 (TCP/MQ/文件投递等) — 不在 iCoDer Server 范围
- 患者主索引 (EMPI) — 医院侧负责,iCoDer 只接收已解析的 patient_id

---

## §1 现状审计 (must-audit-first per PDF §七)

| # | PDF 要求 | iCoDer 现状 | 缺口 | A1C.3 处置 |
|---|---------|------------|------|-----------|
| 1 | 患者上下文 API | **不存在** (RV.5 J8 BLOCKED) | 完全缺失 | 本契约 §2 + 实现 (Migration 029 + endpoint) |
| 2 | 就诊上下文 API | `/api/encounters` (POST/GET/DELETE) | 字段缺 `purpose_of_use` / `consent_legal_basis` / `expires_at` | 本契约 §3 扩展 (defer 到 A1C.4) |
| 3 | 文书提交 API | `/api/encounters` 嵌套 documents[] | 8 类文书枚举未明示 | 本契约 §4 标准化 |
| 4 | 编码任务 API | `/api/agent_run` (Idempotency-Key 已支持) | 完整 | 本契约 §5 引用 |
| 5 | 结果回写 API | **不存在** | 完全缺失 | 本契约 §6 + simulator |
| 6 | 状态回调 | SSE `/api/v1/runs/{id}/events` (Phase 7 Gate 9) | OK,无主动 Webhook | 本契约 §7 设计 (Pilot 实现) |
| 7 | Webhook | **不存在** | 完全缺失 | 本契约 §7 设计 |
| 8 | 幂等键 | Phase 7 Gate 3 IdempotencyKey | OK | 本契约 §8 引用 |
| 9 | 错误码 | 散落各 endpoint (HTTPException) | 未标准化 | 本契约 §9 |
| 10 | 重试 | IdempotencyRecord replay | OK,无客户端指南 | 本契约 §10 |
| 11 | 数据来源标识 | A1B-AE.3 `origin` enum (CLEAN_ROOM_PUBLIC/REVERSE_ENGINEERED/ICODER_INTERNAL/PACK_DECLARED) | OK | 本契约 §11 引用 |
| 12 | 医院组织映射 | A1A Gate 2 organizations.slug + tenant_id (Migration 016) | OK | 本契约 §12 引用 |

**审计结论**: 12 项中 5 项**完全缺失** (#1/#5/#7 + #2 部分 + #9 部分),7 项已存在但需标准化引用。本契约关闭 5 项缺失中的 #1 (设计+实现)、#5/#7 (设计,simulator 验证)、#9 (设计);#2 字段扩展 defer 到 A1C.4。

---

## §2 Patient Context API (关闭 RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT)

### 2.1 Endpoint

```
POST   /api/v1/patient-context         # 创建
GET    /api/v1/patient-context/{id}    # 查看
DELETE /api/v1/patient-context/{id}    # 软删除 (immediate)
POST   /api/v1/patient-context/{id}/extend  # 延长 expires_at (≤ 24h 总寿命)
```

### 2.2 标准 Patient Context (PDF §七 13 字段)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `context_id` | string(12) | 服务端生成 | iCoDer 内部 ID (uuid.uuid4().hex[:12]) |
| `organization_id` | string(12) | 服务端注入 | 从 JWT 提取 (基于 A1A Gate 2 organizations.id) |
| `tenant_id` | string(64) | 必填 | 医院 tenant slug (e.g. `zju-fh-cn-hangzhou`) |
| `source_system` | string(64) | 必填 | HIS/EMR 标识 (e.g. `ZJU-FH-HIS-2024`) |
| `patient_id` | string(64) | 必填 | 脱敏后 patient ID (医院侧 EMPI 已解析) |
| `encounter_id` | string(64) | 可选 | 若已有就诊则填;新就诊留空 |
| `visit_type` | enum(8) | 必填 | `inpatient` / `outpatient` / `emergency` / `day-case` / `home-care` / `telemed` / `rehab` / `observation` |
| `department_id` | string(64) | 必填 | 科室 ID (医院侧 code) |
| `ward_id` | string(64) | 可选 | 病区 ID (inpatient/day-case 必填) |
| `clinician_id` | string(64) | 必填 | 主治医生 ID (医院侧 staff code) |
| `document_ids` | array<string> | 默认 [] | 已有文书 iCoDer 内部 ID (若复用) |
| `purpose_of_use` | enum(6) | 必填 | `treatment` / `billing` / `operations` / `quality` / `research` / `public-health` |
| `consent_legal_basis` | enum(5) | 必填 | `patient-consent` / `treatment-necessity` / `legal-obligation` / `vital-interest` / `public-interest` |
| `trace_id` | string(64) | 服务端生成 | W3C traceparent 格式 (HIS/EMR 也可注入) |
| `created_at` | ISO8601 | 服务端生成 | UTC,带 Z 后缀 |
| `expires_at` | ISO8601 | 服务端生成 | created_at + 24h (硬上限) |

### 2.3 不允许永久保存

- **硬上限**: `expires_at - created_at ≤ 24h`。客户端 `extend` 只能续到上限,不能超越。
- **后台清理**: 每小时 cron 任务软删除 (status='expired') 已过期 context;24h 后物理删除。
- **跨 tenant**: context 创建后只在创建 organization_id 可见;cross-tenant GET/DELETE 返回 404 (per A1A Gate 3 tenant_read_policy exact-404-no-leak)。

### 2.4 RV.5 关闭证据

| RV.5 要求 | 本契约关闭点 |
|----------|------------|
| 正式设计 | §2.1-2.3 (本文件) |
| 实现 | backend/app/api/patient_context.py + Migration 029 (本 commit) |
| OpenAPI | /api/v1/openapi.json 自动包含 (FastAPI auto-gen) |
| SDK | packages/icoder-sdk/src/patient-context.ts (本 commit) |
| 权限 | §12 (RBAC `patient_context.create` / `.read` / `.delete`) |
| 审计 | AuditLog action=`patient_context.create` / `.delete` (system_audit allowlist 已扩) |
| 幂等 | Idempotency-Key (Phase 7 Gate 3 IdempotencyRecord 复用) |
| 生命周期 | §2.3 (24h TTL + cron cleanup) |
| 删除和过期 | §2.1 DELETE + extend + 自动 expire |
| 浏览器旅程 | A1C.8 journey #4 (patient context CRUD) |

---

## §3 Document Ingestion (基于现有 `/api/encounters` 嵌套 documents[])

### 3.1 标准 8 类文书 (per PDF §七)

| doc_type | 中文名 | 必含字段 |
|---------|-------|---------|
| `discharge-summary` | 病案首页 | diagnosis_codes[], procedure_codes[], DRG/DIP 预分组 |
| `admission-record` | 入院记录 | chief_complaint, present_illness, past_history, physical_exam |
| `discharge-record` | 出院记录 | admission_diagnosis, discharge_diagnosis, discharge_instructions |
| `operation-record` | 手术记录 | operation_name, operation_date, surgeon, anesthesia, findings |
| `progress-note` | 病程记录 | note_datetime, author, subjective, objective, assessment, plan |
| `lab-result` | 检验 | test_name, specimen, result_value, unit, ref_range, abnormal_flag |
| `imaging-report` | 检查 | modality, body_part, findings, impression, radiologist |
| `order` | 医嘱 | order_type (med/lab/imaging/...), order_datetime, ordering_physian |

(注: PDF "费用或 DRG/DIP 相关数据" 通过 `discharge-summary` 的 `diagnosis_codes[]` + `procedure_codes[]` 字段携带,iCoDer 计算 DRG/DIP。)

### 3.2 文书提交契约

POST `/api/v1/patient-context/{context_id}/documents`

Body:
```json
{
  "documents": [
    {
      "doc_type": "discharge-summary",
      "title": "病案首页 - 张三 2026-07-25",
      "content": "...",   // 原始文本或结构化 JSON
      "content_format": "text" | "json",
      "doc_order": 0,
      "source_doc_id": "HIS-Doc-12345"   // HIS 侧文书 ID 用于幂等
    }
  ],
  "idempotency_key": "his-batch-001"
}
```

Response 201:
```json
{
  "documents": [
    {"id": "doc-abc123", "encounter_id": "ENC-XYZ", "source_doc_id": "HIS-Doc-12345", "created_at": "..."}
  ]
}
```

---

## §4 Result Callback API (回写 HIS/EMR)

### 4.1 同步返回 vs 异步回调

- **同步**: 调用 `/api/agent_run` 时同步返回 `run_id` + `trace_url` (Phase 7 Gate 7 已实现)
- **异步回调**: HIS/EMR 注册 webhook URL,iCoDer 在 run 完成后主动 POST 结果 (本契约新增)

### 4.2 Webhook 注册

POST `/api/v1/webhooks`

Body:
```json
{
  "url": "https://his.hospital.cn/icoder-callback",
  "events": ["run.completed", "run.failed", "review.completed"],
  "secret": "whsec_..."   // HMAC-SHA256 共享密钥
}
```

Response 201: `{"webhook_id": "wh-abc", "signing_secret": "whsec_..."}`

### 4.3 Result Callback Payload

POST 到 HIS url,body 见 `RESULT_CALLBACK_SCHEMA.json`。Header:

```
X-iCoDer-Event: run.completed
X-iCoDer-Signature: sha256=<hex>
X-iCoDer-Delivery: <uuid>     // 幂等 ID
Content-Type: application/json
User-Agent: iCoDer-Webhook/1.0
```

### 4.4 重试策略

- HIS 返回 2xx: ACK,从队列删除
- HIS 返回 4xx: 立即 ACK (HIS 明确拒绝),不重试,记录到 webhook_delivery.dead_letter
- HIS 返回 5xx 或超时: 指数退避重试 (1m / 5m / 30m / 2h / 6h / 24h — 6 次),之后进死信
- 同一 delivery_id 重试保证 idempotent (HIS 侧应基于 delivery_id 去重)

---

## §5 Coding Task API (引用现有)

- `POST /api/agent_run` (Phase 7 Gate 1-7 完整链)
- Idempotency-Key (Phase 7 Gate 3)
- trace_url (Phase 7 Gate 7)
- SSE `/api/v1/runs/{id}/events` (Phase 7 Gate 9)

A1C.3 不修改,仅引用。

---

## §6 Status Callback (引用现有 SSE + 新增 Webhook)

参见 §4。

---

## §7 Webhook

参见 §4.2 / §4.3 / §4.4。

---

## §8 Idempotency Key

### 8.1 Header

`Idempotency-Key: <client-generated-uuid>` (UUID v4 推荐,1-255 字符)

### 8.2 复用范围

- 同一 Idempotency-Key 在 24h 内重复请求 → 返回首次结果 (cache hit)
- 不同 endpoint 共享同一 Idempotency-Key → 409 Conflict (cross-endpoint key collision detected)

### 8.3 实现引用

Phase 7 Gate 3 `idempotency_service.py` (backend/app/services/idempotency_service.py)。

---

## §9 Error Code 标准化

### 9.1 错误响应格式

```json
{
  "error": {
    "code": "PATIENT_CONTEXT_EXPIRED",
    "message": "patient context ctx-abc123 expired at 2026-07-25T10:00:00Z",
    "trace_id": "00-4a92b...",
    "details": {...}
  }
}
```

### 9.2 标准错误码 (A1C.3 范围)

| HTTP | code | 触发场景 |
|------|------|---------|
| 400 | `INVALID_REQUEST` | Pydantic 校验失败 |
| 401 | `UNAUTHENTICATED` | JWT 缺失或无效 |
| 403 | `PERMISSION_DENIED` | RBAC 拒绝 |
| 404 | `NOT_FOUND` | 资源不存在 (cross-tenant 也走 404) |
| 409 | `STATE_CONFLICT` | 资源状态不允许操作 (e.g. context 已 expired) |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | cross-endpoint key collision |
| 410 | `GONE` | 资源已删除 |
| 422 | `BUSINESS_RULE_VIOLATION` | e.g. ward_id 在 outpatient 场景 |
| 429 | `RATE_LIMITED` | Phase 7 Gate 8 quota |
| 500 | `INTERNAL_ERROR` | 未预期异常 |
| 502 | `UPSTREAM_ERROR` | DeepSeek / KMS / HIS 上游错误 |
| 503 | `SERVICE_UNAVAILABLE` | 健康检查失败 |
| 504 | `UPSTREAM_TIMEOUT` | 上游超时 |

---

## §10 客户端重试指南

| 错误码 | 重试策略 |
|-------|---------|
| 5xx | 指数退避 1s/2s/4s/8s/16s,最多 5 次 |
| 429 | 按 Retry-After header |
| 504 | 单次重试,若仍 504 则降级到下一 LLM provider (LLMGateway 已支持) |
| 4xx (除 408/429) | 不重试 (业务错误) |
| 网络超时 | 同 5xx |
| Idempotency-Key 409 | 检查是否用错 key |

---

## §11 数据来源标识 (引用 A1B-AE.3 `origin` enum)

每条 patient_context / document / run 必须带 `source_system` 字段:
- `CLEAN_ROOM_PUBLIC` — Corti 公开文档 clean-room 副本
- `REVERSE_ENGINEERED` — headed browser 观察得到
- `ICODER_INTERNAL` — iCoDer 原生生成
- `PACK_DECLARED` — agent_pack.json 声明

加上 PDF §七新增的 HIS 来源:
- `HIS_LIVE` — 真实 HIS/EMR (Pilot 部署后)
- `HIS_SIMULATOR` — 本契约 §13 simulator

---

## §12 医院组织映射 (引用 A1A Gate 2)

- `Organization.slug` (unique) — e.g. `zju-fh-cn-hangzhou`
- `Organization.tenant_id` (string) — e.g. `cn-hangzhou` (region shard)
- 创建时通过 `POST /api/organizations` (admin only)
- 跨 organization 拒绝: A1A Gate 2 tenant_read_policy

### 12.1 RBAC 权限矩阵 (新增 patient_context 权限)

| Role | patient_context.create | .read | .delete | documents.submit |
|------|-----------------------|-------|---------|-----------------|
| `org-admin` | ✓ | ✓ | ✓ | ✓ |
| `clinician` | ✓ | ✓ (own dept) | own only | ✓ |
| `coder` | — | ✓ (own org) | — | ✓ |
| `auditor` | — | ✓ (read-only) | — | — |
| `api-client` | ✓ (machine) | ✓ | ✓ | ✓ |

---

## §13 HIS/EMR Simulator (PDF §七)

详见 `HIS_EMR_SIMULATOR/` 目录 + `HIS_EMR_SCENARIO_MATRIX.csv`。

16 个场景:
1. 正常病例 (smoke)
2. 缺字段 (validation 400)
3. 重复消息 (idempotency cache hit)
4. 乱序消息 (document before context — 422)
5. 延迟消息 (client slow, server timeout)
6. 撤回文书 (DELETE document — soft delete)
7. 文书版本更新 (PUT document with version increment)
8. 患者合并 (POST patient-merge event)
9. 就诊号变更 (PUT encounter_id change)
10. 跨机构错误 (cross-tenant deny 404)
11. 网络超时 (TCP timeout — server 504)
12. 5xx (DeepSeek upstream 502)
13. 429 (rate limit)
14. 回调失败 (webhook delivery dead letter)
15. 重复回写 (delivery_id idempotency)
16. consent 拒绝 (consent_legal_basis 缺失 — 422)

---

## §14 Open API / SDK 引用

- OpenAPI: `/api/v1/openapi.json` 自动生成 (FastAPI)
- Python SDK: `packages/icoder-sdk-python/` (A1B-AE.3 已建)
- TypeScript SDK: `packages/icoder-sdk/` (Phase 6 Gate 4)
- A1C.3 新增 patient_context 模块: `packages/icoder-sdk/src/patient-context.ts`

---

## §15 Pilot 启动前置 (必须完成)

- [ ] **G-PILOT-01**: `pytest backend/tests/integration/test_a1c3_his_emr_contract.py` 16 scenario 全 PASS
- [ ] **G-PILOT-02**: Pilot 环境 HIS 厂商签署本契约 MD5 锁定版本 (§11)
- [ ] **G-PILOT-03**: Pilot 环境 PG 上 `patient_contexts` 表迁移成功 (A1C.2 Migration 029)
- [ ] **G-PILOT-04**: Pilot 环境 webhook 死信队列 (Redis stream 或 PG queue) 部署
- [ ] **G-PILOT-05**: A1C.8 journey #4 真实浏览器 CRUD PASS

---

## §16 Verdict

**CONTRACT_AUTHORIZED_FOR_PILOT_IMPLEMENTATION_PARTIAL**:

- **DESIGNED**: §1-§16 全部 16 个章节完成,Patient Context API 完整设计 (13 字段 + 4 endpoint + TTL + RBAC)
- **IMPLEMENTED**: patient_contexts 模型 + Migration 029 + POST/GET/DELETE/extend endpoint + AuditLog + RBAC 检查
- **DEFERRED TO PILOT**: Webhook 死信队列 (需 Redis 部署)、HL7/FHIR 适配器 (医院侧负责)、真实 HIS 对接验证 (Pilot 环境)
- **RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT** 关闭:J8 journey 重新执行 (A1C.8 journey #4)

**Charter §22 forbidden verdicts 已 honour**: 未输出 CONTRACT_FULLY_VERIFIED 或 HIS_EMR_PILOT_DEPLOYED (Pilot 真实对接未发生)。

---

## §17 契约版本锁定 (Pilot 启动时计算 MD5)

```
$ sha256sum reports/phase-a1c/A1C.3/HIS_EMR_INTEGRATION_CONTRACT.md \
            reports/phase-a1c/A1C.3/PATIENT_CONTEXT_SCHEMA.json \
            reports/phase-a1c/A1C.3/DOCUMENT_INGESTION_SCHEMA.json \
            reports/phase-a1c/A1C.3/RESULT_CALLBACK_SCHEMA.json
```

输出 4 个 SHA256 写入 `pilot_charter_lock.md`,医院与 iCoDer 双签后锁版本。任何修改需重新签。
