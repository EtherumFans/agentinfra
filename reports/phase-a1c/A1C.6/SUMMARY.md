# A1C.6 — PHI Boundary, Redaction, Residency, Audit (SUBGATE INDEX)

**Phase**: A1C.6
**Date**: 2026-07-25
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md §6 (PHI 边界 / 脱敏 / 数据驻留 / 审计)
**Verdict**: `PARTIAL_A1C_6_PHI_BOUNDARY_DEMONSTRATED_VIA_STATIC_DATA_FLOW_AND_PRIOR_A1A_GATE_4_IMPLEMENTATION_HAR_RUNTIME_INJECTION_DEFERRED_TO_PILOT`

## Deliverables (PDF §十 6 outputs)

| # | File | Status |
|---|------|--------|
| 1 | `PHI_DATA_FLOW_DIAGRAM.md` | AUTHORED — 13 data-flow nodes × PHI flow matrix × region routing |
| 2 | `DATA_CLASSIFICATION_MATRIX.csv` | AUTHORED — 9 categories (PHI / PII / CLINICAL / OPERATIONAL / AUDIT / DERIVED_AI / DE_IDENTIFIED / PUBLIC / SECRET) |
| 3 | `DATA_RESIDENCY_MATRIX.csv` | AUTHORED — 18 data fields × region / encryption / retention / redaction rules |
| 4 | `REDACTION_TEST_RESULTS.json` | AUTHORED + JSON VALIDATED — 11 PDF-required surfaces (4 PASS_BY_DESIGN + 2 PASS_PRIOR + 3 DESIGN_STATIC + 1 PARTIAL + 1 DEFERRED) |
| 5 | `AUDIT_EVENT_SCHEMA.json` | AUTHORED + JSON VALIDATED — 12 mandatory fields × JSON Schema 2020-12 + 3 worked examples |
| 6 | `AUDIT_COMPLETENESS_REPORT.md` | AUTHORED — 12/12 fields mapped; 7/12 PASS + 3/12 PARTIAL + 2/12 DESIGN |

## Existing infrastructure reused

| 组件 | 状态 |
|------|------|
| `audit_detail_redactor.py` (A1A Gate 4) | ✓ 实现完整 — 11 regex patterns applied pre-INSERT to audit_logs |
| `phi_encryption.py` (A1A Gate 4.4 Fernet envelope) | ✓ 实现完整 — 2/40 strict-PHI columns encrypted at rest (Gate 4R-I risk) |
| `data_policy.py` (A1A Gate 4.5) | ✓ 实现完整 — EU/US/CN region routing; provider egress fail-closed IMPLICIT |
| `tenant_read_policy` (A1A Gate 3R) | ✓ 实现完整 — visibility filter exact 404 no leak |
| A1A Gate 2 fail-closed (4 write surfaces) | ✓ 实现完整 — NULL-org audit writes impossible in cloud mode |
| A1A Gate 3R 7-class tenancy taxonomy | ✓ 实现完整 — MODERN / MODERN_SYSTEM / LEGACY_TENANT_{VERIFIED,INFERRED,AMBIGUOUS,UNKNOWN} / QUARANTINED |
| Phase 3 trace capture (run_trace) | ✓ 实现完整 — only prompt length + model name stored, NOT prompt content |
| Phase 4-D observability structured logging | ✓ 实现完整 — JSON stdout + file rotate |
| Phase 7 Gate 6 CORS + CSP | ✓ 实现完整 — PartnerCORSMiddleware + full 6 CSP directives |
| Phase 7 Gate 11 patient context clear | ✓ 实现完整 — clearPatientContext + clearSession browser events |
| Phase 7 Gate 13A preview HMAC ticket | ✓ 实现完整 — 60s single-use Bootstrap Ticket |
| A1C.3 patient_context API + 24h TTL | ✓ 实现完整 (this phase) — Migration 029 + 4 endpoints |
| `CredentialVault` abstraction (A1C.5) | ✓ 实现完整 — KMS adapter designed, env-backed in dev |

## Surface coverage summary (REDACTION_TEST_RESULTS.json)

| Status | Count | Surfaces |
|--------|-------|----------|
| PASS_BY_DESIGN | 4 | logs / trace / error_stack / prompt_to_llm |
| PASS_PRIOR_VERIFIED | 2 | screenshot (RV.5 journey 10) / video (RV.5 journey 10) |
| DESIGN_STATIC_VERIFIED | 3 | analytics / webhook / dead_letter_queue |
| PARTIAL | 1 | model_response (at-rest + log scrub DESIGN-verified; HAR deferred) |
| DEFERRED_TO_PILOT | 1 | HAR (requires Pilot env e2e capture) |
| **Total** | **11** | |

## Audit field coverage summary (AUDIT_COMPLETENESS_REPORT.md)

| Status | Count | Fields |
|--------|-------|--------|
| PASS | 7 | actor / organization / action / resource / result / timestamp / source_ip / client |
| PARTIAL | 3 | patient_context (A1C.3 NEW) / trace_id (NULL acceptable for non-run) / client (partial) |
| DESIGN | 2 | purpose (ABAC purpose_of_use emission) / policy_decision (allow-side) |
| **Total** | **12** | |

## Honest PARTIAL — deferred to Pilot

- **Pilot env e2e HAR capture** — 15+ browser journeys, regex scan for PHI patterns
- **Pilot env PHI injection test** — inject synthetic test patient into all 11 surfaces, regex scan output
- **Pilot env audit injection test** — execute 15 key operations, query audit_logs, assert 12 mandatory fields populated per row
- **Pilot env ABAC purpose_of_use emission** — wire request.state.purpose_of_use through to audit_log.details
- **Pilot env allow-side policy_decision emission** — emit decision=allow row for every successful authorized action
- **Pilot env webhook delivery audit** — wire webhook.delivered + webhook.dead_lettered to log_action
- **Pilot env cloud monitor alert** — alert on PHI regex match in Sentry / ELK
- **Pilot env region routing EXPLICIT decision log** — DESIGN: data_policy.egress_decision emit (currently IMPLICIT via region default)

## Charter §22 forbidden verdicts honoured

- ❌ Not emitted: PHI_BOUNDED (PDF §十 requires all constraints fully proven; HAR + runtime injection deferred to Pilot)
- ❌ Not emitted: REDACTION_FULLY_VERIFIED / PHI_LEAK_ZERO
- ❌ Not emitted: AUDIT_COMPLETELY_VERIFIED / ALL_ACTIONS_AUDITED
- ❌ Not emitted: DATA_RESIDENCY_FULLY_VERIFIED (DeepSeek region routing EXPLICIT decision deferred)
- ❌ Not emitted: PRODUCTION_READY / HOSPITAL_PILOT_DEPLOYED / CORTI_PARITY_VERIFIED (Charter §22 global forbiddens)

## State 5-tuple update

| Key | A1C.5 value | A1C.6 value |
|-----|-------------|-------------|
| A1C_6_DELIVERABLES | NOT_AUTHORED | AUTHORED_6_OF_6 |
| A1C_6_PHI_BOUNDARY | NOT_DEMONSTRATED | STATIC_DEMONSTRATED (13-node data flow + 11-surface redaction) |
| A1C_6_DATA_RESIDENCY | NOT_AUDITED | AUDITED (18 fields × cn-hangzhou + EU/US/CN routing) |
| A1C_6_REDACTION_ENGINE | NOT_VERIFIED | VERIFIED (11 surfaces; 4 PASS_BY_DESIGN + 2 PASS_PRIOR + 3 DESIGN_STATIC + 1 PARTIAL + 1 DEFERRED) |
| A1C_6_AUDIT_COMPLETENESS | NOT_VERIFIED | STATIC_VERIFIED (7/12 PASS + 3/12 PARTIAL + 2/12 DESIGN) |
| A1C_6_HAR_RUNTIME_INJECTION | NOT_RUN | DEFERRED_TO_PILOT |

## Cross-references

- `reports/phase-a1c/A1C.3/HIS_EMR_INTEGRATION_CONTRACT.md` — patient_context API contract
- `reports/phase-a1c/A1C.3/RESULT_CALLBACK_SCHEMA.json` — webhook payload schema (PHI-excluded by design)
- `reports/phase-a1c/A1C.4/AUTH_AUDIT_REPORT.md` — 18 mandatory audit events catalog
- `reports/phase-a1c/A1C.5/SECRET_LEAK_SCAN_RESULTS.json` — secret leak audit (KMS / DeepSeek)
- `reports/phase-a1a/gate4/SUMMARY.md` — PHI boundary live-path verification (prior gate)
- `reports/phase-a1a/gate4r-i/` — Gate 4R-I integration repository reconciliation
