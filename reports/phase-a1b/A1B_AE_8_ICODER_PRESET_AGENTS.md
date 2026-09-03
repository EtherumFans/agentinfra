# A1B-AE.8 — iCoDer Preset Agents (filed, not verified)

**Sub-gate**: A1B-AE.8 (Commit 9 of 12)
**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (inherited from A1A Gate 4R-I.11)
**Prior commit**: `53af9ab` (A1B-AE.7)

## Scope

Land 5 Corti-§6-compatible iCoDer Preset Agent Cards that bind the Expert
Registry (A1B-AE.3..7) into out-of-the-box usable Agent definitions. Each
preset references canonical Experts by key and declares the Corti §6
surface (name / description / systemPrompt / agentType / experts[] /
mcpServers[]) plus an iCoDer-specific extensions block (`icoder_ext`)
carrying red_lines, runtime modes, and pack-delegation hints.

## The 5 presets

| canonical_key | agent_type | corti_alignment | Wraps / drives |
|---|---|---|---|
| `icoder-medical-coding-preset` | `expert` | CORTI_ALIGNED | `icoder/medical-coding-agent@2.0.0` Pack |
| `icoder-cdi-preset` | `expert` | CORTI_ADAPTED | Phase 5 Track D CDI flow + Interviewing Expert |
| `icoder-drg-dip-preset` | `expert` | CORTI_ADAPTED | DRG/DIP risk + rule-structure (no reimbursement amount) |
| `icoder-intake-interview-preset` | `interviewing-expert` | CORTI_ALIGNED | Interviewing Expert (A1B-AE.7) schema-driven intake |
| `icoder-claim-check-preset` | `orchestrator` | CORTI_ADAPTED | Pre-submission check + appeal drafting |

## §1 Catalog — `agent_catalog/icoder_preset_agents.json`

Clean-room authored. Provenance tier: `ICODER_INTERNAL`.

Each preset declares:
- `canonical_key`, `name`, `name_zh`, `description`
- `agent_type` (3-value Corti enum from A1B-AE.1 §2.1)
- `system_prompt` (clean-room text; no Corti prompts copied)
- `experts[]` — references to A1B-AE.3..7 canonical keys with role (primary / auxiliary / reference)
- `mcp_servers[]` — empty for A1B-AE.8 (MCP wiring is a future enhancement)
- `corti_alignment` (CORTI_ALIGNED / CORTI_ADAPTED)
- `delegates_to_pack` (optional Pack ref; only medical-coding preset sets this)
- `red_lines` — flow-specific hard limits (see §5)
- `default_runtime_mode` + `available_runtime_modes`

## §2 Service — `app/services/preset_agents.py`

Hermetic loader (no network). Reads `icoder_preset_agents.json` once,
caches in module-level `_LOADED_PRESETS` dict.

Public API:
- `all_presets() -> list[PresetAgent]` (deterministic catalog order)
- `get_preset(canonical_key) -> PresetAgent | None`
- `corti_agent_card(canonical_key) -> dict | None` — emits the Corti §6 camelCase card
- `preset_keys() -> list[str]`

`PresetAgent.corti_agent_card()` returns the Corti §6 surface plus an
`icoder_ext` block (canonical_key, name_zh, corti_alignment,
delegates_to_pack, red_lines, runtime modes) — iCoDer extensions are
namespaced to keep the Corti surface clean.

## §3 Corti §6 surface emission

```
{
  "name":             "<preset.name>",
  "description":      "<preset.description>",
  "systemPrompt":     "<preset.system_prompt>",
  "agentType":        "<expert|orchestrator|interviewing-expert>",
  "experts":          [{"canonicalKey": "...", "role": "primary|auxiliary|reference"}],
  "mcpServers":       [],
  "icoder_ext": {
    "canonical_key": "...",
    "name_zh":      "...",
    "corti_alignment": "...",
    "delegates_to_pack": "...|null",
    "red_lines":        {...},
    "default_runtime_mode":    "corti_like_fast",
    "available_runtime_modes": ["corti_like_fast"]
  }
}
```

The Corti §6 fields are emitted exactly as Corti's public create-agent
schema describes (per A1B-AE.1 §2.1 observation). iCoDer extensions do
NOT pollute the Corti namespace.

## §4 Cross-reference integrity

Every expert referenced in any preset MUST be one of the 9 Corti §3.2
canonical keys registered in A1B-AE.3..7. The test
`test_all_preset_expert_refs_resolve_to_canonical_registry` enforces
this — it catches drift if a preset references an unknown Expert.

| Preset | Primary | Auxiliary | Reference |
|---|---|---|---|
| medical-coding | coding-expert | medical-calculator, memory | — |
| cdi | interviewing | memory | pubmed, clinical-trials |
| drg-dip | coding-expert | medical-calculator, memory | — |
| intake-interview | interviewing | memory | — |
| claim-check | coding-expert | memory | pubmed, clinical-trials |

## §5 Red lines enforced

Every preset declares at least the 3 baseline red lines:

```
human_review_required        = true
phi_redacted                 = true
production_writeback_blocked = true
```

Flow-specific extensions:
- medical-coding: `no_upcoding`, `no_inference_beyond_documentation`
- cdi: + `no_auto_diagnosis`, `no_cmi_target` (Phase 5 Track D 9-red-line set)
- drg-dip: + `no_reimbursement_amount`, `no_upcoding`
- claim-check: + `no_auto_submission`, `no_upcoding`

Tests `test_red_line_enforced_true` (parametrized over preset × red line)
ensure no preset silently drops a baseline red line.

## Provenance (Charter Amendment 1 §7)

| Artifact | Tier | Source |
|---|---|---|
| `icoder_preset_agents.json` | `ICODER_INTERNAL` | Clean-room authored; Corti §6 contract surface from A1B-AE.1 public observation |
| `preset_agents.py` | `ICODER_INTERNAL` | iCoDer service; no Corti code referenced |
| Test file | `ICODER_INTERNAL` | Deterministic assertions |
| Report + INDEX | `ICODER_INTERNAL` | This document |

The underlying Experts referenced by presets retain their individual
provenance tiers (CLEAN_ROOM_PUBLIC or ICODER_INTERNAL per A1B-AE.3..7).

## Test coverage — `tests/test_api/test_a1b_ae_8_icoder_preset_agents.py`

**43 tests in 1.33s. All PASS.**

| Section | Tests | Coverage |
|---|---|---|
| §1 Catalog loading | 3 | 5 presets in catalog order; unknown returns None; each expected key present |
| §2 Per-preset structure | 15 (3 tests × 5 presets) | required fields; agent_type in allowed enum; ≥1 expert with allowed role + canonical key; primary role present |
| §3 Corti Agent Card | 3 | camelCase surface + icoder_ext block; unknown returns None; interviewing preset references interviewing Expert |
| §4 Cross-reference | 3 | all expert refs resolve to canonical registry; medical-coding delegates_to_pack correct; agent_type distribution (3 expert + 1 interviewing + 1 orchestrator) |
| §5 Red lines | 23 | 3 baseline × 5 presets parametrized + flow-specific (medical-coding no_upcoding; cdi no_auto_diagnosis + no_cmi_target; claim-check no_auto_submission) |
| §6 Charter | 1 | forbidden verdicts preserved |

**§6 forbidden verdicts preserved**: 8 forbidden ∩ 1 allowed = ∅.

Combined regression A1B-AE.3..8: **149 tests PASS in 3.11s**.

## Explicit parity gaps (recorded as tech debt, not closure)

| Capability | A1B-AE.8 scope | Gap |
|---|---|---|
| MCP servers wiring | `mcp_servers[]` is empty for all 5 presets | Future: wire MCP servers per preset when MCP integration lands |
| cdi / drg-dip / claim-check pack delegation | `delegates_to_pack = null` (no Pack yet) | These presets describe flows; the supporting Packs are A1B-AE.9 or later-phase work |
| Runtime modes beyond `corti_like_fast` | medical-coding exposes `medcoder_deep`; others single-mode | Future: per-preset runtime mode matrix |

These gaps are A1B-AE.9 (tech-debt liquidation) candidates or later-phase
work. They are NOT closure claims.

## Acceptance

```
A1B-AE.8_PARTIAL = FILED
```

- 5 preset Agent Cards filed with Corti §6 surface + iCoDer extensions.
- All expert references resolve to the 9-key Expert Registry.
- 43 new tests PASS; 149 combined A1B-AE.3..8 tests PASS in 3.11s.
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
PARTIAL_A1B_AE_8_ICODER_PRESET_AGENTS_FILED
```

Next: A1B-AE.9 — Agent/Expert tech-debt liquidation.
