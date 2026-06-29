# E2.0 — Negative Signal Archive

**Date:** 2026-06-28
**Status:** Archived as negative / inconclusive.
**Owner:** P1.0 (Agent Runtime productization).
**Future owner:** coding-quality project (separate backlog, see `docs/backlog/CODING_QUALITY_BACKLOG.md`).

---

## 1. What was tried

E2.0 = real verification that E1.8's Stage 1 few-shot exemplars actually improve F1 against the pre-E1.8 baseline.

- Eval driver: `backend/scripts/e2e_medcoder_validation.py --variant full --limit 5`
- Fixture: `tests/fixtures/icoder_201.json` (first 5 cases — same slice used by the pre-E1.8 baseline `data/medcoder/e2e_regression_check.json`)
- Output: `data/medcoder/eval_e20_smoke.json` (eval scratch, gitignored)
- Wall time: 295.1s (5 cases × ~59s/case, vs baseline 305.7s)

---

## 2. Result table

Same 5 cases, apples-to-apples. Numbers copied from `eval_e20_smoke.json` summary + per-case diff.

| metric  | baseline (pre-E1.8) | E2.0 (post-E1.8+E1.9+E1.10) | Δ |
|---------|---------------------|------------------------------|---|
| F1@1    | 0.1500              | 0.1500                       | 0.00 |
| F1@2    | 0.1608              | 0.1644                       | +0.4pp |
| F1@5    | 0.1734              | 0.1498                       | **-2.3pp** |

Per-case predictions are different on 4/5 cases (LLM did respond to the prompt change), but top-1 F1 didn't move.

---

## 3. Why not promoted to product default

1. **No positive F1 signal at the 5-case slice that E1.7/E1.8 were measured against.** F1@1 = 0.1500 exactly (not a coin-flip — the same 0.15 number, on the same 5 cases, before and after). The exemplar prompts are reaching the LLM but not changing the answer quality.
2. **F1@5 dropped 2.3pp.** Even if the gain on procedure extraction were real (which we cannot confirm from this slice), it is offset by a worse top-5 overall.
3. **Sample size is too small to claim a tie.** The previous session that introduced E1.8 crashed before verification — committing without signal is the kind of decision we're now undoing.

---

## 4. Why we did NOT extend to n=30

Product decision (per P1.0 brief):

- The few-shot exemplars are aimed at procedure extraction completeness. 3 of the 5 baseline cases have **zero procedure gold** (`#gold proc = 0`) — they cannot move on procedure metrics regardless of exemplar quality.
- The 2 cases that DO have procedure gold (O82 cesarean cases) show procedure 0× in `predicted_top_5` even after E1.8. The exemplars are not teaching the LLM to extract the cesarean procedure. This is a Stage 4 rerank issue or a Stage 1 extraction quality issue at a deeper layer than exemplars can fix.
- A larger n would not change the diagnosis: with these prompts, on these cases, the LLM does not move F1@1.

---

## 5. Why we did NOT modify Stage 4 rerank in mainline

- Stage 4 rerank belongs to the runtime product surface that P1.0 is productizing. Touching it in the middle of productization risks destabilising the Agent Runtime work.
- The procedural candidate flow may be disconnected from Stage 4 rerank. That is a real defect, but it is a coding-quality issue, not a runtime issue. Moving it to a separate coding-quality project preserves mainline stability.
- P1.0 non-goals explicitly forbid Stage 4 changes. See P1.0 brief.

---

## 6. O82 procedure extracted but not ranked into top-5

**Observed failure mode** (the diagnostic that E2.0 actually produced):

- Case `ZY020000412872` gold: `O82.000, O34.201, 38.8609, 75.9901, ...` (cesarean delivery + diagnostics + cord procedures).
- E2.0 predicted top-5: `N85.801, O34.201, O34.200, O34.200x002, O00.807` — all diagnosis codes, **zero procedure codes**.
- Case `ZY040000505763` is the same pattern.

**Hypothesis (untested):** Stage 1 may emit `procedure_mentions` for `剖宫产术` and `脐动脉插管术`, but the procedure candidates never make it into Stage 4 rerank's candidate list — Stage 4 may be ranking only diseases. This is a candidate-flow defect, not a prompt defect.

**Status:** Logged in `docs/backlog/CODING_QUALITY_BACKLOG.md` for the coding-quality project to investigate.

---

## 7. What this archive is NOT

- It is **not** an indictment of the E1.8 exemplars themselves. They may help on a different (procedurally rich) slice.
- It is **not** a recommendation to delete the exemplars. They remain in `medcoder_adapter.py::_EXTRACTION_FEW_SHOT` for opt-in re-enable.
- It is **not** a recommendation to switch to a different LLM or to add CoT. Both are non-goals in P1.0.

---

## 8. Re-enable path (future)

If a future coding-quality project wants to re-test:

```bash
export ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=true
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/icoder_201.json --variant full --limit 30 --out data/medcoder/eval_coding_quality_v1.json
```

Doctor check (`icoder_doctor.py`) will WARN when the flag is on. It will not FAIL — the flag is opt-in.

---

End of archive.