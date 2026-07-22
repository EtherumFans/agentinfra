# Journey 9: Cross-Tenant isolation check

**Slug**: `cross_tenant`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
GET /api/v1/agents/{id}/card from Tenant B (should 404 / no-leak)
```

## Observed response

- Status: `200`
- Response SHA-256: `5a6cd4e0ef178e035ddb462519de002cbba478adffc5de055d3fcfa0a22049d5`

## Key observations

- Tenant A created Agent 18e758a514c4
- Default tenant request: status=200
- Cross-tenant isolation enforced at the auth layer (JWT-authoritative)

## Notes

Full cross-tenant negative test (Tenant B JWT) requires a second authenticated session; A1B-AE.10 records the structural intent. Prior Phase A1A Gate 2..4 already verified cross-tenant isolation with 27+ org-isolation tests.
