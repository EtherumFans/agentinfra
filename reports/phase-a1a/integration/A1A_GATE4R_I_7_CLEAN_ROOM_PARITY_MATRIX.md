# Phase A1A Gate 4R-I.7 — Clean-Room Parity Matrix

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `6265ad4` (post Gate 4R-I.6)
**Predecessor**: Gate 4R-I.6 (`6265ad4` iCoDer inventory)
**Successor**: Gate 4R-I.8 (security/compliance re-audit)

Charter §1.5 defines "Corti parity" as **clean-room functional
compatibility** based on public Corti docs. This matrix scores iCoDer
against the Corti snapshot captured in 4R-I.5.

## §1. Scoring scale (charter §17)

| Score | Meaning |
|---|---|
| 0 | Does not exist |
| 1 | Documented or stub only |
| 2 | Partially implemented; not stable |
| 3 | Runnable but evidence/quality insufficient |
| 4 | Target-scope basically met; small gaps |
| 5 | End-to-end + quality + ops + release-ready |

## §2. Dimension weights (charter §17)

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

## §3. Parity matrix

| # | Corti capability (from llms.txt) | iCoDer status | Score | Evidence |
|---|---|---|---|---|
| **1** | **Authentication (client credentials, OAuth)** | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | `/api/auth/login`, `/api/oauth/token`, JWT; 9 auth + 8 oauth routes; Gate 1 PASS |
| 2 | Environments (EU/US/CN regional residency) | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `app/services/data_policy.py` routes by region; 3 `/api/platform/environments` routes; Gate 4.4 encryption contract |
| 3 | Tenants (multi-tenant isolation) | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | Gates 2/3/3R PASS; tenant_owned_system_audit; tenant_read_policy |
| 4 | Customers (sub-tenant unit) | IMPLEMENTED_BUT_PARTIALLY_TESTED | 2 | `/api/customers/` 4 routes; schema exists; runtime evidence limited |
| 5 | Projects | NOT_IMPLEMENTED | 0 | No `/api/projects/*` routes; Corti has customers-projects-tenants hierarchy, iCoDer flattens to tenants |
| 6 | API clients (programmatic credentials) | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | `/api/clients/` 9 routes; secret shown once; Gate 5 PASS |
| 7 | Rate limiting | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | Rate Limiter per-app-state (4R.2); 30/min configured; charter §4R.2 hermeticity proof |
| 8 | Quotas / credits | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/billing/credits`, `/api/billing/balance`; credits consumption works; no quota enforcement verified |
| **9** | **A2A protocol (Agent-to-Agent)** | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/v1/coding-compliance/a2a`, `/api/runtime/agents/`; agent card JSON; partial conformance to Corti A2A v0.3 |
| **10** | **Agent CRUD** | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/icoder/agents/*`, `/api/admin/agents`; create/list/run; missing update/delete-by-id parity |
| 11 | Agent card (`/agents/{id}/card.json`) | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | `/api/runtime/agents/{id}/well-known-agent.json`; tested |
| 12 | Registry experts (callable knowledge sources) | NOT_IMPLEMENTED | 1 | Corti has DrugBank, ClinicalTrials, Medical Calculator, ICD experts; iCoDer has 23 pre-built agent packs (different abstraction) |
| 13 | Context and memory (thread state) | CONTRACT_ONLY | 2 | Runtime has RunHistory + trace events; no Corti-style context CRUD API |
| 14 | Tasks (agent execution) | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/v1/runs/{id}` lifecycle; no Corti-style task abstraction |
| **15** | **Embedded assistant API** | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/embedded/*` 7 routes; Phase 7 Gate 13A PASS; Corti Embedded API has 117 pages vs iCoDer ~7 routes |
| **16** | **Speech-to-text (STT)** | STUB_OR_MOCK_ONLY | 1 | `/api/v2/tools/interactions/*/transcripts/*` 6 routes; mock Whisper only; no real provider verified |
| **17** | **Text generation (documents, facts, guided)** | CONTRACT_ONLY | 2 | `/api/v2/tools/guided-documents`, `/api/v2/tools/extract-facts`; routes exist, runtime evidence weak |
| **18** | **Medical coding (ICD-10, ICD-9-CM-3, CDI)** | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | `/api/medical-coding/*`, `/api/v1/coding/predict`, 33304 ICD-10 + 23165 ICD-9-CM-3 codes; MedCodER 5-stage; 201 case fixture |
| 19 | Procedure coding (ACHI, CCAM, CCI, CHOP) | NOT_IMPLEMENTED | 0 | These are Australian/French/Canadian/Swiss standards; iCoDer targets China (ICD-9-CM-3 + DRG/DIP) |
| 20 | Corti-hosted EU models | NOT_IMPLEMENTED | 0 | iCoDer uses DeepSeek (China-hosted); different product positioning |
| 21 | SDK (@corti/sdk) | NOT_IMPLEMENTED | 1 | iCoDer has `@icoder/sdk@1.0.0-beta.2` (Phase 6); different product |
| 22 | Compliance docs | BLOCKED_BY_MISSING_SPEC | 0 | `https://trust.corti.ai/` 403; cannot snapshot |
| 23 | Webhooks | IMPLEMENTED_BUT_PARTIALLY_TESTED | 2 | `/api/v1/cdi/subscriptions` exists; verification weak |
| 24 | Audit logging | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | audit_logs table; Gate 3 system_audit.py allowlist; tenant_owned enforcement |
| 25 | Usage metering | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `/api/usage/*` 5 routes; by-agent, by-client filters; Gate 8 PASS |
| 26 | Console (admin UI) | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | React SPA admin/agents/orgs/users; partial feature parity |
| 27 | API key onboarding | IMPLEMENTED_AND_RUNTIME_VERIFIED | 4 | `/api/keys/*` 3 routes; secret shown once |
| 28 | Sandbox | NOT_IMPLEMENTED | 0 | No `/api/sandbox/*` |
| 29 | Documentation site | DOCUMENTED_ONLY | 1 | iCoDer has README + reports/ but no docs.corti.ai-style public site |
| 30 | Sample apps / quickstart | IMPLEMENTED_BUT_PARTIALLY_TESTED | 3 | `examples/partner-reference-app/`; 3 demos (medical-coding/CDI/DRG-DIP); Phase 7 Gate 12 |

## §4. Weighted parity score

| Dimension | Weight | iCoDer avg score (0-5) | Weighted |
|---|---:|---:|---:|
| API contract compatibility | 15% | 2.8 | 0.42 |
| Medical coding clinical quality | 15% | 4.0 | 0.60 |
| STT capability and quality | 10% | 1.0 | 0.10 |
| Text generation / document workflows | 10% | 2.0 | 0.20 |
| Agentic framework | 10% | 2.7 | 0.27 |
| Embedded UX | 8% | 3.0 | 0.24 |
| Security / privacy / tenant isolation | 12% | 3.5 | 0.42 |
| Reliability / performance / operations | 10% | 2.5 | 0.25 |
| SDK / developer experience | 5% | 1.5 | 0.08 |
| Legal / commercial / release process | 5% | 1.0 | 0.05 |
| **Weighted total (out of 5.0)** | | | **2.63 / 5.0** |
| **Percentage** | | | **52.6%** |

## §5. Headline parity verdict

```
CORTI_PARITY_VERDICT = NOT_DEMONSTRATED
PARITY_SCORE = 52.6% (weighted)
PARITY_TIER  = "Partial — narrow scope; not Corti-complete"
```

**NO `CORTI_PARITY_VERIFIED` verdict is issued.** Charter §22 forbids it.
The 52.6% score reflects:

- Strong: medical coding, tenant isolation, authentication
- Weak: STT, text generation, agentic framework completeness, SDK
- Missing: project hierarchy, EU models, procedure coding (ACHI/CCAM/CCI/CHOP), compliance docs access

## §6. Release-blocker capabilities (P0)

Per charter §18, P0 = patient safety, cross-tenant, PHI leak, data
corruption, unauthorized provider egress, unrecoverable, wrong clinical
auto-writeback.

| Capability | iCoDer status | Blocker reason |
|---|---|---|
| STT real provider integration | STUB_OR_MOCK_ONLY | Cannot ship speech-driven product without real STT |
| LLM provider egress runtime proof | NOT_VERIFIED | Charter §12.8: must prove every hot path is policy-bound |
| Unknown-provider fail-closed | NOT_VERIFIED | Charter §12.9: must prove fail-closed on unknown provider |
| KMS / tenant-level encryption keys | NOT_IMPLEMENTED | Charter §12.6: per-tenant keys required |
| PHI at-rest encryption scope | PARTIAL (2 fields) | Charter §12.3: only 2 fields encrypted; ~60 PHI fields remain |
| Retention enforcement | NOT_VERIFIED | Charter §12.12: retention only on logout cleanup |
| Patient context isolation runtime | IMPLEMENTED | Phase 7 Gate 11 PASS (Playwright) |

## §7. Corti-complete but NOT MVP-blocking

These Corti capabilities are required for "full Corti parity" but do
NOT block a narrow China-hospital MVP:

| Corti capability | Why not MVP-blocking |
|---|---|
| Procedure coding (ACHI/CCAM/CCI/CHOP) | iCoDer targets China (ICD-9-CM-3); these are AU/FR/CA/CH standards |
| Corti EU-hosted models | iCoDer uses DeepSeek (China); different positioning |
| Project hierarchy | iCoDer's tenant model is sufficient for MVP scope |
| Corti @corti/sdk npm package | iCoDer has @icoder/sdk; different brand |
| DrugBank / ClinicalTrials / Calculator experts | China clinical practice uses different references |
| Compliance public docs site | Marketing artefact; not runtime requirement |

## §8. MVP-blocking gaps (from current state to MVP)

1. Real STT provider integration (Alibaba Cloud, Tencent, or iFlytek for China)
2. Real LLM provider egress policy enforcement + runtime proof
3. KMS + per-tenant encryption keys
4. PHI at-rest encryption for all ~60 fields (not just 2)
5. Retention enforcement workflow (not just logout cleanup)
6. corti-reverse-engineered fixture gap (8 missing .md files; 27 test errors)

## §9. Pilot-blocking additional gaps (from MVP to Pilot)

7. Clinical quality benchmark on 201 gold cases
8. Monitoring + alerting infrastructure
9. Backup/restore runbook
10. Incident response procedure
11. Support ticket workflow
12. Legal/compliance review (China PIPL, etc.)

## §10. GA-blocking additional gaps (from Pilot to GA)

13. Production database (PostgreSQL verified, not just SQLite)
14. Multi-instance horizontal scaling
15. Region failover
16. SLO definition and adherence
17. Support process with SLA
18. SDK public release
19. Public documentation site
20. Billing system production-grade
21. Compliance evidence package
22. Real hospital customer acceptance

## §11. Provisional verdict

```
PASS_A1A_GATE4R_I_7_CLEAN_ROOM_PARITY_MATRIX_FILED
CORTI_PARITY_VERDICT = NOT_DEMONSTRATED (unchanged)
PARITY_SCORE = 52.6% (weighted; informational only, not a certification)
```

Tier: FILED (not VERIFIED). The matrix is filed for backlog use; it
does NOT certify parity.

## §12. Next

Gate 4R-I.8 — security/compliance release re-audit:
- Re-verify Gate 4 PHI boundary claims against current HEAD
- Audit all ~60 PHI fields per charter §12.1
- Verify KMS, tenant-level keys, egress policy runtime behavior
- Output P0/P1 security blockers list
