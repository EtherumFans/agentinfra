# Phase 3-D2 Task 4 Verification — Custom Markdown Generators

**Task:** 3 new agents get custom markdown (Code Validation / Compliance Guardrail / Note Completeness); JSON canonical output preserved; AgentChatPage Rendered tab defaults to custom markdown.
**Date:** 2026-07-07
**Status:** PASS
**Files affected:**
- `backend/app/icoder/markdown_generator.py` (MODIFIED — +3 generators + `generate_markdown_for()` dispatcher)
- `backend/app/main.py::_SimpleAgentDispatchHandler._handle_simple()` (MODIFIED — embeds `result["markdown"]` in DataPart)
- `frontend/src/utils/medicalCodingMarkdown.tsx` (MODIFIED — `generateFallbackMarkdown` dispatches by `schema_ref`)
- `backend/tests/unit/icoder/test_markdown_generator.py` (EXTENDED — +4 tests)

## What was built

### 3 per-agent markdown generators

Each generator renders a 5-section Markdown doc per the Phase 3-D2 PDF spec:

**Code Validation** (`generate_code_validation_markdown`):
1. Review Conclusion (conclusion / manual_review_required / rule_set)
2. Fired Rules (numbered list of fired rule IDs)
3. Issue Codes (rule_id / severity / code / message per issue)
4. Modification Suggestions (code / suggestion per issue that has a suggestion)
5. Manual Review Advice (text — fires "人工复核" advice when manual_review_required=True)

**Compliance Guardrail** (`generate_compliance_guardrail_markdown`):
1. Risk Conclusion (conclusion / manual_review_required / drg_suggestion)
2. DRG/DIP Sensitive Items (filtered issues where message contains DRG/DIP or severity is critical/high)
3. Compliance Checks (check_id / passed / severity / detail per check)
4. Risk Level (HIGH/MEDIUM/LOW based on conclusion + issue counts)
5. Audit Advice (text — fires "审计" advice when manual_review_required=True)

**Note Completeness** (`generate_note_completeness_markdown`):
1. Completeness Score (score as percentage / conclusion / manual_review / surgical_case)
2. Missing Sections (numbered list)
3. Present Sections (numbered list)
4. Supplement Suggestions (section / gap_type / suggestion per gap)
5. Coding/DRG/DIP Impact (text — fires "DRG" + "DIP" impact description when missing sections present)

### `generate_markdown_for(agent_id, result)` dispatcher

Keyed on `agent_id`:
- `code-validation-agent` → `generate_code_validation_markdown`
- `compliance-guardrail-agent` → `generate_compliance_guardrail_markdown`
- `note-completeness-agent` → `generate_note_completeness_markdown`
- Unknown → generic JSON dump fallback

### Backend pre-render in _SimpleAgentDispatchHandler

After `dispatch_tool()` returns, the handler calls `generate_markdown_for(agent_id, result)` and embeds the markdown as `result["markdown"]` in the DataPart. The frontend's `_mapA2AResultToRunResult` already projects `v2.markdown` through, so `result.markdown` lands on the frontend.

### Frontend fallback dispatch

`generateFallbackMarkdown(v2)` now checks `v2.schema_ref` (or `v2.output_contract`) and dispatches to per-schema fallback renderers:
- `icoder/CodeValidationOutput/v1` → `_fallbackCodeValidation`
- `icoder/ComplianceGuardrailOutput/v1` → `_fallbackComplianceGuardrail`
- `icoder/NoteCompletenessOutput/v1` → `_fallbackNoteCompleteness`
- Default → generic JSON dump (covers MedicalCodingAgentOutputV2 and unknown schemas)

The fallback only fires when the backend didn't pre-render (legacy/old pack). The Rendered tab already prefers `result.markdown || generateFallbackMarkdown(...)`.

## Verification steps

- [x] V1: Code Validation markdown has all 5 sections + surfaces fired rules + issue codes + suggestions + manual review advice — passes (`test_code_validation_markdown_has_5_sections`)
- [x] V2: Compliance Guardrail markdown has all 5 sections + surfaces DRG/DIP items + risk level + audit advice — passes (`test_compliance_guardrail_markdown_has_5_sections`)
- [x] V3: Note Completeness markdown has all 5 sections + surfaces score as percentage + missing/present sections + coding impact — passes (`test_note_completeness_markdown_has_5_sections`)
- [x] V4: `generate_markdown_for()` dispatches by agent_id; unknown → fallback — passes (`test_generate_markdown_for_dispatches_by_agent_id`)
- [x] V5: Frontend TypeScript compiles — passes (`npx tsc --noEmit` 0 errors)
- [x] V6: Existing Medical Coding Agent markdown (6 sections) still renders — passes (12 existing markdown tests still pass)

## PASS/FAIL criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Code Validation has 5 sections per spec | PASS | V1 |
| Compliance Guardrail has 5 sections per spec | PASS | V2 |
| Note Completeness has 5 sections per spec | PASS | V3 |
| JSON canonical output preserved | PASS | markdown is added as `result["markdown"]` alongside the dict; JSON tab still shows the dict |
| AgentChatPage Rendered tab defaults to custom markdown | PASS | `_SimpleAgentDispatchHandler` pre-renders; frontend prefers `result.markdown` |
| Frontend fallback dispatches by schema_ref | PASS | `generateFallbackMarkdown` updated |
| No regression in markdown tests | PASS | 16/16 markdown tests pass |

## Known limitations

- The frontend fallback renderers are minimal (they produce a usable but less-polished view than the backend pre-render). The backend pre-render is the SSOT; the fallback only fires for legacy/old packs that don't pre-render.
- The DRG/DIP sensitive items filter in `generate_compliance_guardrail_markdown` uses a heuristic (message contains "DRG" or "DIP", or severity is critical/high). This may over- or under-filter in edge cases; the Compliance Checks section always shows all checks regardless.

## Cross-reference

- Phase 3-B2 Loop 3 (Medical Coding Agent markdown) — Task 4 follows the same pattern (backend pre-render + frontend fallback).
- Phase 3-D2 Task 3 (MCP-native) — Task 4's markdown generator wraps the result that `dispatch_tool()` returns.
