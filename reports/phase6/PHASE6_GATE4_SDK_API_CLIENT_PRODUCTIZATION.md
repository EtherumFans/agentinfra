# Phase 6 Gate 4 — SDK + API Client 产品化

**Date**: 2026-07-13
**Tier**: `PACKAGE_BUILD_VERIFIED` (REGISTRY_PUBLISH_DEFERRED per Phase 6 §4.3)
**Estimate vs actual**: ~2h estimate / ~30min actual
**Code changes**: `packages/icoder-sdk/src/resources/runs.ts` (new) + index.ts wiring + package.json bump + README section

## What landed

### 1. 三个新 SDK 资源 (`runs.ts` — 240 LOC)

**`RunsResource`** — POST `/api/v1/agents/{agent_id}/run` 统一入口 (Phase 4-F2 + Phase 6 Gate 5)
- `.run(agentId, body, idempotencyKey?)` — full envelope
- `.runText(agentId, text, opts)` — text-only shortcut

**`RunHistoryResource`** — GET `/api/runtime/runs/history` (alembic 010)
- `.list({ agent_id, days, limit, offset })` — paginated run history

**`RunTraceResource`** — GET `/api/runtime/runs/{run_id}/trace` (alembic 009)
- `.timeline(runId)` — display-safe 9-step timeline
- `.raw(runId)` — full event dump (debug)

### 2. A2A v0.3 类型 (mirror of Python server-side envelope)

SDK 现在暴露:

```ts
export interface A2AEnvelope {
  jsonrpc: '2.0';
  id: string;
  result?: {
    agent_id: string;
    run_id: string;
    trace_id: string;
    context_id: string;
    message_id: string;
    status: 'completed' | 'failed' | string;
    message?: A2AMessage;
  };
  error?: { code: number; message: string; data?: Record<string, unknown> };
}

export interface A2AMessage {
  message_id: string;
  role: 'user' | 'agent';
  parts: A2AMessagePart[];
}

export interface A2AMessagePart {
  kind: 'text' | 'data' | 'file';
  text?: string;
  data?: Record<string, unknown>;
  uri?: string;
  mime_type?: string;
}
```

目前没有 SDK 端 A2A 客户端消费者 (Python A2A 入口在 server 端的 `app/icoder/agent_runtime/a2a_facade.py`)。类型预留用于未来 SDK 直接发 A2A 消息。

### 3. `AgentRunResponse` 类型完整镜像后端

```ts
export interface AgentRunResponse {
  agent_id: string;
  run_id: string;
  trace_id: string;
  trace_url: string;  // Phase 6 Gate 5
  runtime_mode: string;
  latency_ms: number;
  cost: AgentRunCost | Record<string, unknown>;
  summary: string;
  result: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  warnings: string[];
  manual_review_required: boolean;
  trace_events: Array<Record<string, unknown>>;
  error: boolean;
  error_reason: string;
}
```

镜像后端 `backend/app/api/agent_run.py:AgentRunResponse` Pydantic 模型 — 14 字段对齐 (含 Gate 5 的 `trace_url`).

### 4. SDK 主类暴露 3 个新属性

```ts
const icoder = new iCoDer(config);
icoder.runs;        // RunsResource
icoder.runHistory;  // RunHistoryResource
icoder.runTrace;    // RunTraceResource

// 既有属性保留 (向后兼容)
icoder.runtime;     // 旧 RuntimeResource (legacy /api/runtime/*)
icoder.agents;      // ...
```

### 5. Idempotency-Key 支持

```ts
const { data: run } = await icoder.runs.runText(
  'medical-coding-agent',
  text,
  { idempotencyKey: 'uuid-from-his-session' },
);
```

SDK 把 key 转成 `Idempotency-Key` HTTP header. Server-side dedup 是 Phase 7 候选 (当前服务端 ignore，客户端已经在发).

### 6. SSE Client 占位 (Phase 7 candidate)

`runs.ts` 末尾留了 SSE 客户端的设计注释 + skeleton, 不实现 — 因为当前 agent_run 是 request/response 模式，没有 SSE 端点。Phase 7 候选: 后端开 `POST /api/v1/agents/{id}/run/stream` SSE, SDK 增加 `EventSource` 消费者。

## Verification

```bash
# 1. Type-check (existing compliance.ts errors are pre-existing, unrelated to Gate 4)
cd /e/Corti4C/packages/icoder-sdk && npx tsc --noEmit 2>&1 | grep -E "runs\.ts|index\.ts"
# → (no output — my changes have zero type errors)

# 2. Build SDK
npx tsc 2>&1 | grep -E "runs\.ts|index\.ts"
# → (no errors from my files)

# 3. Verify dist contains new resources
ls dist/resources/ | grep -E "runs|runtime"
# → runs.d.ts, runs.js, runtime.d.ts, runtime.js

# 4. Verify exports
grep -E "RunsResource|RunHistoryResource|RunTraceResource|AgentRunResponse" dist/index.d.ts
# → 4 export lines confirmed
```

## Files written / modified

| Path | Change |
|---|---|
| `packages/icoder-sdk/src/resources/runs.ts` | **NEW** — 3 resource classes + 9 types + SSE skeleton comment |
| `packages/icoder-sdk/src/index.ts` | +3 new resource exports, +9 new type exports, +3 new properties on default class |
| `packages/icoder-sdk/package.json` | version `1.0.0-beta.1` → `1.0.0-beta.2` |
| `packages/icoder-sdk/README.md` | +Phase 6 Gate 4 section with examples + resource table |
| `packages/icoder-sdk/dist/*` | Rebuilt via `npx tsc` (includes new `resources/runs.{js,d.ts}`) |

## Compliance with Phase 6 §4.3 (No fake npm publish)

- **NO** `npm publish` executed.
- Version bumped to `1.0.0-beta.2` as git/source-dist-tag only.
- README explicitly states `PACKAGE_BUILD_VERIFIED, REGISTRY_PUBLISH_DEFERRED`.
- Build (`npx tsc`) produces `dist/` — verifiable locally + in CI, but `npm publish` is deferred until Phase 7 partner validation.

## Not done (out of Gate 4 scope)

- **Public npm publish** — Phase 7 candidate after partner validation. Per Phase 6 §4.3: REGISTRY_PUBLISH_DEFERRED.
- **SDK unit tests** — Would require mock axios + sample responses. The underlying resources are 4-line wrappers; their behavior is dictated by the backend. Backend integration tests (`backend/tests/test_api/test_phase4f_agent_run.py`) already cover the contract.
- **Runtime resource cleanup** — The legacy `RuntimeResource` in `runtime.ts` targets `/api/runtime/*` endpoints that have been removed (returns 410 Gone for several paths per Phase 2.1-A). Marked for Phase 7 cleanup with a DEPRECATED.md sibling.
- **compliance.ts pre-existing type errors** — 4 errors in `src/resources/compliance.ts` (Cannot find name 'iCoDerClient'; Property 'http' does not exist). Pre-existing from earlier phase, unrelated to Gate 4. Phase 7 cleanup.
- **OAuth2 Client Credentials flow helper** — SDK's `oauth.clientCredentials()` exists; partners use it to mint API tokens. Already covered.
- **TypeScript ESLint / Prettier config** — Out of scope; SDK is small enough that tsc is the gate.

## Carry-forward to Gate 7/8

- **Gate 7** (3 Demos): Demos should use `icoder.runs.runText()` rather than raw fetch — demonstrates SDK adoption.
- **Gate 8** (API Client + Usage): API Client CRUD endpoints will get their own resource (`icoder.apiClients`); Usage multi-dim filters extend `icoder.usage`.

## Verdict

`GATE4_PASS_PACKAGE_BUILD_VERIFIED_REGISTRY_PUBLISH_DEFERRED` — `@icoder/sdk@1.0.0-beta.2` ships three new resources (`runs`, `runHistory`, `runTrace`) targeting the unified Phase 4-F2 + Phase 6 Gate 5 endpoints, plus A2A v0.3 envelope types for future use. Build verified (`npx tsc` clean for my changes). Per Phase 6 §4.3, **no public npm publish** — dist-tag only, REGISTRY_PUBLISH_DEFERRED until Phase 7 partner validation.

Carry-forward: pre-existing compliance.ts errors and runtime.ts legacy cleanup deferred to Phase 7.
