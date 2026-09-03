=== SCATTERED_EVIDENCE_DISPOSITION.md ===
Date: 2026-07-21 (Gate 4R-I.0 / pre Gate 4R-I.1 merge)

5 untracked files in main worktree were blocking the no-ff merge
because the 4R branch carries canonical versions at the same paths.

## Hash comparison

| Path | Main untracked SHA | 4R canonical SHA | Disposition |
|---|---|---|---|
| gate4r_diff/baseline_only_nodeids.txt | e3b0c44... (empty) | e3b0c44... (empty) | DUPLICATE → delete |
| gate4r_diff/common_nodeids.txt | b041739... | 5123318... | UNIQUE (3591 lines, different content) → ARCHIVE then delete |
| gate4r_diff/gate4_only_nodeids.txt | c526c72... | 94c3195... | UNIQUE (77 lines, different content) → ARCHIVE then delete |
| reports/.../evidence-freeze/GATE4R_GIT_STATE.txt | a472b7d... | a472b7d... | DUPLICATE → delete |
| reports/.../evidence-freeze/SHA256SUMS | df07db2... | df07db2... | DUPLICATE → delete |

## Archive procedure

Two unique files copied to:
- reports/phase-a1a/integration/evidence/scattered-evidence-pre-merge/gate4r_diff__common_nodeids__main-untracked.txt
- reports/phase-a1a/integration/evidence/scattered-evidence-pre-merge/gate4r_diff__gate4_only_nodeids__main-untracked.txt

These represent an earlier iteration of the 4R node-ID diff that was
computed in the main worktree BEFORE switching to the dedicated
remediation worktree. They may have used a different collection order
or node-ID normalization. Preserved as historical evidence.
