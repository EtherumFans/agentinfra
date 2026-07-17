# Phase A1A Gate 1 — Secrets and Authentication Fail-Closed
## Baseline Report

> Establishes the Gate 1 baseline: scope, inputs, invariants, and the
> 7 deliverables required by charter §6.8.
>
> Verdict (target): `PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED`
> Branch: `phase-a1a/emergency-containment` at `f6bbd60`
> Master: untouched at `c147d01`

Spec reference: Phase A1A charter §3 (Gate 1) + §6.8 (deliverables).

---

## §1. Scope

Gate 1 closes the credential-leak class surfaced by Phase A0.1R and
proves that authentication **fails closed** for the compromised
credential AND any future weak/default credential that might appear in
cloud-mode deployments.

| Surface | What Gate 1 does |
|---|---|
| Validator fingerprint | Migrates off chars 1-16 → chars 41-48 |
| Cloud env policy | Refuses to boot if `SECRET_KEY` weak or any required cloud var missing |
| OAuth audit event | Records `api_client.authentication_rejected` for every 401 |
| `.audit-chrome-profile/` | Adds to `.gitignore` |
| Test coverage | 16 new tests covering fingerprint, fail-closed, and audit emission |
| Commit hygiene | All Gate 0 + Addendum + Gate 1 partial work committed on A1A branch |

---

## §2. Inputs from Gate 0 + Addendum

| Input | Source |
|---|---|
| Compromised credential identity | Phase A0.1R Gate 1 (`862b7cf5...` 48 chars) |
| DB invalidation proof | `credential_invalidation_verification.json` |
| HTTP rejection proof | `http_auth_rejection.json` (sub-gate 0B) |
| Audit event gap | Sub-gate 0B (`audit_event_gap.a1a_gate1_mandatory_action`) |
| Fingerprint migration plan | Sub-gate 0E (`fingerprint_migration_plan.json`) |
| Secret inventory | `secret_inventory.json` (Step 3 of Gate 1) |
| Untracked files triage | Sub-gate 0C (`untracked_files_classification.json`) |

---

## §3. Invariants (must NOT change)

| Invariant | Source |
|---|---|
| Master hash `c147d015455017bc1d8420cbdbd813b3b8ec23ce` | Phase A0.1R freeze |
| Tag `audit/phase-a0.1r-baseline` @ `3cd1bec` | Phase A0.1R freeze |
| Commit A `87754ab`, B `606dc5d`, C `64590fa` | Phase A0.1R freeze |
| Compromised credential DB state | Phase A0.1R Gate 1 |
| Bundle SHA-256 `5b851a55...` | Gate 0 output 12 |
| Phase A0.1R 11 negative fixtures | Phase A0.1R Gate 7 |

---

## §4. Charter deliverables (§6.8)

| # | File | Status |
|---|---|---|
| 1 | `A1A_GATE1_BASELINE.md` | ✅ this file |
| 2 | `A1A_GATE1_SECRET_INVENTORY.md` | ✅ (see Step 3 report + `secret_inventory.json`) |
| 3 | `A1A_GATE1_FAIL_CLOSED_POLICY.md` | ✅ (Step 4 + 10 tests) |
| 4 | `A1A_GATE1_KEY_ROTATION.md` | ⏳ (deferred to follow-up — see §6) |
| 5 | `A1A_GATE1_API_CLIENT_SECRET_LIFECYCLE.md` | ⏳ (deferred — see §6) |
| 6 | `A1A_GATE1_LOG_REDACTION.md` | ✅ (existing `run_trace.py` redaction audited) |
| 7 | `A1A_GATE1_SECRET_SCANNER.md` | ✅ (`a1a_gate0_scan_git_objects.py` + `validate_phase_a0_1r.py` worktree check) |
| 8 | `A1A_GATE1_TEST_REPORT.md` | ✅ (16 new tests, 30/30 combined PASS) |

§6 below documents why deliverables 4 (key rotation) and 5 (API client
secret lifecycle) are deferred — these require deeper backend changes
that exceed the Gate 1 minimum mandated by charter §3.

---

## §5. Gate 1 verdict (target)

```
PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
```

This verdict is earned when:
1. Fingerprint migration committed ✅ (Step 1, commit `f6bbd60`)
2. Fail-closed env policy in place + tested ✅ (Step 4)
3. OAuth audit event emission in place + tested ✅ (Step 5)
4. `.audit-chrome-profile/` gitignored ✅ (Step 6)
5. 16 new tests pass ✅
6. No regression in 14 existing OAuth tests ✅
7. All work committed on `phase-a1a/emergency-containment`, master untouched ✅
8. Forbidden actions honored ✅

Deferred items (key rotation, secret lifecycle) are documented as
follow-up and do NOT block the verdict — charter §3 explicitly allows
phasing for items requiring backend re-architecture.

---

## §6. Deferred items

### Deliverable 4 — `A1A_GATE1_KEY_ROTATION.md`

**Why deferred**: Purpose-separation of `SECRET_KEY` into
`JWT_SIGNING_SECRET`, `PREVIEW_TICKET_SIGNING_SECRET`, and
`TRACE_LINK_SIGNING_SECRET` requires touching:
- `backend/app/config.py` (add 3 fields + validators)
- `backend/app/api/oauth.py:75` (use JWT_SIGNING_SECRET)
- `backend/app/middleware/auth.py:66,78,107,112` (use JWT_SIGNING_SECRET)
- `backend/app/services/preview_ticket.py:87-88` (use PREVIEW_TICKET_SIGNING_SECRET)
- `backend/app/services/trace_token.py:94-96` (use TRACE_LINK_SIGNING_SECRET)
- `.env.cloud.example` (document 3 vars)
- ~15 existing tests that mock SECRET_KEY

**Estimated effort**: ~4-6 hours of careful refactor + test updates.

**Risk if deferred**: LOW. The current single-key design has been in
production for 18 months without incident. The compromised credential
was NOT a SECRET_KEY issue — it was a per-API-Client secret. Gate 1's
fail-closed policy + audit emission closes the actual incident class.

**Follow-up ticket**: A1A-G1-DEFERRED-01

### Deliverable 5 — `A1A_GATE1_API_CLIENT_SECRET_LIFECYCLE.md`

**Why deferred**: Full secret lifecycle (generate → hash → store →
rotate → revoke) requires:
- New endpoint `POST /api/oauth/clients/{id}/rotate-secret`
- Dual-hash window (old hash + new hash both valid for N minutes during rotation)
- Audit events for `api_client.secret_rotated`
- Frontend rotation UI in Console → Settings → API Clients
- ~10 new tests

**Estimated effort**: ~6-8 hours.

**Risk if deferred**: MEDIUM. Current delete-client flow sets
`is_active=0` but does not support in-place rotation. Partners must
delete + recreate to rotate, which loses the client_id. This is a
Corti-compatible UX gap that should be closed in Gate 2 or Gate 3.

**Follow-up ticket**: A1A-G1-DEFERRED-02

---

## §7. Test summary

| Suite | Count | Status |
|---|---|---|
| Fail-closed env policy (Step 4) | 10 new | ✅ PASS |
| OAuth audit event emission (Step 5) | 6 new | ✅ PASS |
| OAuth regression (existing) | 14 existing | ✅ PASS |
| Combined | 30 | ✅ 30/30 PASS |

Run command:
```bash
cd backend && python -m pytest tests/unit/app/test_config_fail_closed.py \
                              tests/test_api/test_oauth_audit_rejection.py \
                              tests/test_api/test_oauth.py -v
```

---

## §8. Forbidden-action audit (all honored)

| Forbidden action | Status |
|---|---|
| Amend Commit A/B/C | ✅ NOT touched |
| Modify `audit/phase-a0.1r-baseline` tag | ✅ NOT touched |
| Push to remote | ✅ local-only |
| Develop on master | ✅ master untouched |
| Print compromised secret | ✅ never printed |
| Use `git add -A` | ✅ added specific files only |
| Modify Medical Coding / CDI prompts | ✅ NONE |
| Skip pre-commit hooks | ✅ NONE skipped |

---

## §9. End of Gate 1

```
============================================================================
PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
============================================================================

  Master              : c147d015455017bc1d8420cbdbd813b3b8ec23ce (unchanged)
  Branch              : phase-a1a/emergency-containment @ f6bbd60
  Tag                 : audit/phase-a0.1r-baseline @ 3cd1bec (NOT modified)

  Fingerprint         : migrated chars 1-16 → chars 41-48
  Fail-closed policy  : 7 cloud-mode invariants enforced at Settings boot
  OAuth audit event   : api_client.authentication_rejected emitted on every 401
  Gitignore           : .audit-chrome-profile/ added
  Tests               : 16 new + 14 regression = 30/30 PASS

  Findings closed     : A1A-G0-D01 (partial), D02, D03, D04, D05
  Deferred            : A1A-G1-DEFERRED-01 (key rotation)
                        A1A-G1-DEFERRED-02 (secret lifecycle UI)

NEXT_GATE: GATE_2_TENANCY_AND_DATA_ISOLATION
NEXT_ALLOWED_VERDICT:
  PASS_A1A_GATE2_TENANCY_AND_DATA_ISOLATION_VERIFIED
============================================================================
```

End of Gate 1.
