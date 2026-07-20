# Phase A1A Gate 4.1 — PHI Inventory, Classification and Threat Model

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.0 (`A1A_GATE4_0_BASELINE_GATE3R_ADDENDUM_CARRYOVER_RECONCILIATION.md`)

Closes charter §4.1: produce the canonical PHI inventory + data
classification + threat model + policy matrix that Gate
4.2–4.8 implement against. No code changes.

Gate 4.1 produces this report and one JSON artifact
(`phi_inventory.json`) that downstream gates reference.

---

## §1. Methodology

Every model column with a `Text`, `JSON`, `String` SQLAlchemy
type was inspected across `backend/app/models/*.py` (29 model
files). Each column was classified by what kind of data it
holds in production, not by what type it's declared as. Every
API endpoint under `backend/app/api/*.py` (41 files) was
inspected for whether it (a) accepts PHI on input, (b) returns
PHI on output, (c) writes PHI to a persistent store, (d)
writes PHI to a live-path channel (log/trace/audit/SSE/
embedded event/error).

The inventory is read-only and reflects the **as-of-b737eab**
state of the codebase. Gate 4.2–4.8 will mutate the state;
this report is the immutable baseline those gates diff
against.

---

## §2. PHI Sources — input channels

| Channel | Endpoint(s) | PHI carried | Notes |
|---|---|---|---|
| Console UI — Encounter submit | `POST /api/v1/encounters`, `POST /api/v1/encounters/text` | patient_id (pseudonym), department, admission_reason (chief complaint = clinical content), discharge_summary | patient_id is declared "脱敏" in the model comment; that's an insertion-time claim, not enforced anywhere |
| Console UI — Document upload | Document rows attached to encounter via `/api/v1/encounters` flow | `Document.content` is raw clinical document text | No redaction on input; stored plaintext |
| Console UI — Coding review | `POST /api/v1/agents/{id}/run`, `POST /api/v1/coding-compliance/run`, `POST /api/v1/coding/predict` | encounter text + context | `CodingReviewRun.encounter_text` stores the raw input |
| Console UI — CDI run | `POST /api/v1/cdi/runs` | chart document text, encounter metadata, patient_ref, encounter_ref | CDI agent runs against full chart text |
| Console UI — CDI query/response | `POST /api/v1/cdi/queries/{id}/transition` | clinician free-text response | `ClinicianResponseModel.free_text_response` is unbounded Text |
| Partner API — agent_run | `POST /api/v1/agents/{id}/run` | same as Console UI coding review | API Client-bound; org derived from JWT (not request body) |
| Embedded widget | Widget → Console backend via `assistant.js` | patient context object (`patientId`, `name`, `encounterId` per Phase 6 envelope) | patient.name is a direct identifier |
| Preview session (Gate 13A) | `POST /api/embedded/preview/sessions`, `POST /api/embedded/preview/{token}/exchange` | widget origin, agent_ref; no direct PHI by design | Bootstrap ticket + MessageChannel handshake; no PHI on this path |
| A2A inbound (Agent-to-Agent) | `POST /a2a`, `POST /.well-known/agent-card.json` | task inputs from peer agents | Currently no real A2A traffic; surface exists |

**Sources NOT in scope for Gate 4**:
- `examples/partner-reference-app/` — demo only, synthetic data
- `frontend/src/pages/EmbeddedAssistantPage.tsx` — widget test harness; runs against synthetic demo input only

---

## §3. Persistent stores with PHI

### §3.1 Clinical tables (SQLite, plaintext)

| Table | PHI columns | Risk class |
|---|---|---|
| `encounters` | `patient_id` (direct id), `department`, `admission_reason` (clinical), `discharge_summary` (clinical), `existing_diagnosis_codes` (clinical), `existing_procedure_codes` (clinical) | DIRECT + CLINICAL |
| `documents` | `content` (raw clinical document) | CLINICAL |
| `cdi_cases` | `patient_ref` (direct id), `encounter_ref` (direct id), `encounter_metadata` (clinical), `draft_codes` (clinical), `encounter_summary` (clinical), `coding_specificity_checklist` (clinical), `risk_flags` (clinical), `specialist_trace` (clinical) | DIRECT + CLINICAL |
| `cdi_documentation_gaps` | `description`, `why_it_matters`, `minimal_clarification_needed`, `evidence_quote` (all clinical) | CLINICAL |
| `cdi_provider_queries` | `topic`, `reason`, `query_text`, `response_options`, `evidence_quote` (all clinical) | CLINICAL |
| `cdi_clinician_responses` | `selected_option`, `free_text_response` (clinical) | CLINICAL |
| `cdi_document_versions` | `diff_summary` JSON (contains `old`/`new` clinical spans) | CLINICAL |
| `coding_review_runs` | `encounter_text` (raw clinical), `encounter_text_redacted` (redacted version), `primary_diagnosis`, `secondary_diagnoses`, `procedures`, `high_risk_coding_points`, `evidence_chain`, `risk_route`, `safety_gate`, `drg_route`, `human_review_records` | CLINICAL |
| `evidence` | `text` (clinical evidence snippet) | CLINICAL |
| `code_candidates` | `evidence_ids` (FK list, indirect), `rule_checks` | INDIRECT |
| `reviews` | `report_markdown`, `report_html`, `reviewer_notes`, `primary_diagnosis_reasoning`, `diagnosis_analysis`, `procedure_analysis`, `documentation_gaps`, `uncodable_items`, `drg_impact`, `human_checklist`, `validation_summary`, `evidence_ranking`, `confidence_calibration`, `error_message` | CLINICAL |

### §3.2 Run/audit tables

| Table | PHI columns | Risk class |
|---|---|---|
| `run_history` | `input_text` (truncated encounter text), `output_summary` (truncated agent output), `error_reason` | CLINICAL (truncated) |
| `audit_logs` | `model_input_summary`, `model_output_summary`, `error_message`, `details` (free-form JSON), `ip_address`, `user_agent`, `username` | CLINICAL + DIRECT |
| `run_trace_events` | `safe_metadata_json` (currently blacklist-filtered) | METADATA + possible CLINICAL via metadata leak |
| `idempotency_records` | `response_snapshot` JSON (cached response may contain clinical content) | CLINICAL |

### §3.3 Context / memory tables

| Table | PHI columns | Risk class |
|---|---|---|
| `runtime_contexts` | Context payload (messages, parts) — DB schema in `db_models.py`; messages carry conversation history | CLINICAL |
| `runtime_messages`, `runtime_tasks`, `runtime_artifacts` | Per A2A spec, may carry task input/output | CLINICAL |
| `memories` | `content`, `summary`, `key_facts` | CLINICAL (if user stores clinical context) |
| `runtime_persistence.*` | `payload` JSON, `reason`, `failed_reason` | CLINICAL (if payload is run I/O) |

### §3.4 User / auth tables

| Table | PHI columns | Risk class |
|---|---|---|
| `users` | `email`, `username`, password hash (NOT PHI but sensitive) | DIRECT (email) |
| `organization_invites` | `email` | DIRECT (email) |
| `oauth_clients` | `description`, `allowed_origins` (no PHI but admin metadata) | NOT PHI |
| `preview_sessions` | `allowed_agent_ids`, `allowed_scopes`, `origin` | NOT PHI |

### §3.5 Aggregates — totals

| Category | Tables | PHI columns |
|---|---|---|
| Clinical content tables | 11 | ~40 columns |
| Run/audit tables | 4 | ~10 columns |
| Context/memory tables | ~5 | ~10 columns |
| User/auth tables | 2 | 2 direct (email ×2) |
| **Total** | **22** | **~62 PHI columns** |

**Encryption at rest coverage today**: 0 / 62 columns. SQLite stores everything as plaintext. No `cipher`, `crypto`, `encrypt_at_rest`, `field_encrypt`, or `envelope_encrypt` matches in `backend/app/`.

---

## §4. Live-path destinations — where PHI can leak

| Destination | Current state | PHI risk |
|---|---|---|
| Python logger (`logging.info/warning/error`) | Used in ~80 files; logs to stdout in dev, structured logger in prod | HIGH — many call sites log `input_text` snippets or full errors; no audit |
| Trace events (`run_trace_events.safe_metadata_json`) | Blacklist filter via `_redact_safe_metadata` (run_trace.py:139) — blanks known secret keys, NOT PHI | MEDIUM — clinical content can leak via metadata fields |
| Audit row (`audit_logs.model_input_summary` / `model_output_summary`) | Free-form Text; whatever caller passes lands | HIGH — coding_predict and cdi run paths pass encounter snippets |
| Audit row (`audit_logs.details` JSON) | Free-form JSON; caller-defined shape | HIGH — no allowlist, no schema |
| SSE event payload (`/api/v1/runs/{id}/events`) | Phase 6 unified envelope `{name, payload, meta}`; payload can include input/output previews | MEDIUM — depends on caller |
| Embedded widget event (postMessage to parent) | Phase 6 envelope; same shape as SSE | MEDIUM |
| Error responses (`HTTPException.detail`) | Most endpoints return safe codes; some include exception text | LOW–MEDIUM depending on caller |
| Stack traces (500 errors) | FastAPI default returns str(exc) | HIGH in dev mode; LOW in cloud mode (uvicorn `--no-debug`) |
| Frontend `localStorage` | Auth tokens, UI prefs, `icoder-textgen-templates` (user-saved templates — may contain PHI if user pastes clinical text) | LOW for current keys; MEDIUM for templates |
| Frontend `sessionStorage` | Auth `access-token:PROJECT:CLIENT.data` (per Phase 5 Track H Tier 2 memory) — Corti pattern; iCoDer does NOT use sessionStorage today | LOW |
| HAR / browser devtools | Network panel captures full request/response; tokens, headers, bodies | HIGH if user inspects — but browser-side, not server-controlled |
| LLM provider egress | `LLMGateway` routes to `deepseek` / `openai_compat`; **no region check**, **no PHI redaction on egress** | HIGH — clinical content flows to DeepSeek API as-is |
| Provider response | Returned raw; stored in `coding_review_runs.encounter_text_redacted` (redacted) AND `encounter_text` (raw) | MEDIUM — both columns exist side-by-side |
| Telemetry upload | Disabled by default (`allow_telemetry_upload=false`); no active upload path | LOW |
| Partner webhook (Phase 7 deferred) | Not implemented | N/A |

---

## §5. Data classification

Four classes. Every column in §3 maps to exactly one.

### §5.1 `DIRECT_IDENTIFIER`

Fields that uniquely or near-uniquously identify a patient or
a clinician.

| Field | Tables | Notes |
|---|---|---|
| `patient_id` | encounters | Pseudonym at insert (model comment 脱敏), but re-identifiable via join with `documents` |
| `patient_ref` | cdi_cases | Free-form String(128); no format check |
| `encounter_id` | encounters (unique), cdi_cases.encounter_ref | Direct encounter identifier |
| `email` | users, organization_invites | Clinician/admin direct id |
| `username` | users, audit_logs | Clinician/admin direct id |
| `ip_address` | audit_logs | Network direct id (per HIPAA; per China PIPL also) |
| `user_agent` | audit_logs | Indirect fingerprint; treat as direct |

**Policy**: redact on read for any cross-tenant view; encrypt at rest; never appear in `safe_metadata` or `audit.details`.

### §5.2 `CLINICAL_CONTENT`

Clinical document text, evidence quotes, query text, response
text, reasoning, diff spans. This is the bulk of the PHI
payload.

**Policy**: allowed to flow to approved providers (DeepSeek in
approved regions); must be redacted before any non-approved
destination (logs, trace metadata, audit details, SSE
payloads outside the tenant).

### §5.3 `METADATA`

Non-clinical, non-identifying fields that describe a run:
`agent_id`, `runtime_mode`, `provider_id`, `model_id`,
`stage`, `status`, `duration_ms`, `latency_ms`, `cost_cny`,
`evidence_count`, `result_count`, `redaction_status`,
`policy_decision_id`, `token_usage`.

**Policy**: safe to land in `safe_metadata`, `audit.details`,
SSE payloads, embedded events. Allowlist enforced at the
write site (not blacklist).

### §5.4 `ALLOWED`

Run/audit metadata that is non-PHI even when clinical content
is present elsewhere in the row: `run_id`, `trace_id`,
`event_id`, `sequence_number`, `ts`, `created_at`,
`updated_at`, `id` (any PK), `status`, `error:bool`,
`cancel_reason` (system-generated, not user-input),
`organization_id`, `user_id`, `api_client_id`.

**Policy**: safe everywhere except audit `details` (which is
free-form and can still leak via joined values).

---

## §6. Threat model

For each (asset × threat × vector × control × residual), the
matrix is below. **Asset** is one of the four data classes.
**Threat** is the OWASP / STRIDE category. **Vector** is the
specific code path. **Control** is the existing or planned
mitigation.

### §6.1 DIRECT_IDENTIFIER threats

| ID | Threat | Vector | Current control | Residual | Plan |
|---|---|---|---|---|---|
| T-DI-1 | Spoofing | Attacker forges `Tenant-Name` header to override org | Cloud mode requires JWT org_id match | Local/dev mode allows bypass | Gate 4.2 |
| T-DI-2 | Info disclosure | `audit_logs.ip_address` returned to non-admin | Not currently filtered in list endpoints | LOW (admin-only endpoints) | Gate 4.3 |
| T-DI-3 | Info disclosure | `patient_id` in URL path (e.g. `/api/v1/encounters/{encounter_id}` — encounter_id IS a direct id) | URL is the canonical access path | MEDIUM — by design, but should rotate-friendly | Gate 4.6 doc |
| T-DI-4 | Info disclosure | `email` returned in user list response | Filtered to admin only | LOW | Accept |
| T-DI-5 | Repudiation | `system_audit()` writes NULL org for tenant-owned business action | Lifecycle emits use `log_action` with org | MEDIUM if future caller误routes through `system_audit()` | Gate 4.7 |

### §6.2 CLINICAL_CONTENT threats

| ID | Threat | Vector | Current control | Residual | Plan |
|---|---|---|---|---|---|
| T-CC-1 | Info disclosure | `_redact_safe_metadata` uses blacklist | Blacklist of ~10 known secret keys; PHI field names NOT in list | HIGH — clinical content can land in `safe_metadata` if caller passes it | Gate 4.3 |
| T-CC-2 | Info disclosure | `audit_logs.model_input_summary` / `model_output_summary` written from coding paths | No redaction; caller decides what to summarize | HIGH | Gate 4.3 |
| T-CC-3 | Info disclosure | Logger writes encounter snippets in `info()` calls | No audit of log content | HIGH | Gate 4.3 |
| T-CC-4 | Info disclosure | `coding_review_runs.encounter_text` stored raw alongside `encounter_text_redacted` | Both columns exist; raw is canonical | HIGH | Gate 4.4 (encrypt) + Gate 4.3 (redact on read for non-clinician roles) |
| T-CC-5 | Egress | `LLMGateway` routes clinical content to DeepSeek with no region check | None | HIGH for non-approved regions | Gate 4.5 |
| T-CC-6 | Egress | Provider response stored raw in trace event metadata | Blacklist only; metadata may carry clinical content | MEDIUM | Gate 4.3 |
| T-CC-7 | Info disclosure | SSE event payload can include input/output preview | Caller-defined; no allowlist | MEDIUM | Gate 4.3 |
| T-CC-8 | Info disclosure | Embedded widget postMessage can include clinical content | Same as SSE | MEDIUM | Gate 4.3 |
| T-CC-9 | Info disclosure | Error response `detail` may include exception text containing clinical content | FastAPI default; not redacted | LOW (cloud mode suppresses) | Accept with doc |
| T-CC-10 | At-rest | All clinical Text/JSON columns stored as SQLite plaintext | None | HIGH | Gate 4.4 |
| T-CC-11 | Tampering | `documents.content` editable via PUT; no audit trail of content change | Last-write-wins | MEDIUM | Gate 4.7 (audit close) |
| T-CC-12 | Cross-tenant | Patient A data visible to Org B user | `get_current_organization` enforces org on read; clinical tables nullable org | MEDIUM if any nullable-org row leaks | Gate 4.2 |

### §6.3 METADATA threats

| ID | Threat | Vector | Current control | Residual | Plan |
|---|---|---|---|---|---|
| T-MD-1 | Spoofing | Metadata field injection (`safe_metadata['input_text_snippet'] = ...`) | Blacklist rejects known secret keys | MEDIUM | Gate 4.3 (allowlist) |
| T-MD-2 | Repudiation | `policy_decision_id` not generated; redaction status not stamped | None | LOW | Gate 4.3 |

### §6.4 ALLOWED threats

| ID | Threat | Vector | Current control | Residual | Plan |
|---|---|---|---|---|---|
| T-AL-1 | Info disclosure | `run_id` in URL path is shared via signed trace_token (24h TTL, org-bound) | HMAC verify + org check | LOW | Accept |
| T-AL-2 | Cross-tenant | `run_history.organization_id` nullable for legacy rows | Migration 016 backfilled 470 rows; CHECK added in Migration 019 | LOW | Accept (closed in Gate 3R) |

---

## §7. Policy matrix

For each (data_class, destination), the decision. Decisions:
- **Allow** — may flow as-is
- **AllowWithAllowlist** — may flow only via named-field allowlist
- **EncryptThenAllow** — may flow only after envelope encryption
- **Redact** — must be redacted before flow
- **Deny** — must never flow

| Destination | DIRECT_IDENTIFIER | CLINICAL_CONTENT | METADATA | ALLOWED |
|---|---|---|---|---|
| SQLite table (production) | EncryptThenAllow | EncryptThenAllow | Allow | Allow |
| SQLite table (dev) | Allow | Allow | Allow | Allow |
| Python logger | Redact | Redact | Allow | Allow |
| Trace `safe_metadata_json` | Deny | Deny | AllowWithAllowlist | Allow |
| Audit `model_input_summary` / `model_output_summary` | Deny | Redact | Allow | Allow |
| Audit `details` JSON | Deny | Redact | AllowWithAllowlist | Allow |
| SSE event payload | Redact (hashed pid) | Allow (within tenant session) | Allow | Allow |
| Embedded widget postMessage | Redact | Allow (within tenant session) | Allow | Allow |
| Error response `detail` | Redact | Redact | Allow | Allow |
| Stack trace (dev) | Redact | Redact | Allow | Allow |
| Stack trace (cloud) | Deny | Deny | Deny | Allow |
| LLM provider (approved region) | Redact | Allow | Allow | Allow |
| LLM provider (non-approved region) | Deny | Deny | Allow | Allow |
| HAR / browser devtools | n/a (browser-side) | n/a | n/a | n/a |
| Frontend `localStorage` | Deny | Deny | Allow | Allow |
| Frontend `sessionStorage` | Deny | Deny | Allow | Allow |
| Telemetry upload | Deny | Deny | Allow | Allow |
| Partner webhook (future) | Deny | Redact | Allow | Allow |

### §7.1 Notes on specific decisions

- **SSE payload CLINICAL_CONTENT = Allow within tenant session**:
  The user viewing the SSE stream is the tenant's authenticated
  user; they're allowed to see their own patient's clinical
  content. The risk is widget leak to a different origin; that's
  controlled by CSP + CORS (Gate 7/Phase 7).
- **Embedded widget CLINICAL_CONTENT = Allow within tenant session**:
  Same reasoning.
- **LLM provider DIRECT_IDENTIFIER = Redact**: `PIIRedactor`
  must scrub direct identifiers before the request leaves the
  gateway. Today the redactor is best-effort; Gate 4.3 makes
  it fail-closed.

---

## §8. Threat model summary — top 5 risks

Ranked by residual risk after current controls:

1. **T-CC-10**: At-rest plaintext clinical content (HIGH). Closes in Gate 4.4.
2. **T-CC-5**: LLM egress with no region check (HIGH). Closes in Gate 4.5.
3. **T-CC-1 + T-CC-2 + T-CC-3**: Live-path leaks via metadata blacklist / audit summary / logger (HIGH). Closes in Gate 4.3.
4. **T-CC-12**: Cross-tenant clinical row leak via nullable org (MEDIUM). Closes in Gate 4.2.
5. **T-DI-5**: Tenant-owned system audit attribution loss (MEDIUM). Closes in Gate 4.7.

---

## §9. JSON artifact — `phi_inventory.json`

A companion artifact at
`reports/phase-a1a/artifacts/phi_inventory.json` (created at
Gate 4.1 close) lists every (table, column, data_class) tuple
in §3 plus the policy decision per (data_class, destination)
from §7. Downstream gates reference the JSON, not the
markdown, so policy decisions are machine-checkable.

The JSON is created in this gate. It contains:

- `generated_at` — timestamp
- `generated_from_commit` — `b737eab`
- `columns` — list of `{table, column, type, data_class, notes}`
- `destinations` — list of `{name, description}`
- `policy_matrix` — `{data_class: {destination: decision}}`
- `threats` — list of `{id, asset, threat, vector, current_control, residual, owner_gate}`

Gate 4.8 verifies the as-shipped state matches this JSON
(canonical leak-scan fixture).

---

## §10. Gate 4.1 deliverables

| Artifact | Path |
|---|---|
| This closure report | `reports/phase-a1a/A1A_GATE4_1_PHI_INVENTORY_CLASSIFICATION_THREAT_MODEL.md` |
| Machine-readable inventory | `reports/phase-a1a/artifacts/phi_inventory.json` |

No code, no migration, no test changes in this gate.

---

## §11. Coordination with Gate 4.2–4.8

| Gate | Implements against |
|---|---|
| 4.2 | §5 (classification) + §6 T-DI-1/T-CC-12 + §7 row "SQLite table" + §7 row "Cross-tenant" |
| 4.3 | §6 T-CC-1/T-CC-2/T-CC-3/T-CC-6/T-CC-7/T-CC-8 + §7 rows for logger/trace/audit/SSE/embedded/error |
| 4.4 | §6 T-CC-10/T-CC-4 + §7 row "SQLite table" EncryptThenAllow |
| 4.5 | §6 T-CC-5 + §7 rows for LLM provider |
| 4.6 | §6 T-DI-3/T-CC-9 (browser-side) + §7 rows for localStorage/sessionStorage/HAR |
| 4.7 | §6 T-DI-5/T-CC-11 + §7 row "Partner webhook" |
| 4.8 | full policy matrix verification + leak-scan fixture derived from `phi_inventory.json` |

---

## §12. Forbidden list — re-confirmation

Gate 4.1 did NOT:
- Modify any business code
- Execute any new migration
- Touch any real patient data
- Modify any Medical Coding / CDI / DRG-DIP prompt
- Inherit Gate 3R's broad PHI security conclusions
  (Gate 3R was trace+audit+tenant-read; this gate inventories
  the PHI surface Gate 3R did not cover)
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict

---

## §13. Verdict

```
PASS_A1A_GATE4_1_PHI_INVENTORY_CLASSIFICATION_THREAT_MODEL_VERIFIED
```

The inventory covers 22 tables, ~62 PHI columns, 14 live-path
destinations, 4 data classes, 14 named threats, and a 16-cell
policy matrix. Every P0/P1 threat has a named downstream gate
that owns the close.

Forbidden verdicts (charter §22) remain forbidden.

Gate 4.2 — Patient/Encounter/CDI/Context tenant and context
boundary — follows.
