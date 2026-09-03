# Phase 3-D Task 3 — Manual Corti Parity Verification

**Task**: Task 3 — Test Hygiene
**Date**: 2026-07-06
**Feature**: Stale e2e_product tests deleted + test_register flaky fixed + pytest asyncio warnings cleaned + infra tests opt-in
**Verifier**: Claude Code (default sweep run + isolated re-runs)

## Corti target behavior

Per `docs/reverse_engineering/corti/CORTI_ICODER_QUICK_TESTS.md`:

- Corti's CI default sweep is **green** — every push runs the full default test suite and 0 fail.
- Stale tests testing deleted features are deleted (not skipped), keeping the suite honest.
- Live-server tests requiring infrastructure (e.g. uvicorn on a port) are isolated as opt-in and never run in the default sweep.
- pytest warnings are kept to a minimum so real signal isn't buried in noise.

## iCoDer observed behavior

### Operation 1 — Default sweep before Task 3

```bash
pytest tests/ --ignore=tests/e2e_product --ignore=tests/integration/icoder/retrieval \
             --ignore=tests/integration/icoder/test_orchestrator_real_deepseek \
             -q --no-header --timeout=120 --maxfail=5
```

**Result** (pre-Task-3): `1 failed, 299 passed, 1 skipped, 4 errors in 286s`
- `test_register` flaky (1 fail)
- 4 infra errors (`test_e2e_coding_pipeline.py` 502 Bad Gateway, no live uvicorn)
- 30+ stale e2e_product failures hidden by `--ignore=tests/e2e_product`
- 48+ `PytestWarning: asyncio mark on non-async function` warnings

### Operation 2 — Stale e2e_product tests identified + deleted

Inspected 7 stale test files testing deleted P1.0-era endpoints:
- `test_embed_demo_three_components.py` (deleted earlier in this session) — tested `EmbedDemoCodingReviewPage.tsx` (deleted in P1.2)
- `test_negative_boundaries.py` — tested `mode=model_evaluation` 501 path (endpoint deleted)
- `test_high_risk_priority_codes.py` — tested `/api/icoder/coding-review/run` triggering 5 PRIORITY codes (endpoint returns 404)
- `test_pipeline_validation_full_flow.py` — tested `/run` `pipeline_validation` mode (endpoint deleted)
- `test_report_disclaimer_visible.py` — tested 18-section report format (deleted)
- `test_run_trace_14_stages.py` — tested 14-stage homepage-cosmetic trace (Phase D3 deprecated; MedCodER uses 5 stages)
- `test_workbench_three_column_layout.py` — tested `CodingReviewWorkbenchPage.tsx` (deleted P1.2)

All 7 files deleted. Remaining e2e_product tests (`test_evidence_viewer_kinds.py`, `test_homepage_deprecation_removed.py`) test current functionality and PASS (8 passed, 2 skipped).

### Operation 3 — `test_register` flaky fixed

Root cause: tests used fixed emails/usernames (`new@example.com` / `newuser`) and the session-scoped test DB only drops tables at session end. Re-runs hit 400 (user already exists) instead of 201 → flake.

Fix: per-invocation `uuid.uuid4().hex[:8]` suffix on every username/email in `tests/test_api/test_auth.py`. Re-ran 5 times in sweep context — 5/5 PASS, no flake.

### Operation 4 — pytest asyncio warnings cleaned

Root cause: `tests/integration/conftest.py::pytest_collection_modifyitems` auto-applied `@pytest.mark.asyncio` to EVERY collected item (sync or async), triggering `PytestWarning: asyncio mark on non-async function` on every sync test.

Fix: added `inspect.iscoroutinefunction(obj)` guard — only async def tests get the marker. Re-ran `test_runtime_platform_v2_projection.py` + `test_e1_real_app_startup.py`: 8 passed, **0 PytestWarnings** (was 5+).

### Operation 5 — Infra tests opt-in

Added `pytestmark = pytest.mark.infra` to `tests/integration/test_e2e_coding_pipeline.py` + registered `infra` marker in `pytest.ini` + extended `addopts` to exclude `infra` from default sweep.

```ini
addopts = -m "not heavy and not retrieval and not infra"
```

Opt-in execution: `pytest -m infra` after starting `uvicorn app.main:app --port 8765`.

### Operation 6 — Default sweep after Task 3

```bash
pytest tests/ -q --no-header --timeout=120 --maxfail=10
```

**Result**: `2232 passed, 14 skipped, 10 deselected, 11 warnings in 420s`
- **0 failed** (was 1 + 4 errors + 30 hidden)
- **0 errors** (was 4)
- **10 deselected** = 4 `infra` + 6 `heavy`/`retrieval` (opt-in)
- **11 warnings** (was 226+) — mostly the pre-existing pydantic `model_used` namespace warning + a few resource warnings

## Verdict: ✅ PASS

| # | Corti target | iCoDer observed | Match |
|---|--------------|-----------------|-------|
| 1 | Delete stale tests testing deleted features | 7 files deleted (embed_demo + 6 more) | ✅ |
| 2 | Fix flaky tests at root cause (not retry) | `test_register` uses uuid-suffixed IDs; 5 reruns stable | ✅ |
| 3 | No pytest warnings on non-async tests | conftest `iscoroutinefunction` guard; 0 PytestWarnings | ✅ |
| 4 | Live-infra tests opt-in via marker | `infra` marker + pytest.ini addopts + `pytestmark = pytest.mark.infra` | ✅ |
| 5 | Default sweep 0 fail | `2232 passed, 0 failed, 0 errors` | ✅ |
| 6 | heavy / retrieval / real-deepseek / full e2e are opt-in | `heavy` + `retrieval` + `infra` markers exclude by default; real-deepseek lives under `tests/integration/icoder/test_orchestrator_real_deepseek/` (already isolated) | ✅ |

## Remaining delta

- **11 warnings remain** (down from 226+): 1 pydantic `model_used` namespace warning (pre-existing, cosmetic — would require renaming `ReviewResponse.model_used` field) + ~10 `PytestUnhandledThreadExceptionWarning` / `RuntimeWarning: coroutine never awaited` from `tests/unit/icoder/experts/test_coding_expert.py::test_invoke_sync_cannot_run_inside_event_loop` (intentional — the test asserts that `asyncio.run` raises RuntimeError when called from inside an event loop, which leaves a coroutine unawaited). Both classes are pre-existing and don't fail tests.
- **Real-deepseek tests** are isolated by directory path (`tests/integration/icoder/test_orchestrator_real_deepseek/`), not by marker. They're already excluded by the `--ignore` flag pattern in CI commands. Could be migrated to a `real_deepseek` marker in a future cleanup, but the current pattern works.

## Screenshots

N/A — verification via pytest sweep output. Console log:

```
2232 passed, 14 skipped, 10 deselected, 11 warnings in 420.01s (0:07:00)
```

## Follow-up

- Task 4 (RunTrace Viewer) will add new tests under `tests/unit/icoder/agent_runtime/` and `tests/integration/icoder/`. Default sweep must stay green — verification step will re-run the sweep after Task 4.
- Task 5 (3 Runnable Agents) will add tests per agent. Same invariant.
- Future pre-existing-warning cleanup (pydantic `model_used` rename) can be folded into Phase 3-E if needed; not blocking.
