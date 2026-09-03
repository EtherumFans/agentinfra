# Corti Parity Analysis — README

**Sub-charter**: Phase A1A Gate 4R-I.5 through 4R-I.7
**Opened**: 2026-07-21

## Definition: "Corti parity"

In this project, "Corti parity" means **clean-room functional
compatibility** based on publicly available official Corti documentation.
It does NOT mean copying Corti source code, prompts, UI assets,
trademarks, or non-public materials.

The 5 rules of clean-room parity (charter §1.5):

1. Define compatible behavior from public, legally obtained official docs.
2. Independently implement interfaces, workflows, and user value.
3. Do NOT copy proprietary source code, internal prompts, model weights,
   or restricted materials.
4. Do NOT impersonate Corti or use brand assets that could cause
   source confusion.
5. Mark all undocumented behavior as `UNKNOWN` rather than guessing.

## Canonical sources (only these)

| Source | URL | Use |
|---|---|---|
| Corti main site | `https://www.corti.ai/` | Product positioning, marketing claims (context only, not parity authority) |
| Corti docs | `https://docs.corti.ai/` | API contracts, capability lists, integration patterns |
| Corti docs LLM dump | `https://docs.corti.ai/llms.txt` | Single-file text dump for clean-room snapshot |
| Corti trust | `https://trust.corti.ai/` | Security, compliance, regional deployment claims |
| Official SDK pages | (TBD by Corti docs link) | SDK contract reference |

## Forbidden sources

These are NOT acceptable as canonical target:

- Third-party blog posts
- Search-engine summaries
- Non-official screenshots
- This repo's own historical `docs/corti-reverse-engineered/` content
- Memory of Corti behavior from prior work

## Subdirectories

| Path | Purpose | Sub-gate |
|---|---|---|
| `official-snapshot/` | Frozen snapshot of Corti public docs (captured 2026-07-21) | 4R-I.5 |
| `api-contract/` | Per-endpoint Corti API contract (request/response/auth/scope) | 4R-I.7 |
| `capability-matrix/` | 30+ capability dimensions × iCoDer status | 4R-I.7 |
| `clean-room/` | Implementation notes for clean-room compatibility decisions | 4R-I.7 |
| `clinical-benchmarks/` | (placeholder; gated by separate clinical quality charter) | DEFERRED |
| `embedded/` | Embedded assistant contract comparison | 4R-I.7 |
| `sdk/` | SDK contract comparison | 4R-I.7 |

## Snapshot procedure (charter §8)

1. `WebFetch https://docs.corti.ai/llms.txt` — primary canonical dump.
2. `WebFetch https://docs.corti.ai/` — secondary index.
3. `WebFetch https://trust.corti.ai/` — trust/security/compliance.
4. Save raw captures to `official-snapshot/`.
5. SHA-256 each capture.
6. Per-endpoint, extract: method, path, request schema, response schema,
   auth model, tenant scope, error states, streaming, idempotency,
   pagination, rate limit, usage metering, audit, webhooks.
7. Mark every undocumented behavior as `UNKNOWN`.

## Parity matrix grading

Per capability dimension (charter §17):

| Score | Meaning |
|---|---|
| 0 | Does not exist |
| 1 | Documented or stub only |
| 2 | Partially implemented; not stable |
| 3 | Runnable but evidence/quality insufficient |
| 4 | Target-scope basically met; small gaps |
| 5 | End-to-end + quality + ops + release-ready |

Dimension weights (charter §17):

| Dimension | Weight |
|---|---:|
| API contract compatibility | 15% |
| Medical coding clinical quality | 15% |
| STT capability and quality | 10% |
| Text generation / document workflows | 10% |
| Agentic framework | 10% |
| Embedded UX | 8% |
| Security / privacy / tenant isolation | 12% |
| Reliability / performance / operations | 10% |
| SDK / developer experience | 5% |
| Legal / commercial / release process | 5% |

Only compute the percentage if the canonical target snapshot is complete.

## Forbidden verdicts

This sub-charter does NOT issue `CORTI_PARITY_VERIFIED`. The mandatory
state remains:

```
CORTI_PARITY_VERDICT = NOT_DEMONSTRATED
```

regardless of matrix score. The matrix is a gap-finding tool, not a
certification.
