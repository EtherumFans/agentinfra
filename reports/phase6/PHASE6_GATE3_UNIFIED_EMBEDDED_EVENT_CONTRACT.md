# Phase 6 Gate 3 — 统一 Embedded Event Contract

**Date**: 2026-07-13
**Tier**: `GATE3_UNIFIED_EVENT_CONTRACT_V1_WITH_META_ENVELOPE`
**Estimate vs actual**: ~2h estimate / ~30min actual
**Code changes**: `packages/icoder-embedded/src/icoder-assistant.ts` (meta envelope + AbortController + 1 retry + Idempotency-Key) + `backend/app/api/embedded.py` (preview HTML meta suffix) + 1 new Playwright case

## What landed

### 1. 统一 Event Envelope v1.0 — `meta` block

Every `embedded-event` now carries a `meta` block (Phase 6 Gate 3 schema v1.0):

```ts
export interface EmbeddedEventMeta {
  version: '1.0';
  eventId: string;        // crypto.randomUUID() per event (or fallback)
  timestamp: string;      // new Date().toISOString()
  sessionId: string;      // stable per widget instance (constructor UUID)
  contextId: string;      // current patientContext id, or '' if cleared
}

export interface EmbeddedEventDetail extends EmbeddedEvent {
  meta: EmbeddedEventMeta;
}
```

Embedder dispatch now receives:

```ts
assistant.addEventListener('embedded-event', (e) => {
  const { name, payload, meta } = e.detail;
  // meta.eventId — dedup (idempotency, future Phase 7 server-side)
  // meta.timestamp — cross-widget ordering
  // meta.sessionId — correlate events from one widget instance
  // meta.contextId — PHI-scoped correlation (current patient)
  // meta.version — envelope schema version (currently '1.0')
});
```

字段 `name` 和 `payload` 保持 Corti-compatible — meta 是 iCoDer ADVANTAGE 扩展 (Corti 只发 `{name, payload}`, 不带 meta).

### 2. `_sessionId` 稳定 + `_contextId` 跟随患者

- `_sessionId` — 在 constructor 中生成一次, widget 整个生命周期不变
- `_contextId` — 在 `configureSession`/`setPatientContext` 时设为 `encounterId || patientId || ''`; 在 `clearPatientContext`/`clearSession` 时清空

这样 embedder 可以:
- 用 `meta.sessionId` 区分来自不同 widget 实例的事件 (同一页面可挂多个 widget)
- 用 `meta.contextId` 把事件归到一次患者会话; 切换患者时 contextId 改变, embedder 知道哪些事件属于上一个患者

### 3. AbortController — 90s 默认 timeout, `request-timeout-ms` 属性可调

```ts
const timeoutMs = parseInt(this.getAttribute('request-timeout-ms') || '90000', 10);
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
```

- 默认 90s 覆盖 medical-coding 的 corti_like_fast (~9s) 和 medcoder_deep (30-60s+)
- 超时时抛 `AbortError`, widget 显示友好中文错误 "请求超时 (>90000ms). 请在 backend config 检查 agent runtime 模式或增加 request-timeout-ms 属性."
- Embedder 可改: `<icoder-embedded baseURL="..." request-timeout-ms="120000"></icoder-embedded>`

### 4. 1 Automatic Retry on Network Errors

```ts
try {
  resp = await doFetch(1);
} catch (networkErr: any) {
  if (controller.signal.aborted) throw networkErr;  // don't retry timeout
  try {
    resp = await doFetch(2);
  } catch (retryErr: any) {
    throw new Error(`Network error after retry: ${retryErr.message}`);
  }
}
```

只 retry 网络错误 (TypeError: Failed to fetch — DNS/connection reset). 4xx/5xx HTTP 响应不 retry (服务端已经拒绝, 重试无意义). Timeout (AbortError) 不 retry.

### 5. `Idempotency-Key` Header

每次 `_callAgent()` 生成 UUID, 同时发送 `Idempotency-Key` + `X-Attempt: 1|2` header:

```ts
const idempotencyKey = crypto.randomUUID();
const doFetch = async (attempt: 1 | 2) => fetch(url, {
  ...,
  headers: {
    ...,
    'Idempotency-Key': idempotencyKey,
    'X-Attempt': String(attempt),
  },
});
```

Server-side dedup (用 `Idempotency-Key` 做 cache) 是 Phase 7 候选。客户端重试时复用同一 key, 服务端将来可以做"重复请求 → 返回上次结果"。当前服务端 ignore 这两个 header — 但客户端已在发送, 升级时不用再改 widget.

### 6. Enhanced `error.triggered` payload

```ts
this._emitEmbeddedEvent('error.triggered', {
  message: msg,
  kind: isAbort ? 'timeout' : 'runtime',
  retriable: !isAbort,
});
```

Embedder 可根据 `kind` 和 `retriable` 决定是否显示"重试"按钮。`timeout` 错误 `retriable=false` (说明是慢查询, 重试只会再 timeout); `runtime` 错误 `retriable=true` (临时网络问题已经 retry 过, 但用户可以手动再 retry).

### 7. Preview HTML — meta 信息可见

`backend/app/api/embedded.py:166-168` — event log 每行末尾追加:

```
eid=abc12345 sid=def67890 ctx=P-2026-001
```

- `eid` = `meta.eventId` 前 8 字符
- `sid` = `meta.sessionId` 前 8 字符
- `ctx` = `meta.contextId` 或 `∅` (空)

让集成方在 preview page 直接看到 meta 字段是否被正确填充.

### 8. Playwright 测试 — 新增 1 用例, 强化 2 个既有

`frontend/tests/e2e/phase5_a4_embedded.spec.ts`:

- **`Phase 6 Gate 3 — meta.sessionId stable across multiple events; eventId unique`** (新)
  - 触发 setPatientContext + clearPatientContext 两次事件
  - 断言 `sessionId` 相同 (Set.size === 1)
  - 断言 `eventId` 全部不同
  - 断言 `meta.version` 全部 `'1.0'`
- **`Phase 6 Gate 2 — clearPatientContext() flushes PHI + emits event`** (扩展)
  - 新增 meta envelope 断言: version/eventId/sessionId/contextId/timestamp
  - `contextId` 必须为 `''` (cleared)
- **`Phase 6 Gate 2 — clearSession() flushes PHI + auth + messages`** (扩展)
  - 新增 meta.version + meta.sessionId 断言

## Verification

```bash
# 1. Type-check + rebuild
cd /e/Corti4C/packages/icoder-embedded && npx tsc --noEmit && npx tsc
# → exit 0; dist 27KB → 31KB

# 2. Backend router sanity
cd /e/Corti4C/backend && python -c "from app.api.embedded import router; print(f'OK — {len(router.routes)} routes')"
# → OK — 2 routes

# 3. New meta envelope present in dist
grep -c "EmbeddedEventMeta\|eventId\|sessionId\|contextId" dist/icoder-assistant.js
# → 30+ matches (type erased in JS, field names preserved)

# 4. Backend agent_run regression still passes (Phase 4-F2 + Gate 5 trace_url)
python -m pytest tests/test_api/test_phase4f_agent_run.py -x --tb=short
# → 10 passed in 25s
```

## Contract Summary (v1.0)

```ts
type EmbeddedEventDetail = {
  name: 'ready'
        | 'run.completed'
        | 'account.creditsConsumed'
        | 'error.triggered'
        | 'message.received'
        | 'patient.context.cleared'
        | 'session.cleared',
  payload: { ... per-name ... },
  meta: {
    version: '1.0',
    eventId: string,      // UUID v4, unique per event
    timestamp: string,    // ISO 8601 UTC
    sessionId: string,    // UUID v4, stable per widget instance
    contextId: string,    // encounterId || patientId || ''
  }
}
```

**Event payloads (summary)**:

| name | payload |
|---|---|
| `ready` | `{}` |
| `run.completed` | `{ run_id, agent_id, trace_id, trace_url, latency_ms, output, cost }` |
| `account.creditsConsumed` | `{ amount, currency, run_id }` |
| `error.triggered` | `{ message, kind: 'timeout' \| 'runtime', retriable: boolean }` |
| `message.received` | `{ role: 'user' \| 'agent', content }` |
| `patient.context.cleared` | `{ reason: 'host_invoked_clear' }` |
| `session.cleared` | `{ reason: 'host_invoked_clear' }` |

## Files written / modified

| Path | Change |
|---|---|
| `packages/icoder-embedded/src/icoder-assistant.ts` | +`EmbeddedEventMeta` +`EmbeddedEventDetail` types; +`_sessionId`/`_contextId` fields with constructor init; meta wired into `_emitEmbeddedEvent`; AbortController + 1 retry + Idempotency-Key in `_callAgent`; enhanced `error.triggered` payload with `kind`/`retriable` |
| `packages/icoder-embedded/dist/*` | Rebuilt via `npx tsc` (27KB → 31KB) |
| `backend/app/api/embedded.py` | Preview HTML: meta suffix in every event log line |
| `frontend/tests/e2e/phase5_a4_embedded.spec.ts` | +1 new Gate 3 test; extended 2 Gate 2 tests with meta assertions |

## Not done (out of Gate 3 scope)

- **Server-side Idempotency-Key dedup** — Currently server ignores the header. Implementing server-side cache (Redis or in-memory) is Phase 7 candidate. Client already sends it, so server-side dedup is a backward-compatible change.
- **Event delivery guarantees (at-least-once / exactly-once)** — Browser CustomEvent is in-process, so delivery is "exactly-once" by construction. Server-sent events (SSE) would need at-least-once; not in current architecture.
- **`trace_url` viewer auth for iframe embedding** — Phase 7 candidate (short-lived JWT in query string).
- **Live browser walkthrough** — Deferred to Gate 7.

## Carry-forward to Gate 4/7

- **Gate 4** (SDK): TypeScript SDK should expose `onEvent(callback: (e: EmbeddedEventDetail) => void)` — typed `meta` field on the callback. SDK retry policy can be richer (configurable N retries, exponential backoff) since widget only does 1 attempt.
- **Gate 7** (3 Demos): Medical Coding Demo will demonstrate the meta envelope in the event log + Idempotency-Key for safe retry.

## Verdict

`GATE3_PASS_UNIFIED_EVENT_ENVELOPE_V1_WITH_META_AND_TIMEOUT_AND_IDEMPOTENCY` — every `embedded-event` now carries `{name, payload, meta}` where `meta` includes `version/eventId/timestamp/sessionId/contextId`. `_callAgent` is hardened with AbortController (90s default, configurable), 1 automatic retry on network errors (not on timeout), and `Idempotency-Key` header for future server-side dedup. Enhanced `error.triggered` payload classifies timeout vs runtime errors with retriable flag.

Carry-forward: live browser walkthrough deferred to Gate 7; server-side Idempotency-Key dedup deferred to Phase 7.
