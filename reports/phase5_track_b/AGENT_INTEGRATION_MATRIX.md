# Agent Integration Matrix (B-1.5)

**Date:** 2026-07-11
**Source data:** `outputs/phase5_track_b/agent_integration_matrix.csv`
**Comparison:** Corti vs iCoDer platform-level integration capability
**Dimensions:** 16 per PDF §10

## Coverage matrix

| Integration | Corti | iCoDer | Diff | Notes |
|---|---|---|---|---|
| browser_only | ✓ | ✓ | = | Both have web SPA |
| server_api | ✓ | ✓ | = | REST API |
| sdk_js | ✓ | ✓ | = | Corti: @corti/sdk; iCoDer: packages/icoder-embedded |
| sdk_python | ✗ | ✗ | = | Neither has official Python SDK |
| embedded_web_component | ✓ | ✓ | = | Corti: Web Component; iCoDer: Phase 5 A4 |
| batch_api | ✗ | ✗ | = | Neither (P2 future) |
| streaming_sse | ✓ | ✗ | **-1 Corti** | Corti SSE per Phase 4-H §6; iCoDer capabilities.streaming=false |
| webhook_callbacks | ✓ | ✗ | **-1 Corti** | Corti outbound webhooks; iCoDer none (P2) |
| a2a_protocol | ✓ | ✓ | = | Both implement A2A v0.3 |
| mcp_protocol | ✓ | ✓ | = | Both implement MCP |
| oauth2 | ✓ | ✓ | = | Both |
| api_key | ✓ | ✓ | = | iCoDer Phase 4-G API Client |
| mtls | ✗ | ✗ | = | Neither (enterprise-tier later) |
| webhooks_outbound | ✓ | ✗ | **-1 Corti** | Corti has; iCoDer none |
| storage_api | ✓ | ✓ | = | Both |
| multi_tenant | ✓ | ✓ | = | iCoDer Phase 5 cloud-flip |

**Corti total:** 12/16
**iCoDer total:** 9/16
**Gap:** 3 capabilities (streaming_sse, webhook_callbacks, webhooks_outbound)

## Gap analysis

### P1 gaps (close in Phase 5 Track C or Phase 6)

1. **streaming_sse** — Corti agents stream output tokens via SSE; iCoDer returns single JSON envelope after completion. For long-running agents (medcoder_deep mode ~25s), streaming would improve UX. **Effort**: 2-3 days (add SSE endpoint + frontend EventSource).
2. **webhook_callbacks** — Corti can POST results to a configurable webhook URL; iCoDer requires polling. **Effort**: 1-2 days (add webhook registration + signing).

### P2 gaps (defer to post-China-launch)

3. **webhooks_outbound** — Outbound webhook delivery with retry. Often paired with webhook_callbacks; bundle implementation. **Effort**: 1 day (bundled with #2).

### Architectural parity confirmed (13/16 dims)

The 13 parity dimensions confirm iCoDer has caught up to Corti at the platform integration level since the Phase 4 cloud-flip. The remaining 3 gaps are progressive enhancements, not blockers.

## SDK comparison

| Feature | @corti/sdk | @icoder/embedded |
|---|---|---|
| NPM published | ✓ | prep (Phase 5 A4) |
| TS types | ✓ | ✓ |
| Method-based API | ✓ (`cortiClient.agents.create()`) | ✓ Phase 5 A1-A3 (method-based refactor) |
| A2A message format | ✓ (A2A v0.3) | ✓ (A2A v0.3) |
| OAuth2 | ✓ | ✓ |
| Embedded widget | ✓ | ✓ |
| Docs site | ✓ (corti.com/docs) | needed (Phase 5 D) |

**SDK status:** ~85% parity. Missing: published NPM package (Phase 5 A4 prep complete), docs site.

## API key / OAuth2 dual auth

iCoDer supports BOTH API key (Phase 4-G backend-service) AND OAuth2 (ROPC embedded Web Component). Corti does the same. No gap.

## Multi-tenant implementation

iCoDer's multi-tenant model (post-Phase 5 cloud-flip):
- Environment: EU/US/CN (3)
- Tenant: 医院 (per-tenant DB schema or shared-with-row-level-security)
- API Client: backend-service OR ROPC-embedded (per hospital integration)

Matches Corti's Environment → Organization → Project hierarchy conceptually.

## Recommendation

For Phase 5 Track C:
- **P1**: Implement streaming_sse (long-running medcoder_deep mode benefits most)
- **P2**: Implement webhook_callbacks + webhooks_outbound (hospital HIS integration needs)
- **P2**: Publish `@icoder/embedded` to NPM + docs site

Full data: `outputs/phase5_track_b/agent_integration_matrix.csv` (2 rows × 17 columns).
