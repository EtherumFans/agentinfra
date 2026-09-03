# A1B-AE.9 — Agent/Expert tech-debt liquidation (filed, not verified)

**Sub-gate**: A1B-AE.9 (Commit 10 of 12)
**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (inherited from A1A Gate 4R-I.11)
**Prior commit**: `4aae842` (A1B-AE.8)

## Scope

Three targeted debt paydowns that surface the A1B-AE.7 External-Expert
Gate + A1B-AE.8 Preset Agents via REST and document the legacy-orphan
deletion roadmap without breaking existing call sites.

| # | Deliverable | Surface |
|---|---|---|
| §1 | External-Expert Gate REST endpoint | `GET /api/v1/experts/external-gate/evaluate` |
| §2 | Preset Agents REST router | `GET /api/v1/presets`, `/api/v1/presets/{key}`, `/api/v1/presets/{key}/card` |
| §3 | Legacy-orphan DEPRECATED notices | 3 DEPRECATED.md files (code_validation / compliance_guardrail / note_completeness) |

## §1 External-Expert Gate REST — `app/api/experts.py`

New endpoint `GET /api/v1/experts/external-gate/evaluate` exposes the
A1B-AE.7 gate evaluator. Query params:

- `expert_key` (required) — the canonical_key to evaluate.
- `region` (optional) — CN / EU / US. If omitted, region check is skipped.
- `egress_enabled` (default `false`) — Charter §6 default.
- `provider_opt_in` / `tenant_opt_in` (default `false` each) — web-search gates.
- `licence_token_count` (default `0`) — number of tokens supplied. The
  endpoint deliberately does NOT accept the tokens themselves (that
  would leak credentials in query strings). Callers POST tokens
  out-of-band; the gate just needs the count.

Response shape:

```json
{
  "expert_key": "drugbank",
  "permitted": false,
  "reason": "LICENCE_REQUIRED",
  "notes": "drugbank requires a commercial licence token; supply via licence_tokens. No LLM fallback."
}
```

The gate does NOT perform any live call. It only rules on what *would*
be allowed under the supplied context.

## §2 Preset Agents REST — `app/api/presets.py`

New router mounted at `/api/v1/presets`. Three endpoints:

- `GET /api/v1/presets` — list summary (canonical_key, name, name_zh,
  agent_type, corti_alignment, delegates_to_pack, expert_count).
- `GET /api/v1/presets/{canonical_key}` — full PresetAgent detail
  including red_lines and runtime modes.
- `GET /api/v1/presets/{canonical_key}/card` — Corti §6 camelCase Agent
  Card + icoder_ext block (per A1B-AE.8 §3).

All endpoints are read-only. 404 on unknown canonical_key.

Mount: `app/main.py` imports `presets_router` and calls
`app.include_router(presets_router)`.

## §3 Legacy-orphan DEPRECATED notices

Three `DEPRECATED.md` files created (one per LEGACY_CODE_ORPHAN
identified in A1B-AE.2 §3):

- `backend/official_agents/code_validation/DEPRECATED.md`
- `backend/official_agents/compliance_guardrail/DEPRECATED.md`
- `backend/official_agents/note_completeness/DEPRECATED.md`

Each notice records:
- LEGACY_CODE_ORPHAN status per A1B-AE.2 §3.
- The canonical dash-form successor.
- Why the dir is NOT deleted in A1B-AE.9 (call sites that still import):
  - `code_validation/` → `app/icoder/mcp/handlers/validate_codes.py:44` + `app/main.py:1145`
  - `compliance_guardrail/` → `app/icoder/mcp/handlers/evaluate_compliance.py:32`
  - `note_completeness/` → `app/icoder/mcp/handlers/check_documentation_gaps.py:30`
- Deletion roadmap (deferred to a future A1B phase that migrates the call sites).

A1B-AE.9 deliberately does NOT delete the dirs — that would break
callers. The notices make the debt explicit and trackable.

## Provenance (Charter Amendment 1 §7)

| Artifact | Tier | Source |
|---|---|---|
| `app/api/experts.py` (external-gate endpoint) | `ICODER_INTERNAL` | iCoDer REST surface; gate evaluator is A1B-AE.7 (ICODER_INTERNAL) |
| `app/api/presets.py` | `ICODER_INTERNAL` | iCoDer REST surface; catalog is A1B-AE.8 (ICODER_INTERNAL) |
| `app/main.py` (router mount) | `ICODER_INTERNAL` | iCoDer glue |
| 3 × DEPRECATED.md | `ICODER_INTERNAL` | iCoDer debt ledger |
| Test file | `ICODER_INTERNAL` | Deterministic assertions |
| Report + INDEX | `ICODER_INTERNAL` | This document |

## Test coverage — `tests/test_api/test_a1b_ae_9_tech_debt_liquidation.py`

**15 tests in 1.35s. All PASS.**

| Section | Tests | Coverage |
|---|---|---|
| §1 External-Gate REST | 5 | non-gated passthrough; drugbank LICENCE_REQUIRED; drugbank licence satisfied; web-search PROVIDER_OPT_IN_MISSING; pubmed EGRESS_DISABLED |
| §2 Presets REST | 6 | list returns 5; summary fields; detail returns red_lines + delegates_to_pack; detail 404; card emits Corti §6 camelCase; card 404 |
| §3 DEPRECATED notices | 3 | one per legacy orphan dir; LEGACY_CODE_ORPHAN + A1B-AE.9 + dash-form successor all mentioned |
| §4 Charter | 1 | forbidden verdicts preserved |

**§4 forbidden verdicts preserved**: 8 forbidden ∩ 1 allowed = ∅.

Combined regression A1B-AE.3..9: **164 tests PASS in 3.33s**.

## Explicit debt NOT liquidated in A1B-AE.9 (filed for future)

| Debt | Why deferred |
|---|---|
| Legacy-orphan dir deletion (code_validation / compliance_guardrail / note_completeness) | Call sites still import from these dirs; deletion requires call-site migration first |
| MCP servers wiring in 5 presets | `mcp_servers[]` still empty; future MCP integration |
| cdi / drg-dip / claim-check backing Packs | `delegates_to_pack = null` (A1B-AE.8); the supporting Packs are a future phase |
| PubMed / Clinical Trials live integration | Live E-utilities / CT.gov API calls deferred (Charter §6 egress gate needed first) |
| DrugBank / POSOS live integration | Commercial licence required (no LLM fallback — patient-safety red line) |
| Web Search live integration | Default-disabled; future privacy-preserving provider |
| Interviewing LLM adaptive prompts | Schema-driven loop only; LLM-driven branching is future |

These are recorded for the A1B-AE.11 final reconciliation roadmap.

## Acceptance

```
A1B-AE.9_PARTIAL = FILED
```

- External-Expert Gate now reachable via REST.
- 5 iCoDer Preset Agents now reachable via REST (list + detail + Corti §6 card).
- 3 legacy-orphan DEPRECATED notices filed (dirs not deleted; roadmap recorded).
- 15 new tests PASS; 164 combined A1B-AE.3..9 tests PASS in 3.33s.
- No forbidden verdict used.
- All work in `phase-a1b/agent-expert-clean-room` branch (local-only, not pushed, not merged).

## Forbidden verdicts honoured

```
PRODUCTION_READY                              ∉ filed verdicts
FULLY_VERIFIED                                ∉ filed verdicts
PHI_BOUNDED                                   ∉ filed verdicts
CORTI_PARITY_VERIFIED                         ∉ filed verdicts
PASS_A1A_GATE4_FINAL                          ∉ filed verdicts
READY_FOR_HOSPITAL_DEPLOYMENT                 ∉ filed verdicts
CLINICAL_GRADE_VERIFIED                       ∉ filed verdicts
CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED      ∉ filed verdicts
```

## Verdict

```
PARTIAL_A1B_AE_9_TECH_DEBT_LIQUIDATION_FILED
```

Next: A1B-AE.10 — 10 headed-browser journeys + evidence.
