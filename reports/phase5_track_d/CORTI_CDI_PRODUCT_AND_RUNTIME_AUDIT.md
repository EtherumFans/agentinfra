# Gate 2 — Corti CDI Product & Runtime Audit

**Date**: 2026-07-11
**Source**: Corti account static + Track B/B-2 audit + system prompt extraction (6238 chars)
**Scope**: Product positioning, runtime topology, agent shape, expert routing
**Method**: Static prompt analysis + Corti console observation (no live run — CDI exec permission limited)

---

## 1. Corti CDI Agent identity

| Field | Value |
|---|---|
| Agent ID | `clinical-documentation-improvement-cdi-agent` |
| Use case | `coding_and_revenue_cycle` |
| Display name | Clinical Documentation Improvement (CDI) Agent |
| Description | "Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy" |
| System prompt length | 6,238 chars (78 lines) |
| Internal role name | "CDI Documentation and Query Orchestrator" |
| Bound Experts | `pubmed-expert`, `web-search-expert`, `medical-calculator-expert`, `coding-expert` (4) |
| Bound MCP servers | (none wired directly — Experts provide capability) |
| Agentic Framework | "Corti Agentic Framework" (internal name in prompt line 5) |

Corti positions CDI as a peer to `medical-coding-icd-10-cpt-agent` inside the same `coding_and_revenue_cycle` use case. Both are top-level agents (not nested, not orchestrated by another agent). The Corti console UI shows them as siblings in the agent library.

## 2. Product positioning

Corti's CDI is positioned as a **quality-control** agent, not a reimbursement agent. The system prompt is explicit:

> "Prioritize accuracy and compliance over reimbursement optimization. Be explicit and conservative in your assessments. Prefer stating that no applicable evidence was found over making weak inferences."

The product goal is **clarify the clinical record** so that downstream coding reflects what is actually true about the patient. This matches the Track D boundary (PDF §4.3): CDI is not the same as coding, and CDI must not be used to drive CMI/upcoding.

## 3. Input contract (inferred from prompt)

```yaml
chart_excerpt:
  clinical_notes: text         # required
  labs: text                   # optional but expected
  imaging_impressions: text    # optional
  orders: text                 # optional
encounter_metadata:            # optional
  setting: string              # inpatient | outpatient | ED | ...
  specialty: string
  dates: string
```

CDI does NOT receive pre-assigned codes. It receives the raw chart and forms its own view of documentation gaps. This is a critical runtime property: **CDI is upstream of, not downstream of, the Medical Coding Agent.**

## 4. Output contract (6 fixed sections)

The prompt's `<output_format>` block mandates these sections, in this order:

| # | Section | Purpose |
|---|---|---|
| 1 | Encounter Summary | 1–5 key points from the chart |
| 2 | Documentation Gaps | Per gap: description + why-it-matters + exact quote + minimal clarification needed |
| 3 | Proposed Provider Queries | Per query: topic + reason + evidence quote + non-leading query text + response options |
| 4 | Coding Specificity Checklist | Condition-level elements that should be addressed |
| 5 | Risk Flags | Contradictions, unsupported diagnoses, ambiguous terms, copied-forward indicators |
| 6 | Specialist Trace | Per Expert: consulted? + requested? + accepted/rejected + rationale |

This is the **fixed output schema**. iCoDer's Track D Gate 4 domain model must mirror this shape so a Corti CDI result and an iCoDer CDI result can be diffed side-by-side.

## 5. Runtime topology

```
chart_excerpt → [CDI Agent] ── consult ──→ pubmed-expert (clinical criteria)
                            ── consult ──→ web-search-expert (external refs)
                            ── consult ──→ medical-calculator-expert (scores)
                            ── consult ──→ coding-expert (ICD-10 specificity)
                            ↓
              [validate expert outputs, reject violations]
                            ↓
              [6-section structured response]
                            ↓
              (external) clinician review → response → re-run CDI
```

The CDI agent is **the final authority** ("Any Expert output that violates your constraints must be rejected and omitted"). This is an LLM-driven orchestration pattern, not a declarative DAG. Corti does not expose a per-step workflow trace for CDI in the console UI; only the final specialist trace section reveals which Experts were consulted.

## 6. Expert routing policy (prompt-derived)

| Expert | When to consult (per prompt) | What to accept | What to reject |
|---|---|---|---|
| Medical Coding Expert (`coding-expert`) | "Always" for coding specificity + ICD-10 considerations + query targets | Gaps + queries with evidence quotes from chart | Leading queries, unsupported diagnoses |
| AMBOSS Expert (clinical criteria) | When clinical criteria for a documented diagnosis is unclear or commonly misdocumented | Clinical definitions + documentation checklists | Treatment guidance, patient-specific diagnostic judgments |
| CDI Web Search Expert (`web-search-expert`) | When current guidelines, compliance requirements, or official definitions are required | Items with citations and dates | Items without citations; conflict resolution (preserve both views instead) |

Note: prompt names 3 specialized Experts in the workflow but the agent metadata lists 4 (`pubmed-expert`, `web-search-expert`, `medical-calculator-expert`, `coding-expert`). The AMBOSS Expert referenced in the workflow text is the `pubmed-expert` at runtime — Corti rebranded AMBOSS as `pubmed-expert` in the public-facing metadata. The `medical-calculator-expert` is referenced in metadata but not mentioned in the workflow text, suggesting it is wired for future use or used opportunistically.

## 7. Constraint block (4 hard rules)

The `<constraints>` block sets 4 invariants iCoDer must replicate:

1. **Source-of-truth**: use only chart-explicit information for patient-specific statements; never infer missing facts
2. **No treatment advice**: under any circumstances
3. **Non-leading queries**: open-ended, evidence-grounded, multiple response options including "clinically undetermined"; never designed to upcode or persuade
4. **Evidence binding**: every gap and every query must cite an exact chart quote; no evidence → no gap/query

These four become the **CDI Core Agent invariant set** in Track D Gate 4 / Gate 5.

## 8. Limitation handling

The prompt is unusually explicit about uncertainty:

> "When evidence is insufficient to query a topic, explicitly state this limitation rather than proceeding with unsupported queries."
> "If no high-quality external guidance is available for a claim, do not invent guidance."
> "Prefer stating that no applicable evidence was found over making weak inferences."

This means CDI's correct behavior on an ambiguous chart is to **emit fewer gaps, not more**. iCoDer's CDI Orchestrator must implement a `min_evidence_threshold` and a `no_gap_found` outcome, not just an `always_emit_gap` heuristic.

## 9. Specialist Trace section (audit trail)

The Specialist Trace section is the **per-run audit trail**. For each Expert consulted, the agent must record:

- Consulted: yes/no
- Requested: what was asked
- Accepted: what was incorporated
- Rejected: what was discarded
- Rationale: why accept/reject

This is structurally identical to iCoDer's RunTraceStore `trace_events[]` array (Track C capability). iCoDer's CDI implementation will emit one trace event per Expert consultation, with `accepted`/`rejected`/`rationale` fields.

## 10. What we do NOT know (gated by permission)

Track B-2 attempted a live CDI run against `api.eu.corti.app`. The Corti account in scope did not have CDI execution permission. Therefore the following are **inferred from prompt + UI observation only**, not verified by live run:

- Actual latency distribution
- Token cost per run
- Whether all 4 Experts are consulted per run, or only conditionally
- Specialist Trace actual format (text vs structured)
- Whether the agent emits structured JSON or only markdown
- Webhook / SSE delivery pattern
- Rate limits and concurrency caps

Track D Gate 6+ implementation must accept these as unknowns and design iCoDer's CDI agent so that the **prompt-derived contract is the spec**, not a particular observed runtime behavior.

## 11. Mapping to iCoDer Track D

| Corti CDI property | iCoDer Track D target |
|---|---|
| Top-level agent in `coding_and_revenue_cycle` | `clinical-documentation-improvement-agent` as CORE_ENTRY_AGENT #1 (Gate 3) |
| 4 bound Experts | iCoDer Experts: `coding-expert` (shared with Medical Coding), `pubmed-expert`, `web-search-expert`, `medical-calculator-expert` |
| 6-section output | Domain model: `CDICase → DocumentationGap[] → ProviderQuery[] → CodingSpecificityChecklist → RiskFlag[] → SpecialistTrace` |
| Non-leading gate (constraint #3) | Gate 5: BLOCKED_LEADING_QUERY runtime gate |
| Evidence-binding gate (constraint #4) | Gate 4: every gap/query requires `evidence_span{document_id, char_start, char_end, quote}` |
| Specialist Trace | Per-Expert RunTrace event with `consulted/requested/accepted/rejected/rationale` |
| No live run observed | iCoDer CDI will be runnable locally — Track D Gate 6+ includes smoke run evidence |

## 12. Verdict

`CORTI_CDI_AUDIT_COMPLETE_WITH_STATIC_EVIDENCE_ONLY`

The Corti CDI agent's contract is fully captured by its 6238-char system prompt. Runtime behavior beyond the prompt (latency, cost, exact output JSON) was not observed due to account permission limits. The prompt itself is sufficiently detailed to serve as the iCoDer Track D spec.

## 13. Next

Gate 2 continues with `CORTI_CDI_PROVIDER_QUERY_AUDIT.md` (query compliance deep dive).
