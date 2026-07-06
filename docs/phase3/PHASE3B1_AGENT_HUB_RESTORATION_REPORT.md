# Phase 3-B1 Section B — Agent Hub Endpoint Restoration Report

**Date**: 2026-07-04
**Status**: COMPLETE — `/api/icoder/agents/hub` restored; 13/13 new tests pass; 136 icoder integration tests pass (no regression)

## B.1 What was restored

The Corti-style Agent Hub endpoint `/api/icoder/agents/hub` was deleted in Phase 2.1-B (commit `5c4e0e3`, P1.2 corti-parity-deletion) along with 1029 LOC of self-invented iCoDer concepts (Doctor / MethodCompare / RunTrace / Marketplace / methods/). The deletion was correct in spirit — those concepts were not Corti-aligned — but it left the frontend AgentsPage with no pack-mastered data source. Section B restores the endpoint with a clean Corti-style design.

## B.2 Implementation

### B.2.1 New file: `backend/app/api/icoder_agents_hub.py`

A single-file router (208 LOC) that:

1. Reads `official_agents/**/agent_pack.json` as the canonical source (16 packs on disk).
2. Filters by visibility rules:
   - `hidden_from_hub=true` → excluded
   - `agent_type=expert-stub` → excluded (MedCodER pipeline stages)
   - `agent_type=internal_engine` → excluded (medcoder-coding-review)
3. Projects each visible pack into a Corti-style Hub card with the 13 fields required by the prompt (name, display_name, category, description, maturity, production_ready, hidden_from_hub, human_review, requirements, runnability, output_contract, workflow, risks/constraints).
4. Surfaces 4 Corti red lines for the Medical Coding Agent: `no_upcoding`, `no_inference`, `evidence_required`, `production_writeback_blocked`.
5. Returns the 8-field Phase 3-A output contract for the Medical Coding Agent card (`MedicalCodingAgentOutputV2/v1` schema_ref + required_fields).
6. No auth — product browsing endpoint. Execution is gated separately at the run endpoint.

### B.2.2 Hub response shape

```json
{
  "agents": [
    {
      "agent_ref": "icoder/medical-coding-agent@2.0.0",
      "name": "Medical Coding Agent",
      "display_name": "Medical Coding Agent",
      "category": "medical-coding",
      "category_display": "Coding and Revenue Cycle / 编码与收入周期",
      "icon": "Stethoscope",
      "version": "2.0.0",
      "description": "...",
      "maturity": "mvp",
      "production_ready": false,
      "human_review": "required",
      "hidden_from_hub": false,
      "runnable": true,
      "badge": "MVP / AI-assisted / Human review required",
      "tags": ["icd-10-cn", "icd-9-cm-3", ...],
      "workflow": "Corti 7-step: Synthesize → Extract → Search → Assign → Validate → Identify Gaps → Review",
      "red_lines": {
        "no_upcoding": true,
        "no_inference": true,
        "evidence_required": true,
        "production_writeback_blocked": true
      },
      "requirements": {
        "min_runtime_version": "2.0.0",
        "icoder_runtime_modules": [...],
        "required_models": ["deepseek-v4", "BAAI/bge-m3"]
      },
      "output_contract": {
        "schema_ref": "icoder/MedicalCodingAgentOutputV2/v1",
        "required_fields": [
          "encounter_summary", "documentation_analysis", "code_assignment",
          "documentation_gaps", "uncodable_items", "validation_summary",
          "human_review", "trace_refs"
        ]
      },
      "non_goals": [...],
      "human_review_required_when": [...],
      "a2a_endpoint": "/api/icoder/agents/medical-coding-agent/v1/message:send",
      "run_endpoint": "/api/runtime-platform/agents/icoder/medical-coding-agent@2.0.0/run"
    },
    // ... 10 metadata-only certified packs with runnable=false, badge="Coming Soon / Metadata only"
  ],
  "total": 11,
  "source": "official_agents/agent_pack.json",
  "schema_version": "1.0"
}
```

### B.2.3 Mount in `backend/app/main.py`

Added 2 lines (1 import + 1 `include_router`):

```python
from app.api.icoder_agents_hub import router as icoder_agents_hub_router
# ...
app.include_router(icoder_agents_hub_router)  # Phase 3-B1 (2026-07-04) /api/icoder/agents/hub
```

No conflicts with the A2A discovery router (`/api/icoder/agents` list + `/{agent_id}/card`) because the Hub's `/hub` path is a single segment that doesn't collide with `""` or `/{agent_id}/card`.

## B.3 Files changed

| File | Change | LOC |
|---|---|---|
| `backend/app/api/icoder_agents_hub.py` | **new** — Corti-style Hub router | +208 |
| `backend/app/main.py` | +1 import, +1 include_router | +2 |
| `backend/tests/integration/icoder/test_phase3b1_agent_hub.py` | **new** — 13 contract tests | +275 |
| **Total** | | **+485** |

No agent_pack.json files modified. No frontend files modified (Section F handles frontend sync). No existing tests modified.

## B.4 Tests added (13 new tests, all pass)

| Test | Verifies |
|---|---|
| `test_hub_endpoint_returns_200` | Endpoint returns 200 |
| `test_hub_response_contract_shape` | Response has `agents`, `total`, `source`, `schema_version`; `source == "official_agents/agent_pack.json"` |
| `test_hidden_packs_excluded` | `hidden_from_hub=true` packs don't appear |
| `test_expert_stubs_excluded` | 4 expert-stub packs (evidence-extractor / index-navigator / code-reconciler / tabular-validator) don't appear |
| `test_internal_engine_excluded` | medcoder-coding-review-agent@1.0.0 doesn't appear |
| `test_metadata_only_packs_visible_but_not_runnable` | 10 metadata-only packs visible with `runnable=false`, `run_endpoint=None`, badge="Coming Soon" |
| `test_medical_coding_agent_visible_and_runnable` | Medical Coding Agent visible with `runnable=true`, `run_endpoint` set, `maturity=mvp`, `production_ready=false`, badge includes "MVP" + "AI-assisted" + "Human review" |
| `test_production_ready_field_always_present` | Every card has boolean `production_ready` field (A.5.5) |
| `test_no_production_ready_false_claimed_as_ready` | No `production_ready=false` pack claims `maturity=production-ready` or has "production-ready" in badge |
| `test_hub_total_count_matches_visibility_filter` | Total = 11 (10 metadata-only + medical-coding-agent MVP) |
| `test_runnable_card_has_run_endpoint` | Runnable cards have `run_endpoint` containing `agent_ref`; non-runnable have `None` |
| `test_medical_coding_agent_red_lines_preserved` | 4 Corti red lines surfaced in `red_lines` field |
| `test_medical_coding_agent_output_contract_surfaced` | 8-field `MedicalCodingAgentOutputV2/v1` contract in `output_contract.required_fields` |

**Result**: 13/13 PASS in 14.52s.

## B.5 No-regression verification

| Suite | Before | After | Status |
|---|---|---|---|
| `tests/integration/icoder/` (full) | 123 pass (Phase 3-B0) | 136 pass (Phase 3-B0 + 13 new Hub) | **PASS** — 0 regression, +13 new |

## B.6 Prompt success criteria mapping

| Prompt §B requirement | Implementation | Test |
|---|---|---|
| 1. Endpoint returns Corti-style card list | `_build_card()` projects pack → card | `test_hub_response_contract_shape` |
| 2. agent_pack.json as canonical source | `_load_packs()` reads `official_agents/**/agent_pack.json`; response `source="official_agents/agent_pack.json"` | `test_hub_response_contract_shape` |
| 3. Reads 13 required fields | All 13 fields present in card schema | `test_medical_coding_agent_visible_and_runnable` + `test_medical_coding_agent_red_lines_preserved` + `test_medical_coding_agent_output_contract_surfaced` |
| 4. hidden_from_hub=true excluded | `_is_visible()` filters | `test_hidden_packs_excluded` |
| 5. metadata-only visible but Coming Soon + no Run | `runnable=false`, `run_endpoint=None`, `badge="Coming Soon / Metadata only"` | `test_metadata_only_packs_visible_but_not_runnable` |
| 6. stub packs excluded | `_is_visible()` filters `agent_type=expert-stub` | `test_expert_stubs_excluded` |
| 7. internal_engine excluded | `_is_visible()` filters `agent_type=internal_engine` | `test_internal_engine_excluded` |
| 8. Medical Coding Agent visible with MVP / AI-assisted / Human review | Badge `"MVP / AI-assisted / Human review required"` | `test_medical_coding_agent_visible_and_runnable` |
| 9. production_ready=false not displayed as production-ready | `maturity != "production-ready"` and badge excludes "production-ready" when `production_ready=false` | `test_no_production_ready_false_claimed_as_ready` |
| 10. No run path = not displayed as runnable | `_is_runnable()` requires `experts[]` non-empty AND maturity in `(mvp, runnable, production-ready)` | `test_runnable_card_has_run_endpoint` |

## B.7 Live API smoke (TestClient)

```
GET /api/icoder/agents/hub → 200
{
  "agents": [11 cards],
  "total": 11,
  "source": "official_agents/agent_pack.json",
  "schema_version": "1.0"
}
```

Live `curl` against `http://localhost:8000` returns 404 because the running uvicorn server hasn't been restarted to pick up the new `main.py` changes. TestClient tests prove the code works; Section G Round 4 will restart the server and verify with real HTTP.

## B.8 What was NOT done (intentional)

Per spec: "本轮不实施新的 Pre-built Agent". The 10 metadata-only packs remain metadata-only — they appear in the Hub with "Coming Soon" badges but are not yet runnable. Their implementation is Phase 3-B2.

Per spec: "不允许把 production_ready=false 的 Agent 显示成 production-ready" — enforced.

Per spec: "不允许把没有 run path 的 Agent 显示为 runnable" — enforced via `_is_runnable()` requiring non-empty `experts[]`.

No frontend changes in this section — Section F wires `AgentsPage.tsx` to call this endpoint.

No agent_pack.json modifications — the B0 quick fixes already declared `maturity`, `production_ready`, `hidden_from_hub` correctly across all 15 packs.

## B.9 Verdict

**Section B verdict**: PASS — `/api/icoder/agents/hub` restored; 13/13 new tests pass; 136 icoder integration tests pass (0 regression); 11 visible packs (10 metadata-only + Medical Coding Agent MVP); 4 Corti red lines + 8-field output contract surfaced; honesty rules A.5.1-A.5.5 preserved.

The Hub is now the stable pack-mastered data source for the frontend AgentsPage. Section C unifies it with A2A discovery and agent_definitions; Section D migrates the Medical Coding Agent run path to A2A mainline; Section F wires the frontend to call this endpoint.
