# Phase A1A Gate 4.4 — PHI At-Rest Protection + Key Lifecycle

**Date**: 2026-07-20
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.3 (`A1A_GATE4_3_LIVE_PATH_REDACTION_MINIMUM_NECESSARY_DATA.md`)
**Successor**: Gate 4.5 (Provider egress + regional residency)

Charter §4.4: close T-CC-10 (4.4/5.0 risk — highest in threat model).
SQLite stored all PHI in plaintext; a stolen DB file yielded all PHI
columns without any further work.

---

## §1. Envelope encryption design

`backend/app/services/phi_encryption.py` (new) implements
Fernet-based (AES-128-CBC + HMAC-SHA256) envelope encryption with
versioned key prefixes.

**Storage convention**

- Plaintext: `"free text"` (length N)
- Encrypted: `"v1:gAAAAA...=="` (length ~N + 100 overhead)
- The decrypt path sniffs the prefix `v\d+:` and routes accordingly.

**Key resolution**

- `ICODER_PHI_ENCRYPTION_KEY` — active key (always required in cloud)
- `ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID` — version id for new encrypts (default 1)
- `ICODER_PHI_ENCRYPTION_KEY_V{N}` — historical keys (for decrypt during rotation)

**Constraints satisfied**

1. Cloud-mode fail-closed: `Settings._validate_fail_closed_policy`
   refuses to boot if no key is configured.
2. Local-dev works without a key: `encrypt_phi` returns plaintext
   when no key is set; `is_encrypted_value` returns False so the
   decrypt path passes the value through.
3. Key rotation survivable: each encrypted value carries its
   key_id in the prefix; the decrypt path picks the right key.

---

## §2. Settings validation

`backend/app/config.py::_validate_fail_closed_policy` gains two
checks:

| Check | Failure message |
|---|---|
| `is_encryption_enabled()` returns False | `ICODER_PHI_ENCRYPTION_KEY is empty; required in cloud mode` |
| `ICODER_PHI_REDACTION_BYPASS=1` | `ICODER_PHI_REDACTION_BYPASS is set; forbidden in cloud mode` |

The second check closes the Gate 4.3 escape hatch in cloud mode.

---

## §3. Write-path wiring

`backend/app/api/encounters.py::create_encounter` now wraps the
high-PHI fields before persist:

- `Encounter.admission_reason` → `encrypt_phi(...)`
- `Document.content` → `encrypt_phi(...)`

Other clinical-text columns (e.g. `Encounter.discharge_summary`,
CDI `evidence_quote`, `query_text`) are deferred to a follow-up
gate. The encryption helper is in place; adding fields is a
one-line wrap per write site.

The local-mode fallback preserves the existing docker-compose
workflow: without `ICODER_PHI_ENCRYPTION_KEY` set, `encrypt_phi`
returns plaintext so the dev DB stays readable.

---

## §4. Key rotation runbook

```
# 1. Generate v2 key
python -c "from app.services.phi_encryption import generate_key; print(generate_key())"

# 2. Configure both keys (v2 active, v1 historical)
export ICODER_PHI_ENCRYPTION_KEY=<v2-key>
export ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID=2
export ICODER_PHI_ENCRYPTION_KEY_V1=<old-v1-key>

# 3. Restart — new writes use v2, v1 rows still decryptable

# 4. After validation window, drop V1:
unset ICODER_PHI_ENCRYPTION_KEY_V1
```

A `rotate_encrypted_columns` helper (batch re-encrypt v1 → v2)
will be added in Gate 4.7 when retention + deletion are wired.
Gate 4.4's scope is the encrypt/decrypt primitives + write-path
coverage.

---

## §5. Tests

`backend/tests/test_api/test_a1a_gate4_4_phi_at_rest_encryption.py`
(13 tests):

- §1 Encrypt/decrypt primitives: 6 tests (roundtrip, plaintext
  fallback, decrypt plaintext, None handling, empty string, prefix
  detection)
- §2 Key rotation: 3 tests (decrypt old + new, missing historical
  key raises, generate_key helper)
- §3 Settings validation: 3 tests (cloud refuses without key,
  cloud refuses with redaction bypass, cloud boots with key)
- §4 Write-path wiring: 1 integration test (DB rows carry
  encrypted values; decrypt path recovers original)

Test report: `13 passed in 3.82s`. Regression with Gate 4.2 +
4.3 + Gate 3R security negative: `63 passed in 60.57s`.

---

## §6. Files touched

### Code

| File | Change |
|---|---|
| `backend/app/services/phi_encryption.py` | **NEW**. Fernet envelope encryption with versioned key prefix. |
| `backend/app/config.py` | Cloud-mode Settings validation: refuse boot without encryption key + refuse boot with redaction bypass |
| `backend/app/api/encounters.py` | `create_encounter` wraps `admission_reason` and `Document.content` via `encrypt_phi` |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_4_phi_at_rest_encryption.py` | **NEW**. 13 tests. |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_4_PHI_AT_REST_PROTECTION_KEY_LIFECYCLE.md` | This closure report. |

---

## §7. Forbidden list — re-confirmation

Gate 4.4 did NOT:

- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Wire encryption into CDI sub-tables (`evidence_quote`, `query_text`,
  etc.) — deferred to follow-up; the helper is in place
- Implement `rotate_encrypted_columns` batch helper — deferred to
  Gate 4.7 (retention/deletion scope)

---

## §8. Provisional verdict

```
PASS_A1A_GATE4_4_PHI_AT_REST_PROTECTION_VERIFIED
```

T-CC-10 (4.4/5.0 risk) closed at the primitives + Settings +
write-path layers. Cloud-mode refuses to boot without encryption.
Local-dev keeps working without a key (plaintext fallback).
Rotation is survivable via versioned key prefix.

---

## §9. Next

Gate 4.5 — Provider egress + regional residency.
