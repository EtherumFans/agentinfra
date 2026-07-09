# Phase 3-D2.5 — iCoDer Phase 4 Readiness Report

**Date:** 2026-07-07
**Status:** DONE — verdict: **NOT READY for Phase 4 GA** (2 blockers + 4 P2/P3 gaps)
**Predecessor:** Phase 3-D2 (Corti Parity Hardening Phase 2) — closed 4 gaps, deferred browser walkthrough to Phase 3-D2.5

## 1. Phase 4 GA criteria

Phase 4 GA (General Availability) for the iCoDer cloud SaaS requires:

1. **Medical Coding Agent production-ready** — correct primary dx on standard cardiology input
2. **Chat UX completes within frontend timeout** — no "运行失败 timeout of 60000ms exceeded"
3. **All 4 runnable agents pass browser walkthrough** — verified end-to-end
4. **Corti parity ≥ 80% on 12-dimension scorecard** — currently 70%
5. **Zero P0 bugs open** — currently 1 P0 open
6. **Zero P1 bugs open** — currently 1 P1 open

## 2. Current state — Phase 3-D2.5 exit

### 2.1 What's ready ✅

- **Platform infrastructure (A2A v0.3 + MCP + 9-step RunTrace)** — best-in-class, exceeds Corti (iCoDer has RunTrace viewer + Tool Dispatch Detail, Corti doesn't)
- **3 deterministic agents** — compliance-guardrail / code-validation / note-completeness all production-ready (<100ms, correct output, full Tool Dispatch Detail)
- **Sidebar IA** — 14/17 items match Corti 1:1
- **Agent Hub** — structurally aligned with Corti
- **Bilingual i18n** — full zh + en support (Corti is English-only)
- **Safety / PHI / Auth** — 4/4 API responses clean, 3-layer redaction, 4 MCP auth types, 7 MCP error codes
- **Tool Dispatch Detail (Phase 3-D2.5 Part A)** — 15-field concentrated view, 9/9 tests pass, browser-verified

### 2.2 What's blocking ❌

| # | Severity | Blocker | Effort |
|---|----------|---------|--------|
| 1 | **P0** | medical-coding-agent produces wrong primary dx (J44.900 COPD vs I20.0 unstable angina) + 8 hallucinated procedures | 2-3 weeks (root-cause retrieval + procedure extraction; add eval regression) |
| 2 | **P1** | Frontend axios 60s timeout kills every medical-coding chat run (backend takes 115s) | 1 week (raise timeout to 300s OR wire SSE streaming from Phase 1.2) |

### 2.3 What's lagging ⚠

| # | Severity | Gap | Effort |
|---|----------|-----|--------|
| 3 | **P2** | Chat UX lacks 5 Corti conversational features (Add context / Reply / Copy / Suggest prompt / What can you do) | 2-3 weeks |
| 4 | **P2** | 9 Corti pre-built agents not even stubbed (Rule Explainer / ICU / Triage / Medication Reconciliation / Discharge Education / Nursing Handoff / Prior Auth / Referral / Clinical Education / Clinical Guidelines) | 8-12 weeks (depends on LLM cost) |
| 5 | **P3** | Sidebar missing Text Generation + Embedded Assistant + 3 Speech-to-Text sub-modes | 2 weeks |
| 6 | **P3** | No live cost UI / API Client selector / announcement banner | 2 weeks |

## 3. Path to Phase 4 GA

### 3.1 Phase 3-D2.6 — P0 + P1 blockers (4 weeks)

**Goal:** close the 2 blockers so medical-coding-agent works end-to-end.

Tasks:
1. **P0 fix — medical-coding retrieval pipeline**
   - Reproduce the bug: run the same input through `e2e_medcoder_validation.py --variant full` and check F1@1
   - Inspect BGE-M3 + FAISS top-20 candidates for the failing input
   - Diagnose: is the embedding wrong? Is the catalog filter rejecting valid codes? Is the re-rank LLM ignoring evidence?
   - Fix: likely needs retrieval index rebuild OR re-rank prompt fix OR procedure extraction stage fix
   - Add eval regression: 5-case cardiology smoke test (unstable angina / STEMI / NSTEMI / heart failure / hypertension) to prevent recurrence
2. **P1 fix — frontend timeout**
   - Option A: raise axios timeout for `message:send` to 300s (5 min) — 1-line fix
   - Option B: wire SSE streaming (already built in Phase 1.2 / Streams WSS) so frontend gets incremental progress and never hits wall-clock timeout
   - Recommend Option B for long-term, but Option A is acceptable for Phase 4 GA

Exit criteria:
- medical-coding-agent produces correct primary dx on 5 cardiology test cases
- medical-coding chat completes within 300s from frontend, no timeout error
- 12-dimension scorecard ≥ 80% (currently 70%)

### 3.2 Phase 3-D2.7 — P2 chat UX parity (3 weeks)

**Goal:** close 5 Corti conversational chat feature gaps.

Tasks:
1. "Add context" — JSON file drop zone in chat input area
2. "Reply..." textbox for follow-up messages (multi-turn conversation)
3. "Copy" button on rendered output
4. "What can you do?" — show agent capability card
5. "Suggest prompt" — generate a sample input from agent's system prompt

Exit criteria:
- 5 features implemented + tested
- Chat UX parity score: 3/5 → 5/5

### 3.3 Phase 3-D2.8 — P2 roster backfill (8-12 weeks)

**Goal:** stub + implement 9 missing Corti pre-built agents.

Priority order (by China-market relevance):
1. Rule Explainer Agent (coding decision support — high value)
2. Prior Authorization Agent (insurance workflow — high value)
3. Referral Generator Agent (clinical workflow — medium value)
4. Clinical Education Agent (education — medium value)
5. Clinical Guidelines Agent (decision support — medium value)
6. Patient Discharge Education Agent (patient-facing — low value for coding-revenue-cycle)
7. Nursing Shift Handoff Agent (clinical workflow — low value)
8. ICU Admission Summary Agent (specialty — low value)
9. Triage and Initial Assessment Agent (emergency — low value)

Exit criteria:
- 9 agents stubbed with metadata-only cards
- At least 3 promoted to runnable (Rule Explainer / Prior Auth / Referral)

### 3.4 Phase 3-D2.9 — P3 polish (2 weeks)

**Goal:** close 3 UX polish gaps.

Tasks:
1. Sidebar Text Generation + Embedded Assistant items
2. Sidebar 语音转录 → 3 sub-modes (Dictation / Ambient / Pre-recorded)
3. Live cost UI + API Client selector + announcement banner

Exit criteria:
- 17/17 sidebar items match Corti
- Agent Hub parity score: 3/5 → 5/5

## 4. Phase 4 GA gate

Phase 4 GA can ship when ALL of the following are true:

- [ ] P0 medical-coding output quality bug fixed (5 cardiology test cases pass)
- [ ] P1 frontend timeout fixed (medical-coding chat completes within 300s)
- [ ] 12-dimension scorecard ≥ 80% (currently 70%)
- [ ] 4 runnable agents pass browser walkthrough (currently 3/4 pass; medical-coding fails)
- [ ] Zero P0 bugs open
- [ ] Zero P1 bugs open

**Current verdict: NOT READY** — 2 blockers open (P0 + P1), 3/4 agents pass walkthrough, scorecard 70%.

**Projected GA date:** 4 weeks (Phase 3-D2.6 only) for minimum viable GA; 12-16 weeks for full Corti parity (Phase 3-D2.6 + D2.7 + D2.8 + D2.9).

## 5. Recommendation

**Ship Phase 4 minimum viable GA after Phase 3-D2.6 (4 weeks).**

Minimum viable GA scope:
- ✅ 4 runnable agents (medical-coding fixed + 3 deterministic)
- ✅ RunTrace viewer + Tool Dispatch Detail (differentiator)
- ✅ Bilingual i18n (China-market requirement)
- ✅ Safety / PHI / Auth (verified clean)
- ⚠ Chat UX task-oriented (not conversational) — acceptable for compliance-driven hospital users
- ⚠ 11 preset agents (4 runnable + 7 metadata-only) — acceptable for coding-revenue-cycle MVP

Defer to Phase 4.1+:
- 5 Corti conversational chat features
- 9 missing pre-built agents
- Live cost UI / API Client selector / announcement banner

This positions iCoDer as a **China-market coding-revenue-cycle SaaS** with a differentiator (RunTrace + Tool Dispatch Detail) that Corti doesn't match, while being honest about the chat UX gap (task-oriented vs conversational) and the roster gap (11 vs 20 preset agents).
