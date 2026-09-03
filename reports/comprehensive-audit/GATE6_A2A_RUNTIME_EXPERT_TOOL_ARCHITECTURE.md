# Audit Gate 6 — A2A / Runtime / Expert / Tool Architecture (Tracks H1 + H2 + H3)

> Per PDF §三 Track H: maps the live execution path, parallel Runtime layers, expert wiring, and tool registry. Answers: which expert hierarchy is alive? Is A2A actually spec-compliant? Is the tool layer real or stub?

## H1. A2A protocol layer — REAL v0.3, used in production

### H1.1 Spec compliance — verified

`backend/app/icoder/agent_runtime/a2a/version.py`:
```python
A2A_PROTOCOL_VERSION: Final[str] = "0.3"
SUPPORTED_VERSIONS: Final[tuple[str, ...]] = ("0.3",)
```

Strict header check (no silent fallback): `validate_version_header()` raises `A2AVersionError` → JSON-RPC `-32600 Invalid Request` + HTTP 400 when `A2A-Protocol-Version` is missing or unknown.

`backend/app/icoder/agent_runtime/a2a/parts.py` implements the 3 Part kinds (TextPart / DataPart / FilePart). FilePart is parse-time rejected per Q-A9 (`Phase 1 NOT implemented`).

### H1.2 A2A route surface — 6 endpoints mounted

`mount_a2a()` is invoked once at app startup (main.py:1266). Mounts:

| Path | Method | Purpose |
|------|--------|---------|
| `/.well-known/agent.json` | GET | AgentCard discovery (root) |
| `/llms.txt` | GET | LLM discovery |
| `/api/icoder/agents` | GET | Agent list with capability filter |
| `/api/icoder/agents/{id}/card` | GET | Single AgentCard |
| `/api/icoder/agents/{id}/v1/message:send` | POST | **Inbound message — main A2A entry** |
| `/api/icoder/internal/experts/{id}/v1/message:send` | POST | Outbound expert invocation |
| `/api/icoder/tasks/{id}` | GET | Task polling — **501 stub** |
| `/api/icoder/tasks/{id}/cancel` | POST | Task cancel — **501 stub** |

Tasks endpoints are 501 stubs per Phase 1 scope; A2A v0.3 §7 allows async tasks but iCoDer is sync-only.

### H1.3 InboundHandler — 5-stage state machine

`backend/app/icoder/agent_runtime/orchestrator/inbound_handler.py:577 LOC`:

State flow:
```
received → planning → delegating → aggregating → completed/failed
```

Components wired (main.py:676-690):

| Component | Role | LOC |
|-----------|------|-----|
| `PHIRedactor` | First step PHI redaction (SPEC §6.3) | 189 |
| `Planner` | LLM-driven plan synthesis | 393 |
| `Delegator` | Expert invocation + retry | 271 |
| `Aggregator` | Combine expert results | 252 |
| `state_machine` | State transitions | 125 |
| `run_trace` | Trace emission | 469 |

Server-generated `contextId` (UUID v4, per Q4) — strict context isolation.

### H1.4 A2A in production — single-endpoint facade

`_MedicalCodingV2ProjectingHandler` wraps InboundHandler (main.py:707-795):

```python
def handle(self, agent_id: str, request):
    # medical-coding-agent + no mode → corti_like_fast (default)
    # medical-coding-agent + medcoder_deep → inner InboundHandler 5-stage
    # All other agents → inner InboundHandler 5-stage
```

This is the same shared facade as `/api/v1/agents/{id}/run` (Gate 5 §E1) — both entry points converge on `dispatch_medical_coding_fast` or InboundHandler.

**Verdict**: `A2A_REAL_V0.3_SYNC_ONLY_TASKS_501_STUB`.

## H2. Runtime architecture — 3 parallel layers (G1-001 confirmed)

### H2.1 Layer 1 — icoder_runtime (Runtime Core package)

`backend/icoder_runtime/` — owns the LLM gateway, agent pack format, registry, MCP server.

```
icoder_runtime/
├── core/           ← AgentPackageV1, LLMGateway, Registry, DataPolicy, PIIRedaction
├── backends/       ← PureLLMProvider, LLMWithToolsProvider, RuleEngineProvider, ProviderRegistry (3,829 LOC)
├── providers/      ← medical_coding (DeepSeekCodingAdapter, HybridAdapter), drg, dip
├── embedded/       ← PlatformRuntime (210 LOC)
├── m2a/            ← Model-to-Agent recorder
└── backends/rule_engine_provider.py
```

`PlatformRuntime` (platform_runtime.py) is initialized at app startup (main.py:231):
```python
platform_runtime = PlatformRuntime(
    ...
)
await platform_runtime.start()
app.state.platform_runtime = platform_runtime
```

Per docstring (platform_runtime.py:18-22):
> "Execution (`run_agent`) now raises NotImplementedError with a redirect to the A2A mainline"

→ `PlatformRuntime` is **alive for install/list/registry/status only**. Execution is delegated to InboundHandler.

### H2.2 Layer 2 — app/coding_runtime (CodingRuntimeDispatcher)

`backend/app/coding_runtime/` — owns the medical coding fast-path.

```
app/coding_runtime/
├── base.py            ← CodingRequest, CodingResult, RuntimeMode, CodingRuntime
├── dispatcher.py      ← CodingRuntimeDispatcher (singleton)
├── fast_runtime.py    ← FastCodingRuntime (corti_like_fast, ~5-8s)
└── medcoder_runtime.py ← MedCoderRuntime (medcoder_deep, 30-60s+)
```

Wired as the medical-coding fast-path shared by:
- `/api/v1/agents/{id}/run` (agent_run.py)
- `/api/icoder/agents/{id}/v1/message:send` (via _MedicalCodingV2ProjectingHandler)

### H2.3 Layer 3 — app/icoder/agent_runtime (A2A + Orchestrator)

`backend/app/icoder/agent_runtime/` — owns the A2A protocol + 5-stage orchestrator.

```
app/icoder/agent_runtime/
├── a2a/              ← envelope, parts, routes_inbound/outbound/discovery (1,446 LOC across 13 files)
├── a2a_facade.py     ← Phase 4-F2 unified facade (345 LOC)
├── orchestrator/     ← 5,470 LOC across 24 files (inbound_handler, planner, delegator, aggregator, ...)
├── experts/          ← 5 MedCodER experts (code_reconciler, coding, evidence_extractor, index_navigator, tabular_validator)
├── cdi/              ← 16 CDI files (orchestrator, real_runner, nlq_semantic, ...)
└── context/          ← 10 context-management files
```

### H2.4 Layer integration — 3 entry points converge

```
1. POST /api/v1/agents/{id}/run        → agent_run.py
                                         ├─ medical-coding → CodingRuntimeDispatcher (Layer 2)
                                         └─ other agents → ProviderRegistry (Layer 1) or InboundHandler (Layer 3)

2. POST /api/icoder/agents/{id}/v1/message:send  → _MedicalCodingV2ProjectingHandler
                                                    ├─ medical-coding fast → dispatch_medical_coding_fast (shared)
                                                    └─ other + medcoder_deep → InboundHandler 5-stage

3. POST /api/v1/coding-compliance/run  → CodingComplianceOrchestrator (Layer 3)
                                          └─ 7 stages × provider.invoke (Layer 1)
```

→ **3 layers, 3 entry points, 1 unified facade** (a2a_facade.py). The "parallel Runtime" risk identified in G1-001 is **partially mitigated** by the Phase 4-F2 unified facade, but the underlying code is still spread across 3 packages.

## H3. Expert hierarchies — 2 hierarchies, 1 alive (G1-001 resolved)

### H3.1 Hierarchy A — app/agents/experts/ (legacy)

11 experts, 2,460 LOC:

| Expert | LOC | Status |
|--------|-----|--------|
| audit_expert | 111 | imported by nobody outside `__init__.py` |
| cdi_expert | 85 | imported by `app/tools/analysis_tools.py` only |
| denial_expert | 84 | imported by `__init__.py` only |
| diagnosis_expert | 268 | imported by `__init__.py` only |
| drg_expert | 206 | imported by `app/tools/analysis_tools.py` only |
| evidence_expert | 127 | imported by `__init__.py` only |
| hcc_expert | 86 | imported by `__init__.py` only |
| homepage_expert | 665 | imported by `app/services/context_scoper.py` + `llm_planner.py` (legacy planning code) |
| procedure_expert | 230 | imported by `__init__.py` only |
| report_expert | 343 | imported by `__init__.py` only |
| timeline_expert | 229 | imported by `__init__.py` only |

**Verdict**: `LARGELY_LEGACY`. Only 3 of 11 are referenced outside their own package, and those callers (`tools/analysis_tools.py`, `services/context_scoper.py`, `services/llm_planner.py`) appear to be legacy code paths not on the live medical-coding or CDI mainline.

### H3.2 Hierarchy B — app/icoder/agent_runtime/experts/ (live)

5 MedCodER experts (live):

| Expert | LOC | Used by |
|--------|-----|---------|
| coding_expert | (large) | wiring.py:47 — `build_expert_invoker_from_hybrid` |
| code_reconciler_expert | (medium) | wiring.py:280 |
| evidence_extractor_expert | (medium) | wiring.py:283 |
| index_navigator_expert | (medium) | wiring.py:286 |
| tabular_validator_expert | (medium) | wiring.py:289 |

All wired via `app/icoder/agent_runtime/orchestrator/wiring.py:build_expert_invoker_from_hybrid()` — the live MedCodER 5-stage path uses these.

### H3.3 Hierarchy C — official_agents/ (mixed)

34 agent directories. Python implementation presence:

| Category | Count | Examples |
|----------|-------|----------|
| Both pack + py | 19 | medical_coding, drg-analyzer, cdi, code-validation, compliance-guardrail, evidence_extractor, principal_diagnosis_review, discharge_summary_structuring, procedure-extractor, note-completeness, ... |
| Pack only (metadata-only) | 13 | denial-appeals, diagnosis-extractor, discharge_edu, documentation-gap, evidence-ranker, icd10_navigator, icu_summary, med_reconciliation, nursing_handoff, prior_auth, referral_gen, rule_explainer, surgical_registry, triage |
| Snake + kebab duplicates | 4 pairs | code_validation + code-validation, compliance_guardrail + compliance-guardrail, note_completeness + note-completeness, + 2 more |

### H3.4 G1-001 resolution

| Hierarchy | Alive? |
|-----------|--------|
| `app/agents/experts/` (Hierarchy A) | **LEGACY** — 3/11 referenced outside own package, all by legacy planning code |
| `app/icoder/agent_runtime/experts/` (Hierarchy B) | **LIVE** — all 5 wired via wiring.py into MedCodER 5-stage path |
| `official_agents/` (Hierarchy C) | **MIXED** — 19 have Python impl, 13 are metadata-only (Gate 2 G2-003 confirmed) |

**G1-001 (3 parallel expert hierarchies) status**: confirmed. Hierarchy A is the dead weight; Hierarchy B is the production coding pipeline; Hierarchy C is the agent pack registry (which can be either runnable or metadata-only).

## H4. Tool registry — real MCP integration

### H4.1 MCP server — REAL

`backend/app/icoder/mcp/server.py` (1,037 LOC) is mounted at app startup. Implements MCP protocol over `/mcp/v1/*` endpoints with auth via `auth.py` (239 LOC) + `auth_resolver.py` (476 LOC).

### H4.2 Tool registry — 11 tools declared

`backend/app/icoder/mcp/tool_registry.py:TOOL_REGISTRY` declares 11 tools:

| Tool | Purpose |
|------|---------|
| search_icd | ICD code search |
| verify_code | Code catalog validation |
| get_guidelines | Coding guidelines retrieval |
| explore_code | Code exploration |
| search_codes | Multi-code search |
| get_differentiation_hint | P0/P1 differentiation KB |
| rerank_codes | Candidate reranking |
| calibrate_confidence | Confidence calibration |
| validate_codes | Multi-code validation |
| evaluate_compliance | Compliance rule evaluation |
| check_documentation_gaps | Documentation gap check |

`assert_tool_registry_matches_agent_pack()` runs at mount time to enforce parity between the registry and agent_pack.json tool lists.

### H4.3 App tools — separate legacy layer

`backend/app/tools/` (987 LOC across 11 files) is a SEPARATE tool layer that imports Hierarchy A experts:

```python
# backend/app/tools/analysis_tools.py
from app.agents.experts.drg_expert import DRGDIPExpert, DocumentationGapExpert
from app.agents.experts.cdi_expert import CDIExpert
```

→ These are **legacy tools not wired into the MCP registry**. They appear to be from an earlier tool architecture that was replaced by `app/icoder/mcp/`.

## H5. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G6-001** | P1 | dead-code | `app/agents/experts/` (Hierarchy A, 2,460 LOC, 11 experts) is largely legacy — 8 of 11 experts are imported only by their own `__init__.py`. Should be archived or deleted. |
| G6-002 | P2 | fragmentation | 3 parallel runtime layers (`icoder_runtime/`, `app/coding_runtime/`, `app/icoder/agent_runtime/`) — partially unified via `a2a_facade.py` but the underlying code is still fragmented |
| **G6-003** | P1 | dead-code | `app/tools/` (987 LOC, 11 files) is a separate legacy tool layer not wired into the MCP registry. All tools import Hierarchy A experts which are themselves legacy. |
| **G6-004** | P1 | metadata-only | 13 official_agents directories have agent_pack.json but ZERO .py files (denial-appeals, diagnosis-extractor, discharge_edu, documentation-gap, evidence-ranker, icd10_navigator, icu_summary, med_reconciliation, nursing_handoff, prior_auth, referral_gen, rule_explainer, surgical_registry, triage) — confirms G2-003 at file level |
| G6-005 | P2 | partial-spec | A2A v0.3 Tasks endpoints (`/api/icoder/tasks/{id}`, `/cancel`) are 501 stubs — sync-only per Phase 1 scope but listed in OpenAPI |
| G6-006 | P2 | partial-spec | A2A FilePart is parse-time rejected per Q-A9 — limits file-based agent inputs (e.g. image upload for dermatology) |
| G6-007 | P3 | dual-naming | 4 official_agents have both snake_case (Python) + kebab-case (pack) directories: `code_validation/code-validation`, `compliance_guardrail/compliance-guardrail`, `note_completeness/note-completeness` + 2 more |

## H6. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **H1 A2A** | `REAL_V0.3_SYNC_ONLY_TASKS_STUB` — Spec-compliant envelope, 5-stage state machine, strict version header, HMAC auth; tasks endpoints 501 |
| **H2 Runtime** | `THREE_LAYERS_PARTIALLY_UNIFIED` — 3 packages (icoder_runtime + app/coding_runtime + app/icoder/agent_runtime); a2a_facade.py unifies medical-coding entry; other agents still fragmented |
| **H3 Experts** | `ONE_LIVE_HIERARCHY_PLUS_LEGACY` — Hierarchy B (5 MedCodER experts via wiring.py) is live; Hierarchy A (11 experts) is 73% legacy; Hierarchy C (34 official_agents) is 56% implemented |
| **H4 Tools** | `REAL_MCP_11_TOOLS_PLUS_LEGACY_LAYER` — MCP server.py is real (1,037 LOC), tool_registry has 11 tools with mount-time parity check; `app/tools/` (987 LOC) is a parallel legacy layer not wired to MCP |

## H7. Gate 6 verdict

`A2A_REAL_BUT_EXPERT_AND_TOOL_LAYERS_CARRY_SIGNIFICANT_LEGACY`

Specifically:

- ✅ A2A v0.3 is real — strict spec, mounted at 6 endpoints, drives InboundHandler 5-stage
- ✅ Medical coding facade (Phase 4-F2) successfully unifies 3 entry points
- ❌ **G6-001**: Hierarchy A (`app/agents/experts/`, 2,460 LOC, 11 experts) is 73% legacy — should be archived
- ❌ **G6-003**: `app/tools/` (987 LOC, 11 files) is a parallel legacy tool layer, not wired to MCP registry
- ❌ **G6-004**: 13 official_agents directories confirmed metadata-only at file level (Gate 2 G2-003 re-verified)
- ⚠️ 3 parallel runtime layers partially unified; new engineers will struggle to map a request to a layer
- ✅ MCP integration is real (11 tools, mount-time parity check, auth + resolver)

Gate 6 closes. Proceed to **Gate 7 — Run, Trace, Event, Usage Audit**.
