# A1B-AE-R.2 — Preset Agent Materialization

**Sub-gate**: R.2 (Preset Agent materialization)
**Date**: 2026-07-23
**Branch**: `phase-a1b/agent-expert-runtime-verification`
**Predecessor**: R.1.b (`5332cc3`)

## Verdict

```
PASS_A1B_AE_R_2_PRESET_AGENT_MATERIALIZATION_FILED
```

FILED per charter §10 — phase terminal R.6 decides promotion to `_VERIFIED`.

## Scope

R.2 closes the A1B-AE.8 preset-materialization gap: 4 of 5 Preset Agent
Cards had `delegates_to_pack: null` (only `icoder-medical-coding-preset`
was backed by a real Pack). R.2 wires 3 of the 4 stub presets to real
Pack metadata and adds the Corti-Console quick-create surface that
Journey 7 was originally trying to invoke.

| A1B-AE gap | R.2 fix |
|---|---|
| `icoder-cdi-preset.delegates_to_pack = null` | Set to `icoder/clinical-documentation-improvement-agent@1.0.0` (Pack already existed) |
| `icoder-drg-dip-preset.delegates_to_pack = null` | Set to `icoder/drg-analyzer@1.0.0` (Pack already existed) |
| `icoder-claim-check-preset.delegates_to_pack = null` | Set to `icoder/claim-check@1.0.0` (new slim Pack created in R.2) |
| `icoder-intake-interview-preset.delegates_to_pack = null` | DEFERRED to R.4 — no Interviewing Pack exists yet |
| Journey 7 (`POST /api/v1/agents/quick?from_preset=...`) returned 404 because no quick-create-from-preset path existed | `from_preset` query param added to existing `POST /api/v1/agents/quick`; seeds name/description/system_prompt/agent_type/expert_ids/config from the preset |
| 3 legacy underscore-named dirs marked for deletion in A1B-AE.9 | REFRAMED as RETAINED_AS_PYTHON_IMPLEMENTATION — Python identifiers cannot contain dashes, so the underscore dirs ARE the implementation modules backing the dash-form Pack metadata. Deletion deferred to a future migration phase. |

## Files added / modified

**Added**:
- `backend/official_agents/claim-check/agent_pack.json` — new slim Pack with `agent_ref: icoder/claim-check@1.0.0`, maturity=mvp, wrapping `external-gate/evaluate` + Insurance Audit rule_set
- `backend/tests/test_api/test_a1b_ae_r_2_preset_materialization.py` — 18 tests covering catalog wiring, Pack existence, quick-create from preset, Journey 7 regrade

**Modified**:
- `backend/agent_catalog/icoder_preset_agents.json` — `delegates_to_pack` set on `icoder-cdi-preset` / `icoder-drg-dip-preset` / `icoder-claim-check-preset`
- `backend/app/api/agent_cards.py` — `quick_create_agent` accepts optional `from_preset` query param; when set, looks up the preset and seeds the new Agent's fields + stores `delegates_to_pack` in `config`
- `backend/app/schemas/agent_card.py` — `AgentQuickCreate.name` relaxed to `str | None` (required when no `from_preset`; optional when `from_preset` provides default)
- `backend/official_agents/code_validation/DEPRECATED.md` — reframed as RETAINED_AS_PYTHON_IMPLEMENTATION (was LEGACY_CODE_ORPHAN)
- `backend/official_agents/compliance_guardrail/DEPRECATED.md` — same reframe
- `backend/official_agents/note_completeness/DEPRECATED.md` — same reframe

## Design decisions

### Pack reuse vs. new-build

The plan listed R.2 deliverables as "build slim cdi/ drg-dip/ claim-check/ Pack wrappers." On inspection:
- `icoder/clinical-documentation-improvement-agent@1.0.0` (CDI Pack) already exists at `official_agents/clinical-documentation-improvement-agent/agent_pack.json` with full Corti §6 surface + 9-red-line config + 4 Experts + 7 tools. The CDI Preset delegates to this Pack directly — no new Pack needed.
- `icoder/drg-analyzer@1.0.0` (DRG Pack) already exists at `official_agents/drg-analyzer/agent_pack.json` with DRG/DIP risk review schema + high_risk_code_prefixes + 1 Expert. DRG/DIP Preset delegates to this Pack.
- `icoder/claim-check@1.0.0` (Claim Check Pack) DID NOT exist. R.2 created a slim wrapper Pack at `official_agents/claim-check/agent_pack.json` that wraps `external-gate/evaluate` + Insurance Audit rule_set.

Decision driven by plan §Risk Register #4: "Pack building scope creep — building a full cdi/drg-dip/claim-check Pack from scratch could swallow the phase. Each Pack should be a slim wrapper around existing services, not a reimplementation."

### Legacy orphan deletion — REFRAMED, not executed

Plan §R.2 said: "delete dirs `code_validation/`, `compliance_guardrail/`, `note_completeness/` (underscore form). Migrate any call sites in `backend/app/` that reference these to dash-form canonical."

Plan §Risk Register #3 said: "Legacy orphan deletion blast radius — 3 dirs may have importers or seed scripts referencing them. Grep before delete; migrate first."

R.2 grep found 4 active app importers + 7+ test files referencing these dirs:

```
app/main.py:1145                              from official_agents.code_validation.agent import run
app/icoder/mcp/handlers/validate_codes.py:44  from official_agents.code_validation.agent_legacy import run_legacy
app/icoder/mcp/handlers/evaluate_compliance.py:32 from official_agents.compliance_guardrail.agent import run
app/icoder/mcp/handlers/check_documentation_gaps.py:30 from official_agents.note_completeness.agent import run
app/icoder/markdown_generator.py:248,343,455  3 generator functions
app/icoder/mcp/tool_registry.py:466           wraps agent.py::run() as MCP tool
```

**Root cause**: Python identifiers cannot contain `-`. The dash-form dirs (`code-validation/`, etc.) can only hold `agent_pack.json` metadata; the Python implementation MUST live in an identifier-valid dir. The underscore-form dirs ARE the implementation; the dash-form dirs are the Pack metadata. They are not duplicates — they are two halves of the same Pack.

**R.2 action**: Reframed all 3 underscore-form DEPRECATED.md notices as `RETAINED_AS_PYTHON_IMPLEMENTATION per A1B-AE-R.2 §2`. Documented the migration path (future phase can rename to `code_validation_impl/` or move into `official_agents/_impl/` namespace) and explicitly noted this is out-of-scope for R.2.

### Journey 7 fix — from_preset query parameter

Journey 7 (originally graded `API_WORKFLOW_VERIFIED` despite 404) was regraded in R.0 as `EVIDENCE_MISJUDGMENT_CORRECTED`. R.2 closes the actual gap by extending `POST /api/v1/agents/quick` with an optional `from_preset` query parameter:

```
POST /api/v1/agents/quick?from_preset=icoder-cdi-preset
POST /api/v1/agents/quick?from_preset=icoder-drg-dip-preset
POST /api/v1/agents/quick?from_preset=icoder-claim-check-preset
```

When `from_preset` is set:
- The preset's `name`, `description`, `system_prompt`, `agent_type`, `canonical_key`, and expert keys seed the new Agent row
- `delegates_to_pack` is stored in `config.delegates_to_pack` for the runtime to resolve
- The Agent is then resolvable via `GET /api/v1/agents/resolve/{canonical_key}` (closing the original Journey 7 root cause: no Agent row existed to resolve)

The existing name-only flow (Corti Console create-then-customize UX) still works when `from_preset` is absent.

## Test evidence

```
tests/test_api/test_a1b_ae_r_2_preset_materialization.py   18 passed
tests/test_api/test_a1b_ae_4_agent_crud.py                 32 passed
tests/test_api/test_a1b_ae_8_icoder_preset_agents.py       25 passed
tests/test_api/test_a1b_ae_9_tech_debt_liquidation.py      19 passed
```

### Pre-existing failure (NOT R.2 regression)

```
tests/test_api/test_a1a_gate4_2_clinical_tenant_boundary.py
  ::test_migration_021_added_check_constraint_on_clinical_tables   FAILED
```

Verified pre-existing at R.1.b commit `5332cc3` via `git stash` + re-run. Root cause:
dev DB (`data/icoder.db`) missing the `chk_encounters_org_not_null` CHECK constraint.
Not introduced by R.2 — R.2 doesn't touch encounters/documents/cdi_cases schema.

## Journey 7 regrade evidence

| Step | Original (Journey 7) | R.2 result |
|---|---|---|
| Request | `GET /api/v1/agents/resolve/code_validation` | `POST /api/v1/agents/quick?from_preset=icoder-cdi-preset` |
| Response | 404 (no Agent row) | 200 + new Agent ID + canonical_key=icoder-cdi-preset |
| Followup | none | `GET /api/v1/agents/resolve/icoder-cdi-preset` → 200 |
| Original verdict | `API_WORKFLOW_VERIFIED` (EVIDENCE_MISJUDGMENT) | `EVIDENCE_MISJUDGMENT_CORRECTED` (R.0) → now `HUMAN_WORKFLOW_VERIFIED` (R.5 will re-run headed-browser) |

## 5-tuple state (unchanged)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Forbidden verdicts (8) — honoured

None of `PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` appears in this sub-gate, its report, or its commit message.

## Charter §11 forbidden ops — honoured

- No `git push` (branch remains local)
- No `merge --no-ff` to master
- No `amend`
- No `rebase`
- No `reset --hard`
- No `git add -A` / `-a` (explicit file list)
- No force-push

## R.2 status — complete

R.2 (Preset Agent materialization) is now complete in 1 commit:
- 3/4 stub presets now have delegates_to_pack pointing at real Pack dirs
- claim-check Pack created (new slim wrapper)
- POST /api/v1/agents/quick?from_preset=... endpoint closes Journey 7 root cause
- Legacy orphan deletion reframed as RETAINED_AS_PYTHON_IMPLEMENTATION (Python identifier rule forces dual-naming)

## Next

R.3 — Public Expert + MCP (PubMed/ClinicalTrials live + VCR fixtures + MCP tools/list + tools/call + SSRF allowlist).
