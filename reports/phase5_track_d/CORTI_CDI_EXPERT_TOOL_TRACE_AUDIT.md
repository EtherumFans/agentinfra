# Gate 2 — Corti CDI Expert & Tool Trace Audit

**Date**: 2026-07-11
**Source**: Corti CDI agent metadata + system prompt workflow block + Track B Expert audit
**Scope**: Expert capability mapping, tool invocation pattern, trace emission contract

---

## 1. Corti CDI Experts (4)

Corti's `clinical-documentation-improvement-cdi-agent` binds 4 Experts in metadata. These are referenced as `pubmed-expert`, `web-search-expert`, `medical-calculator-expert`, `coding-expert` in the agent registry.

| Expert | Role in CDI workflow | When consulted | What it returns | MCP server |
|---|---|---|---|---|
| `pubmed-expert` | Clinical criteria + diagnostic definitions + staging info (labeled "AMBOSS Expert" in prompt text) | When clinical criteria for a documented diagnosis is unclear or commonly misdocumented | Clinical definitions, documentation checklists | (none observable in CDI metadata; likely AMBOSS API at runtime) |
| `web-search-expert` | External references + official guidance + current guidelines | When current guidelines, compliance requirements, or official definitions are required | Items with citations and dates | (likely Web Search API) |
| `medical-calculator-expert` | Clinical scores (CHARM-VASC, MELD, etc.) | (not mentioned in workflow text, opportunistic) | Score computation results | (likely internal library) |
| `coding-expert` | Coding specificity guidance, ICD-10 considerations, query targets | "Always" for coding-related gaps | Coding-specific gap and query suggestions | (shared with Medical Coding Agent) |

Notable: workflow text mentions 3 Experts (Coding/AMBOSS/Web Search); metadata lists 4 (PubMed/WebSearch/MedicalCalculator/Coding). The AMBOSS↔PubMed naming is a Corti internal rebrand. The `medical-calculator-expert` is in metadata but not in workflow text — either opportunistic (used when the agent decides it needs a score) or vestigial.

## 2. CDI Agent is the final authority

The prompt is unambiguous:

> "You are the final authority. Any Expert output that violates your constraints must be rejected and omitted from your response."

This means Expert outputs are **advisory**, not authoritative. The CDI LLM (Corti's underlying model) makes the final decision on what to include. The Specialist Trace section records both accepted and rejected Expert outputs.

This is the Corti pattern across all agents studied in Track B: **Experts provide capability, agent provides judgment**. It is an LLM-driven conditional routing pattern, not a declarative DAG.

## 3. Per-Expert accept/reject policy

The workflow block specifies what to accept and reject from each Expert:

### coding-expert

| Accept | Reject |
|---|---|
| Gaps with evidence quotes from chart | Leading queries |
| Queries with evidence quotes from chart | Diagnoses unsupported by the excerpt |
| ICD-10 specificity suggestions | — |

### pubmed-expert (AMBOSS)

| Accept | Reject |
|---|---|
| Clinical definitions | Treatment guidance |
| Documentation checklists | Patient-specific diagnostic judgments |

### web-search-expert

| Accept | Reject |
|---|---|
| Items with citations AND dates | Items without citations |
| (when sources conflict) both viewpoints preserved | Single-viewpoint assertions when conflicting evidence exists |

### medical-calculator-expert

(No accept/reject policy stated; consult condition unspecified)

## 4. Tool invocation pattern

Corti agents do not call MCP tools directly. They invoke **Experts**, which are themselves LLM agents with bound MCP servers. The chain is:

```
CDI Agent (LLM)
  ↓ A2A message
Expert (LLM, e.g. coding-expert)
  ↓ MCP tool call
MCP server (e.g. ICD-10 lookup)
```

This indirection is consistent with the Corti agentic framework: agents → experts → MCP servers. Track B §G confirms 2 of 13 Experts have observable MCP server bindings (`posos` for drug-drug interactions, `drugbank` for drug references). The CDI Experts' MCP servers are not directly observable from agent metadata — they may be Corti-internal APIs.

For iCoDer Track D, the equivalent layering is:

```
CDI Agent (orchestrator)
  ↓ capability.invoke
Capability (e.g. "coding_specificity")
  ↓ tool call (contract-enforced)
Tool (e.g. search_icd10_index)
```

Track C CapabilityRegistry already provides this layer. Track D Gate 6 binds the CDI capabilities.

## 5. Specialist Trace emission contract

The `<output_format>` mandates a Specialist Trace section. For each Expert, the agent records:

```yaml
specialist_trace:
  - expert: coding-expert
    consulted: true
    requested: "Identify coding-specific gaps related to AKI documentation"
    accepted:
      - "Suggest query for AKI etiology based on creatinine trend"
    rejected:
      - "Suggest query 'Does patient have ATN?'"  # leading query
    rationale: "Rejected query is leading and presumes diagnosis"
  - expert: pubmed-expert
    consulted: true
    requested: "Diagnostic criteria for acute tubular necrosis"
    accepted:
      - "ATN requires FENa > 2% and granular casts"
    rejected: []
    rationale: "Definition accepted, used as evidence in query"
  - expert: web-search-expert
    consulted: false
    rationale: "No current-guideline question in this chart"
  - expert: medical-calculator-expert
    consulted: false
    rationale: "No score computation needed"
```

This is the **runtime audit trail**. iCoDer's RunTraceStore (Track C) emits the same shape as `trace_events[]`:

```json
{
  "event_type": "expert.consulted",
  "expert_id": "coding-expert",
  "request": "Identify coding-specific gaps...",
  "response_accepted": ["..."],
  "response_rejected": ["..."],
  "rationale": "...",
  "ts": "2026-07-11T14:23:00Z"
}
```

## 6. Evidence binding invariant

The prompt's `<constraints>` block:

> "Every documentation gap and proposed query must cite exact quotes from the chart excerpt as evidence. No gap or query may be included without supporting evidence from the documentation."

This invariant flows through Experts: when the `coding-expert` returns a suggestion, the CDI agent must verify the suggestion has a chart quote before emitting it. If the suggestion is "Query for AKI etiology" but does not reference a chart quote, the CDI agent must either:

1. Find a chart quote that supports the suggestion (e.g. the elevated creatinine value), or
2. Reject the suggestion with rationale "no chart evidence"

iCoDer Track D Gate 4 implements this as `evidence_span` requirement on every gap and query. The runtime gate is `BLOCKED_MISSING_EVIDENCE`.

## 7. Conflict resolution between Experts

When Experts disagree, the prompt says:

> "If sources conflict, preserve both viewpoints and note the conflict."

This is a **non-default resolution strategy**. Most LLM-driven agents average or pick one. Corti CDI is required to **preserve disagreement** in the output. iCoDer Track C ConflictResolver already supports this via `STRATEGY_DEFER` (no auto-resolve, escalate to human). For CDI, `STRATEGY_DEFER` will be the default for cross-Expert conflicts.

## 8. No live trace observed

Track B-2 attempted to capture Corti CDI network traffic. The Corti account lacked CDI execution permission. Therefore the actual Specialist Trace JSON shape is **inferred from prompt**, not verified.

What we have:

- ✅ System prompt workflow text (describes what should happen)
- ✅ Agent metadata (4 Experts listed)
- ✅ Specialist Trace section requirement (output_format block)
- ❌ Actual Specialist Trace JSON from a live run
- ❌ Expert request/response payloads
- ❌ Per-Expert latency
- ❌ Per-Expert token cost

iCoDer Track D's CDI implementation will produce the first observable Specialist Traces in this product family. The shape will follow the prompt-derived spec above.

## 9. Mapping to iCoDer capabilities (Track C CapabilityRegistry)

Track C CapabilityRegistry already has the following reusable capabilities. Track D binds them to CDI:

| Corti Expert | iCoDer Capability (Track C) | Bound tools | Notes |
|---|---|---|---|
| `coding-expert` | `coding_specificity` | `search_icd10_index`, `explore_code`, `verify_code`, `get_guidelines` | Shared with Medical Coding Agent |
| `pubmed-expert` | `clinical_criteria` | `lookup_criteria` (new in Track D Gate 4) | Initially stub; later wired to AMBOSS or China-equivalent clinical knowledge base |
| `web-search-expert` | `external_references` | `web_search` (with constraint: external web is NOT a patient-fact source — red line #9) | Web search results inform guidelines only, never patient facts |
| `medical-calculator-expert` | `clinical_calculators` | `compute_score` (new in Track D Gate 4) | Initially stub; later wired to MDCalc-equivalent or in-house calculators |

The capabilities layer lets iCoDer swap Experts (e.g. replace AMBOSS with a China clinical knowledge base) without changing the CDI orchestrator code.

## 10. Tool call budget

Corti does not publish a per-agent tool call budget. Inferred from prompt:

- Coding Expert: ~1 call per chart (mandatory)
- PubMed Expert: 0–1 call per chart (conditional)
- Web Search Expert: 0–1 call per chart (conditional)
- Medical Calculator Expert: 0–1 call per chart (conditional)

Expected per-run: 1–4 Expert calls. iCoDer Track D Gate 6 will set a hard ceiling of 6 Expert calls per CDI run to bound latency and cost.

## 11. Verdict

`CORTI_EXPERT_TRACE_CONTRACT_INFERRED_FROM_PROMPT`

The 4-Expert architecture and the accept/reject policy are fully captured by the prompt. Runtime invocation pattern (A2A → Expert → MCP) matches Track B §G observation for other Corti agents. iCoDer Track C CapabilityRegistry + Track D Gate 4 capability bindings will reproduce this layer.

## 12. Next

Gate 2 continues with `CORTI_CDI_UI_AND_INTEGRATION_AUDIT.md` (UI surface + API + Webhook + Embedded).
