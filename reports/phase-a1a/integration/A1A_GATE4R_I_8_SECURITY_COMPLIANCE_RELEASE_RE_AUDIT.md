# Phase A1A Gate 4R-I.8 — Security/Compliance Release Re-Audit

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `f614f01` (post Gate 4R-I.4)
**Predecessor**: Gate 4R-I.4 (`f614f01` engineering debt liquidation)
**Successor**: Gate 4R-I.9 (release tier verdicts)

Charter §12 requires re-verifying Gate 4's PHI boundary claims against
current HEAD, auditing all PHI fields per §12.1, and verifying KMS,
tenant-level keys, and provider egress runtime behaviour. This sub-
gate produces the P0/P1/P2 security blockers list.

## §1. Re-verification of Gate 4 PHI boundary claims

Gate 4 (commit 880f49c) asserted:

| Claim | Re-verification @ f614f01 | Status |
|---|---|---|
| Live-path redaction (audit_detail_redactor) | Code intact at `app/services/audit_detail_redactor.py` | PASS |
| PHI at-rest encryption (Fernet envelope) | `app/services/phi_encryption.py` unchanged | PASS |
| Cloud-mode fail-closed (no key = refuse boot) | `app/config.py` lines 90-96 still enforce | PASS |
| Tenant-owned system audit (allowlist) | `app/middleware/audit.py` system_audit allowlist intact | PASS |
| JWT-authoritative tenant_extractor | `app/middleware/tenant_extractor.py` unchanged | PASS |
| Regional residency (region routing) | `icoder_runtime/core/data_policy.py` PROVIDER_REGIONS intact | PASS |
| Browser storage governance | `frontend/src/store/index.ts` persists only ICODER_LOCALSTORAGE_KEYS allowlist | PASS |
| Retention primitives | `app/services/retention.py` intact | PASS |
| Migration 021 (NOT NULL + CHECK constraints) | `alembic/versions/021_*.py` present | PASS |

Gate 4 surface is preserved. **No regression** introduced by the 4R
merge or subsequent integration work.

## §2. PHI at-rest encryption scope (charter §12.1)

### 2.1 Current coverage (2 of 40 strict-PHI columns)

| Encrypted column | Table | Module |
|---|---|---|
| `admission_reason` | `encounters` | `app/api/encounters.py:47` |
| `content` | `documents` | `app/api/encounters.py:61` |

Both via `encrypt_phi()` from `app/services/phi_encryption.py`.

### 2.2 Unencrypted strict-PHI columns (38 fields, charter §12.1 gap)

Scan of clinical tables (`users`, `encounters`, `documents`,
`clinical_evidences`, `coding_reviews`, `coding_review_runs`,
`cdi_cases`, `cdi_documentation_gaps`, `cdi_provider_queries`,
`cdi_clinician_responses`, `cdi_document_versions`, `run_history`):

**Direct patient identifiers (P0)**:
- `users.username`, `users.email`, `users.full_name`
- `encounters.patient_id`
- `cdi_cases.patient_ref`

**Quasi-identifiers / clinical facts (P1)**:
- `documents.content` — **already encrypted**
- `clinical_evidences.text`
- `encounters.existing_diagnosis_codes` (JSON)
- `coding_reviews.primary_diagnosis_*` (6 columns: code, name, confidence, evidence_ids, judgment, reasoning)
- `coding_reviews.main_procedure_name`, `main_procedure_evidence_ids`
- `coding_reviews.secondary_diagnoses`, `diagnosis_analysis`, `reviewer_notes`, `evidence_ranking`
- `coding_review_runs.primary_diagnosis`, `secondary_diagnoses`, `evidence_chain`
- `coding_review_runs.encounter_text`, `encounter_text_redacted`
- `run_history.context_id`, `run_history.input_text`
- `cdi_documentation_gaps.description`, `evidence_quote`, `evidence_document_id`
- `cdi_provider_queries.query_text`, `evidence_quote`
- `cdi_clinician_responses.free_text_response`

**Derivative / low-sensitivity (P2)**:
- `cdi_document_versions.content_hash`, `content_length`
- Various `evidence_char_start/end`, `evidence_documented_at`

**Count**: ~5 P0 + ~25 P1 + ~8 P2 = ~38 unencrypted strict-PHI columns.

### 2.3 Charter §12.3 verdict

```
PHI_AT_REST_ENCRYPTION_SCOPE = PARTIAL
GAP = ~38 columns beyond the 2 already covered
RELEASE_BLOCKER_FOR_GA = YES
RELEASE_BLOCKER_FOR_CONTROLLED_PILOT = YES (quasi-identifiers must be encrypted)
RELEASE_BLOCKER_FOR_MVP = DEPENDS (P0 direct identifiers required)
```

## §3. KMS / tenant-level encryption keys (charter §12.6)

### 3.1 Current key management

`phi_encryption.py` loads the Fernet key from env vars:
- `ICODER_PHI_ENCRYPTION_KEY` (active)
- `ICODER_PHI_ENCRYPTION_KEY_V{N}` (historical, for rotation)
- `ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID` (version counter)

### 3.2 Gaps vs charter §12.6

| Requirement | Status |
|---|---|
| Keys NOT in env vars / source | NOT MET (keys are in env vars by design) |
| KMS / HSM integration | NOT IMPLEMENTED |
| Per-tenant keys | NOT IMPLEMENTED (single global key) |
| Key rotation workflow with audit | HELPERS EXIST (`rotate_encrypted_columns`) but no operator trigger |
| Ciphertext → tenant binding | NOT ENFORCED (any tenant's ciphertext decrypts with global key) |

```
KMS_INTEGRATION = NOT_IMPLEMENTED
PER_TENANT_KEYS = NOT_IMPLEMENTED
RELEASE_BLOCKER_FOR_GA = YES
RELEASE_BLOCKER_FOR_CONTROLLED_PILOT = YES (audit/compliance will require this)
RELEASE_BLOCKER_FOR_MVP = DEPENDS (single-tenant pilot may accept single key)
```

## §4. Provider egress runtime proof (charter §12.8)

### 4.1 Current enforcement

`icoder_runtime/core/data_policy.py:can_use_provider()`:
1. If `allow_external_llm=false` and provider is external → BLOCK
2. If `egress_policy="strict"` and `provider_region != tenant_region` → BLOCK
3. Otherwise → ALLOW

### 4.2 Charter §12.8 requirements

| Requirement | Status |
|---|---|
| Every LLM hot path passes through `can_use_provider` | PARTIAL — LLMGateway calls it, but not all backend routes route through LLMGateway (some bypass to DeepSeek directly) |
| Runtime evidence on every hot path | NOT COLLECTED — no audit emit on provider allow/deny |
| Allow/deny decision auditable | NOT WIRED — `can_use_provider` logs at DEBUG but does not emit `audit_log` rows |

```
PROVIDER_EGRESS_RUNTIME_PROOF = PARTIAL
RELEASE_BLOCKER_FOR_GA = YES
RELEASE_BLOCKER_FOR_CONTROLLED_PILOT = PARTIAL (hot-path coverage needs completion)
RELEASE_BLOCKER_FOR_MVP = NO (MVP scope is single-region CN tenant; no cross-region risk)
```

## §5. Unknown-provider fail-closed (charter §12.9)

### 5.1 Current behaviour

`get_provider_region()` defaults unknown providers to `"us"`. Combined
with `egress_policy="strict"` + tenant region "cn", an unknown
provider WILL be blocked by the region mismatch.

### 5.2 Charter §12.9 verdict

The block is an **implicit side-effect** of region mismatch, not an
**explicit** fail-closed on unknown. Charter §12.9 calls for the
latter.

| Requirement | Status |
|---|---|
| Unknown provider explicitly blocked | NOT MET (implicit via region default) |
| Error message mentions "unknown provider" | NOT MET (message says "region mismatch") |
| Audit row records the block | NOT MET |

```
UNKNOWN_PROVIDER_FAIL_CLOSED = IMPLICIT_NOT_EXPLICIT
RELEASE_BLOCKER_FOR_GA = YES (compliance audits want explicit)
RELEASE_BLOCKER_FOR_CONTROLLED_PILOT = NO (works in practice)
RELEASE_BLOCKER_FOR_MVP = NO
```

## §6. Browser governance (charter §12.11)

Gate 4 §6 verified:
- Frontend persists only allowlisted `ICODER_LOCALSTORAGE_KEYS`
- Zustand `logout` block removed from persisted state
- Preview iframe uses nonce-CSP + sandbox

Re-verification @ f614f01: **unchanged**. PASS.

## §7. Retention enforcement (charter §12.12)

Gate 4.7 primitives:
- `purge_expired_audit_logs` (TTL default 2557 days / 7 years)
- `purge_expired_run_history` (TTL 90 days)
- `purge_expired_run_trace_events` (TTL 90 days)
- `emit_purge_audit` records each purge in audit log

**Not wired to a scheduler**. Operators must invoke manually or wire
their own cron.

```
RETENTION_ENFORCEMENT = PRIMITIVES_ONLY
RELEASE_BLOCKER_FOR_GA = YES (automated purge required)
RELEASE_BLOCKER_FOR_CONTROLLED_PILOT = NO (manual runbook acceptable)
RELEASE_BLOCKER_FOR_MVP = NO
```

## §8. P0/P1 security blockers consolidated

### P0 — release blockers for ANY tier (MVP included)

1. **Direct PHI identifiers unencrypted** (§2.2 P0 list — 5 columns)
   - `users.username`, `users.email`, `users.full_name`
   - `encounters.patient_id`, `cdi_cases.patient_ref`
   - **Fix**: add `encrypt_phi()` wrapping on write paths for these 5 columns
   - **Effort**: ~1 day (follow Gate 4.4 pattern)

### P1 — release blockers for Controlled Pilot

2. **All ~25 P1 quasi-identifier columns unencrypted** (§2.2 P1 list)
3. **KMS / HSM integration missing** (§3.2)
4. **Per-tenant encryption keys missing** (§3.2)
5. **Provider egress hot-path coverage incomplete** (§4.2)
6. **Unknown-provider fail-closed implicit, not explicit** (§5.2)
7. **Provider allow/deny decision not auditable** (§4.2)

### P2 — release blockers for GA

8. **Retention auto-scheduling missing** (§7)
9. **Ciphertext → tenant binding not enforced** (§3.2)
10. **LLM bypass paths (non-LLMGateway) not gated** (§4.2)

## §9. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Modify clinical prompts | NOT DONE ✓ |
| Weaken JWT/encryption/redaction/egress/retention | NOT DONE ✓ |
| Add features beyond audit scope | NOT DONE ✓ |
| Touch master / origin/master | NOT DONE ✓ |
| Push / PR | NOT DONE ✓ |
| Issue PRODUCTION_READY | NOT DONE ✓ |
| Issue FULLY_VERIFIED | NOT DONE ✓ |

## §10. Provisional verdict

```
PASS_A1A_GATE4R_I_8_SECURITY_COMPLIANCE_RE_AUDIT_FILED
PHI_AT_REST_SCOPE = PARTIAL (2 of 40 columns)
KMS_INTEGRATION = NOT_IMPLEMENTED
PER_TENANT_KEYS = NOT_IMPLEMENTED
PROVIDER_EGRESS_RUNTIME_PROOF = PARTIAL
UNKNOWN_PROVIDER_FAIL_CLOSED = IMPLICIT_NOT_EXPLICIT
RETENTION_ENFORCEMENT = PRIMITIVES_ONLY
```

Tier: FILED (not VERIFIED). The re-audit catalogues 10 blockers
spanning P0/P1/P2. Gate 4 surface is preserved; the gaps are pre-
existing scope deficits, NOT regressions.

## §11. Next

Gate 4R-I.9 — release tier verdicts:

- Aggregate §8 P0/P1/P2 against MVP/Controlled Pilot/GA criteria
- Emit ICODER_MVP_READINESS / ICODER_CONTROLLED_PILOT_READINESS /
  ICODER_GA_READINESS states
- Output the single consolidated release-tier verdict
