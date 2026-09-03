# Phase 6 Gate 1 — 统一 Embedded Contract

**Date**: 2026-07-13
**Tier**: `GATE1_EMBEDDED_CONTRACT_CONSOLIDATED`
**Estimate vs actual**: ~1h estimate / ~20min actual
**Code changes**: `backend/app/api/embedded.py` rewrite (1.0 src-serve → 2.0 dist-serve) + 3 DEPRECATED.md files

## What landed

### 1. `backend/app/api/embedded.py` 升级到 2.0

**Before** (Phase 1 stub): served raw `packages/icoder-embedded/src/icoder-assistant.ts` (TypeScript source, not compiled), preview page used 1.0 attribute-based API (`base-url`, `access-token`, `agent-ref`, `setPatientContext` method call), listened to deprecated `coding.completed` + `error` events.

**After** (Phase 6 Gate 1):
- Serves compiled `packages/icoder-embedded/dist/icoder-assistant.js` (falls back to "build first" banner if dist missing)
- Cache-Control: no-cache (so dev edits pick up immediately)
- Preview page uses 2.0 Corti-compatible method chain: `auth() → configureSession() → configure() → show()`
- Unified event listener with `{name, payload}` envelope
- Live event log overlay (bottom-right) showing `account.creditsConsumed` (yellow) / `error.triggered` (red) / `run.completed` (white) / others
- Sidebar collects: baseURL + JWT + agent key + patient name/id/encounterId + interface language + aiChat feature flag
- Initializes widget with full method chain on button click

### 2. 4 套重复 Web Component 实现整合策略

| Path | Status | Action |
|---|---|---|
| `packages/icoder-embedded/` | **CANONICAL** v2.0.0 | No change — already 1:1 Corti parity |
| `packages/icoder-web/` | **DEPRECATED** | Added DEPRECATED.md — 1.0 attribute-based + STT-only value preserved |
| `packages/web-components/` | **DEPRECATED** | Added DEPRECATED.md — early raw-JS prototype |
| `web-components/` (root) | **DEPRECATED** | Added DEPRECATED.md — early Lit-based prototype |

Each DEPRECATED.md explains:
- Why deprecated (1.0 attribute API vs 2.0 method API)
- What unique value remains (STT components not yet in canonical)
- Migration pointer to `packages/icoder-embedded/MIGRATION-2.0.md`
- Removal timeline (Phase 7, no earlier than 2026-08)

## Verification

```bash
# Backend imports clean
cd /e/Corti4C/backend && python -c "from app.api.embedded import router; print(f'OK — {len(router.routes)} routes')"
# → OK — 2 routes

# Dist exists (Phase 5 A5 build)
ls /e/Corti4C/packages/icoder-embedded/dist/
# → icoder-assistant.d.ts, icoder-assistant.js, index.d.ts, index.js

# TypeScript still type-checks
cd /e/Corti4C/packages/icoder-embedded && npx tsc --noEmit
# → (no output, exit 0)
```

## Files written / modified

| Path | Change |
|---|---|
| `backend/app/api/embedded.py` | Rewrite — 2.0 dist-serve + 2.0 preview HTML with method chain |
| `packages/icoder-web/DEPRECATED.md` | New — explains STT stays, assistant.ts deprecated |
| `packages/web-components/DEPRECATED.md` | New — whole package deprecated |
| `web-components/DEPRECATED.md` | New — whole package deprecated |

## Not done (out of Gate 1 scope)

- Live browser walkthrough of `/api/embedded/preview` — requires uvicorn running + manual JWT input. Deferred to Gate 7 (will be exercised as part of Medical Coding Demo).
- DEPRECATED.md lint check / CI enforcement — Phase 7 concern.

## Carry-forward to Gate 5

RunHistory / Trace / Cost 集成基本已完成(alembic 009 + 010 + per-run cost + TopBar + UsagePage)。Gate 5 只需在 `<icoder-embedded>` UI 加 "View Run Trace" 链接 + 加 `run.completed` event payload 中包含 `trace_url`。
