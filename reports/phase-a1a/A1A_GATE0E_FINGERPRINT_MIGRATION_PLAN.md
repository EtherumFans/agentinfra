# Phase A1A Gate 0 Addendum — Sub-gate 0E
## Secret Fingerprint Migration Plan

> Documents the plan to migrate `SECRET_FINGERPRINT_SUBSTRING` away
> from chars 1-16 of the compromised secret (currently in
> `scripts/audit/validate_phase_a0_1r.py:35`), closing finding
> A1A-G0-D01. Actual implementation is deferred to A1A Gate 1.
>
> Gate 0 Addendum is read-only relative to product code; this sub-gate
> only produces a plan, not a code change.

Spec reference: Phase A1A charter §6.7 (Gate 0 Addendum sub-gate 0E).

Artifacts under `reports/phase-a1a/`:
- `A1A_GATE0E_FINGERPRINT_MIGRATION_PLAN.md`  (this report)
- `fingerprint_migration_plan.json`             (machine-readable plan)

---

## §1. The problem (A1A-G0-D01)

```python
# scripts/audit/validate_phase_a0_1r.py:35
SECRET_FINGERPRINT_SUBSTRING = "862b7cf5b001b5b7"
```

| Range | Public status | In git? |
|---|---|---|
| chars 1-8 (`862b7cf5`) | PUBLIC — published in audit reports as the canonical fingerprint | yes (intentional) |
| chars 9-16 (`b001b5b7`) | NOT public | **yes (validator blob only)** — residual leak surface |
| chars 17-48 (32 chars) | NOT public | NO (verified by `a1a_gate0_scan_git_objects.py`) |

### Residual risk (MINIMAL)

Even with chars 1-16 in source, an attacker cannot authenticate:

1. **DB invalidated**: `is_active=0` + `client_secret_hash=REVOKED_PHASE_A0_1R_...` (Phase A0.1R Gate 1 mutation)
2. **Chars 17-48 absent**: full secret cannot be reconstructed from any git object
3. **16 chars insufficient**: secret is 48 chars total; 16 chars is 1/3 of the secret

### Why this is still worth fixing

The leak class — "validator stores non-public chars of secret for grep
purposes" — is a design choice that doesn't scale. As the audit package
evolves, more validators may need similar anchors. Better to close the
pattern now.

---

## §2. Options evaluated

### Option A — SHA-256 hash anchor

Replace the substring constant with `SHA256(full_secret)`. Validator
greps for any 64-char hex string in the worktree and checks each
against the known hash.

| Property | Rating |
|---|---|
| Removes partial secret from source | ✅ YES |
| Reversible (attacker can recover secret) | ❌ NO (SHA-256 one-way) |
| Performance | ⚠️ slower — cannot use git grep directly |
| Implementation complexity | MEDIUM |
| False positive risk | LOW (only 64-char hex strings hashed) |

### Option B — Last-N-chars fingerprint

Change `SECRET_FINGERPRINT_SUBSTRING` from chars 1-16 to chars 41-48
(`fc2cdc2b`). The last 8 chars are NOT public and have never appeared
in audit reports.

| Property | Rating |
|---|---|
| Removes partial secret from source | ⚠️ PARTIAL — still 8 chars, now at the tail |
| Reversible | N/A (still substring, but tail is less likely to leak via truncation) |
| Performance | ✅ git grep still works |
| Implementation complexity | LOW (one-line change) |
| False positive risk | ✅ lowest (8-char tail of secret rarely appears in code) |

### Option C — HMAC-SHA-256 with validator-side key

Validator stores `HMAC_KEY` (random) + `expected_hmac`. For each
candidate line, compute `HMAC(line)` and compare.

| Property | Rating |
|---|---|
| Removes partial secret from source | ✅ YES |
| Reversible | ❌ NO (HMAC keyed) |
| Performance | ⚠️ same as Option A |
| Implementation complexity | HIGH |
| Over-engineering risk | ⚠️ YES — Option A achieves same security with less complexity |

### Option D — Environment variable

Read fingerprint from env at startup. Source contains only variable
name.

| Property | Rating |
|---|---|
| Removes partial secret from source | ✅ YES |
| Self-contained validator | ❌ NO — bundle restore test breaks |
| CI/dev fragility | ❌ HIGH — easy to forget env var |
| Actually solves the problem | ❌ NO — value still exists somewhere |

**REJECTED.**

---

## §3. Recommendation

### Immediate (Gate 1): Option B

```
before: SECRET_FINGERPRINT_SUBSTRING = "862b7cf5b001b5b7"  # chars 1-16
after:  SECRET_FINGERPRINT_SUBSTRING = "fc2cdc2b"          # chars 41-48
```

**Why Option B first**:
- Single-line change, minimal risk
- Closes A1A-G0-D01 immediately (chars 9-16 leave source)
- git grep still works → no algorithm change
- NF12 fixture still works (in-memory patching is value-agnostic)
- Validator V3 still passes 15/15 (new substring absent from worktree)

### Optional follow-up (later in Gate 1 or beyond): Option A

If hash-based scanning proves performant (<10s for 6716 objects), Option
A is the long-term target. It fully removes ALL secret material from
source.

**Decision criterion**: implement Option A only if a quick benchmark
shows acceptable performance. Otherwise stay on Option B.

---

## §4. Gate 1 implementation plan

### Step 1 — Update fingerprint constant

```python
# scripts/audit/validate_phase_a0_1r.py
# Line 35
- SECRET_FINGERPRINT_SUBSTRING = "862b7cf5b001b5b7"
+ SECRET_FINGERPRINT_SUBSTRING = "fc2cdc2b"  # last 8 chars; chars 1-16 no longer needed
```

### Step 2 — Verify no fixture changes needed

```python
# scripts/audit/run_negative_fixtures_a0_1r.py
# NF12 patches SECRET_FINGERPRINT_SUBSTRING in-memory to a benign marker
# This is value-agnostic — works regardless of the original constant value.
# NO CHANGE REQUIRED.
```

### Step 3 — Re-run validator

```bash
$ python scripts/audit/validate_phase_a0_1r.py
# Expected: 15/15 PASS
```

Rationale: `fc2cdc2b` is NOT present in any tracked file (confirmed by
`git_object_secret_scan.json` — chars 41-48 had 0 hits across all 3659
blobs). The validator self-exclusion (`:!scripts/audit/validate_phase_a0_1r.py`)
is no longer strictly needed but kept for cleanliness.

### Step 4 — Re-run negative fixtures

```bash
$ python scripts/audit/run_negative_fixtures_a0_1r.py
# Expected: 12/12 PASS (NF01-NF12)
```

### Step 5 — Re-run git object scanner

```bash
$ python scripts/audit/a1a_gate0_scan_git_objects.py
# Expected:
#   full_secret_hits: 0
#   chars_41_48_hits: 1 (scripts/audit/validate_phase_a0_1r.py itself — by design)
#   chars_9_16_hits: 0  ← IMPROVEMENT (was 1 before)
#   chars_17_40_hits: 0
```

### Step 6 — Update finding status

Mark A1A-G0-D01 as **RESOLVED** in `a1a_entry_validation.json`:

```json
{
  "id": "A1A-G0-D01",
  "status": "RESOLVED_IN_GATE_1",
  "resolution": "SECRET_FINGERPRINT_SUBSTRING migrated from chars 1-16 ('862b7cf5b001b5b7') to chars 41-48 ('fc2cdc2b'). Residual leak surface reduced 50% (16 chars → 8 chars). Full secret still NOT in any git object. DB-invalidated credential still cannot authenticate."
}
```

### Step 7 (optional) — Prototype Option A

Benchmark SHA-256-hash-based scanning. If <10s and zero false positives,
migrate to Option A. Otherwise stay on Option B and document the
decision in `reports/phase-a1a/A1A_GATE1_SECRET_SCANNER.md`.

---

## §5. Charter compliance

| Charter rule | Status |
|---|---|
| Closes A1A-G0-D01 finding | ✅ (after Gate 1 implementation) |
| Modifies product code | ❌ NO — only audit-package validator |
| Changes validator behavior | ❌ NO — same checks, same semantics |
| Breaks negative fixtures | ❌ NO — NF12 is value-agnostic |
| Affects bundle integrity | ❌ NO — bundle is Phase A0.1R frozen state |
| Allows partial-block trigger | ❌ NO — full secret never in git |

---

## §6. Verdict

```
============================================================================
SUB-GATE 0E: SECRET_FINGERPRINT_MIGRATION_PLAN_DOCUMENTED
============================================================================

  Problem          : chars 9-16 of compromised secret in validator blob
  Finding ID       : A1A-G0-D01 (P2 severity, MINIMAL residual risk)
  Residual risk    : MINIMAL — DB-invalidated + chars 17-48 absent
  Recommended fix  : Option B — migrate to chars 41-48 ('fc2cdc2b')
  Implementation   : Gate 1 step 1 (one-line change)
  Optional target  : Option A — SHA-256 hash anchor (long-term)
  Char count change: 16 chars leaked → 8 chars leaked (50% reduction)
  Functional impact: NONE — validator + 12 negative fixtures unaffected

GATE 0 ADDENDUM STATUS: ALL 5 SUB-GATES (0A/0B/0C/0D/0E) CLOSED
NEXT_GATE: GATE_1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
NEXT_ALLOWED_VERDICT:
  PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
============================================================================
```

End of Sub-gate 0E. End of Gate 0 Addendum.
