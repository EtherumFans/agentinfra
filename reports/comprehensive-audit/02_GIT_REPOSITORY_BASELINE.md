# 02 — Git Repository Baseline (Audit Gate 0)

> Audit Gate 0 output. Establishes the trusted evidence baseline before any subsequent gate runs. Per PDF §十五, **before Gate 0 closes**: no large code changes, no historical PASS rewrites, no new agent development, no CDI prompt tuning, no new model training, no capability inference from README.

## A. Trusted commit baseline

| Field | Value |
|-------|-------|
| HEAD (this audit) | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` |
| Short SHA | `c147d01` |
| Subject | `feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells` |
| Branch | `master` |
| Remote | `origin → https://github.com/EtherumFans/agentinfra.git` |
| Branch tracking | `master` ↔ `remotes/origin/master` |
| Total commits | 278 |
| Tags | `v1.0.0` |
| Working copy `VERSION` | `1.1.0` |
| `CHANGELOG.md` head | `[1.0.0] - 2026-05-31 — Corti-competitive Clinical AI Platform — 首次生产发布` |

**Evidence:** `evidence/git/head.txt`, `evidence/git/last_50_commits.txt`.

## B. Workspace pollution (78 entries in `git status --short`)

The working copy is **not clean**. 78 entries, breakdown:

### B.1 Modified tracked files (33)

Backend (10)
- `backend/app/api/agent_run.py`
- `backend/app/api/embedded.py`
- `backend/app/api/platform_api_clients.py`
- `backend/app/api/usage.py`
- `backend/app/main.py`
- `backend/app/middleware/auth.py`
- `backend/app/models/__init__.py`
- `backend/app/models/oauth.py`
- `backend/app/models/run_history.py`
- `backend/tests/conftest.py`
- `backend/tests/test_api/test_phase4f_agent_run.py`

Frontend (4)
- `frontend/src/App.tsx`
- `frontend/src/components/layout/Layout.tsx`
- `frontend/src/i18n/locales.ts`
- `frontend/tests/e2e/phase5_a4_embedded.spec.ts`

SDK + Embedded (14)
- `packages/icoder-embedded/dist/icoder-assistant.{js,d.ts}`
- `packages/icoder-embedded/package.json`
- `packages/icoder-embedded/src/icoder-assistant.ts`
- `packages/icoder-sdk/README.md`
- `packages/icoder-sdk/package.json`
- `packages/icoder-sdk/src/client.ts`
- `packages/icoder-sdk/src/index.ts`
- `packages/icoder-sdk/src/resources/{agents,billing,compliance,facts,oauth,reviews,textgen}.ts`
- `packages/icoder-sdk/tsconfig.json`

Deleted (1)
- `packages/icoder-sdk/package-lock.json`

### B.2 Untracked new files (45) — **Phase 7 / Gate 13A work that has not been committed**

Backend code (13)
- `backend/alembic/versions/{012_idempotency_records,013_run_history_status_and_cancel,014_api_client_attribution_and_origins,015_preview_sessions}.py`
- `backend/app/api/{examples,preview_sessions,runs}.py`
- `backend/app/middleware/partner_cors.py`
- `backend/app/models/{idempotency_record,preview_session}.py`
- `backend/app/services/{idempotency_service,preview_ticket,run_lifecycle,trace_token}.py`

Backend tests (10)
- `backend/tests/test_api/test_phase7_gate{1_examples_mount,3_agent_run_idempotency,4_run_cancel,5_api_clients,6_cors,7_trace_token,8_usage_api_client,9_sse_run_events}.py`
- `backend/tests/unit/app/api/test_phase7_gate13a_{audit,preview_html,preview_sessions}.py`
- `backend/tests/unit/app/services/test_phase7_gate13a_preview_ticket.py`
- `backend/tests/unit/app/services/test_phase7_gate3_idempotency.py`

Frontend (1)
- `frontend/src/pages/EmbeddedAssistantPage.tsx`

Packages / build artifacts (7)
- `packages/icoder-embedded/demos/` (medical-coding-demo.html, cdi-demo.html, drg-dip-demo.html)
- `packages/icoder-embedded/icoder-embedded-2.0.0.tgz`
- `packages/icoder-sdk/dist/`
- `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz`
- `packages/icoder-sdk/src/resources/runs.ts`
- `packages/icoder-web/DEPRECATED.md`
- `packages/web-components/DEPRECATED.md`
- `web-components/DEPRECATED.md`

Partner / external consumer (3)
- `examples/` (partner-reference-app + phase5_track_b2 + phase5_track_c)
- `phase7-external-consumer/`
- `examples/partner-reference-app/`

Screenshots dropped in repo root (5)
- `corti_embedded_assistant_code_html.png`
- `corti_embedded_assistant_event_inspector.png`
- `corti_embedded_assistant_react_tab.png`
- `corti_embedded_assistant_settings_tab.png`

Reports (3)
- `docs/audit/` (this audit's own working files — legitimate)
- `docs/corti_parity/phase7_gate13a/`
- `reports/phase6/` (Phase 6 reports — should already be committed; presence as `??` means **never added**)
- `reports/phase7/` (Phase 7 reports — same)

**Read:** Phase 7 / Gate 13A is the largest uncommitted block. **All Phase 7 and Phase 6 reports exist only in the working copy, not in git history.** The committed HEAD `c147d01` has no Phase 7 reports at all. Anyone checking out `c147d01` from origin would get a repo without `reports/phase7/`.

### B.3 Diff size

```
32 changed files (tracked-only), +2208 / -616 lines
```

Plus the untracked surface above, the actual unpersisted work is materially larger.

## C. Report ↔ commit correspondence

| Report directory | First added in working copy? | In `c147d01` history? |
|------------------|------------------------------|----------------------|
| `reports/phase4h/` | Committed (Phase 4-H closure) | ✅ |
| `reports/phase5_track_b/` | Committed | ✅ |
| `reports/phase5_track_b2/` | Committed | ✅ |
| `reports/phase5_track_c/` | Committed | ✅ |
| `reports/phase5_track_d/` | Committed | ✅ |
| `reports/phase5_track_d_p0/` | Committed | ✅ |
| `reports/phase5_track_d_p05/` | Committed | ✅ |
| `reports/phase5_d_p05/` | Committed | ✅ |
| `reports/track_h/` | Committed | ✅ |
| **`reports/phase6/`** | **Untracked (??)** | ❌ — Phase 6 (8 gates) reports never committed |
| **`reports/phase7/`** | **Untracked (??)** | ❌ — Phase 7 (13 gates) reports never committed |
| **`reports/phase7/gate13a/`** | **Untracked (??)** | ❌ — Gate 13A security hardening reports never committed |
| `reports/comprehensive-audit/` | (this audit, new) | n/a |

**Implication for audit credibility:** the two largest recent verdicts (Phase 6 FINAL = `PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION_WITH_BROWSER_WALKTHROUGH_DEFERRED` and Phase 7 FINAL = `PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION`) **exist only in the working copy**. They are not part of any committed baseline. Anyone reproducing from origin gets a repo where these reports do not exist.

This is a P1 delivery risk (register in Gate 14 backlog).

## D. Recent commit history (last 25)

```
c147d01 feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells
79b2b03 feat(track-h): H4.2 freeze iter 7 baseline as icoder-cdi-agent-v1.0.0-rc5
0d759e5 feat(track-h): H3.19 sentence-bounded CEA-005/006 negation look-back
7a04c13 feat(track-h): H4.2 freeze iter 6 baseline as icoder-cdi-agent-v1.0.0-rc4
f316cff feat(track-h): H3.18 response_options_4plus padding (0.900 → 1.000) + iter 6 strong gains
3fee413 feat(track-h): H3.16 lab_positive_uncertain emit 0/5 → 1/5 + clear_gap under-query 4/10 → 2/10
ff3161a feat(track-h): H4.2 iter 5 freeze — icoder-cdi-agent-v1.0.0-rc3
5ea70fd feat(track-h): H3.15 extract_claims prompt — close CEA over-block on absence gaps
b9aae7b feat(track-h): H3.15 quote-snap — closes iter 4 CEA over-block + verbatim regression
fd238fc feat(track-h): H3.13b + H3.14 calibration iteration 4 — partial win
619dc1b feat(track-h): H4 formal benchmark closure — iter 3 baseline frozen as icoder-cdi-agent-v1.0.0-rc1
01c8448 feat(track-h): H2 iCoDer-Corti capability gap matrix
b2f69c6 feat(track-h): H3.12 calibration iteration 3 — clear_gap regression fixed
7df16ab feat(track-h): H3.9-H3.11 calibration iteration 2 — partial win
195bd5d feat(track-h): H3.5-H3.8 calibration tuning iteration 1 — over-query reduced 5/10→3/10
4a5b28d feat(track-h): Corti CDI capability ontology + 40-case cross-platform calibration
909ce5e feat(track-d-p05-g8): 40-case Corti teacher calibration — methodology shipped
48dd147 fix(runtrace): back button uses browser history (-1) instead of hardcoded /ai-studio/agents
b88fc83 feat(track-d-p05-g6): workbench product language + Corti UI comparison
f077b8b feat(track-d-p05-g5): conditional expert routing (6 execution modes)
2aac84b feat(track-d-p05-g4): claim-evidence alignment + semantic necessity (STAGES 8→10)
031ef7b feat(track-d-p05-g3): single-dimension gate + NLQ-011 max-5 options
b66bbb4 feat(track-d-p05-g2): wire query necessity gate (NQ-001..NQ-006)
ca6c4a4 feat(track-d-p05-g1): close 0-Gap+N-Query data consistency bug
e18efcc docs(track-d-p0-g6-g7): E2E sweep + final report — PASS_READY_FOR_REAL_CDI_QUALITY_VALIDATION
```

(Evidence: `evidence/git/last_50_commits.txt` for the full 50-commit dump.)

**Observations:**

- The 16 most-recent commits (since `4a5b28d` 2026-07-13) are all `feat(track-h)` — **CDI prompt calibration**. The PDF §一.4 / §十五 explicitly says CDI tuning is paused, but the **last 16 commits are precisely CDI tuning**. The audit must verify this work has actually stopped, not just been promised.
- The most-recent **non-CDI** commit is `909ce5e feat(track-d-p05-g8): 40-case Corti teacher calibration — methodology shipped`.
- The most-recent commits that look like **productization / delivery** (Phase 7 partner integration, Gate 13A security hardening) are **all in the untracked workspace**, not in history. They appear in no commit at all.
- `v1.0.0` tag exists but is not visible in the last 50 commits — implies the tag was set well before HEAD; VERSION file says `1.1.0`. There is no `v1.1.0` tag yet.

## E. Identified entry points (preliminary — deep map in Gate 1)

### E.1 Backend entry

- App object: `backend/app/main.py` (FastAPI)
- Start command (local): `cd backend && python -m uvicorn app.main:app --port 8000`
- Start command (docker): `docker compose -f docker-compose.local-dev.yml up -d --build`
- Alembic INI: `backend/alembic.ini` → `sqlalchemy.url = sqlite+aiosqlite:///./data/icoder.db`
- 15 Alembic migrations present (`002_agent_versioning.py` … `015_preview_sessions.py`, plus `afeb04d02665_001_initial_all_tables.py`); **migrations 012–015 are untracked**.
- Two empty DB files at repo root: `backend/app.db` (0 bytes, 7月14), `backend/icoder.db` (0 bytes, 7月7) — neither matches the Alembic target path `backend/data/icoder.db`. **DB path mismatch** is a known footgun the audit must flag.

### E.2 Frontend entry

- Vite root: `frontend/`
- Start: `cd frontend && npm run dev`
- Build: `tsc && vite build`
- Test: `vitest`, Playwright tests in `frontend/tests/e2e/` (5 specs).

### E.3 Runtime

- Python package: `backend/icoder_runtime/` (has own `pyproject.toml` + `icoder_runtime.egg-info`).
- Core: `backend/icoder_runtime/core/` — agent_pack loader/schema/v1, builtin_pack_provider, data_policy, errors, evidence_parser, llm_gateway, pii_redaction, registry, registry_backend, runtime_config, runtime_result.
- Backends: `backend/icoder_runtime/backends/` (deep audit in Gate 6).
- Providers: `backend/icoder_runtime/providers/{dip,drg,medical_coding}/`.

### E.4 Compliance services

- `backend/compliance_services/` — `rule_engine.py`, `medical_coding_rules.py`, `drg_dip_rules.py`, `insurance_rules.py`, `medcoder_retrieval_rules.py`.

### E.5 Agents (official)

- `backend/official_agents/` — 30 agent directories; **duplication suspected**: `code_validation/` + `code-validation/`; `compliance_guardrail/` + `compliance-guardrail/`; `note_completeness/` + `note-completeness/`; also `evidence_extractor/` + `evidence-ranker/` + `diagnosis-extractor/` + `procedure-extractor/`. **Investigate in Gate 4 + Gate 21.**

### E.6 SDK

- `packages/icoder-sdk/` — `@icoder/sdk@1.0.0-beta.2` — TypeScript SDK. Built `dist/` is **untracked**, `icoder-sdk-1.0.0-beta.2.tgz` is **untracked**. Public npm publish not verified.

### E.7 Embedded

- `packages/icoder-embedded/` — `@icoder/embedded@2.0.0` — Web Component (Corti-compatible method-based API). `demos/`, `dist/`, `icoder-embedded-2.0.0.tgz` all **untracked**.
- **Three parallel implementations exist** and are marked `DEPRECATED.md`:
  - `packages/icoder-web/` (1.0 attribute API) — DEPRECATED
  - `packages/web-components/` (prototype) — DEPRECATED
  - `web-components/` (root-level prototype) — DEPRECATED

### E.8 Partner reference app

- `examples/partner-reference-app/` — express server, `engines.node >= 18`. **Untracked**, not committed.

### E.9 External consumer

- `phase7-external-consumer/` — separate sandbox that installs the SDK from external `.tgz`. **Untracked**.

### E.10 Tests

- Backend pytest: `backend/tests/` — 271 `.py` files under `tests/`.
- `backend/pytest.ini` excludes `heavy`, `retrieval`, `infra` markers by default. **The default sweep does not run the MedCodER BGE-M3 + FAISS retrieval tests.**
- Frontend: 5 Playwright specs in `frontend/tests/e2e/`.

## F. Environment variables required

From `backend/app/config.py`:

**Always required:**
- `SECRET_KEY` (via `ICODER_SECRET_KEY`) — auto-generated on first run if unset.
- `ICODER_DEPLOYMENT_MODE` — `local` (default) | `cloud`.

**Local mode implicit:**
- `LLM_PROVIDER` = `deepseek`
- `LLM_BASE_URL` = `https://api.deepseek.com/v1`
- `LLM_MODEL` = `deepseek-chat`
- `LLM_API_KEY` — resolved from `CredentialVault` at runtime; env override `ICODER_CREDENTIAL_LLM`.
- `LLM_TIMEOUT` = 120s.

**Cloud-only (when `ICODER_DEPLOYMENT_MODE=cloud`):**
- `ICODER_HOSTED_URL`
- `ICODER_ENVIRONMENT` (`eu` | `us` | `cn`)
- `ICODER_REGION`
- `ICODER_TENANT_ID`
- `ICODER_API_CLIENT_ID`
- `ICODER_API_CLIENT_SECRET`
- `ICODER_PHI_REDACTION_MODE` = `edge`
- `ICODER_AUDIT_SINK` = `cloud_audit`
- `ICODER_ASSET_BUCKET`

**Open question for Gate 1:** does the `local` path actually boot from a clean clone without a manually-populated `data/icoder.db`? Both root `.db` files are 0 bytes, so the running service is presumably using `backend/data/icoder.db` (a path that is gitignored or created on demand).

## G. Likely duplicate / legacy paths (deep audit in Gate 21)

| Path | Status |
|------|--------|
| `backend/official_agents/code_validation/` | duplicate of `code-validation/`? |
| `backend/official_agents/compliance_guardrail/` | duplicate of `compliance-guardrail/`? |
| `backend/official_agents/note_completeness/` | duplicate of `note-completeness/`? |
| `backend/app/db.py` vs `backend/app/database.py` | TBD |
| `packages/icoder-web/` | DEPRECATED, but still on disk |
| `packages/web-components/` | DEPRECATED, but still on disk |
| `web-components/` | DEPRECATED, but still on disk |
| `backend/official_agents/medical_coding/` vs `backend/app/coding_runtime/` | TBD |
| `backend/official_agents/medical_coding/` vs `backend/icoder_runtime/providers/medical_coding/` | TBD |
| `packages/icoder-embedded/` vs `web-components/` vs `packages/web-components/` | 3 implementations |
| `packages/icoder-sdk/` vs `phase7-external-consumer/` | (consumer is fine — but is SDK published externally?) |

## H. Generated artifacts inside the repo

- `backend/data/medcoder/faiss.index` (>10MB)
- `backend/data/medcoder/faiss_icd9cm3.index` (>10MB)
- `backend/data/medcoder/metadata.pkl` (>5MB)
- `backend/.icoder/m2a/production_runs.jsonl` (>5MB)
- `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` (untracked)
- `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` (untracked)
- `packages/icoder-sdk/dist/` (untracked)
- `packages/icoder-embedded/dist/` (tracked — checked in)

Built `dist/` for the SDK is **not** committed; built `dist/` for the embedded package **is** committed. **Inconsistent policy** — Gate 21 debt.

## I. Environment limitations (declared up front, per PDF §十五 item 13)

1. **No partner staging environment** — `examples/partner-reference-app/` runs against `http://localhost:8000`, not a real partner HIS/EMR. Anywhere the audit says "partner integration verified" it means localhost sandbox.
2. **No production evidence** — no production trace, no production Usage aggregate, no real hospital data. Anywhere historical reports claim `production`, the audit must downgrade.
3. **CDI prompt tuning is paused** — the audit will not re-run the 40-case Corti calibration. Quality judgements reuse the frozen rc5 baseline.
4. **No external npm publish** — `@icoder/sdk@1.0.0-beta.2` and `@icoder/embedded@2.0.0` are consumed via local `.tgz`, not via `npm install @icoder/sdk`.
5. **Cortex comparison** — Corti `console.corti.app` access requires a live JWT. The audit can re-use captured artifacts in `docs/corti_parity/` but cannot re-run live Corti probes at scale.
6. **LLM provider** — DeepSeek live calls cost real tokens (¥). The audit will reuse captured traces where possible; live new calls only when unavoidable.
7. **Heavy retrieval** — `pytest -m heavy` and `pytest -m retrieval` (MedCodER FAISS) are excluded from default sweeps. The audit must run them at least once explicitly to verify.

## J. Gate 0 — commands to be run (for downstream gates)

| Gate | Command set |
|------|-------------|
| 1 | `pip install -r backend/requirements.txt`, `npm install` (frontend + packages), `npm run build` (SDK + embedded), `docker compose -f docker-compose.local-dev.yml up`, `alembic upgrade head`. |
| 2 | Static scan: route list from `frontend/src/App.tsx`; nav from `frontend/src/components/layout/Layout.tsx`; backend route list from `backend/app/main.py`. |
| 3 | Playwright MCP against `http://localhost:5173` (or built `dist/`). |
| 7 | `pytest backend/tests/test_api/test_phase7_gate{3,4,5,6,7,8,9}_*.py -v` |
| 8 | `cd phase7-external-consumer && npm install && npm run smoke` |
| 11 | `pytest backend/tests/`, `npx vitest run`, `npx playwright test` |
| 14 | Aggregation of all prior gates. |

## K. Evidence Manifest initial state

See `evidence_manifest.json`. Initial schema:

```json
{
  "audit": "iCoDer Comprehensive Product Audit",
  "audit_started": "2026-07-15",
  "trusted_commit": "c147d015455017bc1d8420cbdbd813b3b8ec23ce",
  "branch": "master",
  "workspace_dirty": true,
  "gates_completed": ["gate0"],
  "gates_pending": ["gate1", "gate2", "...", "gate14"],
  "evidence": {
    "git": ["evidence/git/head.txt", "evidence/git/last_50_commits.txt", "evidence/git/workspace_status.txt"],
    "commands": [],
    "test-results": [],
    "browser": [],
    "screenshots": [],
    "playwright-traces": [],
    "sanitized-har": [],
    "console": [],
    "network": [],
    "storage": [],
    "security": [],
    "packages": [],
    "external-consumer": [],
    "architecture": [],
    "hashes": []
  },
  "findings": {
    "P0": [],
    "P1": [
      {
        "id": "G0-001",
        "severity": "P1",
        "domain": "delivery",
        "title": "Phase 6 and Phase 7 reports exist only in working copy, never committed",
        "evidence": "git status shows reports/phase6/ and reports/phase7/ as ??; git log --all does not contain them",
        "impact": "Reproducibility from origin/master is broken; PASS verdicts in Phase 6/7 FINAL reports cannot be independently verified by anyone cloning the repo.",
        "recommended_fix": "Commit reports/phase6/ + reports/phase7/ + reports/phase7/gate13a/ + supporting untracked code (alembic 012-015, services/*, examples/partner-reference-app/) as a Phase 7 closure commit before any further feature work.",
        "verification_gate": "Gate 14"
      }
    ],
    "P2": [
      {
        "id": "G0-002",
        "severity": "P2",
        "domain": "delivery",
        "title": "Three parallel Web Component implementations still on disk despite DEPRECATED.md",
        "evidence": "packages/icoder-web/DEPRECATED.md, packages/web-components/DEPRECATED.md, web-components/DEPRECATED.md all exist; canonical is packages/icoder-embedded/",
        "impact": "Confusion for any consumer reading the repo; risk of importing the wrong package.",
        "recommended_fix": "Delete the three deprecated directories or move to archive/. Re-verify nothing imports them.",
        "verification_gate": "Gate 21"
      },
      {
        "id": "G0-003",
        "severity": "P2",
        "domain": "build-hygiene",
        "title": "Inconsistent dist/ commit policy between icoder-sdk and icoder-embedded",
        "evidence": "packages/icoder-embedded/dist/ is tracked in git; packages/icoder-sdk/dist/ is not",
        "impact": "Inconsistent release story; SDK consumers must build locally, embedded consumers do not.",
        "recommended_fix": "Pick one policy (either ship dist/ for both, or for neither) and document in the package README.",
        "verification_gate": "Gate 8"
      },
      {
        "id": "G0-004",
        "severity": "P2",
        "domain": "build-hygiene",
        "title": "DB path mismatch — two empty .db files at backend root, runtime uses data/icoder.db",
        "evidence": "backend/app.db (0 bytes), backend/icoder.db (0 bytes); alembic.ini → ./data/icoder.db",
        "impact": "Engineer running `sqlite3 backend/icoder.db` sees an empty DB and may believe the system was never used.",
        "recommended_fix": "Remove the stray .db files; document the canonical DB path in README.",
        "verification_gate": "Gate 1"
      }
    ],
    "P3": []
  },
  "baseline_verdict": "AUDIT_GATE0_BASELINE_ESTABLISHED_WITH_DELIVERY_DEBT"
}
```

## L. Baseline verdict

**`AUDIT_GATE0_BASELINE_ESTABLISHED_WITH_DELIVERY_DEBT`**

- Trusted commit identified (`c147d01`).
- Workspace is dirty (78 entries) — material Phase 7 / Gate 13A work is **uncommitted**.
- Phase 6 + Phase 7 + Gate 13A reports exist **only** in working copy, not in commit history. Reproducibility from origin is broken for the most recent PASS verdicts.
- No P0 found at Gate 0 (no security surprise at this layer).
- 1 P1 (G0-001 uncommitted Phase 7 reports), 3 P2 (delivery hygiene).

Gate 0 closes. Proceed to **Gate 1 — Repository Structure and Startup Reproduction**.
