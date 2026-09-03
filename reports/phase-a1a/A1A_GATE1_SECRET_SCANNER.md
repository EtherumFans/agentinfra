# A1A Gate 1 Deliverable #7 — Secret Scanner

> Documents the two-layer secret scanning approach: the Phase A0.1R
> worktree grep validator + the A1A Gate 0 git object database
> scanner. Together they cover both working-tree files and the full
> git object history.

Spec reference: Phase A1A charter §3 (Gate 1) — secret scanner requirement.

---

## §1. Two-layer scanning

### Layer 1 — Worktree grep (Phase A0.1R Validator V3)

```
scripts/audit/validate_phase_a0_1r.py :: check_no_secret_in_worktree()
```

**What it scans**: every file tracked by git (via `git grep -l`),
excluding:
- `.audit-chrome-profile/` (gitignored browser state)
- `reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/` (sanitized snapshots)
- `scripts/audit/validate_phase_a0_1r.py` (the validator itself, which defines the fingerprint)

**Pattern**: `SECRET_FINGERPRINT_SUBSTRING` — currently `fc2cdc2b`
(chars 41-48 of compromised secret, post-Gate 1 Step 1 migration).

**When it runs**:
- Locally on every `python scripts/audit/validate_phase_a0_1r.py` invocation
- Part of `run_negative_fixtures_a0_1r.py` (NF12 injects a benign marker + verifies the check fires)
- Should be wired into pre-commit hook in Gate 2

### Layer 2 — Git object database scanner (A1A Gate 0)

```
scripts/audit/a1a_gate0_scan_git_objects.py
```

**What it scans**: every blob in the git object database (loose + packed),
retrieved via `git cat-file --batch-all-objects --batch-check`.

**Pattern**: 8 substrings covering all non-public char ranges of the
compromised secret:

```python
FULL_SECRET = "862b7cf5b001b5b7f285739eee828cf5fb14ea43fc2cdc2b"
NON_PUBLIC_SUBSTRINGS = [
    ("chars_9_16",   "b001b5b7"),
    ("chars_9_24",   "b001b5b7f285739e"),
    ("chars_17_24",  "f285739e"),
    ("chars_25_32",  "ee828cf5"),
    ("chars_33_40",  "fb14ea43"),
    ("chars_41_48",  "fc2cdc2b"),
    ("chars_9_end",  "b001b5b7f285739eee828cf5fb14ea43fc2cdc2b"),
    ("full_secret",  FULL_SECRET),
]
```

**When it runs**: manual invocation during audit phases. Output:
`reports/phase-a1a/git_object_secret_scan.json`.

---

## §2. Current scan results (post-Gate 1 Step 1)

| Substring | Hits | Location |
|---|---|---|
| chars 1-8 (`862b7cf5`) | (public, not scanned) | — |
| chars 9-16 (`b001b5b7`) | **1** | immutable Commit B blob `4573c81` |
| chars 9-24 | 0 | — |
| chars 17-24 | 0 | — |
| chars 25-32 | 0 | — |
| chars 33-40 | 0 | — |
| chars 41-48 (`fc2cdc2b`) | 1 | current validator blob `fe2bbe8d` (Gate 1 Step 1) |
| chars 9-end | 0 | — |
| full secret | **0** | — |

### Interpretation

- **Full secret NOT in any git object**: ✅ confirmed
- **Chars 17-48 (32 chars) NOT in any git object**: ✅ confirmed
- **Chars 9-16 (8 chars) in 1 immutable blob**: documented as A1A-G0-D01,
  cannot be amended per charter. The blob is the Phase A0.1R Commit B
  validator (frozen baseline).
- **Chars 41-48 (8 chars) in 1 current blob**: by design — the validator
  must reference the fingerprint somehow. Self-excluded from worktree grep
  via `:!scripts/audit/validate_phase_a0_1r.py`.

### Total leak surface

| Source | Char count | Location |
|---|---|---|
| Public fingerprint | 8 | audit reports (intentional) |
| Validator current blob | 8 | `scripts/audit/validate_phase_a0_1r.py:37` |
| Validator Commit B blob | 8 | `4573c81` (immutable) |
| **Total non-public chars in git** | **16** | (was 16 before Step 1; rebalanced from 9-16 to 41-48 in current) |
| **Full secret in git** | **0** | ✅ |

---

## §3. Why not switch to SHA-256 hash anchor (Option A)?

Sub-gate 0E recommended Option B (last-N-chars) for Gate 1 and
deferred Option A (SHA-256 hash) as a follow-up. Reiterating:

| Option | Removes 8-char substring from validator? | Removes historical blob? |
|---|---|---|
| B (current) | NO — still 8 chars at the tail | NO — historical blob immutable |
| A (SHA-256) | YES — validator contains only a hash | NO — historical blob immutable |

Even Option A cannot remove the historical Commit B blob. The
structural leak is permanent until the entire git history is reinitialized
(which would require creating a new master without the Phase A0.1R
baseline — explicitly forbidden by charter).

Option B was selected because:
1. It closes the CURRENT leak surface (chars 9-16 leave current source)
2. Option A would not change the scanner verdict (historical blob persists)
3. Option A requires algorithmic rewrite (slower scan, harder to maintain)

---

## §4. CI integration (Gate 2 follow-up)

### Pre-commit hook

```yaml
# .pre-commit-config.yaml (target Gate 2)
- repo: local
  hooks:
    - id: a1a-secret-scan
      name: A1A secret scanner (worktree)
      entry: python scripts/audit/validate_phase_a0_1r.py
      language: system
      pass_filenames: false
      stages: [pre-commit]
```

### CI step

```yaml
# .github/workflows/audit.yml (target Gate 2)
- name: Secret scan (git object database)
  run: python scripts/audit/a1a_gate0_scan_git_objects.py
```

Both deferred to Gate 2 to avoid touching CI config in Gate 1.

---

## §5. Test coverage

| Test | What it verifies |
|---|---|
| `validate_phase_a0_1r.py` `check_no_secret_in_worktree` | Worktree is clean of fingerprint |
| `run_negative_fixtures_a0_1r.py` NF12 | Injecting fingerprint into tracked file → check FAILS |
| `a1a_gate0_scan_git_objects.py` | All 8 substrings scanned; output JSON written |

No new tests added in Gate 1 — the existing coverage is sufficient.

---

## §6. Operator runbook

### Local scan (before commit)

```bash
$ python scripts/audit/validate_phase_a0_1r.py
=== Phase A0.1R Validator V3 ===
  ...
  [PASS] worktree.no_secret: no plain-text secret in tracked files
  ...
```

### Full history scan (audit time)

```bash
$ python scripts/audit/a1a_gate0_scan_git_objects.py
Scanning all git objects for compromised secret substrings...
Total blob objects in database: 3659
...
VERDICT: PARTIAL_BLOCKED_BY_SECRET_PRESENT_IN_GIT_OBJECT_DATABASE
# (expected: 1 hit on immutable Commit B blob — see §2 above)
```

### Interpreting PARTIAL_BLOCKED

The scanner exits non-zero when ANY hit is found. Charter §6.2
allows partial-block state when:
- (a) residual blob is from immutable historical commit ✅
- (b) chars 17-48 absent ✅
- (c) credential DB-invalidated ✅
- (d) residual disclosed ✅ (A1A-G0-D01)

All four conditions met → charter allows proceeding.

---

End of Secret Scanner.
