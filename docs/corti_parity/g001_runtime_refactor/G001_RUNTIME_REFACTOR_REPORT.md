# G001 Runtime Refactor — Corti-like Fast Coding Default

> **Refactor date**: 2026-07-09
> **Author**: iCoDer Engineering
> **Status**: ✅ COMPLETE (PASS) — backend 15/15 unit tests, tsc 0 errors, vitest 72/3 pre-existing fail, browser walkthrough verified T12 case at 9.96s (Fast) and 9.19s (Fast retry)

---

## 1. Executive Summary

The iCoDer medical coding main flow has been refactored from a research-type 5-stage MedCodER pipeline (default, 60s+ timeout on real LLM) to a product-type Corti-like single-LLM-call Fast Coding runtime (default, 7-12s latency). The MedCodER 5-stage pipeline is preserved as the opt-in "Deep Evidence" mode for advanced / research / complex-case use.

**Key outcomes**:
- **T12 vertebral compression fracture case** (78yo male, osteoporosis, hypertension, T2DM, percutaneous vertebroplasty): returned in **9.96s** (Fast Coding) vs. **60s+ timeout** before refactor — a 6× latency reduction
- **5 codes** predicted with evidence + rationale + warnings + alternatives per code
- **7-step RunTrace** emitted (input_received → language_detect → build_prompt → llm_call → parse_json → project_result → return)
- **No regressions**: 15/15 G001 backend unit tests pass; 72/75 frontend tests pass (3 pre-existing failures unrelated to G001); 0 tsc errors
- **Browser walkthrough**: real-time latency measured at 9.96s + 9.19s across two T12 runs, Copy JSON / Copy Markdown verified, Config drawer mode selector verified, Event Inspector 7-step trace verified

The refactor unblocks iCoDer from a research-grade 60s+ MedCodER timeout and aligns the medical coding UX with Corti's product-grade ~8s single-LLM-call pattern, while preserving MedCodER as a research option.

---

## 2. Background & Motivation

### 2.1 Pre-refactor state

iCoDer's medical coding main flow was the MedCodER 5-stage pipeline (Baksi et al., NAACL 2025 Industry Track):

```
EMR text
  ↓
[Stage 1: Extraction] (DeepSeek chat, 1 call)
  ↓
[Stage 2: Retrieval] (BGE-M3 + FAISS, local)
  ↓
[Stage 3: Merge]
  ↓
[Stage 4: Re-rank] (DeepSeek, RankGPT-style, 1 call)
  ↓
[Stage 5: Compliance + Calibration]
  ↓
MedicalCodingOutputSchema
```

This pipeline made **2 LLM calls** plus a BGE-M3 embedding pass plus a FAISS retrieval, with total latency 30-60s+ on real DeepSeek API.

### 2.2 Corti reference behavior

Corti's Medical Coding Agent (`medical-coding-icd-10-cpt-agent`) returns results in **~8s** on a single LLM call. The Corti UX is a product-grade single-shot pattern:
- User pastes clinical text → clicks Predict → result returns in ~8s with primary dx + secondary dx + procedures + evidence
- No multi-stage retrieval pipeline in the default path
- Advanced features (evidence ranking, validation) are separate experts invoked on demand

### 2.3 Gap analysis (Phase 4-E3 walkthrough, 2026-07-09)

The Phase 4-E3 iCoDer × Corti browser walkthrough (60 gap findings, 1 S1 critical) identified **G001** as the **#1 critical blocker**:

> G001 (S1 P0): MedCodER 5-stage 60s+ timeout vs Corti ~8s success on T12 fracture case — iCoDer could not return a coding result within Corti's product-grade latency budget.

This refactor closes G001.

---

## 3. Problem Statement

### 3.1 The core problem

The default medical coding main flow was bound to MedCodER's 5-stage pipeline. Real-world T12 vertebral compression fracture cases timed out at 60s+ (the A2A HTTP timeout), making the product unusable for clinical workflow integration.

### 3.2 Why MedCodER is slow

- **Stage 1 (Extract)**: 1 DeepSeek call (5-10s)
- **Stage 2 (Retrieve)**: BGE-M3 embedding (1-2s) + FAISS top-20 retrieval (<1s)
- **Stage 3 (Merge)**: in-process set union (<100ms)
- **Stage 4 (Re-rank)**: 1 DeepSeek call (5-10s)
- **Stage 5 (Compliance + Calibration)**: in-process rule engine (<100ms)

Total LLM time alone: 10-20s. Plus Python overhead, JSON parsing, schema validation, RunTrace emission, A2A envelope wrapping → 30-60s end-to-end.

### 3.3 Why Corti is fast

Corti's default path is a **single LLM call** with a strong coding prompt + dictionary-RAG candidate injection (lightweight keyword extraction, <100ms). No multi-stage retrieval, no re-rank LLM call. Result returns in ~8s.

### 3.4 The opportunity

iCoDer's `DeepSeekCodingAdapter` (existing) already implements a Corti-like single-LLM-call coding flow with:
- Chinese medical coding prompt (system + user)
- Dictionary-RAG candidate injection (lightweight)
- Fault-tolerant JSON parsing (markdown fence stripping, partial JSON repair)
- MedicalCodingOutputSchema projection (primary + secondary + procedures → flat code list)

This adapter was previously the **non-default** path. The refactor promotes it to the default (`corti_like_fast` mode), with MedCodER preserved as `medcoder_deep` opt-in.

---

## 4. Solution Architecture

### 4.1 New CodingRuntime abstraction

A new `app/coding_runtime/` module provides a Protocol-based runtime abstraction with mode-based dispatch:

```
CodingRequest (mode, text, coding_system, ...)
       ↓
CodingRuntimeDispatcher
       ↓
   ┌───────────────┴───────────────┐
   ↓                               ↓
FastCodingRuntime          MedCoderRuntime
(corti_like_fast)          (medcoder_deep)
   ↓                               ↓
DeepSeekCodingAdapter      HybridCodingAdapter
(single LLM call)           (5-stage pipeline)
   ↓                               ↓
CodingResult                CodingResult
(codes, trace, latency, ...) (codes, trace, latency, ...)
```

### 4.2 Modes

| Mode | Display name | Latency target | Use case |
|---|---|---|---|
| `corti_like_fast` | Fast Coding | 7-12s | **Default** — product-grade single LLM call, Corti-style |
| `medcoder_deep` | Deep Evidence | 30-60s+ | Advanced / research / complex-case — 5-stage MedCodER pipeline |

### 4.3 Files added

```
backend/app/coding_runtime/
  __init__.py             # SSOT exports
  base.py                 # CodingRequest, CodingResult, CodingRuntime Protocol, RuntimeMode
  fast_runtime.py         # FastCodingRuntime (wraps DeepSeekCodingAdapter, 7-step trace)
  medcoder_runtime.py     # MedCoderRuntime (wraps HybridCodingAdapter, 5-stage trace)
  dispatcher.py           # CodingRuntimeDispatcher + get_dispatcher singleton

backend/app/api/coding_predict.py  # POST /api/v1/coding/predict

backend/tests/coding_runtime/test_g001_runtime.py  # 15 unit tests
```

### 4.4 Files modified

```
backend/app/main.py                                       # include coding_predict_router
frontend/src/services/api.ts                              # codingApi.predict() with mode-aware timeout
frontend/src/pages/MedicalCodingPage.tsx                  # Config drawer mode selector + result display
```

---

## 5. Implementation Details

### 5.1 `base.py` — Runtime contracts

**RuntimeMode** (StrEnum):
```python
class RuntimeMode(StrEnum):
    CORTI_LIKE_FAST = "corti_like_fast"
    MEDCODER_DEEP = "medcoder_deep"

    @classmethod
    def coerce(cls, value: str | None) -> "RuntimeMode":
        # Falls back to CORTI_LIKE_FAST on unknown / None
```

**CodingRequest** (dataclass):
```python
@dataclass
class CodingRequest:
    text: str
    mode: RuntimeMode = RuntimeMode.CORTI_LIKE_FAST
    coding_system: str = "icd10cn"
    include_evidence: bool = True
    include_trace: bool = True
    run_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
```

**CodingResultCode** (dataclass) — per-code structure (Corti 8-field-aligned):
```python
@dataclass
class CodingResultCode:
    code: str
    system: str            # "ICD-10-CN" | "ICD-9-CM-3-CN"
    display: str           # code display name
    type: str              # primary_diagnosis | secondary_diagnosis | procedure
    confidence: float      # 0.0 - 1.0
    evidence: str          # char-anchored evidence spans (semicolon-separated)
    rationale: str         # why this code was selected
    warnings: list[str]    # e.g., ["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"]
    alternatives: list[dict]  # top-K alternative codes (Deep mode only)
```

**CodingResult** (dataclass):
```python
@dataclass
class CodingResult:
    codes: list[CodingResultCode]
    summary: str                    # natural-language summary (shown in Runtime Info panel)
    runtime_mode: str               # "corti_like_fast" | "medcoder_deep"
    latency_ms: int                 # total runtime latency
    llm_provider: str               # "deepseek" | "mock" | ...
    trace_id: str                   # trace-b5ef067c8c... (RunTrace root ID)
    run_id: str | None = None
    cost: float | None = None
    raw_schema: dict | None = None  # full MedicalCodingOutputSchema for debugging
    trace_events: list[dict] | None = None  # 7-step (Fast) or 5-stage (Deep) trace
    error: bool = False             # True if runtime errored
    error_reason: str | None = None
```

**CodingRuntime** (Protocol):
```python
class CodingRuntime(Protocol):
    async def predict(self, request: CodingRequest) -> CodingResult: ...
```

### 5.2 `fast_runtime.py` — FastCodingRuntime

Wraps the existing `DeepSeekCodingAdapter` (single LLM call). Emits 7-step RunTrace:

| # | Step | Status | Metadata |
|---|---|---|---|
| 1 | `input_received` | ok | `{text_len, mode}` |
| 2 | `language_detect` | ok | `{language: "zh" \| "en"}` |
| 3 | `build_prompt` | ok | `{provider, language, system}` |
| 4 | `llm_call` | ok / error | `{provider, model, is_mock}` |
| 5 | `parse_json` | ok / error | (no metadata) |
| 6 | `project_result` | ok | `{code_count}` |
| 7 | `return` | ok | `{latency_ms, code_count}` |

**Failure handling**: empty input → error result; oversize input (>16000 chars) → error result; LLM call failure → error result; JSON parse failure → error result. **FastCodingRuntime never raises** — always returns a `CodingResult` (with `error=True` on failure).

**Schema projection**: `MedicalCodingOutputSchema.primary_diagnosis + secondary_diagnoses + procedures → flat CodingResultCode list`. Each code gets a default warning `需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目` to enforce human-review discipline.

### 5.3 `medcoder_runtime.py` — MedCoderRuntime

Wraps `HybridCodingAdapter(mode="medcoder.full")` (5-stage pipeline). Emits 5-stage trace:

| # | Step | Status | Metadata |
|---|---|---|---|
| 1 | `stage1_extract` | ok | `{note: "stage1+2+3+4+5 run by HybridCodingAdapter"}` |
| 2 | `stage2_retrieve` | ok | synthetic placeholder if adapter did not emit detailed trace |
| 3 | `stage3_merge` | ok | synthetic placeholder |
| 4 | `stage4_rerank` | ok | synthetic placeholder |
| 5 | `stage5_compliance` | ok | synthetic placeholder |
| 6 | `project_result` | ok | `{code_count}` |
| 7 | `return` | ok | `{latency_ms, code_count}` |

Reads `method_stage_trace` from `MedicalCodingOutputSchema` for real stage events; falls back to synthetic placeholders if absent.

**Schema projection**: `MedicalCodingOutputSchema.extracted_diagnoses → flat codes list` with `alternatives` populated from `final_top_k[1:5]`.

### 5.4 `dispatcher.py` — CodingRuntimeDispatcher

```python
class CodingRuntimeDispatcher:
    def __init__(self): self._fast = None; self._deep = None
    def select_runtime(self, mode: RuntimeMode) -> CodingRuntime:
        if mode == RuntimeMode.MEDCODER_DEEP: return self._deep_runtime()
        return self._fast_runtime()

    async def dispatch(self, request: CodingRequest) -> CodingResult:
        try:
            runtime = self.select_runtime(request.mode)
            return await runtime.predict(request)
        except Exception as e:
            # Never raise — return error result
            return CodingResult(codes=[], summary=f"Runtime crash: {e}", ...)

def get_dispatcher() -> CodingRuntimeDispatcher:  # singleton
def reset_dispatcher() -> None:  # for tests
```

### 5.5 `coding_predict.py` — API endpoint

`POST /api/v1/coding/predict`

**Request** (Pydantic):
```python
class CodingPredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=16000)
    mode: str = "corti_like_fast"  # coerced via RuntimeMode.coerce()
    coding_system: str = "icd10cn"
    include_evidence: bool = True
    include_trace: bool = True
```

**Response** (Pydantic):
```python
class CodingPredictResponse(BaseModel):
    codes: list[CodingResultCodeDTO]
    summary: str
    runtime_mode: str
    latency_ms: int
    llm_provider: str
    trace_id: str
    run_id: str | None
    cost: float | None
    raw_schema: dict | None
    trace_events: list[dict] | None
    error: bool = False
    error_reason: str | None = None
```

**Auth**: `get_current_user` (JWT) + LLM credential gate (`ICODER_CREDENTIAL_LLM` must be set).

**Failure contract**: **never silently times out** — returns `200 OK` with `error=true` on runtime errors, with `summary` containing the failure reason and `error_reason` field for diagnostics. This avoids the previous 60s+ timeout UX.

---

## 6. API Design

### 6.1 Endpoint contract

```http
POST /api/v1/coding/predict
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "text": "患者男，78岁，因摔伤致背部疼痛...",
  "mode": "corti_like_fast",
  "coding_system": "icd10cn",
  "include_evidence": true,
  "include_trace": true
}
```

**Response (200 OK)**:
```json
{
  "codes": [
    {
      "code": "M80.080",
      "system": "ICD-10-CN",
      "display": "骨质疏松性椎体压缩性骨折，胸椎",
      "type": "primary_diagnosis",
      "confidence": 0.95,
      "evidence": "摔伤致背部疼痛伴活动受限 1 天; 绝经后骨质疏松症 5 年; ...",
      "rationale": "主要诊断 — 基于病历证据的优先编码候选...",
      "warnings": ["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"],
      "alternatives": []
    },
    {"code": "I10.x00x002", "system": "ICD-10-CN", "display": "原发性高血压", ...},
    {"code": "E11.900", "system": "ICD-10-CN", "display": "2型糖尿病", ...},
    {"code": "M81.000", "system": "ICD-10-CN", "display": "绝经后骨质疏松症", ...},
    {"code": "81.66", "system": "ICD-9-CM-3-CN", "display": "经皮椎体成形术", ...}
  ],
  "summary": "主要诊断选择骨质疏松性椎体压缩骨折（M80.080）...",
  "runtime_mode": "corti_like_fast",
  "latency_ms": 9957,
  "llm_provider": "deepseek",
  "trace_id": "trace-b03ea12d13e84d98",
  "run_id": null,
  "cost": null,
  "raw_schema": null,
  "trace_events": [
    {"step": "input_received", "status": "ok", "metadata": {"text_len": 297, "mode": "corti_like_fast"}},
    {"step": "language_detect", "status": "ok", "metadata": {"language": "zh"}},
    {"step": "build_prompt", "status": "ok", "metadata": {"provider": "deepseek", "language": "zh", "system": "icd-10-cn"}},
    {"step": "llm_call", "status": "ok", "metadata": {"provider": "deepseek", "model": "deepseek-chat", "is_mock": false}},
    {"step": "parse_json", "status": "ok", "metadata": {}},
    {"step": "project_result", "status": "ok", "metadata": {"code_count": 5}},
    {"step": "return", "status": "ok", "metadata": {"latency_ms": 9957, "code_count": 5}}
  ],
  "error": false,
  "error_reason": null
}
```

### 6.2 Mode-aware timeout

The frontend `codingApi.predict()` uses mode-aware timeout:
- Fast Coding (`corti_like_fast`): 45s timeout
- Deep Evidence (`medcoder_deep`): 120s timeout

This ensures Fast mode never hits timeout (target 7-12s, 45s budget) while Deep mode has a 2-minute budget for the 30-60s+ pipeline.

---

## 7. Frontend Changes

### 7.1 `frontend/src/services/api.ts`

Added `CodingMode` type, `CodingResultCode` interface, `CodingPredictResult` interface, and `codingApi.predict()`:

```typescript
export type CodingMode = 'corti_like_fast' | 'medcoder_deep';

export interface CodingResultCode {
  code: string;
  system: string;
  display: string;
  type: string;
  confidence: number;
  evidence?: string;
  rationale?: string;
  warnings?: string[];
  alternatives?: { code: string; display?: string; confidence?: number }[];
}

export interface CodingPredictResult {
  codes: CodingResultCode[];
  summary: string;
  runtime_mode: string;
  latency_ms: number;
  llm_provider: string;
  trace_id: string;
  run_id?: string | null;
  cost?: number | null;
  raw_schema?: Record<string, unknown> | null;
  trace_events?: { step: string; status: string; metadata?: Record<string, unknown> }[];
  error: boolean;
  error_reason?: string | null;
}

export const codingApi = {
  predict: (text: string, mode: CodingMode = 'corti_like_fast', options?) => {
    const timeout = mode === 'medcoder_deep' ? 120000 : 45000;
    return api.post<CodingPredictResult>('/v1/coding/predict', { text, mode, ...options }, { timeout });
  },
};
```

### 7.2 `frontend/src/pages/MedicalCodingPage.tsx`

**Top toolbar**: added mode indicator badge ("Fast" / "Deep") next to Predict button.

**Config drawer**: added "Coding Mode" section with 2-button grid:
- "Fast Coding" — 单阶段 LLM · ~7-12s · 默认
- "Deep Evidence" — MedCodER 5 阶段 · 30-60s+ · 高级

**handlePredict**: rewrote to call `codingApi.predict()` with `codingMode` state; emits RunTrace events to Event Inspector as they arrive; sets error state if `data.error === true`.

**handleRetry**: new method that re-runs predict; supports `switchToFast` flag to retry in Fast mode after Deep mode timeout.

**Runtime Info panel** (output panel): new component showing:
- Mode badge (Fast Coding / Deep Evidence)
- Latency (`9.96s` / `0.0s`)
- LLM provider (`deepseek`)
- Trace ID (`trace-b03ea12d13e84d98`)
- Summary text
- Error banner with "切换 Fast Coding" button (only shown when `error === true`)

**Per-code detail panel**: clicking a code row expands a detail panel below showing:
- Code + display + type + confidence
- 临床证据 (Clinical Evidence)
- Rationale
- Warnings (with alert icon)
- Alternatives (Deep mode only — top-K re-rank candidates)

**Copy JSON / Copy Markdown buttons**: added to Runtime Info panel. Copy JSON copies the full `CodingPredictResult` envelope (pretty-printed); Copy Markdown copies a structured markdown summary.

**Layout fix (config drawer overflow)**: when `configOpen === true`, the main flex container gets `mr-[400px]` to reserve space for the drawer overlay; the output panel gets `hidden` to avoid being covered by the drawer. This eliminates the "empty space on the right of main" UX issue at 1366px viewport.

### 7.3 Layout verification (1366px viewport)

| State | Input width | Output width | Drawer width | Empty space |
|---|---|---|---|---|
| Drawer closed | 656px | 480px | hidden | none |
| Drawer open | 736px | hidden | 400px (overlay) | none |

---

## 8. RunTrace Design

### 8.1 Fast Coding 7-step trace

```
input_received  → language_detect → build_prompt → llm_call → parse_json → project_result → return
```

Each step has `step`, `status`, `metadata`. The Event Inspector renders these as timestamped rows:
```
17:14:52  [input_received] ok  {"text_len":297,"mode":"corti_like_fast"}
17:14:52  [language_detect] ok  {"language":"zh"}
17:14:52  [build_prompt] ok  {"provider":"deepseek","language":"zh","system":"icd-10-cn"}
17:14:52  [llm_call] ok  {"provider":"deepseek","model":"deepseek-chat","is_mock":false}
17:14:52  [parse_json] ok
17:14:52  [project_result] ok  {"code_count":5}
17:14:52  [return] ok  {"latency_ms":9957,"code_count":5}
17:14:52  已完成 9957ms (corti_like_fast)
```

### 8.2 Deep Evidence 5-stage trace

```
stage1_extract → stage2_retrieve → stage3_merge → stage4_rerank → stage5_compliance → project_result → return
```

When `HybridCodingAdapter` does not emit detailed stage trace, `MedCoderRuntime` falls back to synthetic placeholder events with `note: "synthetic — adapter did not emit detailed trace"`.

---

## 9. Test Results

### 9.1 Backend unit tests (15/15 PASS)

```
tests/coding_runtime/test_g001_runtime.py
  test_runtime_mode_coerce_known_values                         PASSED
  test_runtime_mode_coerce_unknown_falls_back_to_fast            PASSED
  test_dispatcher_routes_fast_to_fast_runtime                    PASSED
  test_dispatcher_routes_deep_to_medcoder_runtime                PASSED
  test_dispatcher_unknown_mode_falls_back_to_fast                PASSED
  test_fast_runtime_empty_input_returns_error_result            PASSED
  test_fast_runtime_oversize_input_returns_error_result          PASSED
  test_fast_runtime_llm_call_failure_returns_error_result        PASSED
  test_fast_runtime_happy_path_returns_structured_codes          PASSED
  test_fast_runtime_chinese_input_detected_as_zh                 PASSED
  test_fast_runtime_english_input_detected_as_en                 PASSED
  test_fast_runtime_json_repair_handles_markdown_fences           PASSED
  test_medcoder_runtime_empty_input_returns_error_result         PASSED
  test_dispatcher_dispatch_fast_returns_coding_result             PASSED
  test_dispatcher_dispatch_unknown_mode_falls_back_to_fast       PASSED

======================== 15 passed, 1 warning in 6.70s ========================
```

Tests use a `_FakeGateway` mock for LLM calls — no real DeepSeek API calls needed in CI.

### 9.2 Frontend tsc + vitest

- `npx tsc --noEmit`: **0 errors** (clean)
- `npx vitest run`: **72 passed / 3 failed** (3 pre-existing failures in `agentHubContract.test.ts`, unrelated to G001, stash-verified per Phase 4-E1 memory)

### 9.3 Browser walkthrough

| Step | Verification | Result |
|---|---|---|
| 1. Login admin/admin123 | JWT acquired | ✅ |
| 2. Navigate to /ai-studio/medical-coding | Page renders, sidebar + 2-column layout | ✅ |
| 3. Open Config drawer | "Coding Mode" section visible with Fast/Deep 2-button grid | ✅ |
| 4. Default mode = Fast Coding | Mode badge shows "Fast" near Predict button | ✅ |
| 5. Input T12 case (297 chars) | Text fills input textarea | ✅ |
| 6. Click Predict (Fast mode) | Request fires with `mode=corti_like_fast` | ✅ |
| 7. Result returns in 9.96s | Latency 9957ms, 5 codes, runtime_mode=corti_like_fast | ✅ |
| 8. Event Inspector shows 7-step trace | All 7 steps rendered with metadata | ✅ |
| 9. Per-code detail panel (M80.080) | Evidence + Rationale + Warnings rendered | ✅ |
| 10. Copy JSON button | Clipboard has 6975 chars of valid CodingResult JSON | ✅ |
| 11. Copy Markdown button | Clipboard has 1497 chars of structured markdown | ✅ |
| 12. Switch to Deep Evidence mode | Mode badge changes to "Deep", Config drawer shows Deep selected | ✅ |
| 13. Predict in Deep mode | Request fires with `mode=medcoder_deep`, 5-stage trace emitted | ✅ |
| 14. Layout overflow fix | Drawer open: input 736px + drawer 400px, no empty space | ✅ |
| 15. Drawer closed: output restored | Input 656px + output 480px, full width | ✅ |

### 9.4 T12 case latency measurements

| Run | Mode | Latency | Codes | Trace steps |
|---|---|---|---|---|
| Run 1 | corti_like_fast | **9.96s** (9957ms) | 5 | 7 (Fast) |
| Run 2 | corti_like_fast | **9.19s** (9190ms) | 5 | 7 (Fast) |

Both runs well under the 15s target and 45s frontend timeout. The 60s+ timeout blocker is **resolved**.

---

## 10. Risks & Mitigations

### 10.1 Risk: Fast Coding less accurate than MedCodER

**Risk**: Single LLM call may miss subtle coding nuances that MedCodER's re-rank + retrieval would catch.

**Mitigation**:
- Fast Coding prompt includes dictionary-RAG candidate injection (lightweight keyword extraction, <100ms) — gives the LLM code candidates upfront
- Default warning on every code: `需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目` — enforces human-review discipline
- Deep Evidence mode preserved for advanced / complex cases
- Phase 4-C Code Validation Agent (LLMWithToolsProvider + 4 MCP tools) provides post-hoc validation layer

### 10.2 Risk: Mode confusion for users

**Risk**: Users may not understand when to use Fast vs. Deep.

**Mitigation**:
- Config drawer has tooltip: "G001: Fast = Corti-like single LLM call (~7-12s). Deep Evidence = MedCodER 5-stage pipeline (30-60s+)."
- Mode badge always visible next to Predict button — user knows current mode
- Deep Evidence error banner includes "切换 Fast Coding" quick-action button

### 10.3 Risk: Deep Evidence still 60s+ in real use

**Risk**: MedCodER pipeline is unchanged — still 30-60s+ on real DeepSeek API.

**Mitigation**:
- Deep Evidence is now opt-in (not default) — users explicitly choose it
- Frontend timeout is 120s for Deep (vs. 45s for Fast) — gives Deep room to complete
- Deep Evidence error result includes "切换 Fast Coding" button to retry in Fast mode

### 10.4 Risk: Backend LLM credential leakage

**Risk**: `/api/v1/coding/predict` could expose LLM credentials in error responses.

**Mitigation**:
- LLM credential check at endpoint entry: `ICODER_CREDENTIAL_LLM` must be set, else 503 with clear message
- LLM calls go through `LLMGateway` (existing) which keeps credentials server-side
- Error responses include only `error_reason` (human-readable), never credentials

### 10.5 Risk: Frontend back-compat breakage

**Risk**: MedicalCodingPage previously used A2A flow (`runtimeAgentApi.runAgentViaA2A`). Switching to `codingApi.predict()` may break existing tests.

**Mitigation**:
- Used `isCodingPredictResult` flag in derived state to support both new `CodingPredictResult` and legacy A2A shape
- Existing A2A flow still works for other agents (MedicalCodingPage is the only consumer of the new endpoint)
- 3 pre-existing vitest failures are in `agentHubContract.test.ts` (unrelated to MedicalCodingPage)

---

## 11. Conclusion & Next Steps

### 11.1 Conclusion

The G001 refactor **unblocks iCoDer's medical coding main flow** from a 60s+ MedCodER timeout, aligning with Corti's product-grade ~8s single-LLM-call pattern. The refactor:

- Promotes `DeepSeekCodingAdapter` (existing) to the default `corti_like_fast` runtime
- Preserves `HybridCodingAdapter` (MedCodER 5-stage) as opt-in `medcoder_deep` runtime
- Adds `CodingRuntime` Protocol + `CodingRuntimeDispatcher` for mode-based dispatch
- Adds `POST /api/v1/coding/predict` API with mode parameter
- Adds mode selector + Runtime Info panel + per-code detail panel + Copy JSON/Markdown to MedicalCodingPage
- Emits 7-step (Fast) / 5-stage (Deep) RunTrace
- **Fixes the 60s+ timeout**: T12 case now returns in 9.96s (Fast) / still 30-60s+ (Deep, opt-in)

**Verified at unit, integration, and browser levels** — 15/15 backend tests, 72/75 frontend tests, 0 tsc errors, real T12 case latency 9.96s + 9.19s across two runs.

### 11.2 Next steps

1. **Phase 4-F1**: A/B test Fast vs. Deep accuracy on the 201-case iCoDer gold set — measure F1@1 / F1@5 / per-case micro-F1 for both modes
2. **Phase 4-F2**: Add a "Confidence Threshold" filter to Fast mode (already in Config drawer, currently decorative) — filter codes by `confidence >= threshold` before display
3. **Phase 4-F3**: Wire Fast mode's dictionary-RAG candidate injection to actually pull from `icd10cn_code_catalog` (currently lightweight keyword extraction only)
4. **Phase 4-F4**: Add streaming SSE support to `/api/v1/coding/predict` — emit RunTrace events as they happen (currently returned in single response)
5. **Phase 4-F5**: Add "Compare Modes" feature — run both Fast and Deep on same case, show diff (Corti has no equivalent; this would be an iCoDer differentiator)

---

## Appendix A: T12 case text

```
患者男，78岁，因"摔伤致背部疼痛伴活动受限 1 天"入院。既往有原发性高血压 20 年，
长期口服氨氯地平 5mg qd，血压控制在 130/80 mmHg 左右；2 型糖尿病 10 年，口服
二甲双胍 0.5g bid，血糖控制可；绝经后骨质疏松症 5 年，曾间断服用阿仑膦酸钠。
入院查体：T12 椎体棘突压痛、叩击痛阳性，双下肢感觉运动正常。X 线及 MRI 示
T12 椎体压缩性骨折，椎体高度丢失约 30%，未见椎管内占位。完善术前检查后在全身
麻醉下行经皮椎体成形术（T12），手术顺利，术后疼痛明显缓解。术后予抗骨质疏松
（唑来膦酸）、降压、降糖及抗凝治疗，恢复良好，术后第 5 天出院。
```

## Appendix B: T12 Fast Coding result (Run 1)

| # | Code | System | Display | Type | Confidence |
|---|---|---|---|---|---|
| 1 | M80.080 | ICD-10-CN | 骨质疏松性椎体压缩性骨折，胸椎 | primary_diagnosis | 95% |
| 2 | I10.x00x002 | ICD-10-CN | 原发性高血压 | secondary_diagnosis | 95% |
| 3 | E11.900 | ICD-10-CN | 2型糖尿病 | secondary_diagnosis | 95% |
| 4 | M81.000 | ICD-10-CN | 绝经后骨质疏松症 | secondary_diagnosis | 95% |
| 5 | 81.66 | ICD-9-CM-3-CN | 经皮椎体成形术 | procedure | 95% |

**Runtime info**:
- Mode: corti_like_fast
- Latency: 9.96s (9957ms)
- LLM provider: deepseek
- Trace ID: trace-b03ea12d13e84d98
- Summary: 主要诊断选择骨质疏松性椎体压缩骨折（M80.080），因患者有明确骨质疏松病史且骨折由轻微外伤引起，符合骨质疏松性骨折定义。避免使用M48.56（椎体压缩骨折未特指）或M81.9（骨质疏松未特指），因病历明确为绝经后骨质疏松。

## Appendix C: Related files

**Backend (new)**:
- `backend/app/coding_runtime/__init__.py`
- `backend/app/coding_runtime/base.py`
- `backend/app/coding_runtime/fast_runtime.py`
- `backend/app/coding_runtime/medcoder_runtime.py`
- `backend/app/coding_runtime/dispatcher.py`
- `backend/app/api/coding_predict.py`
- `backend/tests/coding_runtime/test_g001_runtime.py`

**Backend (modified)**:
- `backend/app/main.py` (added coding_predict_router)

**Frontend (modified)**:
- `frontend/src/services/api.ts` (added codingApi.predict with mode-aware timeout)
- `frontend/src/pages/MedicalCodingPage.tsx` (Config drawer mode selector + Runtime Info panel + per-code detail + Copy JSON/Markdown + layout fix)

**Docs**:
- `docs/corti_parity/g001_runtime_refactor/G001_RUNTIME_REFACTOR_REPORT.md` (this file)
- `docs/corti_parity/g001_runtime_refactor/G001_RUNTIME_ARCHITECTURE.md`
- `docs/corti_parity/g001_runtime_refactor/G001_FAST_CODING_PROMPT.md`
- `docs/corti_parity/g001_runtime_refactor/G001_BROWSER_WALKTHROUGH_LOG.md`
- `docs/corti_parity/g001_runtime_refactor/G001_TEST_RESULTS.md`
- `docs/corti_parity/g001_runtime_refactor/screenshots/` (15 screenshots)
