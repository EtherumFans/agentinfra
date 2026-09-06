# CI evidence integrity

## Evidence levels

- PR CI runs frontend Vitest, TypeScript and production build, alongside the
  existing backend, PHI/RLS, contract and SDK gates. The existing frontend job
  name is retained to avoid breaking required-check settings. JUnit evidence is
  uploaded even after failure; a missing report fails the upload.
- Agent Hub offline contracts run without provider credentials. A separate
  live job runs only when a credential is available. Without one, GitHub shows
  the live job as **skipped**, not a successful live-E2E job.
- The always-running Integration evidence summary records `passed`,
  `not_executed`, or `failed` for live E2E, plus commit, run ID and attempt.
  Missing credentials do not fail ordinary offline CI, but `not_executed`
  is explicitly ineligible for release evidence. Failures and cancellations
  cannot be downgraded to a credential skip.
- MedCodER's registry/index smoke is labelled as such: it does not execute
  clinical cases or prove model quality. Default pytest still excludes
  `heavy`, `retrieval` and `infra` tests. Individual suite skips remain visible
  in pytest output; this change does not claim all tests were executed.

## Release Candidate prerequisites

Before any package build, `verify_release_ci_evidence.py` reads GitHub Actions
with **Actions: read** only. For the exact release SHA it requires:

1. `ci-pr.yml`: all required jobs successful, including the named frontend
   unit-test step. A historical build-only frontend check is insufficient.
2. `ci-integration.yml`: Integration, offline contracts, the real 26-Agent
   happy/adversarial/stability/semantic-bundle steps and evidence summary
   successful. A skipped live job blocks release.
3. `e2e.yml`: Playwright's actual test step successful.

Only same-repository `push`, `schedule` and `workflow_dispatch` runs qualify;
PR/fork runs do not. The newest eligible run must pass: the checker never
searches backwards for an older green run after a newer failure. Job lookup
uses GitHub's `filter=latest` so rerun-failed-jobs can reuse the successful
executions from the same workflow run. A changing attempt is rejected.
Pagination and transient network retries are bounded; unavailable evidence
fails closed rather than being treated as a pass.

The resulting `release-ci-evidence.json` records SHA, workflow runs, attempts,
jobs, required steps and links, but no credentials or clinical payloads. RC
assembly revalidates this artifact's commit and required entries and includes
it and frontend JUnit in the SHA-256 release manifest. This is CI provenance,
not a cryptographic attestation or clinical/production approval.

## Operator sequence

1. Run ordinary CI on the intended commit; workflow dispatch is available for
   PR CI, Integration and Playwright if another run is needed.
2. Provision an authorized temporary provider credential through the repository
   secret mechanism, never in a command argument or chat. Re-run Integration on
   the same commit and verify the live job and its semantic bundle succeeded.
3. Dispatch Release Candidate on that commit/ref (or its `rc-v*` tag). Missing,
   stale, skipped or failed required evidence blocks package assembly.
4. Inspect the evidence and release manifest. This workflow remains build-only:
   it does not publish registries, deploy, or grant clinical approval.

This implementation task does not itself invoke a real model or publish a
release. Credentials, independent clinical gold, cloud operations and hospital
acceptance remain separately authorized gates.

## Local contract tests

```text
python -m pytest -q tests/test_ci_evidence.py tests/test_release_candidate_validator.py
```

Tests cover skip/failure distinctions, newer failed runs, wrong SHA/repository,
missing jobs/steps, pagination, API failure behavior, artifact revalidation and
workflow wiring. GitHub behavior follows the official
[workflow jobs](https://docs.github.com/en/rest/actions/workflow-jobs) and
[workflow runs](https://docs.github.com/en/rest/actions/workflow-runs) APIs.

## Implementation verification (2026-09-06)

- CI evidence and existing release-validator contracts: 53 passed.
- Isolated Agent Hub adversarial, semantic-bundle, runtime-matrix, safety and
  deployment-preflight tests: 33 passed (`--noconftest`, no application DB fixture).
- Static deployment preflight: passed, no failed checks.
- Frontend Vitest: 25 files, 177 passed; JUnit generated. TypeScript and Vite
  production build passed, with existing mixed static/dynamic import warnings.
- Read-only GitHub negative probe against master `4cd6065159db2f514fd3cac3f59c1d2e1ffb7458`:
  blocked as expected because its historical frontend job has no unit-test step.
- Local tooling was Python 3.12 and Node 24. These results do not replace a
  fresh GitHub-hosted run on the workflow's Python/Node versions. No live model,
  production database, registry publication or deployment was invoked.
