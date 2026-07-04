# Phase 3-A Section D — Product UI/UX (Corti-style)

**Date**: 2026-07-04
**Status**: COMPLETE — tsc 0 errors; build OK; vitest 54/54; backend pytest 1230/1 unchanged

## D.1 MVP + AI-assisted banners (Corti red lines)

Persistent banners inserted between breadcrumb and action bar in `MedicalCodingPage.tsx`:

```
[MVP — production_ready=false, human_review=required]  [AI-assisted coding — 不替代编码员, 所有编码建议需人工复核]
```

- Amber backdrop (`bg-amber-50/60`) for MVP banner — signals "not yet production-ready"
- Blue backdrop (`bg-blue-50`) for AI-assisted banner — signals "human-in-the-loop"
- Both banners `data-testid="mvp-banner"` + `data-testid="ai-assisted-banner"` for e2e asserts
- Always visible — not conditional on `result` being present
- Corti red lines enforced: no "fully automated" language; no F1 / model effect display

## D.2 Corti-style Review Summary panel (8-field output)

Inserted at bottom of middle column (after DiagnosisCard section), renders Corti-style 8-field output projected from v1 + v2 fields:

| Field | Source (v1 fallback → v2) | UI element |
|---|---|---|
| `human_review.review_conclusion` | `r.review_conclusion \|\| r.human_review?.review_conclusion \|\| (issues_found.length > 0 ? 'WARNING' : 'PASS')` | Pill badge (PASS=emerald / WARNING=amber / FAIL=rose) |
| `human_review.review_required` | `r.manual_review_required \|\| r.human_review?.review_required \|\| issues_found.some(critical/high)` | "Manual review required" rose badge |
| `validation_summary.issues_found` | `r.corti_validation_summary?.issues_found \|\| r.issues_found` | Numbered list with severity color + code + message + suggestion |
| `validation_summary.fired_rules` | `r.corti_validation_summary?.fired_rules \|\| r.trace_refs?.rule_fired` | Inline `Rules fired: R001, R005` |
| `documentation_gaps` | `r.documentation_gaps \|\| []` | List with gap_type + description + related_code + suggestion; "No documentation gaps" placeholder when empty |
| `uncodable_items` | `r.uncodable_items \|\| []` | List with item_type + text + reason; "No uncodable items" placeholder when empty |
| `trace_refs.run_id` + `trace_refs.method_id` | `r.trace_refs?.run_id`, `r.trace_refs?.method_id` | Footer line "Run ID: ... · method: ..." |

**Corti contract enforcement**: every field must be visible (even when empty — placeholders render). No field is omitted from the UI. This matches the schema's `to_dict()` always returning all 8 keys.

**Backward compatibility**: when v2 fields are absent (Section E not yet wired), the panel projects from v1 fields (`issues_found`, `manual_review_required`, `review_conclusion`) so the user sees a Corti-style review summary even before the runtime produces v2 output.

## D.3 i18n keys added

| Key | zh-CN | en-US |
|---|---|---|
| `mvpBanner` | MVP — production_ready=false, human_review=required | MVP — production_ready=false, human_review=required |
| `aiAssistedBanner` | AI-assisted coding — 不替代编码员, 所有编码建议需人工复核 | AI-assisted coding — does not replace the coder; all code suggestions require human review |
| `reviewSummary` | 复核摘要 | Review summary |
| `reviewConclusion` | 复核结论 | Review conclusion |
| `reviewConclusionPass` | 通过 | Pass |
| `reviewConclusionWarning` | 警告 | Warning |
| `reviewConclusionFail` | 失败 | Fail |
| `manualReviewRequired` | 需要人工复核 | Manual review required |
| `uncodableItems` | 无法编码项 | Uncodable items |
| `encounterSummary` | 就诊摘要 | Encounter summary |
| `traceRefs` | 追踪引用 | Trace refs |
| `noDocumentationGaps` | 无文档缺口 | No documentation gaps |
| `noUncodableItems` | 无无法编码项 | No uncodable items |
| `rulesPassed` | 规则通过 | Rules passed |
| `rulesFired` | 触发规则 | Rules fired |
| `runId` | 运行 ID | Run ID |

**Reused existing keys** (already in Review section): `documentationGaps` + `validationSummary` — no duplicates added.

## D.4 Type additions

`frontend/src/types/runtime.ts` — added optional v2 fields to `RuntimeRunResult`:

```typescript
review_conclusion?: 'PASS' | 'WARNING' | 'FAIL' | string;
manual_review_required?: boolean;
encounter_summary?: { chief_complaint?, treatment_course?, key_findings?, document_sources?, encounter_date? };
documentation_gaps?: Array<{ gap_type?, description?, related_code?, suggestion? }>;
uncodable_items?: Array<{ item_type?, text?, reason? }>;
corti_validation_summary?: { passed?, issues_found?, manual_review_required?, rule_set?, fired_rules? };
human_review?: { review_conclusion?, review_required?, review_focus?, notes? };
trace_refs?: { run_id?, stage_trace?, rule_fired?, mode?, method_id?, provider?, model? };
```

All optional — absent when runtime returns v1-only (Section E will populate them).

**Note on `validation_summary` name collision**: existing `validation_summary: { supported: number; needs_review: number }` (line 20) is preserved unchanged. The Corti-style validation fields live in `corti_validation_summary` to avoid TS2717 subsequent-property-declaration conflict. Section E may consolidate by renaming the legacy field, but that's out of scope for Section D.

## D.5 What did NOT change

- 3-column layout (Input | Output | Settings/Code) — already Corti-aligned per Phase 1.1
- DiagnosisCard component (per-disease card with evidence chips + TopK + override) — already Corti-aligned
- HighlightedTextarea + EvidenceHighlighter (char-anchored spans with click-to-highlight) — already Corti-aligned
- All-codes table with confidence % — already Corti-aligned
- Sample menu + 4 inline template cards — already Corti-aligned
- Coding systems selector — already Corti-aligned

## Files changed (Section D)

```
frontend/src/i18n/locales.ts                    (+18 keys × 2 langs = +36 lines zh + en, +18 type def lines)
frontend/src/types/runtime.ts                   (+45 lines: 8 v2 field type declarations)
frontend/src/pages/MedicalCodingPage.tsx        (+9 lines banners, +95 lines Review Summary panel)
```

3 files changed, +193 / -3.

## Verification

```
$ cd frontend && npx tsc --noEmit  (0 errors, EXIT=0)
$ cd frontend && npm run build     (✓ built in 5.03s)
$ cd frontend && npx vitest run src/  (54 passed)

$ cd backend && python -m pytest tests/test_api/ tests/unit/ tests/regression/ tests/e2e/icoder/
1230 passed, 1 skipped, 0 failed in 117.61s  (unchanged from Section C baseline — no backend changes in D)
```

## Out of scope (Section E will wire)

- Runtime actually producing v2 fields in API response (currently panel projects from v1)
- `encounter_summary` rendering (placeholder — no UI yet, since runtime doesn't produce it)
- `documentation_analysis` rendering (placeholder — same reason)
- `code_assignment` rendering (existing all-codes table already serves this role)

Section E (Runtime Integration) will project v1 → v2 in `runtime_platform.py` API responses so the Corti-style panel renders with real v2 data.
