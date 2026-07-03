# OpenAPI path whitelist — reasons

Each entry in `path_whitelist.json` maps a frontend-declared path to the actual
OpenAPI path it corresponds to. Entries are only for paths the static regex
extractor can't normalize on its own (param-name mismatches are handled by
canonicalization; whitelist is for genuine path divergences).

## Entries

### `/api/runtime/trace/{id}` → `/api/runtime-legacy/trace/{pipeline_id}`

**Reason**: The `trace` method on `runtimeApi` in `services/api.ts:361` calls
`/api/runtime/trace/${pipelineId}`, but the backend registers the endpoint
under the deprecated `/api/runtime-legacy/` prefix (see `app/api/runtime.py:18`
and `:290`). The `/api/runtime/` prefix has not been re-exposed for this
endpoint.

**Why whitelisted**: This is a known path-prefix divergence. The trace
endpoint still works at the legacy path; updating the frontend to call
`/runtime-legacy/trace/...` would couple it to a deprecated prefix. The right
fix is to re-expose the trace endpoint under `/api/runtime/` (or move it to
`/api/runtime-platform/`), but that's a backend routing change that belongs in
a future cycle, not in Cycle 25 (which is engineering-stability-only, no new
endpoints).

**Used by**: `AgentTraceViewer.tsx:73` via `runtimeApi.trace(pipelineId)`.

**Remove this entry when**: The backend exposes `GET /api/runtime/trace/{id}`
(or `/api/runtime-platform/trace/{id}`) and the frontend path is updated to
match.

## Adding a new entry

Before adding an entry, ask: can the divergence be fixed instead? The
whitelist is for paths where fixing the divergence is out of scope for the
current cycle. Each entry must have a reason that explains:
1. What the divergence is (which path on frontend, which path on backend)
2. Why it can't be fixed in this cycle
3. Which file/line uses the path
4. When the entry should be removed (the condition that resolves the
   divergence)
