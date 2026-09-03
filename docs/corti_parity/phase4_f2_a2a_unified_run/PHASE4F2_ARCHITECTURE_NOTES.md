# Phase 4-F2 — Architecture Notes

**Date:** 2026-07-10
**Scope:** A2A-Compatible Unified Agent Run Architecture (3-layer separation)

---

## 1. Three-Layer Architecture (per F2 prompt §2)

The F2 architecture separates concerns into 3 layers:

### Layer 1 — A2A Protocol Layer (shared facade)

**Module:** `backend/app/icoder/agent_runtime/a2a_facade.py` (~345 LOC)

**Responsibility:** Owns the A2A envelope semantics. Both entry points
(unified endpoint AND A2A `message:send`) construct their envelope through
this facade, ensuring protocol-level parity.

**Key data structures:**

```python
# InboundRequest envelope (A2A v0.3)
InboundRequest(
    message=InboundMessage(
        role="user",
        parts=[
            {"kind": "text", "text": input_text},
            {"kind": "data", "data": {"schema": "...", "value": extra}}?,  # if extra
        ],
        interaction_id=trace_id,  # cross-reference
    ),
    metadata={
        "agent_id": agent_id,
        "run_id": out_run_id,         # f"run-{uuid4()}"
        "trace_id": out_trace_id,     # f"trace-{hex16}"
        "context_id": context_id,
        "message_id": message_id,
        "runtime_mode": runtime_mode or "",
        "include_trace": include_trace,
        "include_evidence": include_evidence,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "phi_redacted": True,
        "production_writeback_blocked": True,
    },
)
```

**Functions:**

| Function | Purpose |
|---|---|
| `construct_envelope()` | Builds `InboundRequest`, generates `run_id`/`trace_id`/`context_id`/`message_id` |
| `dispatch_medical_coding_fast()` | Routes to `CodingRuntimeDispatcher` (shared by both entry points) |
| `build_medical_coding_inbound_response()` | Projects `CodingResult` → A2A `InboundResponse` with v2 parts |
| `persist_trace_events()` | Emits each inline `trace_event` to `RunTraceStore` |

### Layer 2 — Entry/Facade Layer

**Two entry points share the facade:**

#### Entry Point A: Unified Run Endpoint

**Module:** `backend/app/api/agent_run.py`

```python
@router.post("/{agent_id}/run", response_model=AgentRunResponse)
async def run_agent(agent_id: str, body: AgentRunRequest, ...):
    # 1. Construct A2A envelope via facade
    envelope, run_id, trace_id, context_id, message_id = construct_envelope(...)

    # 2. Dispatch (medical coding fast path OR generic provider path)
    if agent_id in _MEDICAL_CODING_AGENT_IDS:
        response = await _run_medical_coding(...)  # uses dispatch_medical_coding_fast()
    else:
        response = await _run_via_provider_registry(...)  # uses ProviderRegistry

    # 3. Persist trace_events to RunTraceStore
    if response.trace_events and not response.error:
        persist_trace_events(
            run_id=response.run_id or run_id,
            trace_events=response.trace_events,
            agent_id=agent_id,
            runtime_mode=response.runtime_mode,
            trace_id=response.trace_id or trace_id,
        )

    return response
```

**Response envelope:** 13-field `AgentRunResponse` pydantic model
(`agent_id`, `run_id`, `trace_id`, `runtime_mode`, `latency_ms`, `cost`,
`summary`, `result`, `evidence`, `warnings`, `manual_review_required`,
`trace_events`, `error`, `error_reason`).

#### Entry Point B: A2A `message:send`

**Module:** `backend/app/main.py` (`_MedicalCodingV2ProjectingHandler`)

```python
def handle(self, agent_id, request):
    if agent_id == "medical-coding-agent":
        meta = request.metadata or {}
        runtime_mode = meta.get("runtime_mode") or "corti_like_fast"

        if runtime_mode != "medcoder_deep":
            # Fast path — route to CodingRuntimeDispatcher directly
            input_text = extract_text_from_parts(request.message.parts)
            result, out_run_id, out_trace_id = asyncio.run(
                dispatch_medical_coding_fast(...)
            )
            # Persist trace_events (so /runs/{run_id}/trace works for A2A too)
            if result.trace_events and not result.error:
                persist_trace_events(...)
            return build_medical_coding_inbound_response(...)

    # medcoder_deep OR non-medical-coding: pass through to InboundHandler
    return self._inner.handle(agent_id, request)
```

**Response:** A2A `InboundResponse` with v2 parts + `_runtime` envelope
field (carries `runtime_mode` / `latency_ms` / `llm_provider` / `trace_id`
/ `run_id` / `cost` / `trace_events` / `error` / `error_reason`).

### Layer 3 — Runtime Execution Layer

**Modules:**

- `backend/app/coding_runtime/dispatcher.py` — `CodingRuntimeDispatcher`
  - `FastCodingRuntime` for `corti_like_fast` (default, ~6-8s)
  - `MedCoderRuntime` for `medcoder_deep` (5-stage, 30-60s+, opt-in)
- `backend/icoder_runtime/backends/registry.py` — `ProviderRegistry`
  - `PureLLMProvider` for `a2a_pure_llm`
  - `LLMWithToolsProvider` for `llm_with_tools`
  - `RuleEngineProvider` for `rule_engine`

---

## 2. End-to-End Flow (Medical Coding T12 case)

```
1. User clicks "使用智能体" on Medical Coding Agent card
   → /ai-studio/agents/{clone_id}/chat?preset=icoder/medical-coding-agent@2.0.0

2. User types "患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。"
   → presses Ctrl+Enter

3. AgentChatPage.handleSend()
   → calls runtimeAgentApi.runAgentUnified("medical-coding-agent", {...})
   → POST /api/v1/agents/medical-coding-agent/run
       body: {input: {text: "患者男性..."}, runtime_mode: null}

4. agent_run.py::run_agent()
   → construct_envelope(agent_id="medical-coding-agent",
                        input_text="患者男性...",
                        runtime_mode=None,
                        ...)
     → builds InboundRequest envelope with:
       - run_id="run-{uuid4()}"   (e.g., "run-0f0149a9-...")
       - trace_id="trace-{hex16}" (e.g., "trace-9fada93754c54ee7")
       - context_id (uuid4)
       - message_id (uuid4)
       - metadata.runtime_mode = "" (will default to corti_like_fast)

5. agent_id in _MEDICAL_CODING_AGENT_IDS → _run_medical_coding()
   → dispatch_medical_coding_fast(agent_id="medical-coding-agent",
                                   input_text="患者男性...",
                                   runtime_mode=None,  # → corti_like_fast
                                   run_id="run-0f0149a9-...",
                                   trace_id="trace-9fada937...",
                                   ...)
     → CodingRuntimeDispatcher.dispatch(request)
       → FastCodingRuntime.dispatch()
         1. input_received (0ms)   — text_len=28, mode=corti_like_fast
         2. language_detect (0ms) — language=zh
         3. build_prompt (0ms)     — provider=deepseek, language=zh, system=icd-10-cn
         4. llm_call (~3833ms)     — provider=deepseek, model=deepseek-chat, is_mock=false
         5. parse_json (3833ms)    — empty metadata
         6. project_result (3833ms) — code_count=1
         7. return (3833ms)        — latency_ms=3833, code_count=1
       → returns CodingResult(
           codes=[Code(code="S22.000x003", display="胸椎压缩性骨折",
                       type="primary_diagnosis", confidence=0.95, ...)],
           summary="病历明确T12椎体压缩性骨折...",
           runtime_mode="corti_like_fast",
           latency_ms=3833,
           trace_id="trace-9fada937...",
           run_id="run-0f0149a9-...",
           trace_events=[7 events],
         )

6. _map_coding_result()
   → builds AgentRunResponse with all 13 envelope fields
   → 7 trace_events inline in response body

7. Back in run_agent()
   → if response.trace_events and not response.error:  # True (7 events, error=False)
     → persist_trace_events(run_id="run-0f0149a9-...", trace_events=[7 events], ...)
       → for each event: emit_trace_event(run_id, step, status, ...)
         → RunTraceStore.append(RunTraceEvent(...))

8. Response returned to frontend:
   {
     "agent_id": "medical-coding-agent",
     "run_id": "run-0f0149a9-36a5-4fd1-ae3a-2312ed8ffaa8",
     "trace_id": "trace-9fada93754c54ee7",
     "runtime_mode": "corti_like_fast",
     "latency_ms": 3833,
     "summary": "病历明确T12椎体压缩性骨折...",
     "result": {"codes": [{"code": "S22.000x003", ...}], ...},
     "evidence": [{"code": "S22.000x003", "text": "MRI 显示 T12...", ...}],
     "warnings": ["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"],
     "manual_review_required": true,
     "trace_events": [7 events],
     "error": false,
     "error_reason": ""
   }

9. AgentChatPage renders:
   - runtime_mode badge: "corti_like_fast"
   - latency: "耗时 3833ms"
   - View RunTrace link → /runs/run-0f0149a9-.../trace
   - 📋 Trace Events (7) expander (inline viewer)
   - Copy JSON button
   - Copy Markdown button

10. User clicks "View RunTrace"
    → /runs/run-0f0149a9-.../trace
    → RunTracePage fetches GET /api/runtime/runs/run-0f0149a9-.../trace
      → run_trace.py::_get_run_trace_impl()
        → store = get_default_store()  # in-memory RunTraceStore
        → events = store.get_run("run-0f0149a9-...")  # 7 events
        → returns {"run_id": "...", "timeline": [7 events], "step_count": 7}
    → RunTracePage renders:
      - Header: "7 steps, 7 ok, 15332ms total"
      - Timeline:
        1. input_received   ok  ts=1783647582.688
        2. language_detect  ok  ts=1783647582.688
        3. build_prompt     ok  ts=1783647582.688
        4. llm_call         ok  3833.0ms  ts=1783647582.688
        5. parse_json       ok  3833.0ms  ts=1783647582.688
        6. project_result  ok  3833.0ms  ts=1783647582.688
        7. return           ok  3833.0ms  ts=1783647582.688

11. User clicks "Copy JSON"
    → navigator.clipboard.writeText(JSON.stringify(result.codes + raw_schema))
    → clipboard has 3020 chars starting with `{"codes":[{"code":"S22.000x003"...`

12. User clicks "Copy Markdown"
    → navigator.clipboard.writeText(generate_markdown(result))
    → clipboard has 1558 chars starting with `# Agent Run Result\r\n\r\nRun ID: run-... | Trace ID: trace-... | Runtime: corti_like_fast | Latency: 4626ms\r\n...`
```

---

## 3. Pre-F2 vs Post-F2 Behavior

### Pre-F2 (Phase 4-F1 state, 2026-07-10 morning)

| Path | Behavior | Issue |
|---|---|---|
| `POST /api/v1/agents/{id}/run` (medical-coding) | Returned v2 envelope, but did NOT construct A2A envelope internally — just called CodingRuntimeDispatcher directly | No A2A protocol semantics preserved |
| `POST /api/icoder/agents/medical-coding-agent/v1/message:send` | Routed through `_MedicalCodingV2ProjectingHandler` → `InboundHandler` (5-stage MedCodER pipeline) | 60s+ timeout (root cause: defaults to MedCodER not corti_like_fast) |
| `GET /api/runtime/runs/{run_id}/trace` (after unified run) | Returned 404 "no trace events for run_id '...'" | Inline trace_events were returned but never persisted to RunTraceStore |
| `/ai-studio/agents` iCoDer built tab | Vitest contract test failures blocked rendering | Test regex was overly strict (didn't accept `useCase` param) |

### Post-F2 (this sub-phase)

| Path | Behavior | Fix |
|---|---|---|
| `POST /api/v1/agents/{id}/run` (medical-coding) | Constructs A2A envelope via `construct_envelope()` (preserves run_id/trace_id/context_id/message_id), then dispatches via `dispatch_medical_coding_fast()`, then persists trace_events via `persist_trace_events()` | A2A protocol semantics preserved end-to-end |
| `POST /api/icoder/agents/medical-coding-agent/v1/message:send` | `_MedicalCodingV2ProjectingHandler` intercepts: if `runtime_mode != "medcoder_deep"`, calls `dispatch_medical_coding_fast()` directly (bypasses InboundHandler 5-stage) | Default = corti_like_fast (~6-8s, Corti parity) |
| `GET /api/runtime/runs/{run_id}/trace` (after unified run) | Returns 200 with 7 events | `persist_trace_events()` emits each inline event to RunTraceStore |
| `/ai-studio/agents` iCoDer built tab | Renders 14 hub cards correctly | Fixed vitest regex + removed `RunTracePage` from `deletedPages` |

---

## 4. Why a Shared Facade? (vs inline implementation in agent_run.py)

Per F2 prompt §6.1: "如现有 A2A handler 过重，可先做一层轻量 A2A-compatible
adapter，但必须保留 A2A envelope 语义". The shared facade approach has 3
advantages over inlining the envelope construction in `agent_run.py`:

1. **Single source of truth for envelope semantics.** Both the unified
   endpoint AND the A2A `message:send` path construct envelopes through
   `construct_envelope()`. If the envelope schema evolves (e.g., adds a
   `phi_redacted` field), one change updates both paths.

2. **Single source of truth for medical-coding fast path.** Both entry
   points call `dispatch_medical_coding_fast()`. If the fast path logic
   evolves (e.g., adds a circuit breaker), one change updates both paths.

3. **Testability.** The facade can be unit-tested independently of the
   FastAPI request/response layer. `tests/test_api/test_phase4f2_a2a_compatible.py`
   tests both the unified endpoint AND the A2A path through TestClient,
   validating that both produce the same envelope + runtime_mode + trace
   semantics.

---

## 5. Trace Persistence Strategy

`persist_trace_events()` is **defensive** — never raises:

```python
def persist_trace_events(*, run_id, trace_events, agent_id="", runtime_mode="", trace_id=""):
    if not trace_events:
        return
    for ev in trace_events:
        if not isinstance(ev, dict):
            continue
        step = str(ev.get("step", "unknown"))
        status = str(ev.get("status", "ok")) or RunTraceStatus.OK
        duration_ms = float(ev.get("duration_ms", 0) or 0)
        meta = ev.get("metadata") or ev.get("safe_metadata") or {}
        safe_meta = {"agent_id": agent_id, "runtime_mode": runtime_mode, "trace_id": trace_id}
        if isinstance(meta, dict):
            for k, v in meta.items():
                if k in ("agent_id", "runtime_mode", "trace_id"):
                    continue
                safe_meta[k] = v
        try:
            emit_trace_event(run_id, step, status=status,
                             duration_ms=duration_ms, safe_metadata=safe_meta)
        except Exception as e:
            logger.warning("a2a_facade: emit_trace_event failed for run_id=%s step=%s: %s",
                           run_id, step, e)
```

If a single `emit_trace_event` call fails, the others still proceed. The
response body still carries the inline `trace_events` regardless — the
persistence is a side-effect, not a critical path.

---

## 6. A2A Envelope vs HTTP Response Envelope

The F2 architecture has TWO envelope concepts, intentionally:

### A2A Envelope (internal, protocol layer)

- `InboundRequest` / `InboundResponse` (defined in `inbound_handler.py`)
- Carries `message` (with `parts`) + `metadata` (protocol fields)
- Used internally by `a2a_facade.py` to preserve A2A semantics
- Not directly serialized to HTTP — projected to the appropriate
  response shape at the entry layer

### HTTP Response Envelope (external, API contract)

- `AgentRunResponse` (pydantic, 13 fields) — for unified endpoint
- `InboundResponse` (A2A v0.3 JSON-RPC shape) — for `message:send`
- These are DIFFERENT shapes but carry the SAME semantic content
  (run_id, trace_id, runtime_mode, latency_ms, trace_events, etc.)

The `_runtime` field in the A2A `InboundResponse` parts[0].data is the
bridge — it carries the same fields as the unified endpoint's
`AgentRunResponse`, so frontend code that parses either response shape
can extract the runtime metadata uniformly.

---

## 7. References

- F2 prompt §2 (three-layer architecture)
- F2 prompt §6.1 (lightweight A2A-compatible adapter allowed)
- F2 prompt §9.2 (architecture diagram)
- `backend/app/icoder/agent_runtime/a2a_facade.py` — shared facade source
- `backend/app/api/agent_run.py` — unified endpoint
- `backend/app/main.py::_MedicalCodingV2ProjectingHandler` — A2A handler
- `backend/app/coding_runtime/dispatcher.py` — runtime execution layer
- `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` — trace store
