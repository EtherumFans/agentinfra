# Agent Integration Matrix B-2 Report

**Generated**: 2026-07-11 (Phase 5 Track B-2 Phase 11)
**Source**: `outputs/phase5_track_b2/agent_integration_matrix_b2.csv`
**Dimensions**: 16 × 9 agents

---

## 1. Integration Matrix (16 dimensions × 9 agents)

| Integration Dimension | CP1 medical-coding | CP2 code-validation | CP3 compliance-guardrail | CP4 note-completeness | CP5 procedure-extractor | CP6 evidence-extractor | CP7 principal-dx-review | CP8 discharge-summary | CP9 drg-analyzer |
|---|---|---|---|---|---|---|---|---|---|
| Hub discoverable | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Detail page 5 tabs | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Chat UI | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Real DeepSeek | Y | **N (SKELETON)** | Y | Y (8.9-10.9s) | Y | Y (5.5-6.7s) | Y (4.8-16.8s) | Y (6.8-10.2s) | Y (7.2-15.2s) |
| Tool calls (MCP) | Y (4 experts + 4 tools) | N (provider not impl) | N (rule-based + LLM) | N (PureLLM) | N (PureLLM) | N (PureLLM) | N (PureLLM) | N (PureLLM) | N (PureLLM) |
| Backend provider | icoder.medical-coding.v1 (HybridCodingAdapter) | icoder.llm-with-tools.v1 (**SKELETON**) | icoder.rule-engine.v1 | icoder.pure-llm.v1 | icoder.pure-llm.v1 | icoder.pure-llm.v1 | icoder.pure-llm.v1 | icoder.pure-llm.v1 | icoder.pure-llm.v1 |
| Unified API /run | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Trace events | Y (multi-step) | Minimal | Minimal (1) | Minimal (1) | Minimal (1) | Minimal (1) | Minimal (1) | Minimal (1) | Minimal (1) |
| Cost tracking | Y | N (no LLM call) | Y | Y | Y | Y | Y | Y | Y |
| Embedded smoke | Y (4 eligible) | N | N | Y (4 eligible) | N | Y (4 eligible) | Y (4 eligible) | N | N |
| Backend Service Integration | READY | NOT READY | CONDITIONAL READY | CONDITIONAL READY | CONDITIONAL READY | CONDITIONAL READY | CONDITIONAL READY | CONDITIONAL READY | CONDITIONAL READY |
| ROPC Embedded | READY | N | N | READY | N | READY | READY | N | N |
| RunHistory | Y | Y (metadata only) | Y | Y | Y | Y | Y | Y | Y |
| AuditLog | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Fork UI | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Orchestrator sub-agent | Y (entry point) | Should be (post-impl) | Should be (stage 5) | Should be (stage 6) | Should be (after stage 2) | Should be (stage 4) | Should be (stage 3) | Should be (stage 1) | Should be (stage 7 - final) |

---

## 2. Integration readiness summary

### 2.1 Production-ready agents (Backend Service + ROPC both READY)
- **medical-coding-agent** (entry point, multi-step trace, 4 experts + 4 tools)

### 2.2 Conditional-ready agents (Backend Service only, JSON-in-markdown needs parse)
- compliance-guardrail-agent
- note-completeness-agent
- procedure-extractor
- evidence-extractor
- principal-diagnosis-review
- discharge-summary-structuring
- drg-analyzer

### 2.3 Not-ready agents
- code-validation-agent (SKELETON — Track C Gate 1 P0 fix)

---

## 3. Embedded smoke coverage (4/9 agents)

| Agent | Smoke HTML | Status |
|---|---|---|
| medical-coding-agent | examples/phase5_b2_cp1_smoke.html | ✓ validated 13-event chain |
| note-completeness-agent | examples/phase5_b2_cp4_smoke.html | ✓ validated |
| evidence-extractor | examples/phase5_b2_cp6_smoke.html | ✓ validated |
| principal-diagnosis-review | examples/phase5_b2_cp7_smoke.html | ✓ validated |

5 agents not embedded-eligible in B-2: CP2 (SKELETON), CP3 (rule-engine), CP5 (procedure), CP8 (discharge), CP9 (DRG).

Track C Gate 6 §11.4 will add 4 more embedded scenarios per PDF.

---

## 4. Orchestrator sub-agent mapping (per user directive 2026-07-11)

7-stage coding compliance mainline:

| Stage | Sub-agent | Status |
|---|---|---|
| 1 | discharge-summary-structuring (CP8) | NOT WIRED |
| 2 | medical-coding-agent (CP1, entry point) | STANDALONE |
| 3 | principal-diagnosis-review (CP7) | NOT WIRED |
| 4 | evidence-extractor (CP6) | NOT WIRED |
| 5 | compliance-guardrail-agent (CP3) | NOT WIRED |
| 6 | note-completeness-agent (CP4) | NOT WIRED |
| 7 | drg-analyzer (CP9, final pre-settlement) | NOT WIRED |

Track C Gate 4 wires all 7 stages.

---

## 5. Track C integration targets

| Dimension | Current B-2 | Track C Gate 6 target |
|---|---|---|
| Real DeepSeek | 8/9 (CP2 SKELETON) | 9/9 (Gate 1 fix) |
| Tool calls (MCP) | 1/9 (medical-coding) | 2/9 (medical-coding + code-validation) |
| Multi-step trace events | 1/9 | 9/9 (Gate 6) |
| Embedded smoke | 4/9 | 8/9 (Gate 6, all except CP2 if still in flux) |
| Backend Service READY | 8/9 CONDITIONAL | 9/9 READY (Gate 1 structured output) |
| Orchestrator sub-agent wired | 0/9 (all standalone) | 7/9 (Gate 4 mainline; CP2/CP3 stay standalone as gates) |

---

## 6. Integration test backlog (Track C Gate 6 §11)

- Parent-child run tree (run.received → context.built → plan.created → step.started → expert.selected → expert.completed → tool.started → tool.completed → agent.started → agent.completed → aggregation.started → conflict.detected → aggregation.completed → review.required → run.completed → run.failed)
- Total cost aggregation (no double-count across parent + child)
- A2A Card for all 9 official agents (skills + input/output schema + auth + version + runtime status)
- Web Component for 4 scenarios (medical-coding workbench / note completeness panel / evidence review panel / principal dx review panel)
- Third-party context passing (tenant_id + user_id + patient_id + encounter_id + source_system + api_client_id + idempotency_key)
- Review-then-writeback design (writeback fields + version + audit + idempotent; production writeback stays blocked)
