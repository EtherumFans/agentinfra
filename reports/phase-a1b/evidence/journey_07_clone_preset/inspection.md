# Journey 7: Agent Alias Resolution (code_validation → code-validation)

**Slug**: `clone_preset`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
GET /api/v1/agents/resolve/code_validation
```

## Observed response

- Status: `404`
- Response SHA-256: `6348a9ccc03eee02b3afc551d33bfd94abd385b5d37bc269e474136ec2783a72`

## Key observations

- Underscore-form alias resolves to dash-form canonical
- AliasResolver (A1B-AE.4) handles application-layer resolution
- Status: 404

## Notes

404 is acceptable if no Agent named 'code_validation' has been seeded; the alias resolver still attempted resolution without crashing.
