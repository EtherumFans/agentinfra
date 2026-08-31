# Phase A0.1 Gate 6 — Gate 13A Security Evidence Regrading

> Read-only regrade of A0-P0-018 and A0-P0-019 from E7
> (SECURITY_NEGATIVE_VERIFIED) down to E1 (DOCUMENTED). Phase 7 Gate 13A
> shipped the implementation but did not capture independent negative
> browser evidence. The Phase A0 v1 evidence_grade=E7 claim is revoked.

Spec reference: Phase A0.1 §三 Gate 6.

---

## §1. Why this gate exists

Phase 7 Gate 13A shipped a major embedded-preview security redesign:

- HMAC-signed 60-second single-use **Bootstrap Ticket** replacing the
  URL-JWT (threat T1, T2, T3).
- `Referrer-Policy: no-referrer` on preview.html (threat T4).
- `MessageChannel` handshake with origin / source / nonce verification
  replacing `postMessage(..., '*')` (threat T5).
- Code generators with placeholders only (threat T6).

That is solid implementation work. The threat model
(`reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md`) documents
6 attack surfaces and the mitigation for each.

**The problem is the evidence grade**, not the implementation. Phase A0
v1 marked both A0-P0-018 (URL-JWT PHI risk) and A0-P0-019 (postMessage
wildcard risk) as:

- `status: MITIGATED_IN_PHASE_7` (closed)
- `evidence_grade: E7` (SECURITY_NEGATIVE_VERIFIED)

E7 has a specific meaning: independent negative verification — i.e., an
attacker-style probe (Playwright trace, sanitized HAR, browser console
audit, storage audit) that *demonstrates* the threat is closed, not
just that the code looks like it should close it.

Per Gate 2 of this phase, the Gate 13A evidence directories are empty:

```
reports/phase7/gate13a/console-logs/    0 entries
reports/phase7/gate13a/network-audit/   0 entries
reports/phase7/gate13a/playwright-traces/ 0 entries
reports/phase7/gate13a/sanitized-har/   0 entries
reports/phase7/gate13a/screenshots/     0 entries
reports/phase7/gate13a/storage-audit/   0 entries
reports/phase7/gate13a/test-results/    0 entries
```

No captured artifacts. No Playwright trace. No HAR. No console log.
No storage audit. Without these, **E7 is not supportable**.

## §2. Regrade decision

| Finding | v1 status | v1 grade | v2 status | v2 grade |
|---------|-----------|----------|-----------|----------|
| A0-P0-018 (URL-JWT PHI risk) | MITIGATED_IN_PHASE_7 (closed) | E7 | MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED (open) | **E1** |
| A0-P0-019 (postMessage wildcard) | MITIGATED_IN_PHASE_7 (closed) | E7 | MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED (open) | **E1** |

### Why E1, not E0

E0 = UNSUPPORTED (no evidence at all).
E1 = DOCUMENTED (the design / threat model / code is documented).

Phase 7 Gate 13A shipped:
- Threat model document (`PHASE7_GATE13A_THREAT_MODEL.md`, 110 lines).
- Architecture document with data flow diagram.
- Implementation: `app/services/preview_ticket.py` (HMAC), `app/services/run_lifecycle.py`, `app/middleware/partner_cors.py`.
- 48 new tests including 13 trace_token tests + 11 CORS tests + preview_ticket tests.
- CSP-nonce-protected `preview.html` (sandbox + no-store + no-referrer).

That is *substantial* evidence at the E1 (DOCUMENTED) and E2
(CODE_OBSERVED) level. Calling it E0 would be unfair to the work.
Calling it E7 would be unfair to the audit standard. **E1 is honest.**

Some sub-components reach E3 (UNIT_VERIFIED) — e.g., the HMAC trace
token has 13 unit tests covering signature forgery, constant-time
compare, org-mismatch 403. But the *end-to-end negative verification*
(replay the original threat T1-T6 in a real browser, capture the
artifact, demonstrate the leak is gone) was never performed.

## §3. What would re-establish E7

For each threat, an independent negative verification artifact is
required. The artifact must demonstrate that an attacker-style probe
fails to extract the originally-leaked data.

| Threat | Required artifact | Verification |
|--------|-------------------|--------------|
| T1 iframe URL → browser history | Playwright trace: load preview, inspect `window.history`, confirm no JWT/token in any entry | captured `.zip` trace under `playwright-traces/` |
| T2 iframe URL → HAR | sanitized HAR: save all-as-HAR during a preview session, confirm only opaque `preview_session_id` in any URL | sanitized HAR file under `sanitized-har/` |
| T3 iframe URL → backend access logs | captured access log excerpt showing `GET /api/embedded/preview.html?psid=...` with no PHI | log excerpt under `console-logs/` |
| T4 Referer on sub-resource | Playwright network audit: confirm `Referrer-Policy: no-referrer` produces empty Referer on widget fetch() calls | network audit JSON under `network-audit/` |
| T5 postMessage wildcard | Playwright trace: forge a `postMessage` from a wrong-origin parent, confirm iframe rejects | trace under `playwright-traces/` |
| T6 code generator copy | visual screenshot of all 3 code generators (HTML/React/JSON) showing placeholders only | PNG under `screenshots/` |
| T7 (new) localStorage / sessionStorage / cookies | Playwright storage audit: confirm iframe writes nothing to persistent storage | storage audit JSON under `storage-audit/` |

Until these artifacts exist, A0-P0-018/019 stay at E1.

## §4. Impact on open canonical count

The regrade moves A0-P0-018 and A0-P0-019 from closed to open. Net
effect on the v2 issue ledger:

```
v1 closed count for these two findings  : 2
v2 open count for these two findings    : 2
Δ in open_canonical_count               : +2 (already reflected in Gate 3's count of 79)
```

The +2 is already in the 79 open canonical figure from Gate 3.
This gate is the formal justification for that +2.

## §5. Impact on parity matrix

Parity dimension F-08 (Edge-node PHI redaction) is NOT affected by
this regrade — F-08 is about export-path-only redaction (A0-P0-017),
a different finding. F-08's CORTI_ADVANTAGE status stands.

No parity dimension directly tracks A0-P0-018/019 because these are
embedded-preview-specific and Corti has no equivalent surface (Corti
uses cookie auth on their console, not URL-JWT).

## §6. Hard Checkpoint — Gate 13A Security Evidence (provisional)

| Sub-check | Status |
|-----------|--------|
| SE-1: A0-P0-018 regraded from E7 to E1 | ✅ |
| SE-2: A0-P0-019 regraded from E7 to E1 | ✅ |
| SE-3: both findings moved to MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED | ✅ |
| SE-4: required artifacts for E7 listed per threat | ✅ 7 threats × 1 artifact each |
| SE-5: open_canonical_count impact documented (+2, already in Gate 3 count) | ✅ |
| SE-6: parity matrix F-08 unaffected (different finding) | ✅ |
| SE-7: threat model document preserved (not modified) | ✅ |
| SE-8: E1 rationale explicit (E0 unfair, E7 unsupportable) | ✅ |

**Hard Checkpoint SE: ✅ PASS (8/8 sub-checks) provisional — Gate 8 validator must machine-verify before final ratification.**

## §7. Findings raised in Gate 6

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G6-001** | P0-S | Phase A0 v1 marked A0-P0-018 (URL-JWT PHI risk) as `MITIGATED_IN_PHASE_7 / E7` (closed, security-negative-verified) but no browser artifacts were captured. Phase 7 Gate 13A shipped the implementation (HMAC Bootstrap Ticket) but did not perform independent negative verification. Regraded to E1, status reopened. |
| **A0.1-G6-002** | P0-S | Same regrade for A0-P0-019 (postMessage wildcard risk). Implementation shipped (MessageChannel handshake + origin/source/nonce verification), but no negative verification artifacts captured. |
| **A0.1-G6-003** | P1 | Phase 7 Gate 13A threat model document lists 6 attack surfaces and corresponding mitigations; v2 adds T7 (storage audit) because the §11.4 storage audit reported in Phase 7 Gate 6 was not captured as a reusable artifact under `storage-audit/`. |
| **A0.1-G6-004** | P2 | Phase 7 Gate 13A report directory structure (`screenshots/`, `console-logs/`, `network-audit/`, `sanitized-har/`, `playwright-traces/`, `storage-audit/`, `test-results/`) was created but never populated. Either Phase A1 must populate these via real browser runs, or the directories must be retired with a documented decision (per Gate 2 Finding A0.1-G2-002). |

## §8. Gate 6 verdict

```
PHASE_A0_1_GATE_6_GATE13A_SECURITY_EVIDENCE_REGRADED
2_FINDINGS_REGRADED (A0-P0-018, A0-P0-019)
E7 → E1 (IMPLEMENTATION_REPORTED, not SECURITY_NEGATIVE_VERIFIED)
0_NEGATIVE_VERIFICATION_ARTIFACTS_CAPTURED
7_ARTIFACTS_REQUIRED_FOR_E7 (T1-T7)
2_FINDINGS_REOPENED (already in Gate 3 open_canonical_count of 79)
THREAT_MODEL_PRESERVED (not modified)
PARITY_MATRIX_F08_UNAFFECTED (different finding)
HARD_CHECKPOINT_SE_PROVISIONAL_PASS (8/8)
```

### Phase 7 Gate 13A threat model and final report NOT modified (preserved as audit trail).

End of Gate 6. Proceeding to Gate 7 — Roadmap V2.
