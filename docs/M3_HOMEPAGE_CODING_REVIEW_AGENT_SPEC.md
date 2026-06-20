# M3-0 / M3-1 — 病案首页编码审核 Agent (Homepage Coding Review Agent) 规范

**日期**: 2026-06-10
**阶段**: M3-0 (链路验证) / M3-1 (产品化闭环)
**目标**: 在 iCoDer Runtime 上交付 iCoDer 第一个官方样板 Agent, 验证 Runtime / 14 阶段工具编排 / 证据回链 / 风险路由 / 医学安全门禁 / 人工复核 / 审计 / API / 嵌入组件 端到端能力。

---

## 0. 关键定位 (硬性)

- **iCoDer** = 医疗收入合规 AI Runtime 基础设施 (面向 Agent 开发 + 运行, 部署在医院内网)
- **本 Agent** = iCoDer 上的 **第一个官方样板 Agent** (Official Reference Agent / Starter Agent)
- 本 Agent **不可被视为 iCoDer 全部产品定位**, 不代表 iCoDer 商业化形态
- **不在 M3-0 阶段做 SFT、不改 B0、不编造模型预测**。M3-0 是 **pipeline validation** 模式, 验证 Runtime 全链路。
- **production_writeback_blocked 永远为 true** (M3-0 硬性)

---

## 1. Agent 标识

| 字段 | 值 |
|------|----|
| `agent_ref` | `icoder/homepage-coding-review-agent@1.0.0` |
| `agent_category` | `official_reference_agent` |
| `agent_subcategory` | `homepage-coding-review` |
| `agent_type` | `certified` |
| `format_version` | `1.1` |
| `is_reference_agent` | `true` (硬性) |
| `is_product_positioning` | `false` (硬性) |
| `positioning` | `official_starter_agent` |
| `validation_mode_default` | `link_validation` |
| `fabrication_forbidden` | `true` |

注册位置: `backend/official_agents/homepage-coding-review/agent_pack.json`
Python 入口: `backend/official_agents/homepage_coding_review.py` (underscore 别名, 绕开 hyphen 命名)

---

## 2. 14 阶段工具编排 (硬性)

| # | 阶段 | 工具 | 职责 | 失败行为 |
|---|------|------|------|----------|
| 1 | `document_normalizer` | `icoder.document_normalizer` | 标点统一 / 段落切分 / 时间归一 | 失败 → 整体 unavailable |
| 2 | `evidence_fact_extractor` | `icoder.evidence_fact_extractor` | 抽取疾病/手术事实 + 证据 span | 失败 → 整体 unavailable |
| 3 | `coding_eligibility_classifier` | `icoder.coding_eligibility_classifier` | 排除既往史/否定/不确定 | 失败 → 整体 unavailable |
| 4 | `candidate_generator` | `icoder.candidate_generator` | LLM 生成候选 ICD-10 码 | 失败 → 降级 mock fallback |
| 5 | `ontology_service` | `icoder.ontology_service` | icd10cn_code_catalog + synonym_map 查询 | 失败 → 跳过, 标 warning |
| 6 | `high_risk_coding_point_checker` | `icoder.high_risk_coding_point_checker` | **5 重点码 + 62 全集**检查 | 失败 → 标 warning, 不阻塞 |
| 7 | `kg_auditor` | `icoder.kg_auditor` | coding_differentiation_kb P0/P1/P2 | 失败 → 标 warning |
| 8 | `code_reconciler` | `icoder.code_reconciler` | 候选码去重 + 冲突消解 | 失败 → 标 warning |
| 9 | `risk_router` | `icoder.risk_router` | M2a 4 档风险路由 (low/medium/high/critical) | 失败 → 标 warning, 落到 medium |
| 10 | `medical_safety_gate` | `icoder.medical_safety_gate` | 主诊断损伤 / 证据不足 / 高风险 | 失败 → 标 warning, 不阻塞 |
| 11 | `human_review` | `icoder.human_review` | 调 `/{run_id}/human-review` | 由 frontend 触发 |
| 12 | `report_generator` | `icoder.report_generator` | 生成 18 节 HTML 报告 | 失败 → 标 warning |
| 13 | `run_trace_emitter` | `icoder.run_trace_emitter` | M2aRecorder.inference/ctx.stage | 失败 → 标 warning, 不阻塞 |
| 14 | `audit_logger` | `icoder.audit_logger` | 审计日志 (含 reviewer / reviewer_role / reason_code) | 失败 → 标 warning, 不阻塞 |

**实测顺序**: `pipeline_stages_observed` 按完成顺序追加; UI 上固定 14 阶段, 未触发显示 skipped。

---

## 3. 5 重点高风险易错编码点 (硬性)

| Code | 中文名 | 相邻混淆码 | 检查器 |
|------|--------|-----------|--------|
| `I66.901` | 脑梗死 | I63.900, I67.900 | `high_risk_coding_point_checker` |
| `J98.414` | 肺不张 | J18.900, J96.900 | `high_risk_coding_point_checker` |
| `M80.900` | 骨质疏松 w/ 病理性骨折 | M81.900, S32.000 | `high_risk_coding_point_checker` |
| `45.1600x001` | 胃镜活检 | 45.2300, 45.2500 | `high_risk_coding_point_checker` |
| `Z51.102` | 化疗 | Z51.000, Z08.000 | `high_risk_coding_point_checker` |

**硬性规则**:
- 触发 → `human_review_required=true`
- 触发 → `is_priority=true` (前端 ★ 重点 标记)
- 触发 → 主诊断 reject / insufficient_evidence 必须人工 reason_code 显式注明
- 触发 → primary_disease modify 必须提供 `new_code`

---

## 4. API 规范

### 4.1 `POST /api/icoder/coding-review/run`

**Request**:
```json
{
  "encounter_text": "string (可选)",
  "mode": "link_validation | model_evaluation",
  "case_id": "string",
  "input_source": "string",
  "primary_disease_codes": "I20.000",
  "other_disease_codes": "I10.x00,E11.900",
  "primary_surgery_codes": "",
  "other_surgery_codes": ""
}
```

**Response 200**:
```json
{
  "run_id": "uuid",
  "trace_id": "uuid",
  "agent_ref": "icoder/homepage-coding-review-agent@1.0.0",
  "agent_category": "official_reference_agent",
  "prediction_mode": "link_validation",
  "status": "ok | unavailable | degraded",
  "degraded": false,
  "business_result_generated": true,
  "manual_review_required": true,
  "reason": "string",
  "primary_diagnosis": { "code": "", "description": "", "confidence": 0.0, "category": "principal", "evidence": [], "human_review_required": false, "risk_level": "low" },
  "secondary_diagnoses": [],
  "procedures": [],
  "high_risk_coding_points": [],
  "evidence_chain": [],
  "risk_route": { "level": "low|medium|high|critical|unknown", "reasons": [], "sample_rejected": false, "high_risk_hits": [] },
  "safety_gate": { "rule_count": 0, "block_count": 0, "rules": [] },
  "pipeline_stages_observed": [],
  "trace_url": "/api/m2a/runs/{run_id}",
  "human_review_url": "/api/icoder/coding-review/{run_id}/human-review",
  "report_url": "/api/icoder/coding-review/{run_id}/report",
  "started_at": "ISO8601",
  "finished_at": "ISO8601"
}
```

**特殊响应**:
- 完全无输入 → `status=unavailable`, `degraded=true`, `business_result_generated=false`, `manual_review_required=true`, `reason` 含 "empty"/"无"
- `mode=model_evaluation` → **501 Not Implemented** (M3-0 不可用)
- 任何错误 → `degraded=true` + 详细 `reason`

### 4.2 `POST /api/icoder/coding-review/{run_id}/human-review`

**Request**:
```json
{
  "action": "accept | reject | modify | insufficient_evidence | escalate",
  "target_code": "string",
  "target_role": "primary_disease | other_disease | primary_surgery | other_surgery",
  "new_code": "string (modify 时必填, 主诊断 modify 时强制)",
  "reason_code": "string (必填, R001-R010 + 自定义)",
  "review_note": "string (可选)",
  "reviewer": "string (必填, 审核人 ID)",
  "reviewer_role": "admin | coder | medical_insurance_reviewer | it_operator | auditor"
}
```

**校验规则 (M3-0 硬性)**:
1. `action` 必须 ∈ {accept, reject, modify, insufficient_evidence, escalate}
2. `reason_code` 必填
3. `reviewer` 必填
4. `target_role=primary_disease` + `action=modify` → 必须有 `new_code`
5. `target_code ∈ 5 重点码` + `action ∈ {reject, insufficient_evidence}` → 必须有显式 `reason_code`

**Response**:
```json
{
  "run_id": "uuid",
  "accepted": true | false,
  "record_id": "uuid",
  "action": "string",
  "target_code": "string",
  "new_code": "string",
  "production_writeback_blocked": true,
  "validation_errors": [],
  "warnings": [],
  "audit_log_entry": { ... },
  "recorded_at": "ISO8601"
}
```

**`production_writeback_blocked` 永远为 `true`** (M3-0 硬性)。

### 4.3 `GET /api/icoder/coding-review/{run_id}/report?format=html|json`

**Response**:
- HTML → 18 节报告, 包含 pipeline validation disclaimer
- JSON → 完整结构化报告

### 4.4 `GET /api/icoder/coding-review/{run_id}` / `GET /api/icoder/coding-review/`

只读元数据, 用于 M3-0 调试。

---

## 5. 报告生成器 — 18 节 (硬性)

报告 HTML 包含 18 节, 顺序固定:

1. Agent 名称与版本
2. Run ID / Trace ID
3. 运行时间 (started_at / finished_at)
4. 输入来源 (input_source)
5. prediction_mode (link_validation / model_evaluation)
6. 模型版本 (M3-0 阶段: `unknown (M3-0 阶段未接 prediction file)`)
7. 码表版本 (`icd10cn_code_catalog 37,897 codes (M3-0 baseline)`)
8. 规则版本 (`medical_coding R001-R010 (M3-0 baseline)`)
9. 主诊断审核结果
10. 其他诊断审核结果
11. 手术操作审核结果
12. 高风险易错编码点 (**5 重点码必带 `**PRIORITY**` 标记**)
13. 证据回链
14. 人工复核记录
15. 风险路由结果
16. 医学安全门禁结果
17. 审计日志摘要
18. 免责声明 (**Pipeline Validation 模式必显**)

**Pipeline Validation Disclaimer (M3-0 硬性)**:
> 本报告由 iCoDer 病案首页编码审核 Agent 在 **Pipeline Validation 模式**下生成, 验证 iCoDer Runtime / 14 阶段工具编排 / 证据回链 / 风险路由 / 医学安全门禁 / 人工复核 / 审计 / API / 嵌入组件 端到端能力。**不代表模型效果**, **不可用于生产写回** (production_writeback_blocked=true)。M3-0 阶段不接 prediction file。

实现: `backend/icoder_runtime/reports/coding_review_report.py::render_report()`

---

## 6. 前端组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `IcoderCodingReviewApi` | `frontend/src/services/icoderCodingReviewApi.ts` | API 客户端 + 14 阶段 labels + 5 重点码 |
| `EvidenceViewer` | `frontend/src/components/icoder/EvidenceViewer.tsx` | Apple-minimal 证据高亮, 3 类 + 6 人工标记 |
| `HighRiskCodingPointPanel` | `frontend/src/components/icoder/HighRiskCodingPointPanel.tsx` | 5 重点码 + 相邻混淆码 + 复核状态 |
| `RunTraceTimeline` | `frontend/src/components/icoder/RunTraceTimeline.tsx` | 14 阶段 TUI 风格追踪, 可点击展开 |
| `CodingReviewWorkbenchPage` | `frontend/src/pages/CodingReviewWorkbenchPage.tsx` | 3 列布局: 原文 / 编码建议 / 证据与风险 + 底部 RunTrace + 人工复核条 |
| `IcoderReviewPanel` | `frontend/src/components/embed/IcoderReviewPanel.tsx` | Embed 主组件 (chrome-less) |
| `IcoderEvidenceViewer` | `frontend/src/components/embed/IcoderEvidenceViewer.tsx` | Embed 证据回链 |
| `IcoderTraceViewer` | `frontend/src/components/embed/IcoderTraceViewer.tsx` | Embed 运行追踪 |
| `EmbedDemoCodingReviewPage` | `frontend/src/pages/EmbedDemoCodingReviewPage.tsx` | 模拟第三方 HIS 的 Embed 演示 |

路由:
- `/studio/agents/homepage-coding-review` → CodingReviewWorkbenchPage
- `/runtime/coding-review` → CodingReviewWorkbenchPage
- `/runtime/coding-review/:runId` → CodingReviewWorkbenchPage (加载既有 run)
- `/embed-demo/coding-review` → EmbedDemoCodingReviewPage

---

## 7. 复用 vs 不复用 (硬性边界)

**复用**:
- `HybridCodingAdapter` (M2a inference)
- `RiskRouter` (M2a 4 档)
- `MedicalSafetyGate` (M2a)
- `M2aRecorder.inference()` + `_InferenceContext.stage()` (Run Trace)
- `RunTraceService` (start_run / add_tool_call / finalize_run)
- `icd10cn_code_catalog` + `icd10cn_synonym_map` (ontology_service)
- `evidence_anchoring_kb` (high_risk_coding_point_checker)
- `coding_differentiation_kb` (kg_auditor)
- `gold_disease_catalog` (code_reconciler)

**不修改**:
- M2a 任何运行时路径 (`AgentRunner.run()`, `LLMGateway`, `M2aRecorder`)
- M2b 任何 4 个核心样本 (`m2b_smoke_eval_20/50`, `m2b_full_candidate_pool_1800`, `m2b_high_risk_coding_points`)
- 752 个旧测试

---

## 8. 测试覆盖 (18 项, M3-0 硬性)

详见 `backend/tests/test_services/test_m3_homepage_coding_review.py`:

| 组 | 项 | 数量 |
|----|-----|------|
| A. 样板 Agent Manifest | 标识 / pack / positioning | 3 |
| B. 报告生成器 | 18 节 / disclaimer / PRIORITY 标记 | 3 |
| C. coding-review API | run (5) / human-review (3) | 8 |
| D. 不破坏 M2a/M2b | runtime routes / runner / recorder / M2b samples | 4 |
| **合计** | | **18** |

---

## 9. 已知边界与未做事项 (M3-0)

未做 (M3+ 才做):
- B0 prediction file 接入 (`mode=model_evaluation` 当前返回 501)
- Run Trace 阶段级 tool_run_id / 耗时 (M3-0 阶段后端未填充, 前端占位渲染)
- evidence_anchoring_kb 完整 6,490 patterns 接入 (M3-0 阶段只检查 5 重点码 + 62 全集)
- gold_disease_catalog 全量 normalization
- cot_generation_progress_v2 few-shot 接入 rerank
- 数据资产版本元数据 (model_version / code_dict_version / rule_version 当前是 hard-coded baseline)
- 审计日志查询 UI (Audit Log API 不在本 M3-0 范围)

---

## 10. 调用链 (端到端)

```
[Frontend]  CodingReviewWorkbenchPage (3 列布局)
   │
   │  POST /api/icoder/coding-review/run
   │  {encounter_text, primary_disease_codes, ..., mode=link_validation}
   ▼
[Backend]   app/api/icoder_coding_review.py::run_coding_review
   │
   ├── 1. _split_codes / _detect_high_risk (5 重点 + 62 全集)
   ├── 2. _execute_pipeline_14_stages
   │     ├── 1-4. HybridCodingAdapter.infer_async (M2a 复用)
   │     ├── 5.   ontology_service
   │     ├── 6.   high_risk_coding_point_checker (5 + 62)
   │     ├── 7.   kg_auditor
   │     ├── 8.   code_reconciler
   │     ├── 9.   RiskRouter (M2a)
   │     ├── 10.  MedicalSafetyGate (M2a)
   │     ├── 11.  human_review (frontend 后续触发)
   │     ├── 12.  report_generator (M3-0: inline)
   │     ├── 13.  run_trace_emitter (M2aRecorder.inference/ctx.stage)
   │     └── 14.  audit_logger
   │
   │  200 OK + CodingReviewRunResponse
   ▼
[Frontend]  3 列布局渲染: 原文 / 编码建议 (CodeCardGroup) / 证据与风险
            RunTraceTimeline (14 阶段)
            人工复核操作条 (accept / reject / modify)
   │
   │  POST /api/icoder/coding-review/{run_id}/human-review
   ▼
[Backend]   validate 5 规则 → record → 永远 production_writeback_blocked=true
   │
   │  GET /api/icoder/coding-review/{run_id}/report?format=html
   ▼
[Frontend]  下载 18 节 HTML 报告 (含 pipeline validation disclaimer)
```

---

## 11. 变更日志

| 日期 | 阶段 | 内容 |
|------|------|------|
| 2026-06-10 | M3-0 | Agent manifest + 14 阶段编排 + run/human-review/report API + 18 节报告 + 5 重点码 + Apple-minimal UI + 18 测试全绿 + 752 旧测试不破 |
| 2026-06+ | M3-1 | B0 prediction 接入 (model_evaluation 模式可用) + Run Trace 阶段级 tool_run_id + 数据资产版本元数据 |
