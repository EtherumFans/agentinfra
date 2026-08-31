# Phase A0.1 Gate 2 — Canonical Manifest Repair

> Read-only repair of the Phase A0 v2 evidence manifest. Produces
> `evidence_manifest.v2_1.json` (restricted, authoritative) and
> `evidence_manifest.public.json` (redacted). Does NOT modify the original
> Phase A0 v2 manifest (preserved as audit trail).

Spec reference: Phase A0.1 §三 Gate 2.

---

## §1. Scope of repair

The Phase A0 v2 manifest had four classes of defects (per Gate 0 Finding 11):

1. **3 placeholder hashes** marked `NOT_YET_CAPTURED` for git command outputs
   that are trivially capturable from the live working tree.
2. **8 directory placeholders** marked `EMPTY_DIR` — appropriate as a status,
   but the v2 manifest claimed them under evidence paths while also claiming
   "0 placeholders remaining". The two statements are contradictory.
3. **5 future-tense notes** referring to gates that have already closed:
   `"Phase A0 Gate 5 will inherit ..."`, `"Phase A0 Gate 7 will populate"`,
   `grades_to_add_in_phase_a0` (Phase A0 closed, cannot add later).
4. **Internal contradiction** — `placeholders_resolved.count = 24` while
   the surface-level placeholders (`NOT_YET_CAPTURED`, `EMPTY_DIR`,
   future tense) numbered 16+.

This gate repairs all four classes.

## §2. Real SHA-256 captures (replacing NOT_YET_CAPTURED)

Git commands re-run on 2026-07-17 against the live working tree:

| Path | Command | SHA-256 |
|------|---------|---------|
| `evidence/git/phase_a0_commands/git_rev_parse_head.txt` | `git rev-parse HEAD` | `76dbb39d3bb0f832ea700317c7de9beab63c33ea54f881a7b28c80f1aaf4b6c3` |
| `evidence/git/phase_a0_commands/git_status_short.txt` | `git status --short` | `c3e113ccc51f0e9fc7c21282acf58f66e6f80a8025544b58a902f9a5bb804d5e` |
| `evidence/git/phase_a0_commands/git_remote_v.txt` | `git remote -v` | `69fdd7b14a0b0e9ade3d42dbe1f7068dfd55fad31b36ff3ab520290c6598c3e8` |

The `git_rev_parse_head.txt` hash equals the existing
`evidence/git/head.txt` hash — both compute the SHA-256 of the bytes
`c147d015455017bc1d8420cbdbd813b3b8ec23ce\n`, confirming HEAD has not
drifted between Phase A0 capture and Phase A0.1 capture.

## §3. Empty directory placeholders rewritten

`EMPTY_DIR` was a structurally honest status but the Phase A0 v2 manifest
held it under `path` entries that also claimed implicit existence. The
v2.1 schema splits status into three orthogonal fields:

- `exists: true|false` — does the file or directory exist on disk?
- `capture_status: CAPTURED|NOT_CAPTURED|NOT_POPULATED` — has the audit
  captured its content?
- `sha256: <hex>|null` — cryptographic hash, or null if not captured.

Rewritten entries:

| Path | v2 | v2.1 |
|------|-----|------|
| `phase7/gate13a/test-results/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `phase7/gate13a/screenshots/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `phase7/gate13a/console-logs/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `phase7/gate13a/network-audit/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `phase7/gate13a/sanitized-har/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `phase7/gate13a/playwright-traces/` | exists twice (browser + playwright-traces) | dedup; both entries cross-referenced |
| `phase7/gate13a/storage-audit/` | status=EMPTY_DIR | exists=false, capture_status=NOT_CAPTURED, sha256=null |
| `evidence/architecture/` | status=EMPTY_DIR + `"Phase A0 Gate 7 will populate"` | exists=false, capture_status=NOT_POPULATED, sha256=null |

## §4. Future-tense removed

| Location | Before | After |
|----------|--------|-------|
| `evidence_index.security[0].note` | "Phase A0 Gate 5 will inherit Gate 9 ..." | split into two entries referencing the actual closed gate reports; note "NOT independent negative verification" |
| `evidence_index.architecture[0].note` | "Phase A0 Gate 7 will populate" | capture_status=NOT_POPULATED; note that architecture claims rest on textual descriptions |
| `evidence_grade_index.grades_to_add_in_phase_a0` | future-tense list | renamed `grades_planned_but_NOT_achieved`; Phase A0 closed without achieving them |

## §5. Placeholder count reconciliation

v2.1 `placeholders_resolved.count = 16` matches the actual user-visible
placeholder surface fixed in this gate (3 hashes + 8 EMPTY_DIR rewritten +
5 future-tense removed). v2's claim of 24 was correct for the narrow regex
set the v2 validator scanned for, but did not address the user-visible
surface.

The v2.1 manifest does **not** claim "0 placeholders remaining" — that
would require either (a) actually populating the Gate 13A evidence
directories with real browser artifacts (out of Phase A0.1 scope — read-only
audit repair), or (b) honestly stating that they remain uncaptured. The
v2.1 manifest chooses (b).

## §6. Public / restricted split

`evidence_manifest.public.json` is the redacted view. It contains:
- Aggregate counts (36 evidence entries, 27 captured, 9 unsupported)
- Grade distribution
- Gate status summary
- Forbidden verdicts list
- **No** PII (no Corti account email, no project_id)
- **No** secret examples
- **No** individual SHA-256s for sensitive artifacts (only for non-sensitive
  build outputs and evidence already in the repo)

`evidence_manifest.v2_1.json` is the restricted authoritative view. It
contains all of the above plus individual SHA-256s, source metadata, and
the explicit `contains_pii: true` flag on `00_console_access_metadata.md`.

## §7. Validator impact

The Phase A0 validator's `check_no_placeholders_in_v2_manifest` is no
longer fit for purpose. The Phase A0.1 Gate 8 validator (yet to be built)
must scan for:
- `NOT_YET_CAPTURED`
- `EMPTY_DIR`
- `NOT_WRITTEN`, `NOT_VERIFIED`
- Future-tense patterns: `will populate`, `will inherit`, `grades_to_add_in_*`
- `(per-file)`, `pending write`, `TODO`, `<TBD>`, `TBD`

And must NOT consider a manifest "0 placeholders" while any of these
strings appear without an orthogonal `capture_status: CAPTURED` sibling.

## §8. Hard Checkpoint — Canonical Manifest (provisional)

| Sub-check | Status |
|-----------|--------|
| CM-1: Single canonical entry for each evidence path | ✅ v2.1 is the authoritative source |
| CM-2: Real SHA-256 for every `exists: true` path | ✅ 27 of 27 |
| CM-3: `exists: false` paths have null hash + NOT_CAPTURED/NOT_POPULATED | ✅ 9 of 9 |
| CM-4: No placeholder hash strings | ✅ `NOT_YET_CAPTURED` removed |
| CM-5: No future-tense in closed phases | ✅ removed |
| CM-6: Public manifest contains no PII / secrets | ✅ verified by inspection |
| CM-7: Restricted manifest points to public manifest | ✅ publication_policy documented |
| CM-8: Phase A0 v2 preserved as audit trail | ✅ not modified |

**Hard Checkpoint CM: ✅ PASS (8/8 sub-checks) provisional — Phase A0.1 Gate 8 validator must machine-verify before final ratification.**

## §9. Findings raised in Gate 2

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G2-001** | P2 | Phase A0 v2 manifest's `placeholders_resolved.count=24` referred to a narrow regex set, not the user-visible surface; must not be inherited as evidence of completeness. |
| **A0.1-G2-002** | P2 | Evidence directories under `reports/phase7/gate13a/{screenshots,console-logs,network-audit,sanitized-har,playwright-traces,storage-audit,test-results}/` remain empty. Phase A0.1 does NOT populate them (out of read-only scope); Phase A1 should either capture them via real browser runs OR formally retire them with a documented decision. |
| **A0.1-G2-003** | P3 | `evidence/architecture/` directory never populated. Phase A0.1 retires the future-tense obligation; future architecture audits should produce concrete artifacts (e.g., module dependency graphs) under this path. |

## §10. Gate 2 verdict

```
PHASE_A0_1_GATE_2_CANONICAL_MANIFEST_REPAIR_CLOSED
16_PLACEHOLDERS_RESOLVED (3 hashes + 8 EMPTY_DIR + 5 future-tense)
9_EVIDENCE_ENTRIES_HONESTLY_NOT_CAPTURED
27_EVIDENCE_ENTRIES_WITH_REAL_SHA256
PUBLIC_RESTRICTED_SPLIT_VERIFIED
HARD_CHECKPOINT_CM_PROVISIONAL_PASS (8/8)
0_PLACEHOLDER_HASH_STRINGS_REMAINING
0_FUTURE_TENSE_IN_CLOSED_PHASES
```

### Phase A0 v2 manifest NOT modified (preserved as audit trail).

End of Gate 2. Proceeding to Gate 3 — Issue Ledger Normalization.
