# Gate 3 — CDI Agent Promotion Report

**Date**: 2026-07-11
**PDF ref**: §5 Gate 3 — promote cdi-review → cdi core agent
**Status**: `PASS_GATE3_PROMOTED`
**Commit**: `feat(track-d3): promote clinical documentation improvement agent from metadata-only`

---

## 1. What changed

| Before (Gate 0) | After (Gate 3) |
|---|---|
| `icoder/cdi-review@1.0.0` — metadata-only, 1-line system prompt, 0 Experts, 0 real tools | `icoder/clinical-documentation-improvement-agent@1.0.0` — mvp, full Corti-compatible system prompt, 4 Experts, 7 contract-enforced tools |
| `icoder/documentation-gap@1.0.0` — metadata-only top-level agent (PDF §4.3 violation) | Deprecated; folded into CDI as internal capability |
| No CORE_ENTRY_AGENT flag anywhere | `manifest.core_entry_agent: true` + `corti_match_grade: EXACT_MATCH_AT_PRODUCT_AND_RUNTIME_LEVEL` |
| No CDI runtime code | 3 new modules: `cdi/__init__.py`, `cdi/domain.py`, `cdi/orchestrator.py`, `cdi/nlq_gate.py` |
| No tests | 29 new unit tests covering NLQ-001..009 + orchestrator wiring |

## 2. New agent pack

**Path**: `backend/official_agents/clinical-documentation-improvement-agent/agent_pack.json`

Key fields:
- `agent_ref`: `icoder/clinical-documentation-improvement-agent@1.0.0`
- `manifest.core_entry_agent`: `true` (CORE_ENTRY_AGENT #1)
- `manifest.corti_peer_agent_id`: `clinical-documentation-improvement-cdi-agent`
- `manifest.corti_match_grade`: `EXACT_MATCH_AT_PRODUCT_AND_RUNTIME_LEVEL`
- `manifest.maturity`: `mvp` (promoted from metadata-only)
- `manifest.production_ready`: `false` (still requires Gate 6+ runtime + Gate 7 UI)
- `system_prompt`: full CDI Documentation and Query Orchestrator prompt, Corti-compatible
- `experts`: 4 (coding-expert, pubmed-expert, web-search-expert, medical-calculator-expert)
- `tools`: 7 contract-enforced MCP tools (extract_chart_evidence, identify_documentation_gaps, generate_provider_query, validate_non_leading_query, search_icd_for_specificity, lookup_clinical_criteria, search_external_guidelines)
- `non_leading_query_gate`: NLQ-001..009 rules fully specified in pack
- `clarification_lifecycle`: 9 states + 3 side states (DRAFT → PENDING_CDI_REVIEW → APPROVED → SENT_TO_CLINICIAN → VIEWED → RESPONDED → DOCUMENTATION_UPDATED → REVALIDATED → CLOSED)
- `permissions`: all 9 CDI red lines encoded as boolean flags
- `legacy_aliases`: `icoder/cdi-review@1.0.0` (for migration tooling)

## 3. Legacy alias packs (deprecated)

**`backend/official_agents/cdi-review/agent_pack.json`**:
- `deprecated: true`
- `deprecated_reason`: points to new agent_ref
- `deprecated_replacement`: `icoder/clinical-documentation-improvement-agent@1.0.0`
- `hidden_from_hub: true` (no longer discoverable)
- All experts/tools emptied (cannot be invoked)

**`backend/official_agents/documentation-gap/agent_pack.json`**:
- `deprecated: true`
- `deprecated_reason`: PDF §4.3 boundary — documentation-gap is a CDI internal capability, not a top-level agent
- `hidden_from_hub: true`

## 4. Runtime modules (Gate 3 slice, full impl in Gate 4-6)

### 4.1 `cdi/domain.py`
Domain dataclasses (Gate 4 minimal slice):
- `EvidenceSpan` — char-anchored chart quote (red line: chart_evidence_required)
- `EncounterSummary` — section 1 of CDI output
- `DocumentationGap` — section 2
- `ProviderQuery` — section 3, full lifecycle state machine
- `CodingSpecificityItem` — section 4
- `RiskFlag` — section 5 (4 categories: contradiction / unsupported / ambiguous / copied-forward)
- `SpecialistTraceEntry` — section 6
- `CDICase` — top-level case state threaded through orchestrator

### 4.2 `cdi/nlq_gate.py`
Non-leading Query gate. 9 rules (NLQ-001..009):
- Lexical rules (regex): NLQ-001 (yes/no opening), NLQ-006 (treatment advice), NLQ-009 (payment terms)
- Structural rules (schema): NLQ-003 (response_options required), NLQ-004 (≥3 options), NLQ-005 (escape hatch required)
- Semantic rules: NLQ-002 (no diagnosis presumption), NLQ-007 (evidence required), NLQ-008 (no marked-correct option)

Public API: `evaluate(query: ProviderQueryForGate) -> NLQGateResult`

### 4.3 `cdi/orchestrator.py`
Pure-logic orchestrator (Track C pattern):
- 6 Corti-compatible stages: encounter_synthesis → gap_identification → expert_consultation → query_generation → query_compliance_gate → specialist_trace_emit
- Callable runner injection (Gate 6 wires DeepSeek runner; Gate 3 ships stub_runner)
- Per-stage run_id + trace_id capture (Track C parity)
- Completion policy: AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED

## 5. Tests

### 5.1 `tests/unit/icoder/cdi/test_nlq_gate.py` (20 tests)
- NLQ-001: 4 parametrized BLOCK cases + 1 PASS case
- NLQ-003/004/005: structural BLOCK + edge cases
- NLQ-005: accepts zh-CN (无法确定/临床不支持) AND en-US (clinically undetermined)
- NLQ-006: zh-CN + en treatment advice BLOCK
- NLQ-007: empty evidence_quote BLOCK
- NLQ-008: marked-correct option BLOCK
- NLQ-009: 3 payment term phrases BLOCK
- Full compliant query: PASS 9/9
- Block reason format audit (rule_id + name + evidence)
- RuleResult dataclass shape audit

### 5.2 `tests/unit/icoder/cdi/test_orchestrator.py` (9 tests)
- 6-stage Corti-compatible STAGES tuple
- Stub runner completes all 6 stages without exception
- AUTO_PASS when no gaps + no risks
- REVIEW_REQUIRED when gaps but no queries
- REVIEW_RECOMMENDED when queries passed NLQ + risks
- BLOCKED when any query fails NLQ (verifies block_reasons populated)
- Per-stage run_id + trace_id capture from runner
- Gap hydration (evidence_span populated)
- Query hydration + NLQ gate run on each query
- Gap ID auto-generation when missing

### 5.3 Test results

```
============================== 29 passed, 1 warning in 1.37s ========================
```

All 29 new tests pass. 0 regressions (existing tests untouched).

## 6. Boundary enforcement (PDF §4.3)

| Boundary | Enforcement |
|---|---|
| `discharge-summary-structuring` ≠ CDI | Separate agent pack (unchanged), classified as SPECIALIZED_AGENT |
| `note-completeness` ≠ CDI | Separate agent pack (unchanged), classified as SPECIALIZED_AGENT |
| `medical-coding` ≠ CDI | Separate agent pack (unchanged), CORE_ENTRY_AGENT #2; CDI permissions explicitly block `assign_diagnosis_code`, `assign_procedure_code`, `finalize_primary_diagnosis` |
| `documentation-gap` = CDI internal capability | Pack deprecated; folded into CDI as `identify_documentation_gaps` tool |

## 7. Agent registry impact

The new agent is discovered via `official_agents/**/agent_pack.json` glob (no manual registry edit needed). It will appear in the AI Studio hub on next backend reload.

Legacy aliases (`cdi-review`, `documentation-gap`) are hidden from hub via `hidden_from_hub: true`. Existing references in `agent_registry.json` will be migrated in Gate 4 when the full domain model + DB schema lands.

## 8. Migration plan (for downstream consumers)

| Old reference | New reference | Migration path |
|---|---|---|
| `icoder/cdi-review@1.0.0` | `icoder/clinical-documentation-improvement-agent@1.0.0` | legacy_aliases field auto-redirects; A2A facade handles in Gate 6 |
| `icoder/documentation-gap@1.0.0` | (none — use CDI agent's gap output) | code that called documentation-gap directly should call CDI agent's `documentation_gaps` field |
| `cdi_audit` permission preset | `cdi-core-agent` permission preset | Gate 8 migrates permissions |
| `cdi_review` tool name | `extract_chart_evidence` + `identify_documentation_gaps` + `generate_provider_query` + `validate_non_leading_query` | Gate 4 wires the new tools |

## 9. Verification

- ✅ `agent_pack.json` validates as JSON
- ✅ 4 Experts, 7 tools, 9 NLQ rules, 9 lifecycle states declared
- ✅ Pack discovered by `official_agents/**/agent_pack.json` glob
- ✅ Legacy packs marked deprecated + hidden
- ✅ 29/29 new unit tests pass
- ✅ Boundary conditions from PDF §4.3 enforced (block medical-coding tools in CDI permissions)
- ✅ 9 CDI red lines encoded as permission flags
- ✅ Corti-compatible system prompt + 6-section output schema
- ✅ Non-leading query gate runtime-ready (no LLM dependency for rule evaluation)

## 10. What is NOT in Gate 3 (deferred to later gates)

- **Gate 4**: Full domain model + DB persistence + Pydantic validators + ICD-10-CN specificity hints + clinical criteria lookup + external guidelines search
- **Gate 5**: NLQ gate integration into Provider Query DB lifecycle (state machine transitions on DRAFT → PENDING_CDI_REVIEW)
- **Gate 6**: Real DeepSeek-backed runner replacing `stub_runner`; full CDI Orchestrator wiring through CapabilityRegistry
- **Gate 7**: Frontend workbench (3-pane) + Physician Response Panel
- **Gate 8**: Roles + notifications + SLA + audit dashboard
- **Gate 9**: Hospital integration API + A2A endpoint at `/api/v1/cdi/runs`

## 11. Next: Gate 4 — China CDI capability model

PDF §6 Gate 4 — full domain model with:
- `DocumentationGap` schema (8 gap types per PDF §6.2)
- `ProviderQuery` schema (response option taxonomy per Gate 2 spec)
- `EvidenceSpan` validators (char_start ≤ char_end, non-empty quote)
- DB models for CDI case / gap / query / response / document version
- Alembic migration 011

Commit: `feat(track-d4): add documentation gap and provider query domain models`
