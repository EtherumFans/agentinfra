# A1C — Evidence Index

**Phase**: A1C
**Date**: 2026-07-25
**Total evidence files**: 61 (excludes this SHA256SUMS manifest per A1B-AE-RV IC-5 lesson)

---

## §1 A1C.0 — Entry Audit & Charter (5 files)

| File | Purpose |
|------|---------|
| docs/phase-a1c/A1C_CHARTER.md | v1.0 Charter (frozen) |
| docs/phase-a1c/A1C_ENTRY_AUDIT.md | Entry audit worktree/branch/HEAD state |
| reports/phase-a1c/A1C_BASELINE_STATE.json | Baseline 5-tuple state |
| reports/phase-a1c/A1C_ACCEPTANCE_MATRIX.csv | 21-gate acceptance matrix |
| reports/phase-a1c/A1C_ENTRY_SHA256SUMS.detached.txt | Entry-time SHA manifest (self-excluded) |
| reports/phase-a1c/A1B_AE_RV_CLOSEOUT_CONSISTENCY_REPORT.md | RV consistency IC-1..IC-5 resolution |

## §2 A1C.1 — Baseline Failure Cleanup & CI Signal (9 files)

| File | Purpose |
|------|---------|
| BASELINE_FAILURE_LEDGER.csv | 88 failures triaged |
| BASELINE_FAILURES_RAW.csv | Raw pytest collection |
| BASELINE_FAILURE_ROOT_CAUSE_REPORT.md | Root-cause analysis |
| CI_GATE_POLICY.md | CI gate definition |
| CI_TEST_COLLECTION_DIFF.json | Test collection drift |
| CLASSIFICATION_SUMMARY.json | Classification stats |
| DEV_DB_ISOLATION_REPORT.md | Dev DB isolation proof |
| ESLINT_INTRODUCTION_REPORT.md | ESLint blocker report |
| (Migration 027 + 028 .py) | Schema drift fix |

## §3 A1C.2 — PostgreSQL Production Migration (5 files)

| File | Purpose |
|------|---------|
| docker-compose.a1c-postgres.yml | Pilot PG 16 compose |
| POSTGRES_MIGRATION_MATRIX.csv | 8 migration scenarios × parity matrix |
| POSTGRES_MIGRATION_RESULTS.json | SQLite parity PASS / PG DEFERRED |
| POSTGRES_CONSTRAINT_REPORT.md | PG constraint spec |
| POSTGRES_RECOVERY_REPORT.md | S16 interrupted-recovery pattern proof |
| SUMMARY.md | Subgate verdict + state delta |

## §4 A1C.3 — HIS/EMR Integration Contract (10 files)

| File | Purpose |
|------|---------|
| HIS_EMR_INTEGRATION_CONTRACT.md | 17-section contract |
| PATIENT_CONTEXT_SCHEMA.json | Patient context payload schema |
| DOCUMENT_INGESTION_SCHEMA.json | Document ingestion schema |
| RESULT_CALLBACK_SCHEMA.json | Webhook callback schema (PHI-excluded) |
| HIS_EMR_SCENARIO_MATRIX.csv | 16 scenarios × result |
| HIS_EMR_SIMULATOR/ (5 files) | Python simulator package |
| SUMMARY.md | Subgate verdict |

## §5 A1C.4 — Identity, SSO, Authorization (6 files)

| File | Purpose |
|------|---------|
| IDENTITY_AND_AUTHORIZATION_MODEL.md | 7 principals × RBAC + ABAC |
| ROLE_PERMISSION_MATRIX.csv | 8 roles × 28 permissions |
| CROSS_TENANT_ATTACK_MATRIX.csv | 15 attack vectors × defense |
| SSO_INTEGRATION_TEST_RESULTS.json | 16 SSO scenarios (DESIGN) |
| AUTH_AUDIT_REPORT.md | 18 mandatory audit events |
| SUMMARY.md | Subgate verdict |

## §6 A1C.5 — DeepSeek + KMS (6 files)

| File | Purpose |
|------|---------|
| KMS_INTEGRATION_REPORT.md | CredentialVault abstraction + KMS adapter DESIGN |
| SECRET_LEAK_SCAN_RESULTS.json | 8 scan paths (6 PASS_NO_LEAK + 2 BY_DESIGN) |
| DEEPSEEK_FAILURE_MODE_MATRIX.csv | 17 failure modes |
| DEEPSEEK_LIVE_TEST_RESULTS.json | 17 scenarios (3 prior-PASS + 13 DESIGN + 1 infra) |
| AI_DISABLED_MODE_REPORT.md | 6/6 PDF §九 behaviors verified |
| SUMMARY.md | Subgate verdict |

## §7 A1C.6 — PHI Boundary, Redaction, Residency, Audit (7 files)

| File | Purpose |
|------|---------|
| PHI_DATA_FLOW_DIAGRAM.md | 13-node data flow + PHI matrix |
| DATA_CLASSIFICATION_MATRIX.csv | 9 categories |
| DATA_RESIDENCY_MATRIX.csv | 18 fields × region rules |
| REDACTION_TEST_RESULTS.json | 11 surfaces (4 PASS_BY_DESIGN + 2 PRIOR + 3 DESIGN_STATIC + 1 PARTIAL + 1 DEFERRED) |
| AUDIT_EVENT_SCHEMA.json | 12 mandatory fields × JSON Schema 2020-12 |
| AUDIT_COMPLETENESS_REPORT.md | 7/12 PASS + 3/12 PARTIAL + 2/12 DESIGN |
| SUMMARY.md | Subgate verdict |

## §8 A1C.7 — Deployment, Observability, Failure Recovery, Rollback (6 files)

| File | Purpose |
|------|---------|
| PILOT_DEPLOYMENT_ARCHITECTURE.md | 3-tier cloud topology + 9 components |
| DEPLOYMENT_RUNBOOK.md | 10-check pre-flight + 8-step provision |
| OBSERVABILITY_SPEC.md | 4-pillar + 14 metrics + 5 dashboards + 10 alerts |
| FAILURE_INJECTION_RESULTS.json | 17 scenarios (12 PASS/DESIGN_VERIFIED) |
| ROLLBACK_DRILL_REPORT.md | 5 scenarios static walk-through |
| SUMMARY.md | Subgate verdict |

## §9 A1C.8 — Browser Pilot Journeys (4 files)

| File | Purpose |
|------|---------|
| PILOT_JOURNEY_MATRIX.csv | 20 journeys × 9 columns (PDF ≥15) |
| JOURNEY_EVIDENCE_TEMPLATE.md | 9-piece evidence bundle schema |
| REPLAY_PLAN.md | RV.5 provenance + Pilot runner skeleton |
| SUMMARY.md | Subgate verdict |

## §10 A1C.9 — Final Verdict & Runbooks (8 files)

| File | Purpose |
|------|---------|
| A1C_FINAL_VERDICT.md | Final verdict + 21-gate tally |
| A1C_FINAL_STATE.json | Final state 5-tuple + subgate verdicts |
| A1C_FINAL_COMMIT_MANIFEST.json | A1C.0..A1C.9 commit stack |
| A1C_EVIDENCE_SHA256SUMS.detached.txt | Detached SHA manifest (61 files) |
| A1C_PILOT_READINESS_MATRIX.csv | 21-gate × evidence × blockers |
| A1C_OPEN_BLOCKERS.csv | 12 open blockers × severity × resolution |
| RUNBOOK_01_PILOT_DEPLOYMENT.md | Step-by-step deploy |
| RUNBOOK_02_PILOT_OPERATIONS.md | Daily / weekly / monthly ops |
| RUNBOOK_03_INCIDENT_RESPONSE.md | P0/P1/P2/P3 incident response |

## §11 Aggregate counts

| Subgate | Files |
|---------|-------|
| A1C.0 | 5 |
| A1C.1 | 9 |
| A1C.2 | 5 (+1 SUMMARY) |
| A1C.3 | 10 |
| A1C.4 | 6 |
| A1C.5 | 6 |
| A1C.6 | 7 |
| A1C.7 | 6 |
| A1C.8 | 4 |
| A1C.9 | 9 (incl. SHA manifest) |
| **Total** | **61** |

## §12 SHA-256 manifest integrity

```
Manifest file: reports/phase-a1c/A1C.9/A1C_EVIDENCE_SHA256SUMS.detached.txt
Total entries: 61
Self-referential: NO (per A1B-AE-RV IC-5 lesson)
Manifest hash (computed post-commit): NOT included in manifest itself
```

To verify:
```bash
cd E:/Corti4C
sha256sum -c reports/phase-a1c/A1C.9/A1C_EVIDENCE_SHA256SUMS.detached.txt
```

Expected: 61/61 OK.

## §13 Provenance cross-references

A1C references but does NOT include evidence from:
- `reports/phase-a1b/agent-expert-reverification/evidence/` — RV.5 30/30 prior PASS journeys
- `reports/phase7/` — Phase 7 13/13 gates
- `reports/phase-a1a/` — A1A Gate 0..Gate 4R-I
- `E:/iCoDerA/` — iCoDer asset library (ICD dictionaries, BGE-M3 model, FAISS index)

These are external to A1C and tracked in their respective phase reports.
