# Phase A0.1R Gate 5 — Evidence Manifest V2.2

> Corrects the empty-directory semantics and introduces the
> `storage_mode` partitioning required by Phase A0.1R charter
> §3.Gate5.
>
> Verdict: `PHASE_A0_1_R_GATE_5_MANIFEST_V2_2_CORRECTED`

Source: `reports/comprehensive-audit/phase-a0.1/evidence_manifest.v2_1.json`
Target: `reports/comprehensive-audit/phase-a0.1r/evidence_manifest.v2_2.json`
Builder: `scripts/audit/build_evidence_manifest_v2_2.py`

---

## §1. Empty-directory semantics fix

Phase A0.1 v2.1 used `exists=false + capture_status=NOT_CAPTURED`
for empty directories. This conflates two distinct states:

| State | v2.1 (wrong) | v2.2 (correct) |
|---|---|---|
| Directory does not exist | exists=false | exists=false |
| Directory exists but is empty | exists=false | **exists=true + artifact_count=0 + capture_status=DIR_EXISTS_EMPTY** |
| Directory exists with content | exists=true + sha256 set | exists=true + sha256 set |

The distinction matters because:

- An empty directory that **was attempted** (created by the test
  harness but never populated) carries evidentiary value: it
  documents that the attempt was made and the artifact never
  appeared.
- An absent directory (not even created) carries no such value.

### §1.1 Corrections applied (11 entries)

| Category | Path | Before | After |
|---|---|---|---|
| test-results | `phase7/gate13a/test-results/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| browser | `phase7/gate13a/screenshots/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| browser | `phase7/gate13a/network-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| browser | `phase7/gate13a/sanitized-har/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| browser | `phase7/gate13a/playwright-traces/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| browser | `phase7/gate13a/storage-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| playwright-traces | `phase7/gate13a/playwright-traces/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| sanitized-har | `phase7/gate13a/sanitized-har/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| network | `phase7/gate13a/network-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| storage | `phase7/gate13a/storage-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |
| architecture | `evidence/architecture/` | exists=false, NOT_POPULATED | exists=true, artifact_count=0, DIR_EXISTS_EMPTY |

Each corrected entry carries a `phase_a0_1r_correction` block
recording the prior state for audit trail.

## §2. Storage mode partitioning

### §2.1 Storage mode policy

v2.2 adds a `storage_mode` field to every evidence entry. Three
modes:

| Mode | Definition |
|---|---|
| **Public** | Artifact is safe to publish. No PII, no secrets, no session tokens. Committed to audit package. |
| **SPLIT_PUBLIC_RESTRICTED** | Artifact exists in two forms: a **public form** (hash + metadata + redacted excerpts) committed to the audit package, and a **restricted form** (full content with PII) stored locally outside git. |
| **Restricted** | Artifact stays local-only; never committed. Used for raw PHI, raw DB backups, raw HAR. |

Default: `SPLIT_PUBLIC_RESTRICTED` per charter §3.Gate5.

### §2.2 Category-to-mode mapping

| Category | Default mode | Reason |
|---|---|---|
| git | Public | Hashes + commit IDs; no PII |
| commands | Public | Command output of git rev-parse, etc.; no PII |
| hashes | Public | SHA-256 manifests |
| screenshots | SPLIT_PUBLIC_RESTRICTED | Browser screenshots may show PII; public form is redacted excerpt |
| browser | SPLIT_PUBLIC_RESTRICTED | Same as screenshots |
| console | SPLIT_PUBLIC_RESTRICTED | Console walk-through files may contain PII (emails, project IDs) |
| sanitized-har | SPLIT_PUBLIC_RESTRICTED | Already sanitized but kept in restricted form for forensics |
| playwright-traces | SPLIT_PUBLIC_RESTRICTED | Traces contain full request/response; restricted by default |
| network | SPLIT_PUBLIC_RESTRICTED | Network audits include headers; restricted |
| storage | SPLIT_PUBLIC_RESTRICTED | Storage audits inspect local state; restricted |
| security | SPLIT_PUBLIC_RESTRICTED | Security findings may include exploit details; restricted |
| test-results | SPLIT_PUBLIC_RESTRICTED | Test output may include fixture data |
| packages | SPLIT_PUBLIC_RESTRICTED | Built artifacts; public form is hash, restricted is binary |
| external-consumer | SPLIT_PUBLIC_RESTRICTED | Consumer harness output |
| architecture | SPLIT_PUBLIC_RESTRICTED | Architecture evidence dir |

## §3. Phase A0.1R-added evidence (7 new entries)

| Path | Grade | Storage mode |
|---|---|---|
| `A0_1R_00_GATE0_*.md` | E1_DOCUMENTED | Public |
| `A0_1R_01_CREDENTIAL_*.md` | E2_CODE_OBSERVED | Public |
| `evidence/db_snapshots/icoder.db.pre_gate1.*.bak` | E2_CODE_OBSERVED | **Restricted** (contains PII) |
| `evidence/db_snapshots/gate1_pre_state.json` | E2_CODE_OBSERVED | Public |
| `evidence/db_snapshots/gate1_post_state.json` | E2_CODE_OBSERVED | Public |
| `evidence/gate1_sanitized_verification_log.txt` | E1_DOCUMENTED | Public |
| `evidence/gate0_preflight_snapshot.json` | E1_DOCUMENTED | Public |

The DB backup `.bak` is **Restricted** — never committed, never
published. Its SHA-256 will be captured in Commit B for
audit-trail integrity; the file itself stays local.

## §4. Summary statistics

```
total_evidence_entries: 49
  captured with sha256: ~30
  not_captured / not_populated: ~10
  empty_dir_existing (corrected): 11
phase-a0.1r_added_entries: 7
storage_modes_in_use:
  Public: ~12
  SPLIT_PUBLIC_RESTRICTED: ~36
  Restricted: 1 (db backup .bak)
```

(Exact counts machine-derived in the JSON's `summary.v2_2_changes`.)

## §5. Validator V3 hooks

Gate 7 will enforce:

1. Every entry whose path ends in `/` must have
   `capture_status == "DIR_EXISTS_EMPTY"` and
   `artifact_count == 0` and `exists == true`.
2. Every entry must have a `storage_mode` field with value in
   `{Public, SPLIT_PUBLIC_RESTRICTED, Restricted}`.
3. Top-level `storage_mode_policy.default` must equal
   `SPLIT_PUBLIC_RESTRICTED`.
4. Negative fixture `nf06_empty_dir_wrong_semantics.json` (a
   dir-entry with exists=false) fails.

## §6. Findings raised in Gate 5

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G5-001** (closed) | P2 | 11 empty-dir entries corrected to exists=true + artifact_count=0. |
| **A0.1R-G5-002** (closed) | P2 | storage_mode field added to every evidence entry. |
| **A0.1R-G5-003** (closed) | P2 | storage_mode_policy published with Public/SPLIT_PUBLIC_RESTRICTED/Restricted definitions. |
| **A0.1R-G5-004** | P3 | The DB backup `.bak` is Restricted and stays local. Its SHA-256 should be captured in Commit B for integrity verification without publishing the file itself. |

---

## §7. Gate 5 verdict

```
PHASE_A0_1_R_GATE_5_MANIFEST_V2_2_CORRECTED

evidence_manifest.v2_2.json:
  schema_version: 2.2
  supersedes: reports/comprehensive-audit/phase-a0.1/evidence_manifest.v2_1.json
  empty_dir_corrections: 11
  storage_mode_field_added: true (every entry)
  storage_mode_policy_published: true
  phase_a0_1r_added_entries: 7
  total_evidence_entries: 49

NEXT_GATE: GATE_6_BUCKET_D_CLOSURE
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_6_BUCKET_D_CLOSED
```

End of Gate 5.
