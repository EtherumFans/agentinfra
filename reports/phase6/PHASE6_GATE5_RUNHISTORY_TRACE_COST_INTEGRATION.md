# Phase 6 Gate 5 — RunHistory / Trace / Cost 集成

**Date**: 2026-07-13
**Tier**: `GATE5_RUNHISTORY_TRACE_COST_INTEGRATION_CONSOLIDATED`
**Estimate vs actual**: ~1h estimate / ~25min actual
**Code changes**: `backend/app/api/agent_run.py` (+`trace_url` field & helper) + `packages/icoder-embedded/src/icoder-assistant.ts` (run.completed payload) + `backend/app/api/embedded.py` (preview HTML link) + test bump

## What landed

### 1. `AgentRunResponse.trace_url` 新字段

`backend/app/api/agent_run.py:176-203`:

```python
class AgentRunResponse(BaseModel):
    agent_id: str
    run_id: str
    trace_id: str = ""
    trace_url: str = Field(default="", description=(
        "Phase 6 Gate 5: frontend deep-link to the RunTrace viewer "
        "(/ai-studio/runs/{run_id}/trace). ..."
    ))
    ...

def _trace_url_for(run_id: str) -> str:
    if not run_id:
        return ""
    return f"/ai-studio/runs/{run_id}/trace"
```

`trace_url` 在三个 mapper 中都被填充（success / runtime_error / api_error）:
- `_map_coding_result()` — medical-coding-agent 成功/失败两条路径都填
- `_map_backend_response()` — 8 个 PureLLM/LLMWithTools 通用路径
- `_error_response()` — unknown_agent / crash / timeout 等错误兜底

### 2. `<icoder-embedded>` Web Component `run.completed` payload 扩展

`packages/icoder-embedded/src/icoder-assistant.ts:540-565`:

```ts
const traceUrl = data.trace_url
  ? `${this._baseUrl}${data.trace_url}`
  : '';
this._emitEmbeddedEvent('run.completed', {
  run_id: data.run_id,
  agent_id: data.agent_id,
  trace_id: data.trace_id || '',
  trace_url: traceUrl,
  latency_ms: data.latency_ms,
  output,
  cost: data.cost,
});
```

Embedder 收到 `run.completed` 后:
- 拿到 `trace_id` 用于内部索引
- 拿到绝对 URL `trace_url` 可直接打开（新 tab）跳到 iCoDer RunTrace viewer
- 前端路径 `${baseURL}/ai-studio/runs/{run_id}/trace` 要求登录 session

### 3. Preview HTML 浮层 trace 链接

`backend/app/api/embedded.py:170-175` — `run.completed` 事件日志行追加可点击 trace 链接：

```js
} else if (name === 'run.completed') {
  const traceLink = payload.trace_url
    ? ` <a href="${payload.trace_url}" target="_blank" rel="noopener" ...>trace ↗</a>`
    : '';
  append(`${ts} <span class="name">${name}</span> ... ${traceLink}`, '');
}
```

### 4. RunHistory / Trace / Cost 既有实现复用

无需重做。已有 (Phase 4-G/4-F2/Track-A):
- **RunHistory 表** (alembic 010) — `_persist_run_history()` 写入 `run_history` 表 (cost_usd CNY 列、agent_id、latency_ms、status)
- **RunTrace 持久化** (alembic 009) — `persist_trace_events()` 将 inline `trace_events` 落到 RunTraceStore (memory or db per settings.RUNTRACE_STORE)
- **Cost 计算** — 真实 DeepSeek token×pricing (Track-A BUG-12-02 closed, currency=CNY)
- **TopBar live cost** — `/api/v1/usage/live` 已经在 react frontend 中接好

Gate 5 只暴露 `trace_url` 一字段, 把既有 RunTrace/RunHistory 数据"解锁"给 embedded 消费者。

## Verification

```bash
# 1. Backend import sanity
cd /e/Corti4C/backend && python -c "
from app.api.agent_run import AgentRunResponse, _trace_url_for
print('fields:', list(AgentRunResponse.model_fields.keys()))
print('trace_url_for run-abc-123:', _trace_url_for('run-abc-123'))
print('trace_url_for empty:', repr(_trace_url_for('')))
"
# → fields: ['agent_id', 'run_id', 'trace_id', 'trace_url', 'runtime_mode', ...]
# → trace_url_for run-abc-123: /ai-studio/runs/run-abc-123/trace
# → trace_url_for empty: ''

# 2. Agent_run suite (10 tests, includes new trace_url assertion)
python -m pytest tests/test_api/test_phase4f_agent_run.py -x --tb=short
# → 10 passed in 25s

# 3. Embedded TS type check
cd /e/Corti4C/packages/icoder-embedded && npx tsc --noEmit
# → (no output, exit 0)

# 4. Embedded dist rebuilt (size ~24KB)
ls -la /e/Corti4C/packages/icoder-embedded/dist/icoder-assistant.js
# → 24213 bytes, timestamp 7月 13 23:14
```

## Files written / modified

| Path | Change |
|---|---|
| `backend/app/api/agent_run.py` | +`trace_url` field on `AgentRunResponse`; +`_trace_url_for()` helper; populate in 3 mappers (4 return sites) |
| `backend/app/api/embedded.py` | Preview HTML event log: `run.completed` line appends clickable `trace ↗` link |
| `packages/icoder-embedded/src/icoder-assistant.ts` | `run.completed` payload now includes `trace_id` + `trace_url` (absolute, baseURL-prefixed) |
| `packages/icoder-embedded/dist/*` | Rebuilt via `npx tsc` (4 files) |
| `backend/tests/test_api/test_phase4f_agent_run.py` | +`test_error_response_trace_url_is_deep_link`; `_REQUIRED_FIELDS` tuple bumped 13→14 with `trace_url` |

## Not done (out of Gate 5 scope)

- **Server-side `account.creditsConsumed` emit** — Currently this event is emitted client-side by the web component (post `/agents/{id}/run` response). Corti emits it server-side via SSE. iCoDer's response is one-shot JSON, so client-side emission is the correct parity behavior. No change needed.
- **Live browser walkthrough** of the embedded preview page — requires uvicorn running + manual JWT input. Deferred to Gate 7 (will be exercised as part of Medical Coding Demo).
- **`trace_url` deep-link auth** — The `/ai-studio/runs/:runId/trace` route currently requires an iCoDer login session. For partner portals that want to embed the trace viewer in an iframe, we'd need a "scoped trace viewer" with short-lived JWT in query string. Out of scope for Gate 5; documented as Phase 7 candidate.

## Carry-forward to Gate 2/3/4/7/8

- **Gate 2** (Patient/Encounter Context 安全): independent — no overlap with trace_url plumbing.
- **Gate 3** (Unified Event Contract): the `run.completed` payload extension here is additive; Gate 3 will formalize the meta envelope `{version, eventId, timestamp, sessionId, contextId}` without changing field names.
- **Gate 4** (SDK): the TypeScript SDK should expose `run.traceUrl` on its `RunResult` type — directly mirrors the API field.
- **Gate 7** (3 Demos): Medical Coding demo will exercise the trace_url flow end-to-end (real DeepSeek call → trace_url surfaces in event log).
- **Gate 8** (Usage): independent — Usage page already wired to `/api/v1/usage/live` and run_history.

## Verdict

`GATE5_PASS_EMBEDDED_TRACE_URL_SURFACEABLE` — the unified `/api/v1/agents/{id}/run` response now exposes a frontend-deep-linkable `trace_url` that the canonical `<icoder-embedded>` web component surfaces in the `run.completed` event payload. 10/10 backend tests pass; embedded TS type-checks clean; dist rebuilt.

Carry-forward: live browser walkthrough deferred to Gate 7.
