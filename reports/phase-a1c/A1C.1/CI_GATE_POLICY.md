# A1C.1 — CI Gate Policy

**Effective date**: 2026-07-25
**Scope**: All A1C sub-gate commits (A1C.1..A1C.9) must pass this policy. A1C.0 charter audit was exempt (no test modifications).

---

## §1 Hard CI gates (blocking)

A commit is **BLOCKED** from entering A1C history if any of the following fail:

| Gate | Command | Required result | Rationale |
|------|---------|-----------------|-----------|
| G-01 | `cd backend && python -m pytest tests/ --tb=short` | exit 0 (no failures, no errors) | Backend regression baseline |
| G-02 | `cd frontend && npm run typecheck` (tsc) | exit 0 | Frontend type safety |
| G-03 | `cd frontend && npm run build` | exit 0 | Frontend production build |
| G-04 | `cd frontend && npm run test` (vitest) | exit 0 | Frontend unit/contract tests |
| G-05 | `cd frontend && npx playwright test --reporter=line` (a1c subset) | exit 0 | Browser journey smoke (per A1C.8 spec) |
| G-06 | `git diff --check` | exit 0 | No whitespace errors |
| G-07 | ESLint (post-A1C.1 introduction) | exit 0 with ≤0 errors (warnings permitted) | Code quality baseline |
| G-08 | Secret scan (`scripts/a1c_secret_scan.py` to be added in A1C.5) | 0 leaks | No secrets in tree |

---

## §2 Audit gates (non-blocking but tracked)

These metrics must be **audited** before each commit. A change requires explicit justification in commit message body.

| Audit | Tool | Allowed delta |
|-------|------|---------------|
| A-01 Test collection count | `pytest --collect-only -q \| tail -1` | Increase or no-change. **Decrease requires explicit justification** (test deletion forbidden by §六/6.1). |
| A-02 Skipped / xfail count | `pytest --collect-only -q \| grep -c SKIP` | No increase unless explicit `pytest.skip(rationale)` with comment. |
| A-03 New `failed` count | Run full suite | Must be ≤ previous baseline (target: 0). |
| A-04 New `error` count | Same | Must be ≤ previous baseline (target: 0). |
| A-05 Coverage delta (future) | `pytest --cov` | TBD in A1C.6. |

---

## §3 Forbidden practices (per Charter §六 + PDF §十五)

A commit is **REJECTED** if any of the following are detected in the diff:

| ID | Forbidden practice | Detection |
|----|-------------------|-----------|
| F-01 | `git add -A` / `git add .` / `git commit -a` | Manual review of `git show --stat <commit>`: every file in commit must trace to explicit `git add <path>` |
| F-02 | Deleting failing tests | Diff hunk must not delete `def test_*` without replacement |
| F-03 | Adding `@pytest.mark.skip` without rationale | `git diff` must include `# A1C.1 deferral: <reason>` comment |
| F-04 | `@pytest.mark.xfail` without reason string | Same |
| F-05 | Narrowing test scope (e.g., removing params from `@pytest.mark.parametrize`) | Diff inspection |
| F-06 | Replacing real call with `unittest.mock.MagicMock` for charter-required real calls (KMS / DeepSeek / SSO in A1C.5 / A1C.4) | Manual review |
| F-07 | Excluding test files from collection via `pyproject.toml` / `conftest.py` `collect_ignore` | Diff inspection |
| F-08 | Modifying `pyproject.toml [tool.pytest]` to loosen collection | Diff inspection |
| F-09 | Marking Env-blocked tests as PASS in evidence | Manual review |

---

## §4 Integration profile (per PDF A1C.1)

Tests requiring external services (PostgreSQL / DeepSeek live / KMS / SSO / real HIS) must be **separated** into an integration profile so they do not pollute the default CI signal.

**Profile structure** (proposed, to be implemented in A1C.2..A1C.5):

```
backend/
├── tests/
│   ├── unit/                 # default profile — must PASS on every commit
│   ├── integration/          # default profile — must PASS on every commit (uses SQLite/local mocks)
│   └── integration_cloud/    # INTEGRATION PROFILE — only runs with ICODER_CLOUD_PROFILE=1
│       ├── test_postgres_migration.py        # A1C.2
│       ├── test_deepseek_live.py             # A1C.5
│       ├── test_kms_live.py                  # A1C.5
│       ├── test_sso_real_idp.py              # A1C.4
│       └── test_his_emr_real.py              # A1C.3
└── pyproject.toml            # add marker: cloud_integration
```

**CI invocation**:
- Default CI: `pytest tests/` (skips `integration_cloud/`)
- Cloud CI (when env available): `pytest tests/ -m cloud_integration`

---

## §5 Quarantine policy

For pre-existing failures that A1C.1 cannot immediately fix, the **quarantine** mechanism is:

1. Add `@pytest.mark.quarantine("A1C.1 carryover: <root cause>")` to test
2. Register marker in `pyproject.toml`
3. Default pytest run skips quarantined tests
4. `pytest tests/ -m quarantine` re-runs only quarantined tests for status check
5. Quarantine entry must be created in `BASELINE_FAILURE_LEDGER.csv` with `target_gate=A1C.<n>` deferral

**Quarantine cap**: ≤ 10 tests at any point. Above 10 → A1C verdict forced to PARTIAL.

---

## §6 CI enforcement (proposed GitHub Actions workflow)

To be added in A1C.7 (deployment runbook phase). Local pre-commit enforcement via `scripts/a1c_pre_commit_check.py` (to be authored in A1C.1 commit).

---

## §7 Acceptance for A1C.1

| Condition | Status |
|-----------|--------|
| Full pytest run executed on post-merge HEAD | ✓ (Run 2: 53 fail / 1 err / 3895 pass / 14 skip) |
| All failures classified in `BASELINE_FAILURE_LEDGER.csv` | ✓ (54 nodes classified) |
| Root cause report generated | ✓ (this file) |
| Test collection diff documented | ✓ (`CI_TEST_COLLECTION_DIFF.json`) |
| CI gate policy defined | ✓ (this file) |
| Dev DB isolation plan documented | PARTIAL (see `DEV_DB_ISOLATION_REPORT.md`) |
| ESLint introduction plan documented | PARTIAL (see `ESLINT_INTRODUCTION_REPORT.md`) |
| P1 PRODUCT_DEFECT fixed | DEFERRED to A1C.1 follow-up commit |
| P2 SPEC_DRIFT bulk-fixed | DEFERRED to A1C.1 follow-up commit |
| P3 TEST_DEFECT bulk-fixed | DEFERRED to A1C.1 follow-up commit |

**A1C.1 verdict (this artefact)**: `PASS_A1C_1_BASELINE_AND_CI_GATE_POLICY_FILED_VERIFICATION_IN_PROGRESS`
