# Phase 3-A Section E — Runtime Integration Spec (v1 → v2 Projection)

**Date**: 2026-07-04
**Status**: COMPLETE — 5 new tests pass; pytest 1230+5=1235 passing; tsc 0 errors; build OK; vitest 54/54

## E.1 Goal

Wire v1 → v2 projection in the API layer so the Corti-style Review Summary panel (Section D) renders with real v2 data instead of the v1-projected fallback.

## E.2 Approach — Restore `/run` for medical-coding-agent only

`PlatformRuntime.run_agent` raises `NotImplementedError` per Phase 2.1-A (the legacy AgentRunner was deleted; A2A mainline is the only execution path). Rather than touch the A2A layer, we restore the `/api/runtime/agents/{agent_ref}/run` endpoint **for the Medical Coding Agent specifically**:

- `agent_ref == "icoder/medical-coding-agent@2.0.0"` → run `HybridCodingAdapter.infer_async` directly, project v1 → v2, return `RuntimeRunResult`-shaped response with v2 fields hoisted to top level.
- Other agent_refs → still 410 Gone (Phase 2.1-A deprecation preserved).

This:
- Doesn't break Phase 2.1-A's deprecation for other agents
- Unblocks the frontend's existing `runtimeAgentApi.runAgent` call (no frontend changes needed)
- Wires v2 projection in the API layer per the Section C spec
- Keeps A2A mainline untouched (architecturally clean — InboundHandler remains the only orchestrator entry point)

## E.3 Implementation — `app/api/runtime_platform.py`

### E.3.1 Path-parameter change

```python
@router.post("/agents/{agent_ref:path}/run")           # was {agent_ref}
async def run_agent_by_ref(agent_ref: str, body: AgentRunInput, ...):
    ...
```

The `:path` modifier lets `agent_ref` match URLs containing URL-encoded slashes (`%2F`). Without it, the route would 404 when the frontend sends `encodeURIComponent("icoder/medical-coding-agent@2.0.0")`.

Same change applied to:
- `@router.post("/agents/{agent_ref:path}/run")` (runtime-platform prefix)
- `@runtime_router.post("/agents/{agent_ref:path}/run")` (runtime prefix — frontend actually hits this)

### E.3.2 v2 projection logic

```python
if agent_ref != AGENT_REF:                              # "icoder/medical-coding-agent@2.0.0"
    raise HTTPException(410, "Legacy ... removed in Phase 2.1-A. Use A2A mainline ...")

# PII redaction (HARD requirement, matches /medical-coding/test)
messages = [{"role": "user", "content": encounter_text}]
if data_policy.pii_redaction_required:
    messages, redaction_result = PIIRedactor(...).redact_messages(messages)

# Run adapter (bypasses PlatformRuntime.run_agent which raises NotImplementedError)
adapter = HybridCodingAdapter(gateway=gateway, mode="hybrid")
v1 = await adapter.infer_async(messages)

# Project v1 → v2 (Corti-style 8 fields)
v1_schema = v1 if isinstance(v1, MedicalCodingOutputSchema) else MedicalCodingOutputSchema.from_dict(...)
v2 = MedicalCodingAgentOutputV2.from_legacy_v1(v1_schema, run_id=run_id)

# Build response with v2 fields hoisted
response = {
    "run_id": run_id, "agent_ref": agent_ref, "status": "success",
    # v1 fields (back-compat)
    "primary_diagnosis": v1_dict["primary_diagnosis"],
    "secondary_diagnoses": v1_dict["secondary_diagnoses"],
    "procedures": v1_dict["procedures"],
    "issues_found": v1_dict["issues_found"],
    # v2 Corti-style fields (hoisted)
    "review_conclusion": v2_dict["human_review"]["review_conclusion"],
    "manual_review_required": v2_dict["human_review"]["review_required"],
    "encounter_summary": v2_dict["encounter_summary"],
    "documentation_gaps": v2_dict["documentation_gaps"],
    "uncodable_items": v2_dict["uncodable_items"],
    "corti_validation_summary": v2_dict["validation_summary"],
    "human_review": v2_dict["human_review"],
    "trace_refs": {**v2_dict["trace_refs"], "run_id": run_id},
}
```

### E.3.3 `/medical-coding/test` consistency

The legacy `/api/runtime/medical-coding/test` endpoint (called by `runtimeAgentApi.testMedicalCoding`) also receives the v2 projection so callers hitting either endpoint get the same Corti-style shape. Projection is best-effort: failures log a warning but never break the v1 response.

## E.4 Files changed (Section E)

```
backend/app/api/runtime_platform.py                   (+90 lines: run_agent_by_ref rewrite + /medical-coding/test v2 projection + :path modifier)
backend/official_agents/medical_coding/__init__.py    (+20 lines docstring refresh: agent_ref @1.0.0 → @2.0.0, Corti-style 8-step description)
backend/tests/unit/app/api/test_runtime_platform_v2_projection.py  (+185 lines: 5 new tests)
```

3 files changed, +295 / -3.

## E.5 Test coverage

`tests/unit/app/api/test_runtime_platform_v2_projection.py` (5 tests):

| Test | Asserts |
|---|---|
| `test_medical_coding_agent_run_returns_v2_fields` | 200 status; v1 fields preserved (primary_diagnosis.code == "I21.0"); 8 v2 fields hoisted; review_conclusion == "WARNING"; manual_review_required == True; corti_validation_summary.passed == False; trace_refs.run_id present |
| `test_other_agents_still_410` | Non-medical-coding agent_ref → 410 Gone; error mentions "Phase 2.1-A" |
| `test_empty_input_400` | `input: "   "` → 400 |
| `test_medical_coding_test_returns_v2_fields` | `/medical-coding/test` also projects v1 → v2; same 8 v2 fields present |
| `test_v2_fields_always_present` | Corti contract: every field present with correct sub-shape (chief_complaint, issues_found, fired_rules, review_conclusion, review_required, run_id, method_id) — even when empty |

## E.6 Backward compatibility

- v1 fields (`primary_diagnosis`, `secondary_diagnoses`, `procedures`, `issues_found`, `audit_trail`, `processing_time_ms`, `token_usage`, `errors`) are preserved unchanged.
- v2 fields are pure additions — frontend code reading only v1 fields keeps working.
- Frontend's `RuntimeRunResult` TypeScript type already declares all 8 v2 fields as optional (Section D); the API now populates them.

## E.7 What did NOT change

- A2A mainline (`InboundHandler`, `mount_a2a`, A2A routes) — untouched. Still the only orchestrator entry point.
- `PlatformRuntime.run_agent` — still raises `NotImplementedError` per Phase 2.1-A. The `/run` endpoint calls `HybridCodingAdapter` directly, not `PlatformRuntime.run_agent`.
- `MedicalCodingOutputSchema` (v1) — the runtime still produces this internally; v2 is a thin projection layer.
- 410 behavior for non-Medical-Coding agents — preserved.
- MCP server (`/mcp/v1/tools/{list,call}`) — untouched.

## E.8 Out of scope (Phase 3-B+)

- `encounter_summary` is returned as an empty object (chief_complaint, treatment_course, etc. are not yet populated) — runtime doesn't synthesize these from EMR text yet. Phase 3-B may add an LLM synthesis step or an EncounterSynthesizer expert.
- `documentation_gaps` and `uncodable_items` are returned as empty lists. Phase 3-B may populate them from Stage 5 validation.
- A2A InboundHandler response shaping — currently A2A returns v1-shaped parts. If/when A2A needs to return v2, the projection can be lifted into a shared helper.

## Verification

```
$ cd backend && python -m pytest tests/unit/app/api/test_runtime_platform_v2_projection.py -v
5 passed in 0.92s

$ cd backend && python -m pytest tests/test_api/ tests/unit/ tests/regression/ tests/e2e/icoder/ -q --tb=line
1235 passed, 1 skipped, 0 failed (1230 baseline + 5 new)

$ cd frontend && npx tsc --noEmit  (0 errors)
$ cd frontend && npm run build     (✓ built)
$ cd frontend && npx vitest run src/  (54 passed)
```
