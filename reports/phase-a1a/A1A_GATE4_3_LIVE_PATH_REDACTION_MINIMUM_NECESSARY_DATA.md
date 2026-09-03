# Phase A1A Gate 4.3 — Live-path Redaction + Minimum Necessary Data

**Date**: 2026-07-20
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.2 (`A1A_GATE4_2_CLINICAL_DATA_TENANT_CONTEXT_BOUNDARY.md`)
**Successor**: Gate 4.4 (PHI at-rest protection + key lifecycle)

Charter §4.3: close four live-path leak vectors flagged in the
Gate 4.1 threat model.

| Threat | Surface | Pre-Gate-4.3 | Gate 4.3 fix |
|---|---|---|---|
| T-CC-1 | `safe_metadata` (run_trace_events) | Blacklist with value-shape heuristics; new emit-site key carrying PHI passed through unchallenged | Strict allowlist: any key not in `_SAFE_KEYS` is replaced with `[REDACTED]` |
| T-CC-2 | `audit_log.details` | Accept any JSON from caller; emit-site `details={"patient_name": ...}` persisted PHI | Top-level allowlist via `redact_audit_details` |
| T-CC-3 | `audit_log.model_input_summary` / `model_output_summary` | Arbitrary Text; full transcript could land in audit row | Truncate to 200 chars + pass through fail-closed `redact_for_export` |
| T-CC-4 | `phi_redactor.redact_for_export` | Best-effort: returned ORIGINAL on any failure path | Fail-closed: return `[REDACTION_FAILED]` placeholder |

---

## §1. safe_metadata — strict allowlist

`backend/app/icoder/agent_runtime/orchestrator/run_trace.py::_redact_safe_metadata`
is the last-mile chokepoint before trace events hit the DB. The
pre-Gate-4.3 implementation only blanked a key when (a) its name
matched a known-secret pattern (`token`, `secret`, `client_secret`,
...) OR (b) its value looked like a token blob (JWT shape, `Bearer `
prefix, ≥40-char alphanumeric). An emit-site bug writing e.g.
`{"patient_name": "张三"}` would pass through both checks.

The new implementation flips the policy: only keys on `_SAFE_KEYS`
survive. Any other key is replaced with `[REDACTED]` and logged
(`info` for ordinary unknowns, `warning` if the value looks like a
token blob). The `_SAFE_KEYS` set is documented inline with the
contract for adding a new key: confirm the value is display-safe,
add the key, add a test.

`_KNOWN_SECRET_KEYS` is retained for log-severity selection only;
it no longer gates the redaction decision.

---

## §2. audit_log details + summary — chokepoint redaction

`backend/app/services/audit_detail_redactor.py` (new) implements
the audit-side policy:

- `redact_audit_details(details)` walks top-level keys. Keys on
  `_ALLOWED_DETAIL_KEYS` (operational metadata: run_id, agent_id,
  status, encounter_id, ...) survive. Keys on `_KNOWN_PHI_KEYS`
  (patient_name, mrn, input_text, model_input, ...) are
  redacted with a `warning` log. Any other key is redacted with
  an `info` log (defensive — unknown treated as PHI).
- `redact_audit_summary(text)` truncates to `MAX_SUMMARY_LEN=200`
  chars then routes through the fail-closed
  `phi_redactor.redact_for_export` so the same redaction rules
  apply to audit summaries as to export text.

`backend/app/middleware/audit.py::log_action` calls both helpers
before constructing the `AuditLog` row, so the redaction is
applied regardless of caller.

Deep-walking nested dicts inside a top-level value is deliberately
NOT done — the audit hot path can't afford the cost. The contract
is that emit sites put operational metadata at the top level and
free-form content under a known PHI key (which is redacted
wholesale).

---

## §3. phi_redactor — fail-closed

`backend/app/services/phi_redactor.py::redact_for_export` is the
export-path redactor. Pre-Gate-4.3 it returned the original text
on any failure (disabled / unavailable / exception). The new
contract:

| Input / state | Output |
|---|---|
| Empty input | `""` |
| Disabled + bypass set (local-dev only) | original text |
| Disabled without bypass | `[REDACTION_FAILED]` |
| Redactor unavailable | `[REDACTION_FAILED]` |
| Redactor raises | `[REDACTION_FAILED]` |
| Redactor returns | redacted text |

The `[REDACTION_FAILED]` placeholder is visible in the exported
artefact so a customer files a ticket instead of accepting a
silently-leaky report. The alternative (return original) would
leak PHI on any redactor bug, which is the pre-Gate-4.3 behaviour
the threat model flagged.

`ICODER_PHI_REDACTION_BYPASS=1` is the local-dev escape hatch.
Gate 4.4 will add Settings-side validation refusing to boot if
this flag is set in cloud mode.

---

## §4. Tests

`backend/tests/test_api/test_a1a_gate4_3_live_path_redaction.py`
(17 tests):

- §1 safe_metadata allowlist: 5 tests (allows known, redacts
  unknown, redacts token-blobs, handles empty, no mutation)
- §2 audit details / summary: 6 tests (allows operational,
  redacts PHI, redacts unknown defensively, preserves None,
  truncates to MAX_SUMMARY_LEN, preserves None summary)
- §3 phi_redactor fail-closed: 5 tests (disabled, bypass,
  exception, unavailable, empty)
- §4 log_action wiring: 1 integration test (writes audit row
  with PHI in details + long summary, asserts DB-stored row is
  scrubbed and truncated)

Test report: `17 passed in 3.61s`. Regression on trace/audit
neighbour tests: `55 passed in 119.42s`.

---

## §5. Files touched

### Code

| File | Change |
|---|---|
| `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` | `_redact_safe_metadata` flipped to strict allowlist; `_SAFE_KEYS` documented contract |
| `backend/app/services/phi_redactor.py` | Fail-closed contract; `[REDACTION_FAILED]` placeholder; `ICODER_PHI_REDACTION_BYPASS` escape hatch |
| `backend/app/services/audit_detail_redactor.py` | **NEW**. `redact_audit_details` + `redact_audit_summary` |
| `backend/app/middleware/audit.py` | `log_action` routes details + summaries through the redactor before persist |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_3_live_path_redaction.py` | **NEW**. 17 tests covering §1–§4 |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_3_LIVE_PATH_REDACTION_MINIMUM_NECESSARY_DATA.md` | This closure report |

---

## §6. Forbidden list — re-confirmation

Gate 4.3 did NOT:

- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data (tests use synthetic fixtures only)
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Add new Agent / Expert / Tool / Runtime
- Remove the `[REDACTED]` placeholder path — emit sites that
  depend on the old best-effort behaviour will visibly break
  (which is the point: surface the bug, don't hide it)

---

## §7. Provisional verdict

```
PASS_A1A_GATE4_3_LIVE_PATH_REDACTION_VERIFIED
```

Four live-path leak vectors are closed. 17 Gate 4.3 tests pass;
55 regression tests pass. Fail-closed semantics now govern both
the export redactor and the audit-emit chokepoint.

---

## §8. Next

Gate 4.4 — PHI at-rest protection + key lifecycle.
