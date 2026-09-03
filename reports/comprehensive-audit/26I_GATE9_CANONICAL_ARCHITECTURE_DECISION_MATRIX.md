# 26I — Pre-A0 Gate 9: Canonical Architecture + Decision Matrix

> Per spec §16. Defines the canonical architecture iCoDer should converge toward + the per-capability decision matrix.

## Methodology

- Synthesizes findings from Pre-A0 Gates 1-8
- Canonical architecture = single-source-of-truth for each layer (no duplication)
- Decision matrix = per capability: KEEP / CONSOLIDATE / DEPRECATE / BUILD / OUTSOURCE

---

## §1. Canonical architecture (target state)

```
┌────────────────────────────────────────────────────────────────────────┐
│                     API Layer (app/api/)                                │
│  ~190 endpoints + Agent Hub + A2A routes + Platform API                 │
└────────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│        Corti-style Agent Runtime (app/icoder/agent_runtime/)            │
|  CANONICAL EXECUTION LAYER                                              │
|  - InboundHandler (entrypoint)                                          │
|  - corti_like_orchestrator (Planner → Delegator → Aggregator)           │
|  - coding_compliance_orchestrator                                       │
|  - CDI orchestrator                                                     │
|  - A2A v0.3 surface                                                     │
|  - Capability Registry                                                  │
|  - Context + Memory                                                     │
└──────┬──────────────────────────────┬────────────────────────────┬─────┘
       │ mode=corti_like_fast          │ mode=corti_like_full        │ mode=medcoder
       ▼                               ▼                             ▼
┌──────────────┐               ┌─────────────────┐         ┌─────────────────┐
│ Pure LLM     │               │ Multi-stage     │         │ MedCodER        │
│ Provider     │               │ Pipeline        │         │ (coding_runtime)│
│ (backends/)  │               │ (7-stage w/     │         │ 5-stage         │
│              │               │  experts)       │         │ retrieval+rerank│
└──────────────┘               └─────────────────┘         └─────────────────┘
       │                                                          │
       └──────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│        Compliance Services (compliance_services/)                       │
│  RuleEngine + 5 rule_sets (medical_coding, drg_dip, insurance_audit,   │
│  charge_compliance, document_evidence)                                  │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│        Runtime Core (icoder_runtime/) — REGISTRY SHELL ONLY            │
│  - RuntimeAgentRegistry (RG-1, canonical)                              │
│  - AgentPackageV1 loader                                                │
│  - LLMGateway                                                           │
│  - DataPolicy + PII Redaction                                           │
│  - RunHistory / AuditLog / FallbackTracker                              │
│  NOTE: PlatformRuntime.run_agent is NotImplementedError; execution     │
│        lives in Corti-style Agent Runtime above                         │
└────────────────────────────────────────────────────────────────────────┘
```

### Key canonical decisions

1. **One execution layer**: `app/icoder/agent_runtime/` is the canonical execution runtime. `icoder_runtime/` is the registry shell. `coding_runtime/` is a mode-specific sub-runtime.
2. **One agent registry**: `RuntimeAgentRegistry` (`icoder_runtime/core/registry.py`) is canonical. All other registries are either removed (RG-3 legacy) or scoped (RG-2 capability, RG-5 schema).
3. **One tool layer**: `app/icoder/mcp/handlers/` (MCP) is canonical. Legacy `app/tools/` is deprecated.
4. **One expert hierarchy**: Hierarchy C (`official_agents/`) is canonical for user-facing agents. Hierarchies A (legacy) and B/D (sub-components) are internal implementation details.

---

## §2. Per-capability decision matrix

| Capability | Current state (per Gate 2) | Decision | Action |
|------------|---------------------------|----------|--------|
| R-1 icoder_runtime | Registry shell + raises NotImplementedError on run_agent | **KEEP** as registry shell | Document explicitly; remove NotImplementedError ambiguity |
| R-2 coding_runtime | MedCodER 5-stage sub-runtime | **KEEP** as mode-specific sub-runtime | Document as internal |
| R-3 agent_runtime | Canonical execution | **PROMOTE** to sole execution layer | Update all docs |
| E-A app/agents/experts | 11 legacy experts | **DEPRECATE** | Remove if not used (G3-007 says used by T-1 tools); if used, consolidate into E-B |
| E-B agent_runtime/experts | 5 MedCodER stage experts | **KEEP** as internal | Document as MedCodER stages |
| E-C official_agents | 30 unique packaged agents | **KEEP** as canonical Agent Hub source | Dedup kebab/snake pairs |
| E-D agent_runtime/cdi | 12 CDI internal pseudo-experts | **KEEP** as internal | Document as CDI workflow gates |
| T-1 app/tools | 11 legacy tools | **DEPRECATE** | Migrate `/api/tools` + `/api/codes` consumers to MCP, then remove |
| T-2 icoder/mcp/handlers | 11 MCP handlers | **KEEP** as canonical tool layer | |
| T-3 icoder_runtime/tool_registry | Runtime-level registry | **KEEP** | |
| RG-1 RuntimeAgentRegistry | Canonical | **KEEP** | |
| RG-2 CapabilityRegistry | Active sub-registry | **KEEP** | |
| RG-3 app/tools + mcp/tool_registry | Dual home | **REMOVE** legacy; **KEEP** mcp/tool_registry as canonical tool registry | |
| RG-4 icoder_runtime/tool_registry | Runtime-level | **KEEP** | |
| RG-5 A2A SchemaRegistry | Active | **KEEP** | |
| A2A routes_task_stub | Returns 501 | **DECIDE**: implement or remove | Spec §7.5 says implement; resources say remove |

---

## §3. Corti parity decision matrix

For each Corti capability (from Gate 1), iCoDer decision:

| Corti capability | iCoDer decision | Rationale |
|------------------|-----------------|-----------|
| Orchestrator + Experts + Memory architecture | **MATCH** | iCoDer has same 3-component architecture |
| 20 pre-built agents | **MATCH 18 + DEFER 2** | 18 mirrored; Clinical Education + Clinical Guidelines deferred |
| 14 prebuilt experts | **MATCH 2 + DEFER 4 + OUT_OF_SCOPE 4 + DIFFERENT 4** | Memory + Coding = match; PubMed/Web/Calc/Interviewing = nice-to-have; POSOS/DrugBank/ClinicalTrials/AMBOSS = OOS; 4 ICD-10 variants = different-by-design |
| 9 ICD-10 variants | **DIFFERENT_BY_DESIGN** | iCoDer is CN-only; 1 CN variant vs Corti's 9 non-CN |
| Pay-as-you-go + payment processor | **BUILD** | Close billing theater gap |
| Auto top-up + low-balance alerts | **BUILD** | Partner-grade commercial surface |
| Stripe payment methods | **BUILD** | (Alipay/WeChat Pay for CN; Stripe for EU/US) |
| Save-and-go-live agent lifecycle | **DEFER** | iCoDer pack/install lifecycle has architectural reasons |
| .NET SDK | **BUILD** | Currently missing from Code generators |
| Signed trace_url | **KEEP ICODER_ADVANTAGE** | iCoDer has; Corti doesn't |
| RunHistory table | **KEEP ICODER_ADVANTAGE** | iCoDer has; Corti doesn't |
| Patient context events | **KEEP ICODER_ADVANTAGE** | iCoDer has; Corti doesn't |
| 9-state badge taxonomy | **KEEP ICODER_ADVANTAGE** | iCoDer has; Corti doesn't |
| A2A Tasks (long-running) | **BUILD or REMOVE** | 501 stub is ambiguous |

---

## §4. Architecture debt ledger (per spec §21 addendum)

| Debt ID | Title | Source | Severity | Action |
|---------|-------|--------|----------|--------|
| **AD-01** | 3 parallel runtimes confusion (HC-1 refuted) | Pre-A0 Gate 3 | P1 | Update all docs; clarify R-1 is shell, R-2/R-3 are execution |
| **AD-02** | 4 expert hierarchies | Pre-A0 Gate 2 | P1 | Promote E-C canonical; deprecate E-A; document E-B/D as internal |
| **AD-03** | 3 tool layers (T-1/T-2/T-3) | Pre-A0 Gate 2 | P1 | Deprecate T-1; T-2 canonical for MCP; T-3 runtime |
| **AD-04** | 5 registries | Pre-A0 Gate 2 | P1 | RG-1 canonical; RG-3 legacy removed; RG-2/4/5 scoped |
| **AD-05** | 3 kebab/snake duplicate agent pairs | Pre-A0 Gate 2 | P2 | Consolidate to kebab-case |
| **AD-06** | A2A Task stub ambiguity | Pre-A0 Gate 3 | P2 | Decide: implement or remove |
| **AD-07** | Frontend has 0 unit tests | Gate 11 | P2 | Add Vitest |
| **AD-08** | No release automation | Gate 11 | P2 | Add release.yml |
| **AD-09** | No ops runbook | Gate 11 | P2 | Write runbook |
| **AD-10** | Billing theater | Gate 13 | P0 | Build real payment processor |
| **AD-11** | Zero compliance certifications | Gate 13 | P0 | Engage 等保 audit |
| **AD-12** | Zero legal documents | Gate 13 | P0 | Draft 4 legal docs |
| **AD-13** | Zero shippable deployment paths | Gate 13 | P0 | Pick one path |
| **AD-14** | Cloud SaaS docs-only (6 critical features unimplemented) | Gate 11 | P0 | Build region routing + failover + edge PHI |

---

## §5. Findings raised in Gate 9

| ID | Severity | Title |
|----|----------|-------|
| **G9-001** | P1 | Canonical architecture defined: R-3 (agent_runtime) is sole execution layer; all docs must reflect |
| **G9-002** | P1 | 14 architecture debt items (AD-01 to AD-14) consolidated; 4 are P0 |
| **G9-003** | P2 | Per-capability decision matrix provides clear BUILD / KEEP / DEPRECATE / DEFER guidance |
| **G9-004** | P2 | Corti parity matrix shows 18/20 agents mirrored + 12 iCoDer-unique capabilities |

---

## §6. Gate 9 verdict

```
PRE_A0_GATE9_CANONICAL_ARCHITECTURE_AND_DECISION_MATRIX_PUBLISHED
1_CANONICAL_EXECUTION_LAYER (app/icoder/agent_runtime/)
1_CANONICAL_AGENT_REGISTRY (RuntimeAgentRegistry)
1_CANONICAL_TOOL_LAYER (app/icoder/mcp/handlers/)
1_CANONICAL_EXPERT_HIERARCHY (official_agents/)
14_ARCHITECTURE_DEBT_ITEMS_CONSOLIDATED
30_CAPABILITY_DECISIONS_DOCUMENTED
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Hard Checkpoint D status (per spec §20)

**Checkpoint D — No Feature Expansion**: ✅ PASS
- Pre-A0 made NO new Agent/Expert/Tool/Runtime/Prompt additions
- All Pre-A0 gates produced reports + evidence only
- No code was modified (read-only audit honored)
- 4 P0 blockers from Gate 13 remain; no new P0 introduced
- Canonical architecture is a target state, not an implementation — no code changes proposed in this gate

Gate 9 closes. Proceed to **Pre-A0 Final Decision + Evidence Manifest Refresh**.
