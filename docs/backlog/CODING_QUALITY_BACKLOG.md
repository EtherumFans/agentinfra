# Coding Quality Backlog

**Owner:** coding-quality project (separate from iCoDer mainline).
**Created:** 2026-06-28 by P1.0 (Agent Runtime productization handoff).
**Why this file exists:** E2.0 (E1.8 few-shot verification) produced a negative / inconclusive signal on the 5-case slice in `data/medcoder/e2e_regression_check.json`. P1.0 has productized the Agent Runtime mainline; this backlog records the coding-quality work that P1.0 chose NOT to do.

---

## In scope (for coding-quality project)

### CQB-1 — Stage 4 rerank does not surface procedures

- **Symptom:** O82 cesarean cases (gold has procedure codes) — Stage 4 `predicted_top_5` contains zero procedure codes. Procedure candidates appear to be filtered out before rerank.
- **Likely surface:** `backend/icoder_runtime/providers/medical_coding/medcoder_strategy.py` (Stage 3 merge → Stage 4 rerank handoff), or `app/icoder/mcp/handlers/rerank_codes.py` (candidate list construction).
- **Acceptance:** On O82 cases, top-5 must include at least 1 procedure code when gold contains ≥1 procedure.
- **Out of P1.0 scope:** P1.0 explicitly forbade Stage 4 rerank changes.

### CQB-2 — Stage 1 extraction completeness for cesarean narrative

- **Symptom:** Even when `procedure_mentions` is emitted for "剖宫产", the matching ICD-9-CM-3 code (74.0 / 74.1 / 74.2 / 74.4 / 74.99 → Chinese 74.x mapping → O82.x for obstetric) does not enter the candidate set.
- **Likely surface:** `medcoder_adapter.py::build_extraction_messages`, `medcoder_strategy.py` Stage 1 → Stage 3.
- **Acceptance:** Stage 3 candidate set contains at least 1 procedure code per diagnosis whose text contains cesarean markers.

### CQB-3 — Diagnosis / procedure ranking separation

- **Symptom:** Predicted top-5 is dominated by diagnosis codes; procedures (when present in candidates) never break into top-K.
- **Hypothesis:** Stage 4 rerank ranks across one combined list. A two-track design (diagnosis-rank + procedure-rank, merged at output) may be needed.
- **Acceptance:** When gold has procedures, top-5 contains ≥1 procedure (matching CQB-1).

### CQB-4 — Expanded evaluation sample (procedurally rich slice)

- **Symptom:** Current 5-case baseline (`e2e_regression_check.json`) has only 2 procedurally rich cases. Statistical signal is weak.
- **Acceptance:** Run a procedurally balanced eval set (≥30 cases with procedure gold ≥2) and report F1@1, F1@5, **procedure-F1@5** (NEW metric: P-F1@5 over `expected_procedure_codes` only).
- **Why deferred:** Per P1.0 brief, no n=30 expansion on mainline.

### CQB-5 — Few-shot exemplar revision

- **Symptom:** E1.8 exemplar 2 talks about "因胎儿窘迫行子宫下段剖宫产术 + 脐动脉插管术" but the LLM still doesn't extract cesarean on the O82 cases.
- **Possible action:** Rewrite exemplar 2 to use a shorter, more declarative structure with an explicit "you MUST extract all 手术/操作 even if mentioned only in passing" preamble.
- **Why deferred:** Per P1.0 brief, no prompt engineering on mainline.
- **Re-enable:** Set `ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=true` to test new exemplar.

### CQB-6 — Re-rank CoT few-shot (E1.8 follow-on, deferred from M3)

- **Symptom:** M3 milestone originally planned CoT few-shot for Stage 4 rerank. Per M2d phase report, deferred because M3 wasn't started.
- **Note:** `cot_generation_progress_v2.json` (175/500 rerank CoT few-shot) is on disk but not wired.
- **Why deferred:** Per P1.0 brief, no CoT few-shot, no Stage 4 changes.

---

## Explicitly OUT OF SCOPE for coding-quality project (these are NOT backlog items)

- Anything in `icoder_runtime/observability/` or `app/state.m2a_recorder` — that's observability, not coding quality.
- Agent Pack validator — that's runtime productization (P1.0-C).
- Marketplace work — that's runtime productization (P1.1+).
- FAISS / BGE memory knobs — that's deployment stability (E1.9/E1.10, completed).
- Cloud-flip / API Client / OAuth / billing — that's cloud infrastructure (separate project).

---

## Success criteria (coding-quality project's own)

- **CQB-1+CQB-3:** O82 case top-5 includes a procedure code (single highest-leverage win).
- **CQB-4:** P-F1@5 ≥ 0.40 on a procedurally rich slice (the metric E1.7 / E1.8 should have improved but didn't).
- **CQB-5:** When `ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=true`, F1@1 ≥ 0.20 on the procedurally rich slice.

These success criteria are aspirational — coding-quality project owns the work breakdown.

---

End of backlog.