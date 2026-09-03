# Gate 4 — China CDI Capability Model Report

**Date**: 2026-07-11
**PDF ref**: §6 Gate 4 — full domain model with 8 gap types + evidence binding
**Status**: `PASS_GATE4_DOMAIN_MODELED`
**Commit**: `feat(track-d4): add documentation gap and provider query domain models`

---

## 1. What changed

| Before (Gate 3) | After (Gate 4) |
|---|---|
| `domain.py` = 8 dataclasses, no enums, no DB models | `domain.py` extended with 8-tuple GapType enum, 4-tuple RiskFlagCategory, 8-tuple DocumentType, 4-tuple ResponseOptionCategory + classifier helpers |
| No DB persistence | 5 new SQLAlchemy models (`app/models/cdi_case.py`) + alembic migration `011_cdi_models.py` |
| No gap classifier | `classify_gap_type(description, why_it_matters) -> GapType` — keyword-based classifier covering all 8 PDF §6.2 gap types |
| No response option classifier | `classify_response_option(label) -> ResponseOptionCategory` — identifies escape hatches (NLQ-005 support) |
| 29 tests | 55 tests (26 new in Gate 4) |

## 2. PDF §6.2 — 8 Gap Types

Per Corti CDI prompt + Track D PDF §6.2 + China clinical practice:

| GapType | Example | ICD-10-CN impact |
|---|---|---|
| `diagnostic_specificity` | 肺炎 vs 细菌性肺炎 | J18.9 vs J13 |
| `etiology_unspecified` | 急性肾损伤 病因未记录 | N17.x vs N17.0/.1/.2 |
| `severity_unspecified` | 慢性肾病 严重程度未记录 | N18.x CKD stage missing |
| `acuity_unspecified` | 心力衰竭 急慢性未区分 | I50.x acute vs chronic |
| `anatomical_site_unspecified` | 骨折 部位/侧别未明确 | S72.0 vs S72.1 + left/right 6th char |
| `clinical_correlation_unestablished` | 痰培养 vs 临床表现 关联未建立 | 病原体是否为致病菌 |
| `temporal_unspecified` | 术后发热 时间关系未记录 | 是否为术后并发症 |
| `conflicting_documentation` | 入院诊断 vs 出院诊断 不一致 | 主诊断选择 |

Classifier keywords (full list in `domain.py`):
- `diagnostic_specificity`: 特异性 / 病原体 / specificity
- `etiology_unspecified`: 病因 / etiology / cause of
- `severity_unspecified`: 严重程度 / 分级 / stage / severity / grade
- `acuity_unspecified`: 急性 / 慢性 / 急慢性 / acute / chronic
- `anatomical_site_unspecified`: 部位 / 左侧 / 右侧 / site / laterality
- `clinical_correlation_unestablished`: 临床关联 / 临床不符 / correlation
- `temporal_unspecified`: 时间关系 / 术后 / temporal / timing
- `conflicting_documentation`: 冲突 / 不一致 / 矛盾 / conflict / contradiction

Classifier behavior:
- Picks GapType with most keyword hits (case-insensitive substring match)
- Default on ties or no hits: `diagnostic_specificity` (most common CDI gap type)
- Case-insensitive (lower() on both sides)

## 3. PDF §6.3 — Response Option Taxonomy

4 categories per Gate 2 audit (CORTI_CDI_PROVIDER_QUERY_AUDIT.md §7):

| Category | Purpose | Example |
|---|---|---|
| `specific_clinical_answer` | Clinician confirms a specific clinical fact | "A. 肺炎病原体为肺炎链球菌 (J13)" |
| `free_text_fallback` | Catch-all for unlisted answers | "B. 其他已知病原体, 请在自由文本中说明" |
| `colonization_or_non_pathological` | Lab result does not equal clinical diagnosis | "C. 痰培养结果为定植菌, 不作为病原体" |
| `escape_hatch` | Required by NLQ-005 — always include ≥1 | "D. 无法确定" / "E. 临床不支持" |

Classifier precedence: `escape_hatch > colonization > free_text > specific_clinical_answer`.

The orchestrator uses this to verify escape hatches are present in every generated query (NLQ-005 rule).

## 4. DB Models (5 tables)

### 4.1 `cdi_cases` (20 columns)
Top-level CDI run per encounter.
- PK: `id` (string 64)
- FK: `organization_id → organizations.id`
- Per-run envelope: `run_id`, `trace_id`, `agent_ref`
- 6-section output snapshot: `encounter_summary`, `coding_specificity_checklist`, `risk_flags`, `specialist_trace`
- Lifecycle: `completion_state` (AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED)
- Indexes: org+created, patient_ref, encounter_ref, run_id, completion_state, created_by_user_id

### 4.2 `cdi_documentation_gaps` (18 columns)
Per-gap rows.
- FK: `case_id → cdi_cases.id`
- `gap_type` (one of 8 enum values)
- Evidence binding (red line: chart_evidence_required): `evidence_document_id`, `evidence_quote`, `evidence_char_start`, `evidence_char_end`, `evidence_documented_at`
- Status workflow: OPEN → QUERY_DRAFTED → QUERY_SENT → RESOLVED | WONT_RESOLVE | SUPERSEDED
- Audit: `superseded_by_id`, `resolved_at`
- Indexes: case_id, gap_type, status

### 4.3 `cdi_provider_queries` (29 columns)
Per-query rows with full audit trail.
- FK: `case_id`, `gap_id`
- Content: `topic`, `reason`, `query_text`, `response_options` (JSON array)
- Evidence binding (mirrors gap; query may cite different quote)
- **NLQ gate audit trail**: `nlq_gate_verdict`, `nlq_gate_rules_evaluated`, `nlq_gate_rules_passed`, `nlq_gate_block_reasons`, `nlq_gate_version`
- 9-state lifecycle: DRAFT → PENDING_CDI_REVIEW → APPROVED → SENT_TO_CLINICIAN → VIEWED → RESPONDED → DOCUMENTATION_UPDATED → REVALIDATED → CLOSED (+ CANCELLED, ESCALATED, EXPIRED side states)
- SLA: `sla_due_at`, `sent_at`, `viewed_at`, `responded_at`, `closed_at`
- Reviewer/recipient: `cdi_specialist_user_id`, `cdi_reviewed_at`, `clinician_user_id`
- Indexes: case_id, gap_id, lifecycle_state, clinician_user_id, sla_due_at

### 4.4 `cdi_clinician_responses` (11 columns)
Per-response rows (a query may receive multiple responses over time).
- FK: `query_id`, `case_id`
- Content: `selected_option`, `free_text_response`, `response_metadata`
- `is_latest` flag for fast lookup of current response
- Indexes: query_id, case_id, is_latest, submitted_at

### 4.5 `cdi_document_versions` (12 columns)
Snapshot of chart document before/after clarification (Gate 7 diff view).
- FK: `case_id`, `query_id` (nullable — initial snapshot has no query)
- `document_id` (string), `document_type` (8 enum values)
- `version_label`: initial | post_clarification | revalidated
- `content_hash`, `content_length`, `diff_summary` (JSON)
- Indexes: case_id, query_id, captured_at

## 5. Alembic Migration 011

**Path**: `backend/alembic/versions/011_cdi_models.py`

- Revision: `011`
- Revises: `010` (run_history)
- 5 CREATE TABLE statements
- 18 CREATE INDEX statements
- Full `downgrade()` impl (drops indexes + tables in reverse order)

Migration applied successfully to `data/icoder.db`. All 5 tables present with expected column counts.

## 6. Tests (26 new)

### 6.1 `tests/unit/icoder/cdi/test_domain_gate4.py`

8-way parametrized `test_classify_gap_type_covers_all_8_types` — verifies each GapType has working classifier keywords.

Plus:
- `test_classify_gap_type_defaults_to_diagnostic_specificity` (empty input fallback)
- `test_classify_gap_type_is_case_insensitive`
- `test_classify_gap_type_picks_highest_scoring` (multi-keyword priority)
- 7-way parametrized `test_classify_response_option_covers_4_categories`
- `test_classify_response_option_picks_escape_hatch_first` (NLQ-005 reliability)
- `test_response_option_dataclass_defaults`
- `test_response_option_with_icd_hint`
- `test_documentation_gap_includes_gap_type_field`
- `test_documentation_gap_accepts_all_8_gap_types`
- `test_cdi_db_models_import_cleanly` (5 models + table names)
- `test_cdi_models_have_required_indexes`
- `test_provider_query_model_includes_full_nlq_gate_audit_trail`

### 6.2 Test results

```
======================== 55 passed, 1 warning in 1.85s ========================
```

All 55 tests pass (29 from Gate 3 + 26 from Gate 4). 0 regressions.

## 7. Verification

- ✅ 5 DB tables created via alembic 011
- ✅ 8 GapType classifier covers all 8 PDF §6.2 types
- ✅ 4 ResponseOptionCategory classifier covers all 4 categories
- ✅ Escape hatch detection reliable (NLQ-005 support)
- ✅ All 5 DB models import cleanly
- ✅ ProviderQueryModel stores full NLQ gate audit trail
- ✅ alembic upgrade head reaches 011 (head)
- ✅ Migration reversible (full downgrade path)

## 8. What is NOT in Gate 4 (deferred)

- **Gate 5**: Provider Query lifecycle state machine — DB transitions on DRAFT → PENDING_CDI_REVIEW; NLQ gate integration into DB persistence
- **Gate 6**: Real DeepSeek runner for CDI Orchestrator; full capability wiring
- **Gate 7**: Frontend 3-pane workbench; document diff view
- **Gate 8**: SLA tracker cron; clinician notifications; audit dashboard
- **Gate 9**: REST API at `/api/v1/cdi/runs` + A2A endpoint

## 9. Boundary enforcement audit

| Boundary | Gate 4 enforcement |
|---|---|
| CDI ≠ medical-coding | `cdi-core-agent` permission preset BLOCKS `assign_diagnosis_code`, `finalize_primary_diagnosis` (Gate 3 pack) |
| CDI ≠ discharge-summary-structuring | Discharge structuring has its own agent pack; CDI's `discharge-summary-structuring` is referenced as an upstream SPECIALIZED agent that prepares chart context |
| CDI ≠ note-completeness | Note-completeness has its own agent pack; CDI focuses on clinical specificity, not formal completeness |
| documentation-gap ≠ top-level agent | Pack deprecated in Gate 3; in Gate 4 it becomes a `gap_type` classifier output within CDI |

## 10. Next: Gate 5 — Provider Query data model + non-leading gate wiring

PDF §7 Gate 5 — provider query state machine integration:
- Service layer (`app/services/cdi_query_lifecycle.py`) that drives DB transitions
- NLQ gate runs on every DRAFT query before it can transition to PENDING_CDI_REVIEW
- Audit event emission per state transition
- Tests for invalid transitions (e.g. DRAFT → SENT_TO_CLINICIAN must be blocked)

Commit: `feat(track-d5): add non-leading query compliance gate`
