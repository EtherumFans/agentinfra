#!/usr/bin/env bash
# Phase A0.1 Gate 9 - Safe Commit + Annotated Tag
#
# Stages two commits on master + creates annotated tag audit/phase-a0.1-baseline.
# Does NOT push. Does NOT use 'git add -A'. Does NOT modify product code.
#
# Pre-conditions (verified by the script):
#   1. HEAD == c147d015455017bc1d8420cbdbd813b3b8ec23ce (Trusted commit)
#   2. scripts/audit/validate_phase_a0_1.py exits 0
#   3. Branch == master
#
# Post-conditions:
#   - Commit A "audit/phase-a0.1: audited product snapshot (Bucket A)"
#     contains ~70 product + migration + test + partner-app files
#   - Commit B "audit/phase-a0.1: audit package (Bucket B)"
#     contains the comprehensive-audit/phase-a0.1/ + scripts/audit/
#   - Annotated tag `audit/phase-a0.1-baseline` on Commit B HEAD
#
# Bucket C (Unsafe) is NEVER added:
#   - backend/.env (gitignored)
#   - examples/partner-reference-app/.env (gitignored)
#   - .audit-chrome-profile/ (gitignored)
#   - *.png at repo root (must be moved or deleted by user before push)
#
# Bucket D (Ambiguous) is DEFERRED:
#   - packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz
#   - packages/icoder-embedded/icoder-embedded-2.0.0.tgz
#   - packages/icoder-sdk/dist/ (7 files)
#   - phase7-external-consumer/dist/
#   These need a per-file reproducibility decision before they can join Commit A.
#   Tracked in reports/comprehensive-audit/phase-a0.1/A0_1_09_BUCKET_D_DEFERRED.md.
#
# Usage:
#   bash scripts/audit/stage_phase_a0_1_commit.sh          # stage + commit + tag
#   bash scripts/audit/stage_phase_a0_1_commit.sh --dry-run # print commands, don't execute

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

TRUSTED_HEAD="c147d015455017bc1d8420cbdbd813b3b8ec23ce"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "=== Phase A0.1 Gate 9 - Safe Commit ==="
echo "Repo: $REPO_ROOT"
echo "Mode: $([[ $DRY_RUN == 1 ]] && echo 'DRY-RUN' || echo 'EXECUTE')"
echo

# --- Pre-condition checks ---
echo "[1/5] Pre-condition checks..."

CURRENT_HEAD="$(git rev-parse HEAD)"
if [[ "$CURRENT_HEAD" != "$TRUSTED_HEAD" ]]; then
    echo "FAIL: HEAD drift. Expected $TRUSTED_HEAD, got $CURRENT_HEAD"
    exit 1
fi
echo "  HEAD = $TRUSTED_HEAD  OK"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "master" ]]; then
    echo "FAIL: not on master (on $BRANCH)"
    exit 1
fi
echo "  branch = master  OK"

echo "  running validator..."
if ! python scripts/audit/validate_phase_a0_1.py > /tmp/a0_1_validator.log 2>&1; then
    echo "FAIL: validator did not pass. Log:"
    cat /tmp/a0_1_validator.log
    exit 1
fi
echo "  validator PASS (55/55 checks)  OK"

# --- Bucket A: Audited Product ---
echo
echo "[2/5] Bucket A - Audited Product staging..."

BUCKET_A_FILES=(
    # A1. Modified backend code (9 files)
    backend/app/api/agent_run.py
    backend/app/api/embedded.py
    backend/app/api/platform_api_clients.py
    backend/app/api/usage.py
    backend/app/main.py
    backend/app/middleware/auth.py
    backend/app/models/__init__.py
    backend/app/models/oauth.py
    backend/app/models/run_history.py
    # A2. Modified tests (2 files)
    backend/tests/conftest.py
    backend/tests/test_api/test_phase4f_agent_run.py
    # A3. New backend code (Phase 7) - migrations + services + middleware + models + api
    backend/alembic/versions/012_idempotency_records.py
    backend/alembic/versions/013_run_history_status_and_cancel.py
    backend/alembic/versions/014_api_client_attribution_and_origins.py
    backend/alembic/versions/015_preview_sessions.py
    backend/app/api/examples.py
    backend/app/api/preview_sessions.py
    backend/app/api/runs.py
    backend/app/middleware/partner_cors.py
    backend/app/models/idempotency_record.py
    backend/app/models/preview_session.py
    backend/app/services/idempotency_service.py
    backend/app/services/preview_ticket.py
    backend/app/services/run_lifecycle.py
    backend/app/services/trace_token.py
    # A4. New backend tests (Phase 7)
    backend/tests/test_api/test_phase7_gate1_examples_mount.py
    backend/tests/test_api/test_phase7_gate3_agent_run_idempotency.py
    backend/tests/test_api/test_phase7_gate4_run_cancel.py
    backend/tests/test_api/test_phase7_gate5_api_clients.py
    backend/tests/test_api/test_phase7_gate6_cors.py
    backend/tests/test_api/test_phase7_gate7_trace_token.py
    backend/tests/test_api/test_phase7_gate8_usage_api_client.py
    backend/tests/test_api/test_phase7_gate9_sse_run_events.py
    backend/tests/unit/app/api/test_phase7_gate13a_audit.py
    backend/tests/unit/app/api/test_phase7_gate13a_preview_html.py
    backend/tests/unit/app/api/test_phase7_gate13a_preview_sessions.py
    backend/tests/unit/app/services/test_phase7_gate13a_preview_ticket.py
    backend/tests/unit/app/services/test_phase7_gate3_idempotency.py
    # A5/A6. Frontend
    frontend/src/pages/EmbeddedAssistantPage.tsx
    frontend/src/App.tsx
    frontend/src/components/layout/Layout.tsx
    frontend/src/i18n/locales.ts
    frontend/tests/e2e/phase5_a4_embedded.spec.ts
    # A7. packages/icoder-embedded
    packages/icoder-embedded/dist/icoder-assistant.d.ts
    packages/icoder-embedded/dist/icoder-assistant.js
    packages/icoder-embedded/package.json
    packages/icoder-embedded/src/icoder-assistant.ts
    packages/icoder-embedded/demos/cdi-demo.html
    packages/icoder-embedded/demos/config.example.js
    packages/icoder-embedded/demos/drg-dip-demo.html
    packages/icoder-embedded/demos/medical-coding-demo.html
    packages/icoder-embedded/demos/README.md
    # A8. packages/icoder-sdk
    packages/icoder-sdk/README.md
    packages/icoder-sdk/package.json
    packages/icoder-sdk/src/client.ts
    packages/icoder-sdk/src/index.ts
    packages/icoder-sdk/src/resources/agents.ts
    packages/icoder-sdk/src/resources/billing.ts
    packages/icoder-sdk/src/resources/compliance.ts
    packages/icoder-sdk/src/resources/facts.ts
    packages/icoder-sdk/src/resources/oauth.ts
    packages/icoder-sdk/src/resources/reviews.ts
    packages/icoder-sdk/src/resources/textgen.ts
    packages/icoder-sdk/src/resources/runs.ts
    packages/icoder-sdk/tsconfig.json
    # A9. Deletion
    packages/icoder-sdk/package-lock.json
    # A10. Partner app
    examples/partner-reference-app/.env.example
    examples/partner-reference-app/package-lock.json
    examples/partner-reference-app/package.json
    examples/partner-reference-app/README.md
    examples/partner-reference-app/server.js
    examples/partner-reference-app/views/index.ejs
    # A11. External consumer harness
    phase7-external-consumer/build.mjs
    phase7-external-consumer/entry.mjs
    phase7-external-consumer/package.json
    phase7-external-consumer/package-lock.json
    phase7-external-consumer/smoke.mjs
    phase7-external-consumer/tsconfig.json
    phase7-external-consumer/types-test.ts
    # A12. Deprecated markers
    packages/icoder-web/DEPRECATED.md
    packages/web-components/DEPRECATED.md
    web-components/DEPRECATED.md
)

if [[ $DRY_RUN == 1 ]]; then
    echo "  (dry-run) git add ${BUCKET_A_FILES[*]}"
else
    git add -- "${BUCKET_A_FILES[@]}"
    # Deletion
    git rm --cached packages/icoder-sdk/package-lock.json 2>/dev/null || true
    # Partner app public dir if exists
    git add examples/partner-reference-app/public/ 2>/dev/null || true
fi
STAGED_A=$(git diff --cached --name-only | wc -l)
echo "  staged $STAGED_A files for Commit A"

# --- Commit A ---
echo
echo "[3/5] Commit A..."

COMMIT_A_MSG="$(cat <<'EOF'
audit/phase-a0.1: audited product snapshot (Bucket A)

Phase A0.1 Gate 9 Commit A. Stages the product substrate that Phase A0
and Phase A0.1 audit opines about. Read-only with respect to the audit:
no product code was modified during Phase A0.1; this commit only anchors
the working tree state that the audit already reviewed.

Bucket A contents (per Phase A0.1 Gate 1 classification):
- 9 modified backend code files
- 2 modified backend tests
- 4 new alembic migrations (012/013/014/015)
- 10 new backend services + middleware + models + api files
- 13 new backend tests for Phase 7 Gates 1-13A
- 1 new frontend page (EmbeddedAssistantPage)
- 4 modified frontend files
- 5 new packages/icoder-embedded demo files + 4 modified dist/src/pkg
- 11 modified packages/icoder-sdk files + 1 new (runs.ts)
- 1 deletion (packages/icoder-sdk/package-lock.json)
- 6 partner-reference-app files (env.example + 5 source files)
- 7 phase7-external-consumer harness files
- 3 new DEPRECATED.md markers

Bucket D (tarballs + dist/ outputs) is DEFERRED. See
reports/comprehensive-audit/phase-a0.1/A0_1_09_BUCKET_D_DEFERRED.md
for the per-file reproducibility decision matrix.

Validator: PASS_PHASE_A0_1_SEMANTIC_VALIDATOR_V2 (55/55 checks).

Trusted HEAD at staging: c147d015455017bc1d8420cbdbd813b3b8ec23ce

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

if [[ $DRY_RUN == 1 ]]; then
    echo "  (dry-run) git commit -m \"...\""
else
    git commit -m "$COMMIT_A_MSG"
fi

# --- Bucket B: Audit-Only ---
echo
echo "[4/5] Bucket B - Audit Package staging..."

# Bucket B = all reports/comprehensive-audit/phase-a0.1/ + new scripts/audit/ files
# These reference Bucket A but are themselves metadata.
if [[ $DRY_RUN == 1 ]]; then
    echo "  (dry-run) git add reports/comprehensive-audit/phase-a0.1/"
    echo "  (dry-run) git add reports/comprehensive-audit/evidence/git/phase_a0_commands/"
    echo "  (dry-run) git add scripts/audit/validate_phase_a0_1.py"
    echo "  (dry-run) git add scripts/audit/build_parity_v2_2.py"
    echo "  (dry-run) git add scripts/audit/build_maturity_v2.py"
    echo "  (dry-run) git add scripts/audit/stage_phase_a0_1_commit.sh"
else
    git add reports/comprehensive-audit/phase-a0.1/
    git add reports/comprehensive-audit/evidence/git/phase_a0_commands/
    git add scripts/audit/validate_phase_a0_1.py
    git add scripts/audit/build_parity_v2_2.py
    git add scripts/audit/build_maturity_v2.py
    git add scripts/audit/stage_phase_a0_1_commit.sh
fi
STAGED_B=$(git diff --cached --name-only | wc -l)
echo "  staged $STAGED_B files for Commit B"

# --- Commit B ---
echo
echo "[5/5] Commit B + annotated tag..."

COMMIT_B_MSG="$(cat <<'EOF'
audit/phase-a0.1: audit package (Bucket B) + immutable baseline freeze

Phase A0.1 Gate 9 Commit B. The audit-repair deliverables themselves.

Supersedes (but does NOT modify) reports/comprehensive-audit/phase-a0/.
The Phase A0 audit package is preserved as audit trail; Phase A0.1
provides corrected V2 versions of every Phase A0 artifact:
- evidence_manifest.v2_1.json (27 real SHA-256 captures; 9 honest NOT_CAPTURED)
- evidence_manifest.public.json (redacted view, no PII, no secrets)
- issue_ledger.v2.json (91 raw → 86 canonical → 79 open; machine-derived)
- parity_matrix_v2_2.json (59 dimensions; 9 ICODER_ADVANTAGE downgrades;
  A-05 field typo fixed; thresholds enforced)
- product_maturity_v2.json (16 scenarios × 5 axes; CN-01 L8 regraded to
  code=L4 + quality=SMOKE_ONLY; CN-02 OPEN_LOOP explicit)
- gate0_findings.json (machine-readable findings for cross-reference)

Plus 9 gate reports documenting:
- Gate 0: 16 required findings reproducing Phase A0 semantic failures
- Gate 1: 4-bucket classification of 97 working-tree entries
- Gate 2: canonical manifest repair (16 placeholders resolved)
- Gate 3: issue ledger normalization (75/82/91 inconsistency retired)
- Gate 4: parity matrix V2.2 (51-dimension claim corrected to 59)
- Gate 5: product maturity V2 (multi-axis; L8 overclaim regraded)
- Gate 6: Gate 13A security evidence regrading (E7 → E1 for A0-P0-018/019)
- Gate 7: roadmap V2 (forbidden verdicts removed; A1 scope 23 → 19)
- Gate 8: semantic validator V2 (6 passes, 55 checks, 0 FAIL)

scripts/audit/validate_phase_a0_1.py is the canonical machine-verifier.
Exit code 0 = PASS; required pre-condition for any Phase A1 start.

This commit + the annotated tag audit/phase-a0.1-baseline establish
the REPRODUCIBLE_AUDITED_PRODUCT_BASELINE that Phase A0.1 §一 requires.

NO push. NO npm publish. NO PR. Per Phase A0.1 §六.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

if [[ $DRY_RUN == 1 ]]; then
    echo "  (dry-run) git commit -m \"...\""
    echo "  (dry-run) git tag -a audit/phase-a0.1-baseline -m \"...\""
else
    git commit -m "$COMMIT_B_MSG"
    git tag -a audit/phase-a0.1-baseline -m "$(cat <<'EOF'
Phase A0.1 - Audit Repair and Immutable Baseline Freeze

Establishes the REPRODUCIBLE_AUDITED_PRODUCT_BASELINE required for
Phase A1 entry.

Verdict: PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1

Validator: PASS_PHASE_A0_1_SEMANTIC_VALIDATOR_V2 (55/55 checks).
Issue ledger: 86 canonical / 79 open (machine-derived).
Parity matrix: 59 dimensions (machine-derived).
Product maturity: 16 scenarios × 5 axes; 0 at L7+; 0 with formal benchmark.
Roadmap: A1=19 P0 / A2=22 P1 + 4 P0-commercial-deferred / A3=27 P2 / A4=11 P3.

Phase A0 v1 PASS_PHASE_A0_* verdict REFUTED (7 findings in Gate 0).
Phase A0 v1 artifacts PRESERVED (not modified) as audit trail.

NO push. NO npm publish. NO PR. Local freeze only.
EOF
)"
fi

echo
echo "=== Gate 9 complete ==="
if [[ $DRY_RUN == 0 ]]; then
    git log --oneline -3
    echo
    git tag -l 'audit/phase-a0.1*'
    echo
    echo "Tag points at: $(git rev-list -n 1 audit/phase-a0.1-baseline)"
fi
