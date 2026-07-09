# G001 Runtime Architecture — Corti-like Fast Coding Dispatch

> **Refactor date**: 2026-07-09
> **Module**: `backend/app/coding_runtime/`
> **Related**: [G001_RUNTIME_REFACTOR_REPORT.md](./G001_RUNTIME_REFACTOR_REPORT.md)

---

## 1. Module overview

`backend/app/coding_runtime/` is the new SSOT (single source of truth) for the CodingRuntime abstraction. It provides:

- A Protocol-based runtime interface (`CodingRuntime`)
- Two runtime implementations: `FastCodingRuntime` (Corti-like single LLM call) + `MedCoderRuntime` (MedCodER 5-stage pipeline)
- A dispatcher (`CodingRuntimeDispatcher`) that routes a `CodingRequest` to the appropriate runtime based on `request.mode`
- A singleton accessor (`get_dispatcher()`) for app-state integration
- A test reset hook (`reset_dispatcher()`) for unit tests

```
backend/app/coding_runtime/
  __init__.py             # SSOT exports
  base.py                 # CodingRequest, CodingResult, CodingRuntime Protocol, RuntimeMode
  fast_runtime.py         # FastCodingRuntime (wraps DeepSeekCodingAdapter, 7-step trace)
  medcoder_runtime.py     # MedCoderRuntime (wraps HybridCodingAdapter, 5-stage trace)
  dispatcher.py           # CodingRuntimeDispatcher + get_dispatcher singleton
```

---

## 2. High-level architecture

```
                        ┌──────────────────────────────────────────┐
                        │  Frontend (React SPA)                    │
                        │  MedicalCodingPage.tsx                   │
                        │  ┌─────────────────────────────────────┐ │
                        │  │  Input textarea + Predict button    │ │
                        │  │  Config drawer (mode selector)      │ │
                        │  │  Output panel (Runtime Info +       │ │
                        │  │    codes table + per-code detail)   │ │
                        │  │  Event Inspector (RunTrace)         │ │
                        │  └─────────────────────────────────────┘ │
                        └──────────────────┬───────────────────────┘
                                           │ POST /api/v1/coding/predict
                                           │ { text, mode, coding_system, ... }
                                           ▼
                        ┌──────────────────────────────────────────┐
                        │  Backend (FastAPI)                       │
                        │  app/api/coding_predict.py               │
                        │  ┌─────────────────────────────────────┐ │
                        │  │  Auth (get_current_user + JWT)      │ │
                        │  │  LLM credential gate                 │ │
                        │  │  Pydantic request/response models   │ │
                        │  │  → CodingRequest (dataclass)         │ │
                        │  │  → dispatcher.dispatch(req)         │ │
                        │  │  → CodingPredictResponse             │ │
                        │  └──────────────────┬──────────────────┘ │
                        └─────────────────────┼───────────────────┘
                                              │
                                              ▼
                        ┌──────────────────────────────────────────┐
                        │  app/coding_runtime/dispatcher.py        │
                        │  CodingRuntimeDispatcher                │
                        │  ┌─────────────────────────────────────┐ │
                        │  │  select_runtime(mode)                │ │
                        │  │    - corti_like_fast → _fast_runtime │ │
                        │  │    - medcoder_deep   → _deep_runtime │ │
                        │  │  dispatch(request) → CodingResult   │ │
                        │  │  (never raises — catches crashes)   │ │
                        │  └──────────────────┬──────────────────┘ │
                        └─────────────────────┼───────────────────┘
                                              │
                          ┌───────────────────┴───────────────────┐
                          │                                       │
                          ▼                                       ▼
        ┌─────────────────────────────┐         ┌─────────────────────────────┐
        │  FastCodingRuntime          │         │  MedCoderRuntime            │
        │  (corti_like_fast)           │         │  (medcoder_deep)            │
        │  ┌─────────────────────────┐ │         │  ┌─────────────────────────┐ │
        │  │ 7-step RunTrace emit:  │ │         │  │ 5-stage RunTrace emit:  │ │
        │  │  input_received         │ │         │  │  stage1_extract         │ │
        │  │  language_detect        │ │         │  │  stage2_retrieve         │ │
        │  │  build_prompt           │ │         │  │  stage3_merge            │ │
        │  │  llm_call               │ │         │  │  stage4_rerank          │ │
        │  │  parse_json             │ │         │  │  stage5_compliance       │ │
        │  │  project_result         │ │         │  │  project_result          │ │
        │  │  return                 │ │         │  │  return                  │ │
        │  └─────────────────────────┘ │         │  └─────────────────────────┘ │
        │           │                   │         │              │              │
        │           ▼                   │         │              ▼              │
        │  DeepSeekCodingAdapter       │         │  HybridCodingAdapter       │
        │  (single LLM call)           │         │  (5-stage pipeline)         │
        │           │                   │         │              │              │
        │           ▼                   │         │  ┌────────────────────────┐ │
        │  MedicalCodingOutputSchema   │         │  │ Stage 1: Extraction     │ │
        │  (primary + secondary +      │         │  │   (DeepSeek chat, 1 call)│ │
        │   procedures)                 │         │  ├────────────────────────┤ │
        │           │                   │         │  │ Stage 2: Retrieval      │ │
        │           ▼                   │         │  │   (BGE-M3 + FAISS local)│ │
        │  project_to_coding_result()  │         │  ├────────────────────────┤ │
        │  → CodingResultCode[]        │         │  │ Stage 3: Merge          │ │
        │  → CodingResult              │         │  │   (in-process set union) │ │
        │           │                   │         │  ├────────────────────────┤ │
        └───────────┼───────────────────┘         │  │ Stage 4: Re-rank        │ │
                    │                             │  │   (DeepSeek RankGPT)    │ │
                    │                             │  ├────────────────────────┤ │
                    │                             │  │ Stage 5: Compliance    │ │
                    │                             │  │   (MedicalCodingRuleSet)│ │
                    │                             │  └────────────────────────┘ │
                    │                             │              │              │
                    │                             │              ▼              │
                    │                             │  MedicalCodingOutputSchema  │
                    │                             │  (extracted_diagnoses)      │
                    │                             │              │              │
                    │                             │              ▼              │
                    │                             │  project_to_coding_result() │
                    │                             │  → CodingResultCode[]      │
                    │                             │  → CodingResult             │
                    │                             └──────────────┼──────────────┘
                    │                                            │
                    └──────────────────┬─────────────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────────────────┐
                        │  CodingPredictResponse (Pydantic)        │
                        │  - codes: list[CodingResultCodeDTO]      │
                        │  - summary, runtime_mode, latency_ms     │
                        │  - llm_provider, trace_id, run_id        │
                        │  - trace_events: list[dict]              │
                        │  - error, error_reason                   │
                        └──────────────────────────────────────────┘
```

---

## 3. Component breakdown

### 3.1 `base.py` — Runtime contracts

```python
class RuntimeMode(StrEnum):
    CORTI_LIKE_FAST = "corti_like_fast"  # default
    MEDCODER_DEEP = "medcoder_deep"       # opt-in

    @classmethod
    def coerce(cls, value: str | None) -> "RuntimeMode":
        # Maps known values to enum, falls back to CORTI_LIKE_FAST on unknown/None

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

@dataclass
class CodingResultCode:
    code: str
    system: str               # "ICD-10-CN" | "ICD-9-CM-3-CN"
    display: str
    type: str                 # primary_diagnosis | secondary_diagnosis | procedure
    confidence: float         # 0.0 - 1.0
    evidence: str             # char-anchored evidence spans
    rationale: str
    warnings: list[str]
    alternatives: list[dict]  # Deep mode only

@dataclass
class CodingResult:
    codes: list[CodingResultCode]
    summary: str
    runtime_mode: str
    latency_ms: int
    llm_provider: str
    trace_id: str
    run_id: str | None = None
    cost: float | None = None
    raw_schema: dict | None = None
    trace_events: list[dict] | None = None
    error: bool = False
    error_reason: str | None = None

class CodingRuntime(Protocol):
    async def predict(self, request: CodingRequest) -> CodingResult: ...
```

### 3.2 `fast_runtime.py` — FastCodingRuntime

```python
class FastCodingRuntime:
    def __init__(self):
        self._adapter: DeepSeekCodingAdapter | None = None

    async def predict(self, request: CodingRequest) -> CodingResult:
        # 7-step trace
        # 1. input_received (text_len, mode)
        # 2. language_detect (zh / en, via regex on CJK chars)
        # 3. build_prompt (provider, language, system)
        # 4. llm_call (provider, model, is_mock)  ← actual LLM call
        # 5. parse_json (markdown fence stripping, partial JSON repair)
        # 6. project_result (code_count)  ← MedicalCodingOutputSchema → flat codes
        # 7. return (latency_ms, code_count)

        # Guards:
        # - empty input → error result (never raises)
        # - oversize input (>16000 chars) → error result
        # - LLM call failure → error result (detects DS001 error schema → friendly message)
        # - JSON parse failure → error result

        # Schema projection:
        # - primary_diagnosis → CodingResultCode(type="primary_diagnosis")
        # - secondary_diagnoses → CodingResultCode(type="secondary_diagnosis") × N
        # - procedures → CodingResultCode(type="procedure") × N
        # - Each code gets default warning:
        #   "需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"
```

### 3.3 `medcoder_runtime.py` — MedCoderRuntime

```python
class MedCoderRuntime:
    def __init__(self):
        self._adapter: HybridCodingAdapter | None = None

    async def predict(self, request: CodingRequest) -> CodingResult:
        # 5-stage trace (reads method_stage_trace from schema if present,
        #                 falls back to synthetic placeholders)
        # 1. stage1_extract
        # 2. stage2_retrieve
        # 3. stage3_merge
        # 4. stage4_rerank
        # 5. stage5_compliance
        # 6. project_result (code_count)
        # 7. return (latency_ms, code_count)

        # Schema projection:
        # - extracted_diagnoses → flat codes list
        # - alternatives populated from final_top_k[1:5] (top-K re-rank)
```

### 3.4 `dispatcher.py` — CodingRuntimeDispatcher

```python
class CodingRuntimeDispatcher:
    def __init__(self):
        self._fast: FastCodingRuntime | None = None  # lazy
        self._deep: MedCoderRuntime | None = None    # lazy

    def _fast_runtime(self) -> FastCodingRuntime:
        if self._fast is None:
            self._fast = FastCodingRuntime()
        return self._fast

    def _deep_runtime(self) -> MedCoderRuntime:
        if self._deep is None:
            self._deep = MedCoderRuntime()
        return self._deep

    def select_runtime(self, mode: RuntimeMode) -> CodingRuntime:
        if mode == RuntimeMode.MEDCODER_DEEP:
            return self._deep_runtime()
        return self._fast_runtime()

    async def dispatch(self, request: CodingRequest) -> CodingResult:
        try:
            runtime = self.select_runtime(request.mode)
            return await runtime.predict(request)
        except Exception as e:
            # Never raise — return error result
            return CodingResult(
                codes=[],
                summary=f"Runtime crash: {e}",
                runtime_mode=request.mode.value,
                latency_ms=0,
                llm_provider="unknown",
                trace_id="",
                error=True,
                error_reason=str(e),
            )

_dispatcher: CodingRuntimeDispatcher | None = None

def get_dispatcher() -> CodingRuntimeDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = CodingRuntimeDispatcher()
    return _dispatcher

def reset_dispatcher() -> None:
    global _dispatcher
    _dispatcher = None
```

### 3.5 `coding_predict.py` — API endpoint

```python
@router.post("/api/v1/coding/predict")
async def predict_codes(
    req: CodingPredictRequest,
    user: User = Depends(get_current_user),
) -> CodingPredictResponse:
    # 1. Auth check (JWT via get_current_user)
    # 2. LLM credential gate (ICODER_CREDENTIAL_LLM must be set)
    # 3. Coerce mode via RuntimeMode.coerce(req.mode)
    # 4. Build CodingRequest dataclass
    # 5. dispatcher.dispatch(request) → CodingResult
    # 6. Project to CodingPredictResponse (Pydantic)
    # 7. Return 200 OK (always — even on runtime error, return error=true)
```

---

## 4. Sequence diagram — Fast Coding (default)

```
 Frontend              Backend API           Dispatcher          FastCodingRuntime        LLMGateway           DeepSeek
    │                      │                     │                       │                      │                    │
    │  POST /predict       │                     │                       │                      │                    │
    │  {text, mode=fast}   │                     │                       │                      │                    │
    │─────────────────────▶│                     │                       │                      │                    │
    │                      │  auth + cred gate   │                       │                      │                    │
    │                      │  coerce mode       │                       │                      │                    │
    │                      │  dispatch(req)      │                       │                      │                    │
    │                      │────────────────────▶│                       │                      │                    │
    │                      │                     │  select_runtime(fast) │                      │                    │
    │                      │                     │  predict(req)         │                      │                    │
    │                      │                     │──────────────────────▶│                      │                    │
    │                      │                     │                       │  [1] input_received  │                    │
    │                      │                     │                       │  [2] language_detect │                    │
    │                      │                     │                       │  [3] build_prompt    │                    │
    │                      │                     │                       │  [4] llm_call        │                    │
    │                      │                     │                       │  build DeepSeek msg │                    │
    │                      │                     │                       │──────────────────────────────────────────▶│
    │                      │                     │                       │                      │   chat.completions │
    │                      │                     │                       │                      │───────────────────▶│
    │                      │                     │                       │                      │                    │
    │                      │                     │                       │                      │   ◀──── response ──│
    │                      │                     │                       │◀──────────────────────────────────────────│
    │                      │                     │                       │  [5] parse_json      │                    │
    │                      │                     │                       │  [6] project_result  │                    │
    │                      │                     │                       │  [7] return          │                    │
    │                      │                     │                       │  (latency_ms, etc.) │                    │
    │                      │                     │◀──────────────────────│                      │                    │
    │                      │                     │  CodingResult         │                      │                    │
    │                      │◀────────────────────│                       │                      │                    │
    │                      │  project to response│                      │                      │                    │
    │  200 OK + JSON      │                     │                       │                      │                    │
    │◀─────────────────────│                     │                       │                      │                    │
    │                      │                     │                       │                      │                    │
    │  Render Runtime Info │                     │                       │                      │                    │
    │  + codes table      │                     │                       │                      │                    │
    │  + Event Inspector  │                     │                       │                      │                    │
    │  (7 trace events)   │                     │                       │                      │                    │
```

**Latency budget** (T12 case, real measurement):
- Frontend → Backend: <10ms
- Backend auth + cred gate + mode coerce: <5ms
- Dispatcher + FastCodingRuntime init: <5ms
- Steps 1-3 (input/lang/prompt): <5ms
- Step 4 (LLM call): **~9.9s** (the dominant cost)
- Steps 5-7 (parse/project/return): <50ms
- Backend response + frontend render: <100ms
- **Total: ~9.96s** (Run 1) / **9.19s** (Run 2)

---

## 5. Sequence diagram — Deep Evidence (opt-in)

```
 Frontend              Backend API           Dispatcher          MedCoderRuntime         HybridCodingAdapter      DeepSeek + BGE-M3 + FAISS
    │                      │                     │                       │                       │                          │
    │  POST /predict       │                     │                       │                       │                          │
    │  {text, mode=deep}  │                     │                       │                       │                          │
    │─────────────────────▶│                     │                       │                       │                          │
    │                      │  dispatch(req)      │                       │                       │                          │
    │                      │────────────────────▶│                       │                       │                          │
    │                      │                     │  select_runtime(deep) │                       │                          │
    │                      │                     │  predict(req)        │                       │                          │
    │                      │                     │──────────────────────▶│                       │                          │
    │                      │                     │                       │  infer_async(mode=    │                          │
    │                      │                     │                       │  medcoder.full)       │                          │
    │                      │                     │                       │──────────────────────▶│                          │
    │                      │                     │                       │                       │  Stage 1: Extraction     │
    │                      │                     │                       │                       │  (DeepSeek chat)         │
    │                      │                     │                       │                       │─────────────────────────▶│
    │                      │                     │                       │                       │◀─────────extract─────────│
    │                      │                     │                       │                       │  Stage 2: Retrieval      │
    │                      │                     │                       │                       │  (BGE-M3 + FAISS)        │
    │                      │                     │                       │                       │  (local, no LLM)         │
    │                      │                     │                       │                       │  Stage 3: Merge          │
    │                      │                     │                       │                       │  (in-process)            │
    │                      │                     │                       │                       │  Stage 4: Re-rank        │
    │                      │                     │                       │                       │  (DeepSeek RankGPT)      │
    │                      │                     │                       │                       │─────────────────────────▶│
    │                      │                     │                       │                       │◀─────────rerank──────────│
    │                      │                     │                       │                       │  Stage 5: Compliance     │
    │                      │                     │                       │                       │  (MedicalCodingRuleSet)  │
    │                      │                     │                       │                       │  (in-process)            │
    │                      │                     │                       │◀──────────────────────│                          │
    │                      │                     │                       │  MedicalCodingOutputSchema                        │
    │                      │                     │                       │  (extracted_diagnoses)                           │
    │                      │                     │                       │  [stage1..5 trace + project_result + return]    │
    │                      │                     │◀──────────────────────│                       │                          │
    │                      │                     │  CodingResult         │                       │                          │
    │                      │◀────────────────────│                       │                       │                          │
    │  200 OK + JSON      │                     │                       │                       │                          │
    │◀─────────────────────│                     │                       │                       │                          │
```

**Latency budget** (estimated, not measured):
- Stage 1 (Extract LLM): 5-10s
- Stage 2 (Retrieve, local): 1-2s
- Stage 3 (Merge, in-process): <100ms
- Stage 4 (Re-rank LLM): 5-10s
- Stage 5 (Compliance, in-process): <100ms
- **Total: 30-60s+**

---

## 6. Data flow — CodingResultCode projection

### 6.1 Fast Coding projection (MedicalCodingOutputSchema → CodingResultCode[])

```
MedicalCodingOutputSchema
  ├── primary_diagnosis: {code, name, ...}
  │     → CodingResultCode(code, system="ICD-10-CN", display=name,
  │                        type="primary_diagnosis", confidence, evidence, rationale,
  │                        warnings=["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"],
  │                        alternatives=[])
  ├── secondary_diagnoses: [{code, name, ...}, ...]
  │     → CodingResultCode(...) × N (type="secondary_diagnosis")
  └── procedures: [{code, name, ...}, ...]
        → CodingResultCode(...) × N (type="procedure",
                                      system="ICD-9-CM-3-CN")
```

### 6.2 Deep Evidence projection (extracted_diagnoses → CodingResultCode[])

```
MedicalCodingOutputSchema
  └── extracted_diagnoses: [
        {
          disease: "...",
          llm_initial_code: "...",
          final_code: "...",
          final_confidence: 0.95,
          final_top_k: [
            {code, confidence, ...},  # 1st (final_code)
            {code, confidence, ...},  # 2nd
            {code, confidence, ...},  # 3rd
            {code, confidence, ...},  # 4th
            {code, confidence, ...}   # 5th
          ],
          supporting_evidence: ["...", "...", ...]
        },
        ...
      ]

For each extracted_diagnosis:
  → CodingResultCode(
      code=d.final_code,
      system="ICD-10-CN" | "ICD-9-CM-3-CN" (based on code prefix),
      display=...,
      type="primary_diagnosis" | "secondary_diagnosis" (based on order),
      confidence=d.final_confidence,
      evidence="; ".join(d.supporting_evidence),
      rationale="主要诊断 — based on evidence" (or fallback),
      warnings=["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"],
      alternatives=[{code, display, confidence} for k in d.final_top_k[1:5]]
    )
```

---

## 7. RunTrace emission patterns

### 7.1 Fast Coding 7-step trace

```python
trace_events = [
    {"step": "input_received",   "status": "ok", "metadata": {"text_len": 297, "mode": "corti_like_fast"}},
    {"step": "language_detect",  "status": "ok", "metadata": {"language": "zh"}},
    {"step": "build_prompt",     "status": "ok", "metadata": {"provider": "deepseek", "language": "zh", "system": "icd-10-cn"}},
    {"step": "llm_call",         "status": "ok", "metadata": {"provider": "deepseek", "model": "deepseek-chat", "is_mock": False}},
    {"step": "parse_json",       "status": "ok", "metadata": {}},
    {"step": "project_result",   "status": "ok", "metadata": {"code_count": 5}},
    {"step": "return",           "status": "ok", "metadata": {"latency_ms": 9957, "code_count": 5}},
]
```

On failure, the failing step gets `status="error"` with `metadata.error` containing the reason; subsequent steps are skipped; the final `return` step still emits with `status="error"`.

### 7.2 Deep Evidence 5-stage trace

```python
trace_events = [
    {"step": "stage1_extract",     "status": "ok", "metadata": {"note": "stage1+2+3+4+5 run by HybridCodingAdapter"}},
    {"step": "stage2_retrieve",    "status": "ok", "metadata": {"note": "synthetic — adapter did not emit detailed trace"}},
    {"step": "stage3_merge",       "status": "ok", "metadata": {"note": "synthetic — adapter did not emit detailed trace"}},
    {"step": "stage4_rerank",      "status": "ok", "metadata": {"note": "synthetic — adapter did not emit detailed trace"}},
    {"step": "stage5_compliance",  "status": "ok", "metadata": {"note": "synthetic — adapter did not emit detailed trace"}},
    {"step": "project_result",     "status": "ok", "metadata": {"code_count": 1}},
    {"step": "return",             "status": "ok", "metadata": {"latency_ms": 41, "code_count": 1}},
]
```

When `HybridCodingAdapter` emits `method_stage_trace` in the schema, MedCoderRuntime reads it for real stage events (with retrieval counts, rerank scores, compliance rule hits). Otherwise, synthetic placeholders are used.

---

## 8. Failure modes & contracts

### 8.1 FastCodingRuntime — never raises

| Failure | Behavior |
|---|---|
| Empty input (`text == ""`) | Returns `CodingResult(error=True, summary="输入文本为空", error_reason="empty_input")` |
| Oversize input (`len(text) > 16000`) | Returns `CodingResult(error=True, summary="输入文本过长", error_reason="oversize_input")` |
| LLM call raises | Returns `CodingResult(error=True, summary="LLM 调用失败: ...", error_reason="llm_call_failed")` |
| LLM returns DS001 error schema | Detects, returns friendly `error_reason="llm_returned_error_schema"` |
| JSON parse failure | Returns `CodingResult(error=True, summary="JSON 解析失败", error_reason="json_parse_failed")` |

### 8.2 MedCoderRuntime — never raises

| Failure | Behavior |
|---|---|
| Empty input | Returns `CodingResult(error=True, ...)` |
| Adapter crash | Returns `CodingResult(error=True, summary="MedCodER adapter crashed: ...", ...)` |

### 8.3 CodingRuntimeDispatcher — never raises

| Failure | Behavior |
|---|---|
| Runtime raises (defensive) | Catches, returns `CodingResult(error=True, summary="Runtime crash: ...", error_reason=str(e))` |

### 8.4 API endpoint — never silently times out

| Failure | Behavior |
|---|---|
| Auth failure | 401 Unauthorized |
| LLM credential missing | 503 Service Unavailable with `{detail: "LLM credential not configured"}` |
| Runtime returns error result | 200 OK with `error=true` (client shows error banner) |
| Runtime crash | 200 OK with `error=true` (caught by dispatcher) |
| Unhandled exception | 500 Internal Server Error (should not happen in normal flow) |

---

## 9. Singleton lifecycle

`get_dispatcher()` returns a process-wide singleton `CodingRuntimeDispatcher`. The dispatcher lazily initializes `_fast` and `_deep` runtimes on first use.

- **Tests**: call `reset_dispatcher()` between tests to ensure isolation
- **Production**: singleton lives for the lifetime of the uvicorn worker; runtimes are reused across requests (no per-request init overhead)

---

## 10. App-state integration

`FastCodingRuntime` and `MedCoderRuntime` both lazily resolve the platform LLM gateway from `app.state`:

```python
def _get_gateway(self) -> LLMGateway:
    from app.main import app
    return app.state.platform_gateway  # or however the gateway is wired
```

This avoids import-time circular dependencies and lets tests inject a `_FakeGateway` mock via `app.state.platform_gateway = _FakeGateway()` before calling `dispatch()`.

---

## 11. Backward compatibility

The new `POST /api/v1/coding/predict` endpoint is **additive** — existing endpoints (`/api/v2/tools/coding/icoder`, A2A Medical Coding Agent flow) continue to work unchanged. The new endpoint is the **recommended** path for new integrations; the legacy paths are preserved for back-compat.

| Caller | Old path | New path |
|---|---|---|
| Frontend MedicalCodingPage | A2A via `runtimeAgentApi.runAgentViaA2A(medicalCodingAgentId, text)` | `codingApi.predict(text, mode)` |
| External API Client (backend-service) | `POST /api/v2/tools/coding/icoder` | `POST /api/v1/coding/predict` (recommended) |
| External API Client (ROPC embedded) | A2A via `/api/icoder/agents/{id}/v1/message:send` | `POST /api/v1/coding/predict` (recommended) |

The frontend MedicalCodingPage is the **only** caller migrated to the new endpoint in this refactor. Other callers continue using legacy paths.
