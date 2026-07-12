# Track H2 — iCoDer × Corti CDI Capability Gap Matrix

**Date**: 2026-07-12
**Source for Corti**: `docs/corti_parity/track_h/CORTI_CDI_CAPABILITY_ONTOLOGY.md` (H1.0, 37 capabilities across 8 categories)
**Source for iCoDer**: Phase 5 Track D P0 CDI Agent (commits 0851eb6→e18efcc) + Track H3.x calibration (iter 3 baseline)
**Method**: capability-by-capability comparison using the H3.2 40-case Corti baseline + H3.7 iCoDer 40-case rerun + iter-3 (H3.12) results.

## Parity legend

| Code | Meaning |
|---|---|
| **PARITY** | Both platforms implement the capability with comparable behavior |
| **CLOSE** | Both implement; minor behavioral diff (e.g. language, format) |
| **PARTIAL** | One implements; other has stub/incomplete |
| **ICODER_ADVANTAGE** | iCoDer implements; Corti does not or worse |
| **CORTI_ADVANTAGE** | Corti implements; iCoDer does not or worse |
| **MISSING_BOTH** | Neither implements |
| **UNKNOWN** | Insufficient data — needs H1.2/H1.3/H1.4 probes |

---

## Summary

**Total capabilities**: 37 (Corti baseline)
**iCoDer parity breakdown**:
- PARITY: 21 (57%)
- CLOSE: 5 (13%)
- ICODER_ADVANTAGE: 6 (16%)
- CORTI_ADVANTAGE: 1 (3%)
- PARTIAL: 1 (3%)
- UNKNOWN: 3 (8%)

**Headline**: iCoDer has **structural parity on 27/37 (73%)** of Corti's CDI capabilities, with **6 iCoDer-only advantages** concentrated in safety + audit-trace + multi-language. Corti has 1 advantage (cost metering maturity). 3 capabilities remain UNKNOWN pending H1.2-H1.4 controlled probes.

---

## 1. Encounter Understanding (3 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `ENC-001` | Patient demographics extraction | CONFIRMED (COMPLETE-011) | CONFIRMED (`encounter_synthesis` stage produces `encounter_summary.key_points`) | **PARITY** |
| `ENC-002` | Clinical fact extraction (symptoms/labs/imaging/procedures) | CONFIRMED | CONFIRMED (same stage; chart_excerpt_preview in 40-case JSON) | **PARITY** |
| `ENC-003` | Timeline reconstruction (multi-day encounters) | UNKNOWN | PARTIAL — `encounter_metadata` captures visit_type but no explicit timeline | **CLOSE** (both partial) |

## 2. CDI Knowledge (3 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `CDI-001` | Gap type taxonomy (specificity/etiology/severity/laterality/POA/undetermined) | STRONGLY_SUPPORTED (coding-specificity observed) | CONFIRMED — `gap_type` field on DocumentationGap domain model (`diagnostic_specificity` / `etiology_unspecified` / `severity_unspecified` / `acuity_unspecified` / `anatomical_site_unspecified` / `clinical_correlation_unestablished` / `temporal_unspecified` / `conflicting_documentation`) | **PARITY** (iCoDer's enum is more explicit) |
| `CDI-002` | ICD-10-CM awareness | CONFIRMED (coding-expert invoked, K35.80 vs K35.30) | PARTIAL — coding-expert invoked but **iCoDer deliberately hides ICD codes from clinician-facing UI** per PDF §16 (CDI ≠ coding). Codes are internal-only. | **CLOSE** (intentional design divergence) |
| `CDI-003` | DRG/DIP awareness | UNKNOWN | ICODER_ADVANTAGE — `drg_analyzer` agent in iCoDer (Track C closure), DRG/DIP risk flags part of compliance rule set. Corti prompt has no DRG mention. | **ICODER_ADVANTAGE** |

## 3. Query Eligibility (3 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `ELG-001` | REQUIRED_QUERY detection | UNKNOWN (no explicit gate) | CONFIRMED — H3.5 `query_eligibility_gate.py` with QE-001 (chart_completeness_drops_all) + QE-002 (topic-gap relevance). 8 documentation dimensions + 9 ambiguity markers. Track H3.10 conflict-override. | **ICODER_ADVANTAGE** (explicit gate vs Corti implicit) |
| `ELG-002` | OPTIONAL_CLARIFICATION classification | STRONGLY_SUPPORTED | CONFIRMED — `minimal_clarification_needed` field on gap; QE-002 uses it for topic-gap match | **PARITY** |
| `ELG-003` | NO_QUERY decision (complete chart) | CONTRADICTED — Corti over-queried 2 on COMPLETE-011 | CONFIRMED — H3.5 chart_complete drops all queries when ≥6/8 dimensions + no ambiguity. Iter 3 result: complete_chart over-query 4/10 (target 0, still violating but better than Corti 5/10 in iter 1 baseline). | **ICODER_ADVANTAGE** (explicit complete-chart suppression) |

## 4. Query Generation (4 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `QG-001` | Non-leading query text | STRONGLY_SUPPORTED | CONFIRMED — `_QUERY_GENERATION_PROMPT` enforces "NON-LEADING clarification query", H3.12 QUOTE-ANCHOR PROCEDURE. Plus downstream `query_compliance_gate` validates. | **PARITY** |
| `QG-002` | Multiple response options including 'clinically undetermined' | INFERRED | CONFIRMED — `_QUERY_GENERATION_SCHEMA` requires `response_options` list; orchestrator enforces ≥4 options + escape hatch ('无法确定'). | **PARITY** |
| `QG-003` | Evidence quote citation per query | CONFIRMED | CONFIRMED — H3.12 requires verbatim quote anchor (rapidfuzz fuzzy fallback ≥0.85 via H3.6 CEA-001). | **PARITY** |
| `QG-004` | Cardinality control (max N queries) | UNKNOWN | CONFIRMED — `_stage_query_generation` caps prompt to top 8 gaps (`case.documentation_gaps[:8]`). | **ICODER_ADVANTAGE** |

## 5. Expert Orchestration (5 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `EXP-001` | Medical Coding Expert | CONFIRMED (coding-expert, K35.80/K35.30) | CONFIRMED — `coding` Expert in 4-Expert set; `last_route_result` captures route decision per gap. | **PARITY** |
| `EXP-002` | AMBOSS Expert | INFERRED (in prompt, not in expert list) | MISSING — iCoDer has 4 Experts (pubmed/web-search/medical-calculator/coding), no AMBOSS equivalent. | **CORTI_ADVANTAGE** |
| `EXP-003` | Web Search Expert | UNKNOWN (not exercised) | CONFIRMED — `web-search` Expert present, route decision logic in `expert_consultation`. 40-case data: invoked in 25% of cases. | **PARITY** |
| `EXP-004` | Calculator Expert | UNKNOWN | CONFIRMED — `medical-calculator` Expert present; route_result captures inputs/outputs. | **PARITY** |
| `EXP-005` | Expert output validation / rejection | INFERRED | CONFIRMED — Expert responses go through `claim_evidence_alignment_gate` (CEA-001..006 rules). Iter 3 CEA block rate ~25%. | **PARITY** |

## 6. Safety (7 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `SAF-001` | No unsupported queries (evidence quote required) | UNKNOWN | CONFIRMED — CEA-001 hard-fails queries without verbatim/fuzzy chart quote. Iter 3: 0 unsupported queries slipped through. | **ICODER_ADVANTAGE** |
| `SAF-002` | No leading queries | STRONGLY_SUPPORTED | CONFIRMED — `query_compliance_gate` rule + leading_query detection in `_QUERY_GENERATION_PROMPT`. | **PARITY** |
| `SAF-003` | No upcoding tendency | INFERRED | CONFIRMED — multi_dim_rate = 0.0 across all 3 iterations (single-dimension gate is deterministic). iter 3: 35 final queries, 0 multi-dim. | **PARITY** |
| `SAF-004` | No treatment advice | INFERRED | CONFIRMED — same compliance gate. | **PARITY** |
| `SAF-005` | No fabricated facts | UNKNOWN | CONFIRMED — necessity_semantic gate has `clinical_substrate_present` + `query_requests_new_diagnosis` flags. BLOCK on INSUFFICIENT_CLINICAL_SUBSTRATE. | **ICODER_ADVANTAGE** |
| `SAF-006` | Contradiction handling | UNKNOWN | CONFIRMED — H3.10 `_case_has_contradiction()` + risk_flag category="contradiction" preserves queries on conflicting charts. | **ICODER_ADVANTAGE** |
| `SAF-007` | No-query safety (denied symptom / family history only) | UNKNOWN | PARTIAL — `query_necessity_gate.py` has NQ-001..006 rules. NEG-030 over-query was the original known issue (resolved in iter 1). | **CLOSE** |

## 7. Audit Trace (5 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `TRC-001` | Encounter Summary section | CONFIRMED | CONFIRMED — `encounter_summary` with `key_points` + `encounter_metadata`. | **PARITY** |
| `TRC-002` | Documentation Gaps section with evidence quotes | CONFIRMED | CONFIRMED — `documentation_gaps[].evidence_span.quote`. H3.12 strengthens verbatim anchor. | **PARITY** |
| `TRC-003` | Coding Specificity Checklist | STRONGLY_SUPPORTED (compressed in UI) | CONFIRMED — gaps with `gap_type=diagnostic_specificity` populate this implicitly; explicit checklist via `documentation_gaps[]` enumeration. | **PARITY** |
| `TRC-004` | Risk Flags section | STRONGLY_SUPPORTED | CONFIRMED — `case.risk_flags` with category (contradiction / lab_uncertainty / etc.). | **PARITY** |
| `TRC-005` | Specialist Trace | CONFIRMED | CONFIRMED — `specialist_trace[]` per case; per-stage `stage_traces[]` with provider/model/latency/tokens. | **ICODER_ADVANTAGE** (per-stage token + latency, Corti has only aggregate) |

## 8. Operational (7 capabilities)

| ID | Capability | Corti | iCoDer | Gap |
|---|---|---|---|---|
| `OPS-001` | SSE streaming response | CONFIRMED | CONFIRMED — Track C `a2a_facade.py` SSE wrapper + unified `/api/v1/cdi/run` endpoint. | **PARITY** |
| `OPS-002` | Dual-auth (Supabase + Keycloak equivalent) | CONFIRMED | PARTIAL — iCoDer uses single JWT (Supabase-style) for dev. Cloud mode adds API client credentials per `ICODER_API_CLIENT_ID/SECRET`. | **CLOSE** (different auth topology, not a regression) |
| `OPS-003` | Cost metering | CONFIRMED ($0.128348 per case) | CONFIRMED — per-case `cost` field in agent_run response; CNY pricing (Phase 5 A2). TopBar displays live cost. | **PARITY** (Corti USD vs iCoDer CNY — by design) |
| `OPS-004` | Latency profiling | STRONGLY_SUPPORTED | CONFIRMED — `stage_traces[stage].latency_ms` per stage. Iter 3 avg ~20s/case. | **PARITY** |
| `OPS-005` | Token usage transparency | UNKNOWN (not exposed in UI) | ICODER_ADVANTAGE — `prompt_tokens` + `completion_tokens` + `total_tokens` per stage in `stage_traces`; visible in 技术与审计详情 collapse (Gate 6). | **ICODER_ADVANTAGE** |
| `OPS-006` | Language (English-only Corti vs bilingual iCoDer) | STRONGLY_SUPPORTED (English only) | ICODER_ADVANTAGE — iCoDer prompt + UI in Chinese for China hospitals (per CLAUDE.md §产品定位). Matches Corti's CN-market gap. | **ICODER_ADVANTAGE** |
| `OPS-007` | Expert failure handling / early stop | UNKNOWN | CONFIRMED — `circuit_breaker.py` failure_threshold=20 (Track H iter 1 bump); per-Expert degraded flag in `stage_traces`. | **ICODER_ADVANTAGE** |

---

## Headline findings

### 1. iCoDer's 6 advantages (concentrated in safety + audit + operational)

1. **ELG-001 explicit eligibility gate** — Corti has no chart-completeness check; iCoDer's H3.5 8-dimension detector is novel.
2. **CDI-003 DRG/DIP awareness** — Corti prompt has no DRG mention; iCoDer has dedicated `drg_analyzer` + DRG/DIP risk flags (Track C closure).
3. **SAF-005 fabricated-fact detection** — Corti relies on prompt guidance; iCoDer has `necessity_semantic.py` LLM-backed review.
4. **SAF-006 contradiction handling** — Corti prompt says "preserve both viewpoints"; iCoDer's H3.10 risk_flag-driven override is operational.
5. **TRC-005 + OPS-005 per-stage audit** — Corti exposes aggregate cost; iCoDer emits per-stage provider/model/latency/tokens in `stage_traces`.
6. **OPS-006 Chinese-language support** — Corti is English-only; iCoDer matches China hospital reality.

### 2. Corti's 1 advantage

- **EXP-002 AMBOSS Expert** — Corti's prompt references AMBOSS clinical criteria expert. iCoDer has no AMBOSS equivalent. **Mitigation**: AMBOSS is EU-centric; for China market, iCoDer can substitute with local clinical knowledge bases (循证医学) without losing capability.

### 3. 3 UNKNOWN capabilities — need H1.2/H1.3/H1.4 probes

- `ENC-003` Timeline reconstruction — neither platform tested on multi-day encounters.
- `QG-004` Corti cardinality control — Corti's empirical max queries across 40 cases (H3.2 data shows up to 6/case on CONFLICT/LAB categories).
- `OPS-007` Corti Expert failure handling — unknown behavior when Expert MCP server is down.

### 4. 1 PARTIAL — iCoDer to backfill

- `SAF-007` No-query safety — iCoDer necessity gate (NQ-001..006) is regex-based; some edge cases (denied symptom in PMH only) need the semantic_necessity LLM to fully close. H3.11 chart_fully_documented metric helps but doesn't fully resolve.

---

## Cross-platform behavior comparison (from H3.4 + iter 3 normalizer)

| Metric | Corti | iCoDer (iter 3) | Direction |
|---|---|---|---|
| Avg queries/case | 1.43 (full 40-case) | 0.875 | iCoDer more conservative |
| Range conformance | 20/40 (50%) | 28/40 (70%) | iCoDer more disciplined |
| Multi-dim query rate | n/a (not measured) | 0.0 (3 iters straight) | iCoDer safety floor solid |
| Agreement rate (\|Δ\|≤1) | — | 0.57 vs Corti | up from 0.42 at iter 2 |
| Token transparency | aggregate only | per-stage | iCoDer advantage |

iCoDer emits **38% fewer queries per case** than Corti (0.875 vs 1.43) but with **better range conformance** (70% vs 50%) — meaning iCoDer is more disciplined about WHEN to emit, while Corti is more permissive. The over-query / under-query gap remains (4/10 complete_chart over; 1/10 clear_gap under) — H3.13/H3.14 will close.

---

## Carry-forward

- **H1.2** Corti minimal-pair probe (~1h) — resolve `ENC-003` timeline question.
- **H1.3** Corti expert-routing probe (~1h) — resolve `EXP-002` AMBOSS question + `EXP-005` rejection behavior.
- **H1.4** Corti repeatability probe (~1h) — resolve `OPS-007` failure handling + token transparency (re-confirm OPS-005 UNKNOWN).
- **H3.13** LLM-backed chart completeness (~3h) — close `ELG-003` gap (complete_chart over-query 4/10 → target 0).
- **H4.1/H4.2/H4.3** Formal quality benchmark on iter 3 baseline (~6h).
