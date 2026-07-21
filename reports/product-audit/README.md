# Product Audit — README

**Sub-charter**: Phase A1A Gate 4R-I.6 through 4R-I.10
**Opened**: 2026-07-21

## Purpose

This directory holds the **current-state product audit** for iCoDer.
It is independent of the Git merge judgement (Gate 4R-I.1) and the
post-merge regression (Gate 4R-I.3). A clean merge does NOT imply a
clean product; product state is assessed here on its own merits.

The audit uses a strict 5-tier ladder (charter §1):

```
"code exists" → "interface exists" → "test passes" → "E2E usable" → "clinical quality acceptable" → "releaseable"
```

Each tier is proven independently. Lower tiers do NOT imply higher tiers.

## Subdirectories

| Path | Purpose | Sub-gate |
|---|---|---|
| `evidence/` | Per-capability evidence files (route test outputs, screenshots, Playwright traces, runtime proofs) | 4R-I.6 |
| `parity/` | Corti-vs-iCoDer parity matrix artefacts | 4R-I.7 |
| `release-readiness/` | MVP / Controlled Pilot / GA tier verdicts | 4R-I.9 |
| `roadmap/` | Development backlog with P0/P1/P2/P3 issues, owner roles, effort estimates | 4R-I.10 |

## Capability status enum (charter §9)

Each capability is graded against exactly one of these statuses. The
enum is closed; ad-hoc labels are forbidden.

```
IMPLEMENTED_AND_RUNTIME_VERIFIED
IMPLEMENTED_BUT_PARTIALLY_TESTED
IMPLEMENTED_BUT_BROKEN
CONTRACT_ONLY
STUB_OR_MOCK_ONLY
TEST_ONLY
DOCUMENTED_ONLY
NOT_IMPLEMENTED
BLOCKED_BY_MISSING_SPEC
BLOCKED_BY_EXTERNAL_DEPENDENCY
BLOCKED_BY_UNKNOWN_REQUIREMENT
```

## Verification dimensions (charter §9)

Each capability must be assessed on all 18 dimensions:

1. Route exists
2. Request schema
3. Response schema
4. Auth
5. Tenant scope
6. Data persistence
7. Error states
8. Idempotency
9. Streaming
10. Audit
11. Usage metering
12. Actual runtime (not just contract)
13. Test
14. Frontend entry
15. Documentation
16. Stub/mock indicator
17. External provider dependency
18. Production configuration support

## Forbidden shortcuts

- Marking a capability `IMPLEMENTED_AND_RUNTIME_VERIFIED` because the
  file exists (charter §1 forbids this)
- Marking a capability `IMPLEMENTED_AND_RUNTIME_VERIFIED` because a unit
  test passes (charter §1 forbids this)
- Marking a capability VERIFIED without an E2E runtime evidence file
- Counting "stub agents" or "mock STT" as production features

## Audit independence

This audit does NOT inherit Gate 4's PASS verdict (Gate 4 is REOPENED).
It does NOT inherit any earlier Phase A0 / A0.1 conclusion unless the
underlying code is reverified against current HEAD (`ca36c51`).

The audit is evidence-driven: every claim cites a file path + line
range or a runtime artefact (HTTP request/response, JUnit XML, log).
