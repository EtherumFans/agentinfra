# Journey 8: Context Delete (negative test — non-existent Context)

**Slug**: `context_delete`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
DELETE /api/v1/agents/contexts/ctx-does-not-exist-2026-07-22T092838Z
```

## Observed response

- Status: `404`
- Response SHA-256: `cfa2856048a655f4abec3a09b432a15cf58edda6a70cdcab3b14664af0a4905b`

## Key observations

- Non-existent Context ID: ctx-does-not-exist-2026-07-22T092838Z
- Status: 404 (404 = no-leak; 405 = endpoint not wired; both acceptable)
- No exception, no PHI leak
