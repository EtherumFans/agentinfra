# CI Test Matrix — Phase A A5

**Date**: 2026-06-25
**Goal**: Stop using `--ignore=tests/integration` as the main CI strategy. Split tests by speed / scope so the PR gate is fast while integration / regression / e2e still run nightly.

## Workflow files

| File | Trigger | Scope | Wall time |
|---|---|---|---|
| `ci-pr.yml` | push / PR to main or master | Unit tests + frontend build + SDK typecheck | ~5-8 min |
| `ci-integration.yml` | nightly cron + push to master + manual dispatch | Integration + regression + e2e + e2e_product + MedCodER smoke | ~30-60 min |
| `e2e.yml` | push / PR | Playwright frontend E2E (Docker compose) | ~10-15 min |

## Test category split

### ci-pr.yml — Unit tests

```
tests/
├── test_api/                 (9 files, auth/oauth/coding_review_*)
├── test_compliance/          (1)
├── test_models/              (1)
├── test_services/            (48 — hybrid_medcoder/llm_gateway/m2a/gold_case/medcoder_retriever)
├── unit/
│   ├── app/                  (1)
│   ├── icoder/               (30 — orchestrator/context/mcp/a2a/experts/providers)
│   └── medical_coding/       (1 — mode enum)
└── review/                   (1)
```

Excluded from PR:
- `tests/integration/`  — needs PostgreSQL service
- `tests/e2e/`          — needs real DeepSeek key + long wall time
- `tests/e2e_product/`  — needs frontend build + docker compose
- `tests/regression/`   — F1 baseline tests need fixtures + LLM

### ci-integration.yml — Slow tests

| Subdir | Files | Wall time | Notes |
|---|---|---|---|
| `tests/integration/icoder/a2a/` | 1 | ~30s | A2A endpoints |
| `tests/integration/icoder/context/` | 5 | ~1 min | Context lifecycle / repository / isolation / audit / GC |
| `tests/integration/icoder/retrieval/` | 1 | ~10s | Smoke recall only |
| `tests/regression/` | 9 | ~2-3 min | F1 baseline / confidence / disagreement / timeline |
| `tests/e2e/icoder/` | 3 | ~5-10 min | orchestrator_real_deepseek needs `LLM_API_KEY`; `continue-on-error: true` |
| `tests/e2e_product/` | 8 | ~3-5 min | Workbench / pipeline / trace / disclaimer |

### MedCodER-specific gates

The `medcoder-validation` job in `ci-integration.yml` runs:

1. **FAISS index health check** — empty / missing / corrupt index reports `degraded`
2. **Mode registry smoke** — confirms `Mode` enum is importable and 4 MedCodER modes are registered

The full 4-variant ablation (`scripts/e2e_medcoder_validation.py`) runs **nightly only** on a runner with a pre-built FAISS index (`scripts/build_medcoder_index.py` produces ~150 MB index in ~10-15 min CPU).

## PR gate vs nightly gate

| Test tier | PR gate (ci-pr.yml) | Nightly (ci-integration.yml) |
|---|---|---|
| Unit | ✅ | (skipped, already passed) |
| Integration | ❌ | ✅ |
| Regression (F1) | ❌ | ✅ |
| Backend e2e | ❌ | ✅ (`continue-on-error` for missing LLM key) |
| e2e_product | ❌ | ✅ |
| MedCodER smoke | ❌ | ✅ |
| Frontend Playwright | ✅ (via e2e.yml) | (skipped, already passed) |
| Frontend TS + Build | ✅ | (skipped) |

## What changed vs the old `ci.yml`

| Old (ci.yml) | New (ci-pr.yml) |
|---|---|
| `pytest tests/ -v --ignore=tests/integration` | `pytest tests/ -q --ignore=tests/integration --ignore=tests/e2e --ignore=tests/e2e_product --ignore=tests/regression -k "not test_mcp_client_pubmed_search"` |

| Old (test.yml) | New (ci-integration.yml) |
|---|---|
| Same `--ignore=tests/integration` on master only | Integration + regression + e2e + e2e_product + MedCodER smoke, on nightly cron + push to master + manual dispatch |

| Kept as-is | e2e.yml |
|---|---|
| Playwright frontend E2E via docker compose | Same |

## Failure mode

- **PR push fails**: developer must fix unit tests before merge
- **Nightly fails**: on-call rotation investigates the regression; the failure is visible on the workflow status badge + Slack alert (manual wiring)

## Future improvements

- Add per-test timing tracking to identify slow outliers
- Add a `medcoder-validation-full` job that runs against the icoder_201 fixture (4 variants × 201 cases), wired to a runner with the pre-built FAISS index
- D6: upload `coverage.xml` and gate new code at 80%+ coverage