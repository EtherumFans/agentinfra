# iCoDer Medical AI Architecture

## Product Positioning

iCoDer is **Auditable Clinical AI** — every decision traceable to source evidence, every code choice replayable via SHA-256 audit chain.

- Audit first: deterministic ICD indexing, evidence binding, append-only decision trails — built for compliance and disputes, not just output
- Pre-built capabilities: coding audit, speech-to-text, text generation, fact extraction — ready on deploy
- Data on-premise: runtime runs inside hospital infrastructure, data never leaves
- ICD-10-CN / ICD-9-CM-3 native, with SDK extensibility for HIS/EMR integration

## Core Problem: LLM Autonomy vs Medical Determinism

Research conclusion: **Pure LLM autonomous tool selection is unacceptable in healthcare.**

Brain Co. controlled experiment (Dec 2025):

| Metric | Agentic Tool-Calling | Deterministic Pipeline |
|--------|---------------------|----------------------|
| F1 | 62.2% | **94.5%** |
| Latency | 28min | **182s** |
| Token | baseline | **1/5th** |

ContractBench (May 2026): **No LLM model exceeds 80% on tool contract compliance.**
Production tool selection/calling failure rate: ~10-20%.

### Solution: Contract-Enforced Tool Calling

Neither "LLM freely chooses tools" nor "hardcoded pipeline order." Instead:

- LLM autonomously decides which tools to call and in what order
- **The Harness (DeterministicRuntime) enforces pre/post-conditions on every tool call in code**
- On contract violation, Harness rejects execution and feeds back to LLM; LLM corrects and retries

## Architecture: Two-Tier Tool System + Contract Enforcement

```
Agent = System Prompt + Contract-Bound Tools + Harness

┌─────────────────────────────────────────────┐
│                  Agent                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ System   │  │ Tools    │  │ Harness    │  │
│  │ Prompt   │  │ (Tier1+2)│  │ (Runtime)  │  │
│  └──────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────┘
```

### Tier 1: Deterministic Core Tools (Contract-Enforced)

These are the accuracy-critical capabilities. Each has machine-verifiable pre/post-conditions.
Execution is deterministic code — zero LLM involvement.

| Tool ID | Function | Deterministic |
|---------|----------|---------------|
| `search_icd10_index` | ICD-10 alphabetic index lookup | Yes (tree traversal) |
| `triage_clinical_facts` | Classify facts: codable/history/ruled_out | Yes (rule engine) |
| `rank_evidence` | Evidence strength scoring + conflict detection | Yes (scoring algorithm) |
| `calibrate_confidence` | AUTO/REVIEW/ESCALATE tier assignment | Yes (threshold-based) |
| `validate_coding_rules` | Gender/procedure consistency checks | Yes (rule engine) |
| `guard_input` | PHI detection, blocked terms, input validation | Yes (regex + rules) |
| `guard_output` | Blocked terms (prescriptions, dosages, etc.) | Yes (hardcoded blocklist) |

### Tier 2: Reasoning Tools (LLM-Powered, Optional)

These use LLM but operate on data already verified by Tier 1 tools.

| Tool ID | Function | LLM Role |
|---------|----------|----------|
| `extract_evidence` | Extract clinical facts from text | LLM extraction, structured output |
| `assign_diagnosis_code` | Select best code from ICD-10 candidates | LLM selection within deterministic candidate set |
| `assign_procedure_code` | Select best procedure code | Same pattern |
| `verify_evidence` | Check each code has supporting evidence | LLM verification, deterministic cross-check |
| `analyze_drg_impact` | DRG grouping impact analysis | LLM analysis, deterministic DRG grouper |
| `check_documentation_gaps` | Identify missing/incomplete docs | LLM analysis |
| `generate_cdi_query` | Generate clinician query for doc improvement | LLM generation |
| `format_report` | Format final report (markdown/html) | LLM formatting |

### Contract Enforcement Flow

```
LLM proposes tool call
       │
       ▼
Harness.pre_check(tool_id, params)
  ├─ Evaluate preconditions against symbolic_state
  ├─ ❌ DENY → return structured error to LLM → LLM corrects → retry
  └─ ✅ ALLOW → execute tool
       │
       ▼
Tool executes (deterministic code or constrained LLM)
       │
       ▼
Harness.post_check(tool_id, result)
  ├─ Validate postconditions
  ├─ ❌ DENY → reject result, don't write to state, return error to LLM
  └─ ✅ ALLOW → merge result into symbolic_state, append to audit chain
       │
       ▼
LLM receives verified result → plans next step
```

### Key Design Decisions

**Why Tier 1 tools cannot be optionally skipped by LLM:**
Brain Co. data: F1 drops from 94.5% to 62.2%. ContractBench: best model <80%.
But Tier 1 tools are not "forced sequential." LLM has freedom in:
- Order (can search ICD-10 before or after evidence extraction)
- Batching (can query multiple terms before assigning codes)
- Iteration (can jump back to add more evidence)

The Harness only validates **logical correctness**, not **execution order**.

**Why contract enforcement beats hardcoded pipelines:**
1. **Composable** — New Agent = new tool combination, no code changes
2. **Explainable** — Every rejection has explicit contract violation reason in audit chain
3. **Anti-degradation** — Contracts remain valid after LLM upgrades; hardcoded pipelines become dead weight
4. **Developer-friendly** — Third-party devs understand tool interfaces, not pipeline internals

### Comparison: Corti vs iCoDer Agent Runtime

| Dimension | Corti Agent Runtime | iCoDer Agent Runtime |
|-----------|-------------------|---------------------|
| **Agent =** | System prompt + Expert refs | System prompt + contract-bound tools |
| **Tool mechanism** | Expert = prompt template + MCP | Tool = contract-defined deterministic function or LLM prompt |
| **Accuracy guarantee** | Prompt quality dependent | **Contract-enforced**: pre/post-conditions verified by code |
| **Orchestration** | LLM decides call sequence (no constraints) | LLM proposes → Harness validates → reject → LLM corrects |
| **Medical determinism** | None | Tier 1 tools: zero LLM (ICD index, evidence ranking, confidence calibration) |
| **Safety boundary** | MCP level (per-tool) | Harness level (per-call validation pipeline) |
| **Auditability** | usage_count | Full tool call chain + contract verification records |
| **Target user** | Clinical end users | Developers building agents via SDK; end users via apps |
| **Memory system** | Thread sessions | Multi-layer: instruction/symbolic state/conversation history/audit chain |

## Implementation Phases

### Phase 1: Tool Contract Infrastructure
- `tool_registry.py` — ToolDefinition + ToolRegistry
- `contract_engine.py` — SymbolicState + pre/post condition evaluation
- Enhanced `ToolGate` in `runtime.py`

### Phase 2: Refactor Capabilities into Contract Tools
- `backend/app/tools/` — extraction, coding, verification, analysis, report, safety tools
- Each tool wraps an existing orchestrator step with contract metadata

### Phase 3: Tool-Native AgentRunner Execution Path
- `_run_tool_native()` — LLM tool-calling loop with harness contract enforcement
- Existing `run()` paths preserved for backward compatibility

### Phase 4: API + Frontend
- `GET /api/tools` — tool catalog endpoint
- Agent config extended with `tools` field
- ToolSelector UI component + tools tab in AgentDetailPage

## References

- ToolGate: Contract-Grounded and Verified Tool Execution for LLMs (Jan 2026)
- Anthropic Managed Agents: Brain/Hands/Session Architecture (Apr 2026)
- Anthropic Programmatic Tool Calling (Nov 2025)
- Solver-Aided Verification of Policy Compliance in Tool-Augmented LLM Agents (Mar 2026)
- ContractBench: Can LLM Agents Preserve Observation Contracts? (May 2026)
- Brain Co: When Deterministic Pipelines Outperform Agentic Wandering (Dec 2025)
