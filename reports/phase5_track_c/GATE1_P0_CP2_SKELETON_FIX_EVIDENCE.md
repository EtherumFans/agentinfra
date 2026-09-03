# Gate 1 P0 Fix — CP2 LLMWithToolsProvider SKELETON → Real LLM

**Fixed**: 2026-07-11 (Phase 5 Track C Gate 1)
**Commit precursor**: this document; commit will follow Gate 1 StructuredOutputProjector work
**Severity**: P0 (B-2 verdict `WITH_GAPS` qualifier, blocked 9/9 agent Corti-parity)

---

## 1. Root cause

`backend/icoder_runtime/backends/registry.py:397` instantiates `LLMWithToolsProvider()` with no args. Unlike `PureLLMProvider` which has `_resolve_client()` lazy-lookup (line 343-364), `LLMWithToolsProvider` checked only `self._llm_client is None` and fell through to `_skeleton_pipeline`. Result: code-validation-agent always returned `raw_provider_response.skeleton=true` regardless of whether `app/main.py` had registered the LLMGateway.

## 2. Fix

Added `_resolve_client()` method to `LLMWithToolsProvider` mirroring `PureLLMProvider._resolve_client()`:

```python
def _resolve_client(self) -> LLMClient | None:
    if self._llm_client is not None:
        return self._llm_client
    try:
        from .registry import get_gateway
        gateway = get_gateway()
    except Exception:
        return None
    if gateway is None:
        return None
    from .llm_gateway_adapter import LLMGatewayAdapter
    client = LLMGatewayAdapter(gateway)
    self._llm_client = client  # cache
    return client
```

Updated `invoke()` to call `client = self._resolve_client()` before the skeleton fallback.

## 3. Smoke test evidence (2026-07-11)

```
POST /api/v1/agents/code-validation-agent/run
input: "Verify ICD-10-CM I21.19 for 'Acute STEMI inferior wall'."

Before fix (B-2 evidence):
  raw.skeleton: True
  raw.tool_rounds: 1
  tool_calls count: 1 (verify_code with error 'request not passed')
  markdown: placeholder LLMWithToolsProvider skeleton
  cost: 0 (no LLM call)
  latency_ms: ~50ms (immediate)

After fix (Track C Gate 1):
  raw.skeleton: None (not skeleton)
  raw.tool_rounds: 3
  raw.tool_calls_count: 5
  tool_calls count: 5
  markdown: real DeepSeek analysis with ICD-10-CM validation table
  cost: > 0 (real LLM)
  latency_ms: ~10-15s (real LLM)
```

## 4. Caveats discovered

The 5 tool calls all errored with `"ToolMCPCompatLayer.call requires request"`. This is because the FastAPI handler at `/api/v1/agents/{id}/run` doesn't currently pass the `Request` object to `provider.invoke(..., request=request)`. The LLM correctly detected this and synthesized a knowledge-based answer instead.

This is a separate Gate 2 fix (wire `request` through `agent_run.py` → `agent_runner` → `provider.invoke(request=...)`). Tracked as Gate 2 dependency.

## 5. B-2 verdict qualifier `WITH_GAPS` partially closed

B-2 P0 gap: "CP2 LLMWithToolsProvider SKELETON" — **CLOSED**.

Remaining B-2 P1 gaps (15 total):
- 8× unified API structured output → Gate 1 StructuredOutputProjector (in progress)
- 7× orchestrator wiring → Gate 4

Once StructuredOutputProjector lands, the remaining P1 gaps shift to Gate 4/6 scope.
