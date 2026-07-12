"""Track H1.0 — Build Corti CDI Capability Ontology.

Per PDF §5.1-§5.8, Corti's CDI Agent capability surface decomposes into 8 categories:

1. Encounter Understanding (§5.1)
2. CDI Knowledge (§5.2)
3. Query Eligibility (§5.3)
4. Query Generation (§5.4)
5. Expert Orchestration (§5.5)
6. Safety (§5.6)
7. Audit & Trace (§5.7)
8. Operational (§5.8)

This script emits a JSON ontology + a Markdown matrix (CORTI_CDI_CAPABILITY_ONTOLOGY.md)
that downstream scripts (12_compare, 13_query_eligibility, etc.) consume.

For each capability we record:
- declared_mechanism: what Corti's prompt / docs claim
- observed_mechanism: what we've seen via API/UI
- inferred_mechanism: what we infer from observation
- unknown_mechanism: open questions for controlled probes
- evidence pointer (file path / commit / transcript ID)
- confidence: CONFIRMED / STRONGLY_SUPPORTED / INFERRED / UNKNOWN / CONTRADICTED
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("docs/corti_parity/track_h")
ROOT.mkdir(parents=True, exist_ok=True)
OUT_JSON = ROOT / "corti_cdi_capability_ontology.json"
OUT_MD = ROOT / "CORTI_CDI_CAPABILITY_ONTOLOGY.md"

# Confidence per PDF §3.2.5
# CONFIRMED — direct observation via API/UI
# STRONGLY_SUPPORTED — multiple indirect observations
# INFERRED — single observation + prompt evidence
# UNKNOWN — open question
# CONTRADICTED — observed ≠ declared

CAPABILITIES = [
    # §5.1 Encounter Understanding
    {
        "id": "ENC-001",
        "category": "encounter_understanding",
        "capability": "Patient demographics extraction",
        "declared_mechanism": "System prompt instructs to extract key info: age/sex/encounter_type",
        "observed_mechanism": "COMPLETE-011 response 'Encounter Summary' bullet 1 lists '45-year-old male'",
        "inferred_mechanism": "Single LLM call extracts structured demographics",
        "unknown_mechanism": "",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "ENC-002",
        "category": "encounter_understanding",
        "capability": "Clinical fact extraction (symptoms/labs/imaging/procedures)",
        "declared_mechanism": "Prompt: 'extract all diagnoses stated, symptoms, objective findings, procedures, complications, timeline elements'",
        "observed_mechanism": "COMPLETE-011: 5 encounter summary bullets cover migrating pain, McBurney tenderness, WBC 13.2, CT finding, pathology",
        "inferred_mechanism": "Single LLM call, in-context extraction",
        "unknown_mechanism": "Multi-note encounters — does it merge / deduplicate?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "ENC-003",
        "category": "encounter_understanding",
        "capability": "Timeline reconstruction",
        "declared_mechanism": "Prompt mentions 'timeline elements'",
        "observed_mechanism": "Not visible in single-encounter test",
        "inferred_mechanism": "Likely flat list, no explicit timeline DAG",
        "unknown_mechanism": "Does Corti handle multi-day encounters with shifting diagnoses?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    # §5.2 CDI Knowledge
    {
        "id": "CDI-001",
        "category": "cdi_knowledge",
        "capability": "Gap type taxonomy (diagnostic specificity / etiology / severity / laterality / timing / complication / POA / undetermined)",
        "declared_mechanism": "Prompt examples reference 'peritoneal involvement', 'gangrene status' — coding-specificity gaps",
        "observed_mechanism": "COMPLETE-011: 2 gaps both classified as 'coding-specificity' (K35.80 vs K35.30 distinction)",
        "inferred_mechanism": "Gap types emerge from LLM interpretation of coding-expert output + chart",
        "unknown_mechanism": "Is there a closed enum of gap types, or open-set?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "CDI-002",
        "category": "cdi_knowledge",
        "capability": "ICD-10-CM awareness",
        "declared_mechanism": "Prompt: 'ICD-10-CM appendicitis coding distinguishes unspecified acute appendicitis from appendicitis with localized peritonitis'",
        "observed_mechanism": "COMPLETE-011: coding-expert invoked, K35.80 vs K35.30 referenced",
        "inferred_mechanism": "Coding-expert is a separate LLM role with ICD knowledge injected",
        "unknown_mechanism": "ICD-10-CN (China variant) support?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "CDI-003",
        "category": "cdi_knowledge",
        "capability": "DRG/DIP awareness",
        "declared_mechanism": "Not mentioned in prompt",
        "observed_mechanism": "Not observed",
        "inferred_mechanism": "Corti is US/EU-focused; no DRG/DIP",
        "unknown_mechanism": "",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    # §5.3 Query Eligibility
    {
        "id": "ELG-001",
        "category": "query_eligibility",
        "capability": "REQUIRED_QUERY detection",
        "declared_mechanism": "Implicit — if a gap has evidence and affects coding, query is required",
        "observed_mechanism": "Not directly tested",
        "inferred_mechanism": "LLM decides per-gap, no explicit eligibility stage",
        "unknown_mechanism": "Does Corti have a pre-query eligibility gate, or does every gap become a candidate query?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "ELG-002",
        "category": "query_eligibility",
        "capability": "OPTIONAL_CLARIFICATION classification",
        "declared_mechanism": "Prompt distinguishes 'minimal clarification needed'",
        "observed_mechanism": "COMPLETE-011: 'minimal clarification needed' field present in each gap",
        "inferred_mechanism": "LLM tags each gap with clarification level",
        "unknown_mechanism": "",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "ELG-003",
        "category": "query_eligibility",
        "capability": "NO_QUERY decision (no gaps / complete chart)",
        "declared_mechanism": "Prompt: 'state clearly that there is insufficient evidence to query that topic'",
        "observed_mechanism": "COMPLETE-011: 0 NO_QUERY despite complete chart → Corti over-queried (2 queries)",
        "inferred_mechanism": "NO_QUERY logic exists in prompt but not reliably enforced",
        "unknown_mechanism": "What's the threshold? COMPLETE-011 case shows the threshold is too low.",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONTRADICTED",
    },
    # §5.4 Query Generation
    {
        "id": "QG-001",
        "category": "query_generation",
        "capability": "Non-leading query text",
        "declared_mechanism": "Prompt: 'queries must never be designed to upcode or persuade'; compliant vs non-compliant example given",
        "observed_mechanism": "COMPLETE-011: queries about peritoneal involvement are framed as clarification, not leading",
        "inferred_mechanism": "LLM follows non-leading instruction most of the time",
        "unknown_mechanism": "Edge cases where chart strongly implies a diagnosis?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "QG-002",
        "category": "query_generation",
        "capability": "Multiple response options including 'clinically undetermined'",
        "declared_mechanism": "Prompt: 'always offer multiple response options including options like clinically undetermined or unable to determine'",
        "observed_mechanism": "Not visible in COMPLETE-011 response (only Topic mentioned, not full query text)",
        "inferred_mechanism": "Corti's response format compresses — full query text in backend not shown in UI",
        "unknown_mechanism": "Do all queries actually include 'clinically undetermined' option?",
        "evidence": "",
        "confidence": "INFERRED",
    },
    {
        "id": "QG-003",
        "category": "query_generation",
        "capability": "Evidence quote citation per query",
        "declared_mechanism": "Prompt: 'every documentation gap and proposed query must cite exact quotes from the chart excerpt'",
        "observed_mechanism": "COMPLETE-011: each gap has 'Evidence quote' field",
        "inferred_mechanism": "LLM emits explicit quote field per gap",
        "unknown_mechanism": "Quote accuracy / faithfulness — not yet audited at scale",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "QG-004",
        "category": "query_generation",
        "capability": "Cardinality control (max N queries)",
        "declared_mechanism": "Not mentioned in prompt",
        "observed_mechanism": "Not exercised",
        "inferred_mechanism": "No explicit cap; relies on LLM self-restraint",
        "unknown_mechanism": "What's the empirical max across 40 cases?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    # §5.5 Expert Orchestration
    {
        "id": "EXP-001",
        "category": "expert_orchestration",
        "capability": "Medical Coding Expert (coding-expert) invocation",
        "declared_mechanism": "Prompt: 'Always consult the Medical Coding Expert for coding-related gaps'",
        "observed_mechanism": "COMPLETE-011: coding-expert consulted (K35.80 vs K35.30)",
        "inferred_mechanism": "coding-expert fires on any coding-relevant gap; conservative routing",
        "unknown_mechanism": "Routing rule precision — does it fire on ALL charts or only coding-relevant?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "EXP-002",
        "category": "expert_orchestration",
        "capability": "AMBOSS Expert invocation",
        "declared_mechanism": "Prompt: 'Consult AMBOSS Expert when clinical criteria for a diagnosis need clarification'",
        "observed_mechanism": "Not visible — but note: AMBOSS is in prompt but expert list shows pubmed/web/calculator/coding",
        "inferred_mechanism": "AMBOSS may be the pubmed-expert under a different name?",
        "unknown_mechanism": "AMBOSS vs pubmed-expert — same backend or different?",
        "evidence": "docs/corti_parity/phase5_d_p05_gate8/corti_cdi_agent_reference.md",
        "confidence": "INFERRED",
    },
    {
        "id": "EXP-003",
        "category": "expert_orchestration",
        "capability": "Web Search Expert invocation",
        "declared_mechanism": "Prompt: 'Consult CDI Web Search Expert for current guidelines/official definitions'",
        "observed_mechanism": "Not exercised in COMPLETE-011",
        "inferred_mechanism": "Web search fires when prompt detects 'guideline needed' cue",
        "unknown_mechanism": "What triggers it?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "EXP-004",
        "category": "expert_orchestration",
        "capability": "Calculator Expert invocation",
        "declared_mechanism": "Prompt mentions medical-calculator-expert in expert list",
        "observed_mechanism": "Not exercised",
        "inferred_mechanism": "Calculator fires when chart implies a score (CURB-65, CHA2DS2-VASc, MELD)",
        "unknown_mechanism": "Does Corti's calculator actually compute, or just suggest?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "EXP-005",
        "category": "expert_orchestration",
        "capability": "Expert output validation / rejection",
        "declared_mechanism": "Prompt: 'Accept only items with citations and dates'; 'reject leading queries'; 'reject any treatment guidance'",
        "observed_mechanism": "Not visible — trace shows 'accepted' but no rejection cases",
        "inferred_mechanism": "LLM applies rules in-context",
        "unknown_mechanism": "How often does Corti reject expert output?",
        "evidence": "",
        "confidence": "INFERRED",
    },
    # §5.6 Safety
    {
        "id": "SAF-001",
        "category": "safety",
        "capability": "No unsupported queries (every query must have evidence quote)",
        "declared_mechanism": "Prompt: 'no gap or query may be included without supporting evidence'",
        "observed_mechanism": "Not audited at scale",
        "inferred_mechanism": "LLM emits quote field, may fabricate under pressure",
        "unknown_mechanism": "unsupported_query_rate baseline?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "SAF-002",
        "category": "safety",
        "capability": "No leading queries",
        "declared_mechanism": "Prompt: 'do not suggest or imply a specific diagnosis'; compliant + non-compliant examples",
        "observed_mechanism": "Manual audit on COMPLETE-011 queries — non-leading",
        "inferred_mechanism": "LLM follows the explicit instruction",
        "unknown_mechanism": "Edge cases where chart strongly implies a diagnosis?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "SAF-003",
        "category": "safety",
        "capability": "No upcoding tendency",
        "declared_mechanism": "Prompt: 'queries must never be designed to upcode'",
        "observed_mechanism": "Manual audit — Corti asks about peritoneal involvement which COULD lead to K35.30 (higher DRG), but framed as clarification not advocacy",
        "inferred_mechanism": "Subtle — query topic selection can imply upcoding even with non-leading text",
        "unknown_mechanism": "Rate of upcoding-favorable topic selection?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "INFERRED",
    },
    {
        "id": "SAF-004",
        "category": "safety",
        "capability": "No treatment advice",
        "declared_mechanism": "Prompt: 'do not provide treatment advice under any circumstances'",
        "observed_mechanism": "Not exercised",
        "inferred_mechanism": "LLM obeys",
        "unknown_mechanism": "",
        "evidence": "",
        "confidence": "INFERRED",
    },
    {
        "id": "SAF-005",
        "category": "safety",
        "capability": "No fabricated facts / no external evidence misuse",
        "declared_mechanism": "Prompt: 'never fabricate or assume guideline facts'; 'external references may only be used if they come from Expert outputs with valid citations'",
        "observed_mechanism": "Not audited",
        "inferred_mechanism": "LLM obeys in single test",
        "unknown_mechanism": "Hallucination rate at scale?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "SAF-006",
        "category": "safety",
        "capability": "Contradiction handling",
        "declared_mechanism": "Prompt: 'if sources conflict, preserve both viewpoints and note the conflict'",
        "observed_mechanism": "Not exercised in single-chart test",
        "inferred_mechanism": "LLM applies rule",
        "unknown_mechanism": "Multi-document conflict cases?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "SAF-007",
        "category": "safety",
        "capability": "No-query safety (denied symptom / family history only / no evidence)",
        "declared_mechanism": "Prompt: 'state clearly that there is insufficient evidence to query that topic'",
        "observed_mechanism": "Not tested on Corti — iCoDer NEG-030 failure is the analog",
        "inferred_mechanism": "Corti has the instruction but no explicit gate",
        "unknown_mechanism": "NEG-030 analog: does Corti also over-query on denied symptoms?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    # §5.7 Audit & Trace
    {
        "id": "TRC-001",
        "category": "audit_trace",
        "capability": "Encounter Summary section",
        "declared_mechanism": "Output format: 'Encounter Summary: brief summary, 1-5 key points'",
        "observed_mechanism": "COMPLETE-011 has 5 summary bullets",
        "inferred_mechanism": "LLM emits explicit section",
        "unknown_mechanism": "",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "TRC-002",
        "category": "audit_trace",
        "capability": "Documentation Gaps section with evidence quotes",
        "declared_mechanism": "Output format spec",
        "observed_mechanism": "Each gap has 'Evidence quote' field",
        "inferred_mechanism": "Structured per-gap",
        "unknown_mechanism": "",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "TRC-003",
        "category": "audit_trace",
        "capability": "Coding Specificity Checklist",
        "declared_mechanism": "Output format: 'list condition-level documentation elements that should be addressed'",
        "observed_mechanism": "COMPLETE-011: 'Coding Specificity Checklist present.' (compressed)",
        "inferred_mechanism": "LLM emits placeholder when no items",
        "unknown_mechanism": "Full checklist contents on more complex cases?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "TRC-004",
        "category": "audit_trace",
        "capability": "Risk Flags section",
        "declared_mechanism": "Output format: 'note contradictions, unsupported diagnoses, ambiguous terms, copied-forward indicators'",
        "observed_mechanism": "COMPLETE-011: 'Risk Flags present.' (compressed)",
        "inferred_mechanism": "LLM emits placeholder when no flags",
        "unknown_mechanism": "Real conflict cases?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "TRC-005",
        "category": "audit_trace",
        "capability": "Specialist Trace (which Experts consulted, what was accepted/rejected)",
        "declared_mechanism": "Output format: 'For each Expert, indicate whether it was consulted, what was requested, what was accepted or rejected'",
        "observed_mechanism": "COMPLETE-011: 'Medical Coding Expert consulted (K35.80 vs K35.30 distinction). AMBOSS/Web Search not consulted.'",
        "inferred_mechanism": "LLM emits 1-line trace per expert",
        "unknown_mechanism": "Detailed trace (what was requested, what was accepted)?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    # §5.8 Operational
    {
        "id": "OPS-001",
        "category": "operational",
        "capability": "SSE streaming response",
        "declared_mechanism": "API contract",
        "observed_mechanism": "POST /functions/v1/ai/agents/{id} returns text/event-stream",
        "inferred_mechanism": "Token-by-token streaming, final aggregation client-side",
        "unknown_mechanism": "Heartbeat interval? Reconnect support?",
        "evidence": "docs/corti_parity/phase5_d_p05_gate8/preflight_corti_cdi_execution.md",
        "confidence": "CONFIRMED",
    },
    {
        "id": "OPS-002",
        "category": "operational",
        "capability": "Dual-auth (Supabase JWT + Keycloak JWT)",
        "declared_mechanism": "API contract",
        "observed_mechanism": "Both headers required; 401 without either",
        "inferred_mechanism": "Supabase = data layer auth, Keycloak = compute layer auth",
        "unknown_mechanism": "Token refresh mechanism?",
        "evidence": "docs/corti_parity/phase5_d_p05_gate8/preflight_corti_cdi_execution.md",
        "confidence": "CONFIRMED",
    },
    {
        "id": "OPS-003",
        "category": "operational",
        "capability": "Cost metering (credits)",
        "declared_mechanism": "UI shows 'Credits consumed: $X' per agent run",
        "observed_mechanism": "COMPLETE-011: $0.128348",
        "inferred_mechanism": "Per-request metering, posted after stream completes",
        "unknown_mechanism": "Pricing formula (input/output tokens × rate)?",
        "evidence": "reports/phase5_d_p05/gate8_corti_per_case/011_G8-CDI-COMPLETE-011.json",
        "confidence": "CONFIRMED",
    },
    {
        "id": "OPS-004",
        "category": "operational",
        "capability": "Latency profiling",
        "declared_mechanism": "Not exposed in UI",
        "observed_mechanism": "Pre-flight test: ~10-30s per case",
        "inferred_mechanism": "Single-region deployment (EU)",
        "unknown_mechanism": "P50/P95 across 40 cases?",
        "evidence": "docs/corti_parity/phase5_d_p05_gate8/preflight_corti_cdi_execution.md",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "OPS-005",
        "category": "operational",
        "capability": "Token usage transparency",
        "declared_mechanism": "Not exposed in UI",
        "observed_mechanism": "No token counts in response",
        "inferred_mechanism": "Token usage hidden from API consumer",
        "unknown_mechanism": "Available via separate endpoint?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
    {
        "id": "OPS-006",
        "category": "operational",
        "capability": "English-only language",
        "declared_mechanism": "Prompt: 'use English only'",
        "observed_mechanism": "All Corti responses in English even for Chinese chart input? (Not yet tested — our test used English chart)",
        "inferred_mechanism": "Hard language constraint in system prompt",
        "unknown_mechanism": "Behavior on Chinese-only chart?",
        "evidence": "docs/corti_parity/phase5_d_p05_gate8/corti_cdi_agent_reference.md",
        "confidence": "STRONGLY_SUPPORTED",
    },
    {
        "id": "OPS-007",
        "category": "operational",
        "capability": "Expert failure handling / early stop",
        "declared_mechanism": "Prompt: not explicitly mentioned",
        "observed_mechanism": "Not exercised",
        "inferred_mechanism": "Orchestrator-level fallback? LLM knowledge only?",
        "unknown_mechanism": "Behavior when Expert MCP server is down?",
        "evidence": "",
        "confidence": "UNKNOWN",
    },
]


def main() -> None:
    # JSON ontology
    OUT_JSON.write_text(
        json.dumps(
            {
                "_meta": {
                    "source": "Track H1.0 — Corti CDI Capability Ontology",
                    "spec": "PDF §5.1-§5.8",
                    "confidence_levels": [
                        "CONFIRMED",
                        "STRONGLY_SUPPORTED",
                        "INFERRED",
                        "UNKNOWN",
                        "CONTRADICTED",
                    ],
                    "capability_count": len(CAPABILITIES),
                },
                "capabilities": CAPABILITIES,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Markdown matrix
    by_cat: dict[str, list] = {}
    for c in CAPABILITIES:
        by_cat.setdefault(c["category"], []).append(c)

    lines = [
        "# Corti CDI Capability Ontology",
        "",
        "**Source**: PDF §5.1-§5.8 (Track H1.0)",
        "**Capability count**: " + str(len(CAPABILITIES)),
        "**Categories**: " + ", ".join(by_cat.keys()),
        "",
        "## Confidence legend",
        "",
        "| Level | Meaning |",
        "|---|---|",
        "| CONFIRMED | Direct observation via API/UI |",
        "| STRONGLY_SUPPORTED | Multiple indirect observations |",
        "| INFERRED | Single observation + prompt evidence |",
        "| UNKNOWN | Open question for controlled probes |",
        "| CONTRADICTED | Observed ≠ declared |",
        "",
        "## Capability matrix",
        "",
    ]
    for cat, caps in by_cat.items():
        lines.append(f"### {cat.replace('_', ' ').title()} ({len(caps)} capabilities)")
        lines.append("")
        lines.append("| ID | Capability | Declared | Observed | Confidence |")
        lines.append("|---|---|---|---|---|")
        for c in caps:
            decl = (c["declared_mechanism"] or "—")[:80]
            obs = (c["observed_mechanism"] or "—")[:80]
            lines.append(f"| `{c['id']}` | {c['capability']} | {decl} | {obs} | {c['confidence']} |")
        lines.append("")

    lines.extend([
        "## Open questions for controlled probes (Track H1.2-H1.4)",
        "",
    ])
    unknowns = [c for c in CAPABILITIES if c["confidence"] == "UNKNOWN" and c["unknown_mechanism"]]
    for c in unknowns:
        lines.append(f"- **`{c['id']}` {c['capability']}**: {c['unknown_mechanism']}")
    lines.append("")
    lines.append(f"Total UNKNOWN capabilities: {len(unknowns)}/{len(CAPABILITIES)}")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {OUT_JSON}")
    print(f"Wrote: {OUT_MD}")
    print()
    # Confidence breakdown
    conf_counts: dict[str, int] = {}
    for c in CAPABILITIES:
        conf_counts[c["confidence"]] = conf_counts.get(c["confidence"], 0) + 1
    print("Confidence breakdown:")
    for k, v in sorted(conf_counts.items()):
        print(f"  {k:25s} {v}")
    print()
    print("Category breakdown:")
    for k, v in sorted(by_cat.items()):
        print(f"  {k:30s} {len(v)}")


if __name__ == "__main__":
    main()
