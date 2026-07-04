# OpenAPI path whitelist — reasons

Each entry in `path_whitelist.json` maps a frontend-declared path to the actual
OpenAPI path it corresponds to. Entries are only for paths the static regex
extractor can't normalize on its own (param-name mismatches are handled by
canonicalization; whitelist is for genuine path divergences).

## Entries

(empty — `path_whitelist.json` is `{}` as of Phase 2.1-B Step 2)

The previous entry mapping `/api/runtime/trace/{id}` → `/api/runtime-legacy/trace/{pipeline_id}`
was removed in Phase 2.1-B Step 1+2 when:
- `app/api/runtime.py` was deleted (Step 1, commit 1c6c4c0)
- The `trace` method on `runtimeStatusApi` in `services/api.ts` was deleted (Step 2, commit 9a2723c)
- `AgentTraceViewer.tsx` was deleted (Step 2, commit 9a2723c)

No whitelist entries are currently needed — all surviving frontend API calls
resolve to paths present in `docs/openapi/openapi.json` directly.

## Adding a new entry

Before adding an entry, ask: can the divergence be fixed instead? The
whitelist is for paths where fixing the divergence is out of scope for the
current cycle. Each entry must have a reason that explains:
1. What the divergence is (which path on frontend, which path on backend)
2. Why it can't be fixed in this cycle
3. Which file/line uses the path
4. When the entry should be removed (the condition that resolves the
   divergence)
