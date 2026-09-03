# Phase 3-D2.5 Part E — iCoDer × Corti Parity Scorecard (12 Dimensions × 0-5)

**Date:** 2026-07-07
**Status:** DONE
**Scoring rubric:** 0 = absent, 1 = broken, 2 = partial, 3 = functional but rough, 4 = production-ready with minor gaps, 5 = best-in-class (matches or beats Corti)

## 12-dimension scorecard

| # | Dimension | Score | Corti score | Verdict |
|---|-----------|-------|-------------|---------|
| 1 | Sidebar Information Architecture | 4 | 5 | iCoDer has 14/17 items; missing Text Generation + Embedded Assistant + 3 Speech-to-Text sub-modes |
| 2 | Agent Hub layout & filtering | 3 | 5 | iCoDer lacks live cost UI / API Client combobox / announcement banner |
| 3 | Pre-built Agent Roster | 3 | 5 | 4/20 runnable + 4/20 metadata-only = 8/20 (40%); 9 missing adjacent clinical agents |
| 4 | Agent Card detail page | 3 | 5 | Task-oriented UX is fine but lacks 5 Corti conversational features (Add context / Reply / Copy / Suggest prompt / What can you do) |
| 5 | Real-time orchestrator progress | 1 | 5 | Lacks live "Calling expert: ..." messages in chat; only "运行中…" button state |
| 6 | Output rendering | 4 | 5 | Has Rendered + JSON tabs (Corti has 1); lacks Copy + emoji markers |
| 7 | RunTrace viewer | 5 | 0 | **iCoDer beats Corti** — 9-step timeline + 15-field Tool Dispatch Detail; Corti has no Console-side viewer |
| 8 | Tool Dispatch Detail (Part A) | 5 | 0 | **iCoDer beats Corti** — 15-field concentrated view with auto-expand on failure |
| 9 | Safety / PHI / Auth | 5 | 4 | 4/4 API responses clean; 3-layer redaction; 4 MCP auth types + 7 error codes |
| 10 | Output quality | 1 | 5 | **CRITICAL BUG** — wrong primary dx (J44.900 COPD vs I20.0 unstable angina) + 8 hallucinated procedures |
| 11 | Performance | 3 | 5 | 3/4 deterministic agents excellent (<100ms); medical-coding UX broken by 60s axios timeout vs 115s backend |
| 12 | i18n / Localization | 5 | 2 | **iCoDer beats Corti** — full bilingual (zh + en); Corti is English-only |

**Total: 42/60 (70%)** — Corti would score 47/60 (78%) on the same rubric.

## Per-dimension verdicts

### D1 Sidebar IA — Score 4/5 (Corti 5/5)

Structural parity achieved (14/17 items match 1:1). 3 missing items:
- ❌ Text Generation sidebar item
- ❌ Embedded Assistant sidebar item  
- ❌ Corti Models sub-item (frontier model marketplace)

Plus 1 partial: 语音转录 is 1 item vs Corti's 3 sub-modes (Dictation / Ambient / Pre-recorded).

**Why 4 not 5:** the 3 missing items are not blocking for coding-revenue-cycle MVP, but full Corti parity requires them.

### D2 Agent Hub — Score 3/5 (Corti 5/5)

7/10 features match. 3 gaps:
- ❌ Live cost counter ("$0.000000 Reset live cost" + "$49.22")
- ❌ API Client combobox in breadcrumb
- ❌ Product announcement banner

iCoDer differentiator: agent cards show **maturity badge** + **production_ready flag** + **tags** — better for compliance-conscious buyers.

**Why 3 not 4:** the 3 missing UX elements matter for PAYG monetization and per-agent API client binding, both of which are Phase 4 GA requirements.

### D3 Pre-built Roster — Score 3/5 (Corti 5/5)

8/20 Corti agents have iCoDer equivalents (4 runnable + 4 metadata-only). 9 Corti agents have no iCoDer equivalent at all.

iCoDer covers **100% of Corti's coding-revenue-cycle agents** (Medical Coding / Compliance / Code Validation / Note Completeness) but only 40% of Corti's full healthcare catalog.

iCoDer has 3 China-specific extras (DRG / Evidence Ranker / Documentation Gap) that Corti doesn't have — these are differentiators, not gaps.

**Why 3 not 4:** coding-revenue-cycle parity is sufficient for China hospital MVP, but 9 missing adjacent agents limit platform breadth.

### D4 Agent Card detail — Score 3/5 (Corti 5/5)

Task-oriented UX is functional and arguably better for compliance-driven hospital users. But 5 Corti conversational features are missing:
- ❌ "Add context" (drop JSON files)
- ❌ "Reply..." textbox for follow-up
- ❌ "Copy" button on output
- ❌ "What can you do?" / "Suggest prompt" buttons
- ❌ "Clear chat" button

**Why 3 not 4:** the missing features reduce developer ergonomics. Corti's conversational flow with context files and follow-up replies is a real productivity boost.

### D5 Real-time progress — Score 1/5 (Corti 5/5)

iCoDer shows only "运行中…" button state during the 115s medical-coding run. No live orchestrator messages. Corti shows "Calling expert: coding-expert..." live in chat.

**Why 1 not 2:** the infrastructure for SSE streaming exists (built in Phase 1.2 / Streams WSS), but it's not wired to the chat UI. This is a known P2 gap.

### D6 Output rendering — Score 4/5 (Corti 5/5)

iCoDer has "Rendered" + "JSON" tabs (Corti has 1 view only) — differentiator. "View RunTrace" link is unique.

Gaps:
- ❌ No "Copy" button on output
- ⚠ Tabular format is more rigid than Corti's emoji-marked list (⚠ ❌)

**Why 4 not 5:** the Copy button and emoji markers are small polish items.

### D7 RunTrace viewer — Score 5/5 (Corti 0/5) ★

**iCoDer beats Corti.** Dedicated RunTrace page with 9-step timeline + 15-field Tool Dispatch Detail + raw safe_metadata + auto-expand on failure. Corti has no Console-side equivalent (run trace accessible only via API).

This is iCoDer's strongest differentiator for compliance-conscious buyers and developers debugging agent behavior.

### D8 Tool Dispatch Detail — Score 5/5 (Corti 0/5) ★

**iCoDer beats Corti.** 15-field concentrated view of every MCP tool dispatch lifecycle, with display-safe invariant (no token / secret / PHI), auto-expand on failure, and defense-in-depth redaction (backend `_redact_safe_metadata` + frontend `SECRET_KEY_RE`).

Verified by 9/9 tests (6 backend + 3 frontend) and live browser walkthrough.

### D9 Safety / PHI / Auth — Score 5/5 (Corti 4/5)

4/4 API responses verified clean (trace / tools/list / message:send / tools/call). PHI redaction working. 3-layer defense-in-depth. 4 MCP auth types. 7 MCP error codes.

**Why 5:** all safety checks pass. Corti presumably has equivalent safety but it's not directly auditable from the Console UI.

### D10 Output quality — Score 1/5 (Corti 5/5) ❌ CRITICAL

**P0 bug:** iCoDer medical-coding-agent produced wrong primary dx (J44.900 COPD) and 8 hallucinated procedures (腹腔穿刺 / 胸膜外引流 / 中心静脉置管 / 气管插管 / 呼吸机 / 血液透析 / 子宫内输血 / 静脉输液港) — none of which appear in the input text. Missed all 3 documentation gaps and 2 uncodable items that Corti caught.

**Why 1 not 0:** the deterministic agents (compliance-guardrail / code-validation / note-completeness) produce correct output. Only the orchestrator-driven medical-coding-agent has the quality bug.

**Root cause hypothesis:** BGE-M3 + FAISS retrieval returned wrong candidates (input too short? embedding mismatch?), and the re-rank LLM didn't catch the mismatch. The 8 hallucinated procedures suggest the procedure extraction stage is broken (returning a default procedure list instead of extracting from input).

**Blocker for Phase 4 GA.**

### D11 Performance — Score 3/5 (Corti 5/5)

3/4 deterministic agents are excellent (<100ms). Medical-coding UX is broken by 60s frontend axios timeout vs 115s backend orchestrator.

**Why 3 not 4:** the deterministic agents are fast and reliable. The medical-coding timeout is a P1 bug that breaks the user-facing chat experience.

### D12 i18n — Score 5/5 (Corti 2/5) ★

**iCoDer beats Corti.** Full bilingual (zh + en) support with language toggle. All sidebar items, agent names, descriptions, chat prompts, run trace labels, and Tool Dispatch Detail fields have both zh + en translations. Corti Console is English-only.

This is a China-market requirement and a real differentiator.

## Final verdict

**Total: 42/60 (70%)**

### Letter grade: B

**Rubric:**
- A (50-60): production-ready, full Corti parity or better
- B (40-49): structural parity achieved; 1-2 P0/P1 blockers remain
- C (30-39): partial parity; multiple P0/P1 blockers
- D (<30): fundamental gaps in architecture or execution

**iCoDer earns B** because:
- ✅ Structural parity with Corti at platform level (A2A + MCP + 9-step RunTrace + sidebar IA + Agent Hub)
- ✅ Beats Corti on 3 dimensions (RunTrace viewer / Tool Dispatch Detail / i18n)
- ❌ Has 1 P0 blocker (medical-coding output quality bug)
- ❌ Has 1 P1 blocker (frontend axios 60s timeout)
- ❌ Lacks 5 Corti conversational chat features (P2)

### Path to A

To upgrade from B to A, iCoDer must close:
1. **P0 — medical-coding output quality bug** (fix retrieval pipeline + procedure extraction; add eval regression to prevent recurrence)
2. **P1 — frontend axios 60s timeout** (raise to 300s or switch to SSE streaming)
3. **P2 — chat UX features** (Add context / Reply / Copy / Suggest prompt / What can you do)
4. **P2 — 9 missing Corti pre-built agents** (stub + implement Rule Explainer / ICU / Triage / Medication Reconciliation / Discharge Education / Nursing Handoff / Prior Auth / Referral / Clinical Education / Clinical Guidelines)
5. **P3 — sidebar Text Generation + Embedded Assistant + 3 Speech-to-Text sub-modes**
6. **P3 — live cost UI + API Client selector + announcement banner**

Estimated effort: 4-6 weeks for P0+P1 (blockers), 8-12 weeks for P2+P3 (parity polish).

## Per-agent verdict

| Agent | Verdict | Notes |
|-------|---------|-------|
| compliance-guardrail-agent | A (5/5) | Deterministic, fast, correct output, full Tool Dispatch Detail |
| code-validation-agent | A (5/5) | Deterministic, fast, correct output |
| note-completeness-agent | A (5/5) | Deterministic, fast, correct output |
| medical-coding-agent | D (1/5) | Wrong primary dx + 8 hallucinated procedures + 60s frontend timeout |

**Bottom line:** iCoDer's deterministic agents are production-ready. The orchestrator-driven medical-coding-agent has a critical quality bug that must be fixed before Phase 4 GA. The platform infrastructure (A2A + MCP + RunTrace + Tool Dispatch Detail) is best-in-class and exceeds Corti.
