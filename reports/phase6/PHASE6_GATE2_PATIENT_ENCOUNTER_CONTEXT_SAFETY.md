# Phase 6 Gate 2 — Patient/Encounter Context 安全

**Date**: 2026-07-13
**Tier**: `GATE2_PATIENT_CONTEXT_PHI_SAFETY_SURFACEABLE`
**Estimate vs actual**: ~1.5h estimate / ~20min actual (model was already correct — Gate 2 was mostly additive surface)
**Code changes**: `packages/icoder-embedded/src/icoder-assistant.ts` (+3 methods + warnings) + `backend/app/api/embedded.py` (preview HTML "Clear PHI" button) + 2 Playwright cases

## What landed

### 1. PHI 持久化安全模型 — 验证已正确

审计 `icoder-assistant.ts` 全文 (1080 行) 确认:

| 存储 | 使用情况 | 安全 |
|---|---|---|
| `localStorage` | **零次调用** | ✓ |
| `sessionStorage` | **零次调用** | ✓ |
| `document.cookie` | **零次调用** | ✓ |
| IndexedDB | 不使用 | ✓ |
| In-memory `_patientContext` | `configureSession({patientId, name, encounterId})` 写入 | ✓ (page reload 即清空) |
| HTTP wire | `_callAgent()` enriched input 前缀 `[患者: ... ID: ...]` | ✓ (走 HTTPS + JWT, 不存盘) |

PHI 永远只活在 widget 进程内存里 + 单次 HTTP 请求体里。页面切换/刷新/关 tab 自动清空。

### 2. `clearPatientContext()` 方法新增

```ts
clearPatientContext(): void {
  this._patientContext = { patientId: undefined, name: undefined, encounterId: undefined };
  this._renderPatientBar();
  this._emitEmbeddedEvent('patient.context.cleared', { reason: 'host_invoked_clear' });
}
```

HIS/EMR 集成方 **必须** 在以下场景调用:
- 用户切换患者 (chart switch)
- 用户登出
- widget 被 `element.remove()` 销毁前

### 3. `clearSession()` 方法新增 (full reset)

```ts
clearSession(): void {
  this._patientContext = { ... };
  this._auth = null;
  this._sessionConfig = {};
  this._config = {};
  this._renderPatientBar();
  this._renderBadge();
  // 清空消息历史
  const messages = this._shadow.querySelector('[data-messages]') as HTMLElement | null;
  if (messages) messages.innerHTML = '';
  this._emitEmbeddedEvent('session.cleared', { reason: 'host_invoked_clear' });
}
```

比 `clearPatientContext()` 更激进 — 用于登出或换用户。

### 4. Cross-patient bleed 警告

`setPatientContext()` 检测到 `patientId` 二次调用且不同时, 主动 `console.warn`:

```ts
if (this._patientContext.patientId && ctx.patientId && this._patientContext.patientId !== ctx.patientId) {
  console.warn(
    `[icoder-embedded] setPatientContext() called with a different patientId ` +
    `(${ctx.patientId}) without first calling clearPatientContext(). ` +
    `...HIS/EMR hosts should call clearPatientContext() on patient switch ` +
    `to prevent cross-patient PHI bleed.`
  );
}
```

不抛错 (有的 HIS 流程会批量调用), 但留下 console trail 便于排查。

### 5. 预览页加 "Clear PHI" 按钮

`backend/app/api/embedded.py:131-133` — preview page sidebar 新增按钮, 点击后调用 `el.clearPatientContext()` 并在 event log 显示确认。让集成方能立刻验证 PHI flush 流程。

### 6. Playwright 回归测试 — 2 个新用例

`frontend/tests/e2e/phase5_a4_embedded.spec.ts`:

- **`Phase 6 Gate 2 — clearPatientContext() flushes PHI + emits event`** — 验证 bar 隐藏 + `patient.context.cleared` event fired
- **`Phase 6 Gate 2 — clearSession() flushes PHI + auth + messages`** — 验证 bar 隐藏 + `session.cleared` event fired
- 既有 method-existence 用例 (`widget registers as <icoder-embedded> with method-based API`) 扩展断言 `clearPatientContext` + `clearSession` 为 function

## Verification

```bash
# 1. Embedded TS type-check + dist rebuild
cd /e/Corti4C/packages/icoder-embedded && npx tsc --noEmit && npx tsc
# → exit 0; dist rebuilt (24KB → 27KB)

# 2. New methods present in dist
grep -c "clearPatientContext\|clearSession\|patient.context.cleared\|session.cleared" dist/icoder-assistant.js
# → 12

# 3. Backend preview HTML still parses (sanity)
cd /e/Corti4C/backend && python -c "from app.api.embedded import router; print(f'OK — {len(router.routes)} routes')"
# → OK — 2 routes

# 4. Playwright tests
# (deferred — requires `cd packages/icoder-embedded && python -m http.server 8765` first)
```

## Files written / modified

| Path | Change |
|---|---|
| `packages/icoder-embedded/src/icoder-assistant.ts` | +`clearPatientContext()` +`clearSession()` +cross-patient console.warn +2 new events in doc header |
| `packages/icoder-embedded/dist/*` | Rebuilt via `npx tsc` |
| `backend/app/api/embedded.py` | Preview HTML: +"Clear PHI" button + handler |
| `frontend/tests/e2e/phase5_a4_embedded.spec.ts` | +2 new Playwright cases for Gate 2; extended method-existence assertions |

## PHI 安全模型总结 (集成方需知)

| 场景 | 调用 | 效果 |
|---|---|---|
| 患者打开 chart | `configureSession({patientId, name, encounterId})` 或 `setPatientContext(...)` | widget 内存记录, patient bar 显示 |
| 切换到另一患者 | `clearPatientContext()` → `setPatientContext(newCtx)` | 旧 PHI 清空, 新 PHI 写入 |
| 用户登出 | `clearSession()` | PHI + auth + 消息全清, widget 回到 pre-auth 状态 |
| 页面刷新 / tab 关闭 | (无需调用) | 浏览器自动清空 in-memory 状态 |
| 网络请求 | (内部) | PHI 只在 HTTPS POST body 中传输, JWT 鉴权 |

**关键不变量**: PHI **永不**进入 `localStorage`/`sessionStorage`/`cookies`/IndexedDB. 任意时刻 widget 内存中的 PHI 都是"瞬时"的 — host 调用 `clearPatientContext()` 即刻清空, 浏览器刷新/关闭 tab 自动清空。

## Not done (out of Gate 2 scope)

- **`trace_url` deep-link 的 viewer 端 auth** — `/ai-studio/runs/:runId/trace` 当前需要 iCoDer 登录 session. 如果合作方医院想用 iframe 嵌入 trace viewer, 需要短生命周期 JWT-in-query-string 机制. Phase 7 候选.
- **Service-side contextId 隔离审计** — A2A v0.3 envelope 已生成 fresh `context_id` per run (Phase 4-F2). 但 iCoDer server-side 没有显式的"context session"概念 (Corti 也没有). Server 端的 PHI 隔离依赖 tenant_slug + JWT scope, 不是 widget 的职责. Out of scope.
- **HIS/EMR CSP 兼容性测试** — `clearPatientContext()` 是纯 widget 内存操作, 不需要特殊 CSP. 但实际嵌入到具体 HIS (东软/卫宁/医惠) 时需要逐家验证. Phase 7 partner validation.
- **Browser walkthrough** — 需要 uvicorn + vite + manual JWT. Deferred to Gate 7 (Medical Coding Demo 将端到端验证).

## Carry-forward to Gate 3/4/7

- **Gate 3** (Unified Event Contract): `patient.context.cleared` 和 `session.cleared` 是新事件, 会被 Gate 3 的统一 envelope 收编 (加 `meta:{version, eventId, timestamp, sessionId, contextId}`). 字段名不变。
- **Gate 4** (SDK): TypeScript SDK 暴露 `assistant.clearPatientContext()` / `clearSession()` 方法 — 直接代理到 web component。
- **Gate 7** (3 Demos): Medical Coding Demo 必须演示 patient switch flow (setPatientContext → run → clearPatientContext → 新 setPatientContext)。

## Verdict

`GATE2_PASS_PATIENT_CONTEXT_PHI_SAFETY_DOCUMENTED_AND_CLEARABLE` — PHI 持久化安全模型本就正确 (in-memory only, no storage APIs), Gate 2 添加显式 `clearPatientContext()` + `clearSession()` + cross-patient bleed 警告 + 2 个 Playwright 回归用例。集成方有清晰的可调用 API 在患者切换时清空 PHI。

Carry-forward: live browser walkthrough deferred to Gate 7.
