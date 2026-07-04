# Phase 1.1 — Medical Coding 路径 + schema 对齐 Corti §3.1

> Date: 2026-06-30
> Roadmap reference: `docs/corti-reverse-engineered/SUMMARY.md §15.5 Phase 1 路线`
> Commit: (followed up on Phase 1.0 / `0fd00f0`)

## 1. 背景

Phase 1.0 (`0fd00f0`) 在 OAuth 上补齐 Corti 的 4 个共享原语
(Tenant header / 5min TTL / capability scope / realm URL)。
按 §15.5 路线, Phase 1.1 = **Medical Coding 路径 + schema 对齐 §3.1**。

iCoDer 此前的 Medical Coding 入口 (Phase 2.1-B 已物理删除, 以下为历史背景):

| 维度 | 历史 (M3-0, deleted in Phase 2.1-B Step 4) |
|---|---|
| URL | `POST /api/icoder/coding-review/run` (router deleted, commit accc5be) |
| Req shape | `{encounter_text, primary_disease_codes, ...}` (扁平, 多字段拼装) |
| Resp shape | `primary_diagnosis + secondary_diagnoses + procedures + evidence_chain + risk_route + pipeline_stages_observed + ...` |
| Evidence | 字符串截取 `"span": "..."`, 无 char offset |
| Alternatives | 无对应字段 |

Corti §3.1 的目标 shape (从 `api.eu.corti.app/v2/tools/coding/` 抓包还原):

| 维度 | Corti §3.1 |
|---|---|
| URL | `POST /v2/tools/coding/` |
| Req | `{context:[{text, type}], system:["icd10cm-outpatient"]}` |
| Resp | `{codes:[{system, code, display, evidences:[{contextIndex, text, start, end}], alternatives:[{code, display}]}]}` |
| Evidence | char offset `(start, end)` 指向具体 `context[contextIndex].text` 切片 |

Phase 1.1 在不动 M3-0 legacy 的前提下, 新增一条 Corti-shape HTTP 路径:

- `POST /api/v2/tools/coding`
- 默认 mode = `medcoder.full` (5 阶段 MedCodER NAACL 2025 真管线)
- `system` 字段**只接受 iCoDer 中国体系命名** (`icd10cn-outpatient` /
  `icd10cn-inpatient` / `icd9cm3-procedure` / `icd9cm3-diagnostic`)，
  Corti US 命名 (`icd10cm-outpatient` / `icd10pcs` / `icd9cm` / `cpt`)
  一律 `400 unsupported_system`

## 2. 端到端契约

### 2.1 Request

```json
{
  "context": [
    { "text": "患者男性,67 岁,因「反复胸闷...LVEF 38%。诊断:1. 慢性心力衰竭 心功能 III 级(NYHA);2. 心房颤动", "type": "text" }
  ],
  "system": ["icd10cn-outpatient"]
}
```

### 2.2 Response (200)

```json
{
  "codes": [
    {
      "system": "icd10cn-outpatient",
      "code": "I50.901",
      "display": "充血性心力衰竭",
      "evidences": [
        { "contextIndex": 0, "text": "LVEF 38%", "start": 110, "end": 118 }
      ],
      "alternatives": [
        { "code": "I50.900", "display": "心力衰竭,未特指" }
      ]
    }
  ]
}
```

### 2.3 错误响应

| HTTP | `detail.error` | 触发 |
|---|---|---|
| 400 | `empty_context` | `context` 为空数组或所有 text 为空 |
| 400 | `unsupported_system` | `system[]` 包含非 iCoDer 体系命名 (含 Corti US 命名) |
| 400 | `unsupported_mode` | `?mode=` 不在 `medcoder` / `full` / `prompt` / `retrieve` / `prompt+retrieve` |
| 502 | `coding_pipeline_failed` | MedCodER 5 阶段管线异常 |
| 502 | `empty_extracted_diagnoses` | 5 阶段跑完但 `extracted_diagnoses` 为空 (通常伴随 LLM 失败) |
| 503 | `llm_credential_missing` | `ICODER_CREDENTIAL_LLM` 未设置且 `ICODER_ALLOW_DEGRADED_NO_KEY != 1` (hospital pilot gate) |

## 3. 字段映射 (iCoDer Runtime ↔ Corti §3.1)

| Corti 字段 | 来源 |
|---|---|
| `codes[].system` | `body.system[0]` 原值回显 (默认 `icd10cn-outpatient`) |
| `codes[].code` | `extracted_diagnoses[i].final_top_k[0].code` (rerank 头选) |
| `codes[].display` | 主选 `CandidateCode.name` (首选), fallback 到 `CodeDictionaryService._display_for(code)` |
| `codes[].evidences[].contextIndex` | single-context 时 = 0; multi-context 时按 evidence `doc_id` 命中 `context[]` 索引 |
| `codes[].evidences[].text` | `supporting_evidence[j].text` |
| `codes[].evidences[].start` | `supporting_evidence[j].char_start` (inclusive) |
| `codes[].evidences[].end` | `supporting_evidence[j].char_end` (exclusive) |
| `codes[].alternatives[]` | `extracted_diagnoses[i].final_top_k[1:5]` (cap 4 个, 主选不算) |
| `codes[]` 排序 | `extracted_diagnoses` 按 `final_confidence` desc |

## 4. Mode 查询参数

| `?mode=` | HybridCodingAdapter.mode | 说明 |
|---|---|---|
| `full` (默认) | `medcoder.full` | 5 阶段完整管线 (NAACL 2025 §448) |
| `medcoder` | `medcoder.full` | `full` 别名 |
| `prompt` | `medcoder.prompt` | 仅 Stage 1 LLM 抽取 (无 RAG) |
| `retrieve` | `medcoder.retrieve` | 仅 Stage 2 BGE-M3 RAG (无 LLM) |
| `prompt+retrieve` | `medcoder.prompt_retrieve` | Stage 1+2 合并去重 (无 rerank) |

## 5. Reuse 现有组件 (不重写)

- `icoder_runtime/providers/medical_coding/hybrid_adapter.py:71`
  `HybridCodingAdapter.infer_async` — **直接调**, 不重写 5 阶段
- `icoder_runtime/providers/medical_coding/medcoder_strategy.py:981`
  `_build_extracted_diagnosis` — `EvidenceSpan` 已含 `(char_start, char_end, text)`
- `icoder_runtime/providers/medical_coding/medcoder_adapter.py:419`
  `fuzzy_evidence_to_span` + `:476` `_snap_to_sentence` — char-span 算法已 green
- `official_agents/medical_coding/schema.py:20` `EvidenceSpan` — iCoDer Runtime SSOT
- `app/services/code_dictionary.py` `_ICD10_CODES + _ICD9_CODES` — display name 取值 (sync lookup)
- `icoder_runtime/core/pii_redaction.py` `PIIRedactor` — 中国本地 PHI 脱敏
- Phase 1.0 `app/middleware/auth.py` `Depends(get_current_user)` — 复用

## 6. Out of scope (Phase 1.1 显式不做)

- ❌ M3-0 `/api/icoder/coding-review/*` 三端点 (Phase 2.1-B Step 4 已物理删除)
- ❌ `coding` capability scope 注册 (Phase 1.2 接 OAuth 一起做)
- ❌ 重写 HybridCodingAdapter / MedCodER 真管线 (复用)
- ❌ 前端 MedicalCodingPage / MethodComparePage 改造 (Phase 1.1 是后端 HTTP shape 对齐)
- ❌ char-span 备选实现 (复用 `fuzzy_evidence_to_span`)

## 7. 测试矩阵 (8 / 8 PASS)

`backend/tests/test_api/test_v2_tools_coding.py`:

| # | 测试 | 验证 |
|---|---|---|
| 1 | `test_v2_coding_shape_minimal` | 标准 Corti-shape 请求 → 200, codes[0] 含全部字段 |
| 2 | `test_v2_coding_evidence_span_roundtrip` | char offset 与 source text 切片一致 (no off-by-one) |
| 3 | `test_v2_coding_alternatives_contains_rerank` | final_top_k ≥ 3 时, `len(alternatives) >= 2` |
| 4 | `test_v2_coding_icoder_system_accepted` | `icd10cn-outpatient/inpatient/icd9cm3-procedure/diagnostic` 全部接受 |
| 5 | `test_v2_coding_corti_us_system_rejected` | `icd10cm-* / icd10pcs / icd9cm / cpt` 全部 400 |
| 6 | `test_v2_coding_multi_context_contextindex` | 多 context 块时 `contextIndex` 跟随输入顺序, 不串台 |
| 7 | `test_v2_coding_empty_context_rejected` | 空 / 全空白 context → 400 `empty_context` |
| 8 | `test_v2_coding_no_llm_credential_returns_503` | 无 LLM credential + 无 dev opt-in → 503 hospital pilot gate |

## 8. Verification

```bash
# Phase 1.1 端点 unit
cd backend && pytest tests/test_api/test_v2_tools_coding.py -v
# 全量回归 (Phase 1.1 + Phase 1.0 + M3-0 不回归)
cd backend && pytest tests/ -q
# 前端 tsc + vite build (跨前后端契约不破坏)
cd frontend && npx tsc --noEmit && npm run build
```

## 9. 后续

| Phase | 内容 |
|---|---|
| 1.2 | `coding` capability scope 注册 + 此端点接入 OAuth (`/api/oauth/realms/.../token`) |
| 1.2 | `/api/v2/text-gen/...` 5 个文本生成端点 (按 Corti §13.4) |
| 1.3 | `/api/v2/interactions/...` 3 个 STT 端点 (按 Corti §13.3) |
| Phase 2 | 前端 MedicalCodingPage 加 v2 endpoint toggle (manual/corti-shape) |

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 无 LLM credential 时 caller 拿到空 codes[] 误以为是真实结果 | hospital pilot gate 在 503 拒绝, 不做 fake codes |
| char-span 精度 (现成 fuzzy 算法 85% 阈值) 被改坏 | 测试 #2 显式 roundtrip 锁定, char-span 算法变更必先绿 |
| display lookup miss (ICD-10-CN 37,897 码极端 case) | fallback `({code})`, 永远不抛 5xx |
| Corti SDK caller 用 US 系统名期望自动 alias | 显式 400 拒绝, 透明暴露体系差异, 不假装兼容 |
