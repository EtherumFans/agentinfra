# Audit Gate 11 — Test / Performance / Deployment / Docs (Tracks L, N)

> Per PDF §三 Tracks L + N: audits the test pyramid (unit / integration / regression / e2e / product), performance benchmarks, deployment artifacts, runbooks, and documentation completeness. Determines whether iCoDer can be safely operated by a third-party on-call engineer and whether regressions will be caught before reaching production.

## L1. Test pyramid — 3,355 collected tests, 250 test files

### L1.1 Test inventory

`backend/tests/` directory structure:

| Category | Files | LOC avg | Purpose |
|----------|-------|---------|---------|
| `unit/` | 103 | ~80 | Pure-function tests, no DB, no LLM |
| `test_api/` | 54 | ~120 | API endpoint tests, mostly SQLite in-memory |
| `test_services/` | 53 | ~100 | Service-layer tests (LLMGateway, RuleEngine, etc.) |
| `integration/icoder/` | 20 | ~150 | DB + MCP + A2A + Context + Retrieval |
| `regression/` | 9 | ~200 | F1 baseline, confidence, disagreement, evidence |
| `e2e/icoder/` | 4 | ~250 | orchestrator_real_deepseek, a2a_e2e, throughput |
| `e2e_product/` | 2 | ~150 | homepage deprecation, evidence viewer kinds |
| `coding_runtime/` | 1 | ~80 | runtime dispatch |
| `test_comcurrency.py` | 1 | 126 | concurrent pipeline execution |
| `test_compliance/` | 2 | — | compliance rule engine |
| `test_models/` | 1 | — | DB model behavior |

**Total: 3,355 tests collected** (10 deselected by default per `addopts`).

### L1.2 Pytest markers + default skip behavior

`backend/pytest.ini`:

```ini
markers =
    heavy:      BGE-M3 + FAISS, OOM-prone on Windows CPU
    retrieval:  live FAISS + BGE-M3, slow
    slow:       >10s warm
    e2e:        full stack
    asyncio:    pytest-asyncio
    infra:      live uvicorn on :8765

addopts = -m "not heavy and not retrieval and not infra"
```

Marker counts (collected live):

```
default run        3,355 tests
heavy                       6 tests  (excluded by default)
retrieval                   6 tests  (excluded by default)
infra                       4 tests  (excluded by default)
slow                        0 tests  (no marker applied)
e2e                         0 tests  (marker defined but unused)
```

⚠️ `e2e` marker is defined but **never applied** to any test. The e2e test files exist (4 files in `tests/e2e/icoder/`) but they're collected as regular tests, not marked. Register as **G11-001 (P3)**: marker declared but unused — confusing for new engineers.

### L1.3 Real-LLM coverage — sparse

`tests/e2e/icoder/test_orchestrator_real_deepseek.py` is the only test that actually hits DeepSeek's API. It is in the `tests/e2e/` directory which is excluded from the PR-gate CI workflow (`ci-pr.yml` runs `--ignore=tests/e2e`).

CI coverage on PR:
- ✅ Unit tests (103 files)
- ✅ API tests (54 files)
- ✅ Service tests (53 files)
- ❌ Integration / regression / e2e — **deferred to nightly workflow**

`ci-integration.yml` runs nightly at 03:00 UTC + on master push + manual + labeled PR. So a PR can merge with broken integration / regression tests if the label-triggered job is not run.

### L1.4 Frontend tests — only 7 files

```
frontend/tests/e2e/*.spec.ts  — 7 Playwright E2E specs
frontend/tests/unit/          — 0 files (no Vitest unit tests in tests/)
```

The frontend has no unit tests. Playwright E2E only. Frontend relies entirely on:
- `npx tsc --noEmit` (type check) in PR gate
- `npx vite build` (build success) in PR gate
- Playwright E2E in `e2e.yml`

Register as **G11-002 (P2)**: frontend has 0 unit tests; 100% of frontend logic verification relies on Playwright E2E which is slow and brittle. No component test coverage.

## L2. Performance testing — one scripted-doubles throughput smoke

### L2.1 The throughput test

`backend/tests/e2e/icoder/test_orchestrator_throughput.py`:

```python
@pytest.mark.skipif(
    os.environ.get("ICODER_RUN_STRESS") != "1",
    reason="ICODER_RUN_STRESS=1 not set — skipping throughput smoke",
)
def test_orchestrator_100_sequential_calls_latency():
    """Drive 100 sequential InboundHandler.handle() calls against
    scripted test doubles (no real LLM, no real MedCodER). Reports
    P50/P95/P99 wall-clock per call.

    Phase 1 budgets: P95 < 500 ms / call on warm scripted doubles.
    Phase 2 budgets (with real MedCodER): TBD after warmup.
    """
    ...
```

- ✅ Real benchmark harness with P50/P95/P99 reporting
- ❌ Uses scripted doubles — **measures only orchestration overhead, not actual LLM latency**
- ❌ Requires `ICODER_RUN_STRESS=1` env var to even run (skipped by default)
- ❌ "Phase 2 budgets (with real MedCodER): TBD after warmup" — budget still undefined

### L2.2 No production latency budget

`docs/cloud/CLOUD_DEPLOYMENT.md §5 SLA`:

```
| Availability        | 99.5% (single region) / 99.9% (active-active, future) |
| P50 latency (coding run) | ≤ 8s (BGE-M3 cached) / ≤ 60s (cold) |
| P99 latency (coding run) | ≤ 120s |
| Data durability     | 99.999999% (S3-compatible)                          |
| RTO                 | ≤ 4h (single region) / ≤ 30min (active-active)      |
| RPO                 | ≤ 1h (single region) / ≤ 1min (active-active)       |
```

SLA targets are documented. But:

- ❌ No production latency tracking — the `token_tracker.py` is in-memory (G7-006)
- ❌ No production P50/P99 dashboard — `/api/usage` reports cost, not latency
- ❌ No alerting on SLA breach

Register as **G11-003 (P1)**: SLA targets are documented but no production observability exists to measure them. P99 ≤ 120s target cannot be verified post-deploy. The single real run visible in DB (admin, drg-analyzer, 9.1s) is one data point.

### L2.3 No load testing

- No locust / k6 / wrk configuration in the repo
- No load test scripts in `scripts/`
- The "throughput" test only does sequential calls, not concurrent
- `test_concurrency.py` exists but is a manual script (`python tests/test_concurrency.py`), not a pytest-collected benchmark

## L3. Deployment artifacts — local-dev only, no production

### L3.1 Docker Compose — local-dev only

`docker-compose.local-dev.yml`:

```yaml
# 用途: 本地开发 / CI e2e 测试。**绝不允许**用于生产部署或医院内网交付。
# 生产部署走 iCoDer 托管云 SaaS (Environment EU/US/CN):
#   https://{tenant_slug}.{region}.icoder.cloud
# 详见: docs/cloud/CLOUD_DEPLOYMENT.md
```

- ✅ Postgres 16 + backend + frontend services
- ✅ Bind-mount for `.data/pgdata`
- ❌ No TLS termination
- ❌ No production secrets handling
- ❌ No horizontal scaling (single replica per service)

### L3.2 Dockerfiles — basic

`backend/Dockerfile` + `frontend/Dockerfile` exist. Used by `docker-compose.local-dev.yml`. No multi-stage production build, no distroless variant, no SBOM generation.

### L3.3 Cloud deployment — DOCUMENTATION ONLY

`docs/cloud/CLOUD_DEPLOYMENT.md §7 Migration Path`:

```
本 cloud-flip 范围 (Phase 1):
- ✅ 文档翻转 (CLAUDE.md / README.md / 22 篇 docs)
- ✅ 部署 artifact 翻转 (config.py / docker-compose → local-dev / .env.cloud.example)
- ✅ 5 个 platform API stub 端点 (返 501 + doc-link)

Phase 2+ (out-of-scope, 已记录):
- ❌ team.py 加 org_id filter
- ❌ ICODER_ENVIRONMENT 真路由逻辑 (LLMGateway / DataPolicy 按 env branch)
- ❌ Stripe / 计费接线
- ❌ Env-region active-active failover
- ❌ Edge node PHI redaction 引擎 (in-hospital edge node)
- ❌ Platform API stub 端点的真实实现
```

The "cloud" story is **explicitly Phase 1 = docs only, Phase 2+ unimplemented**. 6 critical cloud features are documented as out-of-scope:

1. Org-scoped team management
2. Real region routing (LLM, data policy)
3. Billing integration (Stripe)
4. Multi-region failover
5. Edge-node PHI redaction (the "原始 PHI 不进云" promise)
6. Platform API stubs (5 endpoints return 501)

Register as **G11-004 (P0)**: cloud SaaS deployment is documentation-only. None of the 6 critical cloud features are implemented. The "iCoDer 托管云 SaaS" hero claim in CLAUDE.md is not backed by shippable deployment artifacts.

### L3.4 Region catalog — declarative but inert

`deploy/cloud/regions.yaml`:

```yaml
environments:
  - code: eu
    regions:
      - code: eu-frankfurt
        enabled: false  # Phase 2
      - code: eu-stockholm
        ...
```

**All regions are `enabled: false`**. The Phase 1 cloud-flip is documentation + config skeleton only.

## L4. CI/CD — 3 workflows, real but conservative

### L4.1 Workflow inventory

| File | Triggers | Coverage |
|------|----------|----------|
| `.github/workflows/ci-pr.yml` | push master/main + PR | Frontend tsc+build, backend unit, SDK tsc |
| `.github/workflows/ci-integration.yml` | nightly 03:00 UTC + master push + labeled PR + manual | Integration + regression + e2e + product |
| `.github/workflows/e2e.yml` | push master/main + PR + manual | Playwright E2E |

### L4.2 ci-pr.yml — fast gate

```yaml
backend-unit:
  steps:
    - python -m pytest tests/ -q
        --ignore=tests/integration
        --ignore=tests/e2e
        --ignore=tests/e2e_product
        --ignore=tests/regression
        -k "not test_mcp_client_pubmed_search"
```

- ✅ Fast (~2-3min)
- ✅ Python 3.11, pip cache
- ✅ Excludes the slow stuff

### L4.3 ci-integration.yml — comprehensive but optional

```yaml
on:
  schedule:
    - cron: "0 3 * * *"  # nightly
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
    types: [labeled]   # ← only on labeled PR
  workflow_dispatch:
```

- ✅ Postgres 16 service container
- ✅ Sets `ICODER_DATABASE_URL=postgresql+asyncpg://...`
- ✅ Runs the full test pyramid (integration + regression + e2e + product)
- ⚠️ PR trigger requires label → easy to skip

### L4.4 e2e.yml — Playwright with local-dev docker

```yaml
- name: Start docker compose (local-dev only)
  run: |
    docker compose -f docker-compose.local-dev.yml up -d --build
    for i in $(seq 1 30); do
      if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "Backend healthy after ${i}s"
        break
      fi
      sleep 2
```

- ✅ Real backend start, real Playwright
- ✅ Health-check loop before tests
- ❌ 15min timeout — tight for cold start + browser install

### L4.5 No release pipeline

- No `release.yml` workflow
- No git tag → PyPI / npm publish step (matches G8-001 — packages not on npm)
- No semantic version bump automation
- No changelog generation

Register as **G11-005 (P2)**: no release automation. Every "release" is a manual `git push` to master.

## L5. Documentation — large but fragmented, 379 markdown files

### L5.1 Documentation inventory

```
$ find docs -name "*.md" | wc -l
379
```

By directory:

| Dir | Files | Purpose |
|-----|-------|---------|
| `docs/corti_parity/` | 87 | Corti-vs-iCoDer comparison reports |
| `docs/archive/` | 63 | Historical / superseded |
| `docs/phase_cycles/` | 44 | Phase-by-phase retrospective |
| `docs/corti-reverse-engineered/` | 33 | Corti API/SDK reverse engineering |
| `docs/operation-manual/` | 23 | Page-by-page user manual |
| `docs/phase3/` | 21 | Phase 3 design notes |
| `docs/reverse_engineering/` | 18 | More Corti research |
| `docs/architecture/` | 18 | RFC + design docs |
| `docs/phase2/` | 6 | Phase 2 design |
| `docs/cloud/` | 4 | Cloud deployment (this is the deployment surface) |
| `docs/audit/` | 1 | The audit spec itself |

### L5.2 README.md — claims vs reality

`README.md` line 1:

```
# iCoDer — Clinical AI Platform

Corti-competitive 临床 AI 平台。Agent Runtime + 编码审核 + 语音转录 + 文书生成 + 事实提取 + 嵌入助手，即开即用。
```

- ✅ Clear positioning
- ❌ "语音转录" — speech-to-text is **DEAD** per G2-004 / G3-003 (route removed, orphan component)
- ❌ "即开即用" (ready out of the box) — false per Gate 9 (committed SECRET_KEY=change-me, DEBUG=true), Gate 11 (cloud deployment Phase 1 = docs only)
- ❌ "Every decision chain is SHA-256 verifiable" — `run_trace_events` table is empty per G7-001

### L5.3 Operation manual — comprehensive page-by-page

`docs/operation-manual/01-HomePage.md` through `20-Support.md` — 20 files covering every Console page. This is real, useful documentation.

⚠️ No equivalent "Operations Runbook" for backend / on-call engineers. The closest thing is `docs/dev/BACKEND_RECOVERY.md` (recovery from backend failures). No:
- Incident response playbook
- On-call escalation matrix
- Backup/restore procedures (despite SLA claims)
- Database migration rollback guide
- Secret rotation runbook

Register as **G11-006 (P2)**: no ops runbook. Hospital pilots require documented incident response, backup/restore, and secret rotation procedures. SLA targets in CLOUD_DEPLOYMENT.md are unbacked by runbooks.

### L5.4 Architecture docs — partially deprecated

`docs/ARCHITECTURE.md`:

```
> **DEPRECATED (Phase 2-F / 2026-07-02 — TD-099)**: 本文档为旧版架构描述, 已被新版替代.
> 当前主线参考: docs/architecture/CURRENT_ARCHITECTURE.md + docs/phase2/MAINLINE_VS_LEGACY.md
```

The root `ARCHITECTURE.md` is explicitly deprecated. 18 RFC / design docs live under `docs/architecture/` but no single canonical "current architecture" doc.

### L5.5 The audit spec itself is in the repo

`docs/audit/icoder_comprehensive_product_audit.txt` — the 42-page audit prompt that drives this very audit. This is good (self-documenting) but also means the audit is being run against a target that has known issues.

## L6. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G11-001** | P0 | deploy-artifacts | Cloud SaaS deployment is **documentation-only**. `CLOUD_DEPLOYMENT.md §7` explicitly lists 6 critical cloud features as out-of-scope (region routing, billing, failover, edge PHI, real platform APIs, org-scoped team). `deploy/cloud/regions.yaml` has all regions `enabled: false`. CLAUDE.md hero claim "托管云 SaaS" is unbacked by shippable artifacts. |
| **G11-002** | P1 | observability | SLA targets documented (P50 ≤ 8s warm / ≤ 60s cold, P99 ≤ 120s, 99.5% availability, RTO 4h, RPO 1h) but no production observability exists to measure them. Token tracker is in-memory (G7-006), no latency dashboard, no SLA-breach alerting. |
| **G11-003** | P2 | frontend-tests | Frontend has 0 unit tests (no Vitest). 100% of frontend verification relies on `tsc --noEmit` + Playwright E2E. Component-level logic is untested. |
| **G11-004** | P2 | release-pipeline | No release automation. No `release.yml` workflow, no git-tag-triggered publish, no semantic version bump, no changelog generation. Every "release" is a manual `git push` to master. |
| **G11-005** | P2 | ops-runbook | No ops runbook for on-call engineers. SLA targets in `CLOUD_DEPLOYMENT.md` (99.5% availability, 4h RTO, 1h RPO) are unbacked by incident response / backup-restore / secret-rotation procedures. |
| G11-006 | P3 | test-marker | `e2e` pytest marker is defined in `pytest.ini` but never applied to any test (0 collected). Misleading for new engineers. |
| G11-007 | P3 | deprecated-docs | Root `docs/ARCHITECTURE.md` is explicitly DEPRECATED but still in the docs tree. 63 files in `docs/archive/` are historical. Doc-tree hygiene is poor. |
| G11-008 | P3 | perf-budget-tbd | Throughput test budgets for real MedCodER marked "TBD after warmup" — never defined. Phase 1 budget is for scripted doubles only, which doesn't reflect production LLM latency. |
| G11-009 | P3 | no-load-test | No locust / k6 / wrk configuration. No concurrent-load benchmark. "throughput" test is sequential only. |

## L7. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **L1 Test pyramid** | `3355_TESTS_REAL_BUT_SLOW_ONES_DEFERRED_TO_NIGHTLY` — 3,355 tests collected; 250 test files; integration/e2e excluded from PR gate |
| **L2 Performance** | `ONE_SCRIPTED_DOUBLES_THROUGHPUT_TEST_NO_PROD_OBSERVABILITY` — Orchestrator overhead measured; real LLM latency unmeasured; SLA targets unbacked |
| **L3 Deployment** | `LOCAL_DEV_ONLY_CLOUD_IS_DOCS_ONLY` — docker-compose.local-dev.yml only; 6 critical cloud features documented as Phase 2+ out-of-scope |
| **L4 CI/CD** | `3_WORKFLOWS_REAL_BUT_NO_RELEASE_AUTOMATION` — PR + integration + e2e workflows functional; no release pipeline |
| **L5 Docs** | `379_MD_FILES_FRAGMENTED_NO_OPS_RUNBOOK` — Operation manual is comprehensive; architecture docs partially deprecated; no on-call runbook |

## L8. Gate 11 verdict

`TESTS_REAL_BUT_DEPLOYMENT_IS_LOCAL_DEV_ONLY_AND_CLOUD_IS_DOCS_ONLY`

Specifically:

- ✅ 3,355 tests collected (250 files) — real test pyramid
- ✅ 3 CI workflows functional (PR / integration / e2e)
- ✅ Playwright E2E with real backend startup
- ✅ 20-page operation-manual covering every Console page
- ✅ 87-file Corti-parity audit corpus
- ✅ 4-file cloud deployment documentation
- ❌ **G11-001 P0**: cloud SaaS is documentation-only; 6 critical features (region routing, billing, failover, edge PHI, real platform APIs, org-scoped team) explicitly Phase 2+ out-of-scope; all regions `enabled: false`
- ❌ **G11-002 P1**: SLA targets documented but no production observability to measure them
- ❌ Frontend has 0 unit tests; 100% E2E-based verification
- ❌ No release automation, no ops runbook, no load testing
- ⚠️ Throughput test measures scripted-doubles overhead, not real LLM latency
- ⚠️ Doc tree has 379 files, 63 archived, root ARCHITECTURE.md deprecated — fragmentation is real

Gate 11 closes. Proceed to **Gate 12 — Corti Benchmark and Strategic Fit**.
