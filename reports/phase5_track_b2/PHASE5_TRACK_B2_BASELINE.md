# Phase 5 Track B-2 — Baseline

**Date:** 2026-07-11
**Auditor:** Claude (sonnet-4-5) + user (Corti authorized account, full Agent run permission)
**Baseline commit:** `de9e6f4` (HEAD after Track A 5 commits + Track B-1 2 commits)
**Working tree:** clean

## Git state

```
de9e6f4 docs(phase5-a): Track A summary + Phase 4-H leftover reports/screenshots
232dbbc feat(phase5-a6): frontend run history filter + TopBar CNY + i18n
f4040d4 feat(phase5-a4): Web Component 2.0 method-based API + e2e + npm prep
d27eec3 feat(phase5-a3): Usage wire run_history.cost + days filter backend
58d3cf2 fix(phase5-a1): trace double-count + currency CNY backend
4bfac22 docs(phase5-b1): Track B Corti x iCoDer agent deep benchmark audit
5c03c9f fix(phase5-b1): GAP-13-02 add 10 metadata-only agent packs to hub (14 -> 24)
e292420 docs(phase4g): walkthrough report + 4 screenshots
```

Track A 6/6 gaps closed + B-1 verdict PASS_WITH_CORTI_PERMISSION_LIMITATIONS (now upgradeable to tier 1 since user confirmed Corti account has full Agent run permission).

## Dev env

| Component | Status | Evidence |
|---|---|---|
| Backend | RUNNING | `curl http://127.0.0.1:8000/api/health` returns healthy + provider=deepseek + medcoder_index_ready=true |
| Frontend (vite) | RUNNING (PID 7724) | `curl http://localhost:3002/` returns 200; standard `vite --port 3002` launched |
| Chrome debug | TO START | needs user to launch `chrome.exe --remote-debugging-port=9222`; deferred to CP1 start |
| Playwright MCP | TO CONNECT | via connect-chrome skill once Chrome debug port is up |
| Corti session | LOGGED IN | user-managed browser session (B-1 continuation); FULL Agent run permission confirmed |

## Fixtures generated (Phase 1.3)

12 synthetic de-identified clinical cases per PDF §4 written to `fixtures/phase5_track_b2/01-12_*.json`:

| # | ID | Department | Scoring | Notes |
|---|---|---|---|---|
| 1 | `01_orthopedics` | 骨科 | yes | T12 compression fracture (Phase 4-F3 gold case) |
| 2 | `02_cardiology` | 心血管内科 | yes | AMI + LAD PCI |
| 3 | `03_respiratory` | 呼吸内科 | yes | COPD exacerbation + CAP (Pseudomonas) |
| 4 | `04_gastroenterology` | 肝胆外科 | yes | Acute cholecystitis + lap cholecystectomy |
| 5 | `05_oncology` | 肿瘤科 | yes | Post-gastric-cancer chemo admission |
| 6 | `06_obstetrics` | 产科 | yes | Cesarean + postpartum hemorrhage |
| 7 | `07_pediatrics` | 儿科 | yes | Pediatric mycoplasma pneumonia (age 5) |
| 8 | `08_general_surgery` | 普通外科 | yes | Appendectomy (laparoscopic) |
| 9 | `09_complex_comorbidity` | 老年医学科 | yes | Diabetes + HTN + CHD + CKD + post-CVA |
| 10 | `10_negation_and_history` | 呼吸内科 | **NO** | 12+ negation/historical terms stress test |
| 11 | `11_conflicting_documentation` | 普通外科 | **NO** | Left/right + admission/discharge dx conflict |
| 12 | `12_incomplete_documentation` | 内科 | **NO** | 10+ missing critical fields |

Quality gate (PDF §4): 0 issues, 100/100 pytest PASS, 9 scoring-eligible + 3 not-for-scoring (10/11/12).

## Runnable iCoDer agents (9, per B-1.2 + hub v2)

| # | Agent ID | Runtime mode | Maturity | Corti mapping |
|---|---|---|---|---|
| 1 | `medical-coding-agent` | corti_like_fast + medcoder_deep | mvp | medical-coding-icd-10-cpt-agent (EXACT) |
| 2 | `code-validation-agent` | llm_with_tools | runnable | code-validation-agent (EXACT) |
| 3 | `compliance-guardrail-agent` | rule_engine + a2a_pure_llm | runnable | compliance-guardrail-agent (EXACT) |
| 4 | `note-completeness-agent` | a2a_pure_llm | runnable | note-completeness-agent (EXACT) |
| 5 | `procedure-extractor` | a2a_pure_llm | mvp | procedure-entity-extractor-agent (EXACT) |
| 6 | `evidence-extractor` | a2a_pure_llm | mvp | CORTI_BUNDLED_EQUIVALENT |
| 7 | `principal-diagnosis-review` | a2a_pure_llm | mvp | CORTI_BUNDLED_EQUIVALENT |
| 8 | `discharge-summary-structuring` | a2a_pure_llm | mvp | CORTI_CLOSEST_WORKFLOW (CDI) |
| 9 | `drg-analyzer` | a2a_pure_llm | mvp | NO_CORTI_EQUIVALENT |

## Metadata-only iCoDer agents (15, deferred to METADATA_ONLY_AGENT_CATALOG_REVIEW.md)

- 5 prior: `denial-appeals` / `evidence-ranker` / `diagnosis-extractor` / `cdi-review` / `documentation-gap`
- 10 GAP-13-02 fix: `icd10-navigator` / `rule-explainer` / `surgical-registry` / `icu-summary` / `triage` / `med-reconciliation` / `discharge-edu` / `nursing-handoff` / `prior-auth` / `referral-gen`

## Corti state

**Major scope unlock (user 2026-07-11 11:00):** Corti account has FULL Agent run permission.

Impact:
- Every iCoDer runnable agent checkpoint now includes parallel Corti same-input run
- Final verdict target upgrades from `PASS_WITH_CORTI_RUNTIME_PERMISSION_LIMITATIONS` (tier 2) to `PASS_ALL_RUNNABLE_AGENTS_DEEPLY_VALIDATED` (tier 1)
- Estimated effort per checkpoint: +1-1.5h for Corti run + output comparison
- Total Track B-2 estimate: 38-48h (up from 25-35h)

## Lock decisions (user 2026-07-11)

1. **9 checkpoints**, 1 agent/checkpoint, 3-4h each, single commit each
2. **12 synthetic fixtures** by Claude with medical knowledge, labeled `SYNTHETIC_FIXTURE`
3. **Corti runtime accessible** — tier 1 verdict target
4. **Track A landed first** (5 commits done) — clean working tree for B-2

## Audit freeze principle (PDF §1.4)

During B-2 audit:
- No iCoDer feature work (Phase 5 Track C deferred)
- Only `AUDIT_BLOCKER_FIX` allowed (page won't load / agent won't run / route 500 / network can't capture / real provider misconfig)
- All other issues → Gap Backlog
- Each AUDIT_BLOCKER_FIX commit must include regression test

## What's NOT in B-2 (deferred)

- B-1 Gap Backlog P1 fixes (GAP-13-01 A2A discovery / GAP-13-03 promote 3 metadata / GAP-14-03 category fix) — these are P1 Track B-2 work AFTER audit, not part of audit itself
- Track C 5-step chain pilot
- Hospital pilot launch

## Acceptance criteria (PDF §17)

This baseline supports the following PDF §17 acceptance:
- 9 runnable iCoDer agents × full 11-step browser walkthrough (per CP)
- 9 agents × Real DeepSeek (latency > 1500ms + cost > 0)
- 9 agents × 7 input types (normal/long/missing/negation/conflict/invalid/repeatability)
- 9 agents × full UI screenshots (21+ per agent)
- 9 agents × Run ID/Trace ID/Cost recorded
- 9 agents × independent API call
- 4 agents × Embedded smoke (medical-coding / note-completeness / evidence-extractor / principal-diagnosis-review)
- Expert/Tool marked INVOKED only with trace evidence
- Corti permission-blocked tags cleared (now full access)
- 3 prior verdicts corrected (UX 56.8 vs 47.0 / DRG Risk vs Grouper / Pilot readiness)
- 9 agents × independent verdict (7-tier)
- 0 Mock conclusions
- 0 DRG Risk = Grouper confusion
- 0 premature pilot readiness claims

## Next step

Phase 1.4-1.5: Fixtures + data gating test + dev env verified, ready to commit. Chrome debug port setup deferred to CP1 start (requires user to relaunch Chrome). Then CP1: medical-coding-agent 11-step walkthrough.
