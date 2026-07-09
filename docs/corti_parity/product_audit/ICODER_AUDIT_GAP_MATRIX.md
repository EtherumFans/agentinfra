# Phase 3-D2.5 — iCoDer × Corti Parity Audit Gap Matrix

**Date:** 2026-07-07
**Status:** DONE — 12 dimensions × 27 gaps catalogued

## Legend

- **Severity:** P0 (blocker) / P1 (high) / P2 (medium) / P3 (low) / ✅ (no gap, iCoDer matches or beats Corti)
- **Effort:** S (≤1 day) / M (1-5 days) / L (1-4 weeks) / XL (4+ weeks)
- **Phase:** 3-D2.6 (next, blockers) / 3-D2.7 (chat UX) / 3-D2.8 (roster) / 3-D2.9 (polish) / Phase 4.1+

## D1 — Sidebar Information Architecture (4 gaps)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 1.1 | Text Generation sidebar item | absent | present | P3 | S | 3-D2.9 |
| 1.2 | Embedded Assistant sidebar item | absent | present | P3 | S | 3-D2.9 |
| 1.3 | Corti Models sub-item (frontier model marketplace) | absent | present | P3 | L | Phase 4.1+ |
| 1.4 | Speech to Text 3 sub-modes (Dictation / Ambient / Pre-recorded) | 1 item | 3 sub-modes | P3 | M | 3-D2.9 |
| — | All other sidebar items (14/17) | ✅ match | — | ✅ | — | — |

## D2 — Agent Hub layout & filtering (3 gaps)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 2.1 | Live cost counter ("$0.000000 Reset live cost") | absent | present | P3 | M | 3-D2.9 |
| 2.2 | Balance display ("$49.22") | absent | present | P3 | S | 3-D2.9 |
| 2.3 | API Client combobox in breadcrumb | absent | present | P2 | M | 3-D2.7 |
| 2.4 | Product announcement banner ("Corti Models is here") | absent | present | P3 | S | 3-D2.9 |
| — | Tab toggle (My/Pre-built) | ✅ match (tabs vs radio, equivalent UX) | — | ✅ | — | — |
| — | Search textbox | ✅ match | — | ✅ | — | — |
| — | Use case filter | ✅ match | — | ✅ | — | — |
| — | Agent card maturity badge + tags | ✅ iCoDer differentiator (better for compliance buyers) | — | ✅ | — | — |

## D3 — Pre-built Agent Roster (9 missing + 4 metadata-only)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 3.1 | Rule Explainer Agent | absent | present | P2 | L | 3-D2.8 |
| 3.2 | Surgical Registry Intelligence Agent | absent | present | P2 | XL | Phase 4.1+ |
| 3.3 | ICU Admission Summary Agent | absent | present | P2 | XL | Phase 4.1+ |
| 3.4 | Triage and Initial Assessment Agent | absent | present | P2 | XL | Phase 4.1+ |
| 3.5 | Medication Reconciliation Agent | absent | present | P2 | L | 3-D2.8 |
| 3.6 | Patient Discharge Education Agent | absent | present | P2 | L | 3-D2.8 |
| 3.7 | Nursing Shift Handoff Agent | absent | present | P2 | L | 3-D2.8 |
| 3.8 | Prior Authorization Agent | absent | present | P2 | L | 3-D2.8 |
| 3.9 | Referral Generator Agent | absent | present | P2 | L | 3-D2.8 |
| 3.10 | Clinical Education Agent | absent | present | P2 | L | 3-D2.8 |
| 3.11 | Clinical Guidelines Agent | absent | present | P2 | L | 3-D2.8 |
| 3.12 | Procedure Entity Extractor | metadata-only | runnable | P2 | L | 3-D2.8 |
| 3.13 | Diagnostic Entity Extractor | metadata-only | runnable | P2 | L | 3-D2.8 |
| 3.14 | Denial Appeals Agent | metadata-only | runnable | P2 | L | 3-D2.8 |
| 3.15 | CDI Agent | metadata-only | runnable | P2 | L | 3-D2.8 |
| 3.16 | ICD-10 Index Navigator | metadata-only | runnable | P2 | L | 3-D2.8 |
| — | Medical Coding Agent | ✅ runnable (orchestrator) | runnable | ✅ | — | — |
| — | Compliance Guardrail Agent | ✅ runnable (deterministic) | runnable | ✅ | — | — |
| — | Code Validation Agent | ✅ runnable (deterministic) | runnable | ✅ | — | — |
| — | Note Completeness Agent | ✅ runnable (deterministic) | runnable | ✅ | — | — |
| — | DRG 分析智能体 | iCoDer-only ✅ (China-specific) | absent | ✅ differentiator | — | — |
| — | 证据排序智能体 | iCoDer-only ✅ | absent | ✅ differentiator | — | — |
| — | 病历缺口智能体 | iCoDer-only ✅ | absent | ✅ differentiator | — | — |

## D4 — Agent Card detail page (5 gaps)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 4.1 | "Add context" button (drop JSON files) | absent | present | P2 | M | 3-D2.7 |
| 4.2 | "Reply..." textbox for follow-up | absent (each run is fresh form) | present | P2 | L | 3-D2.7 |
| 4.3 | "Copy" button on output | absent | present | P2 | S | 3-D2.7 |
| 4.4 | "What can you do?" button | absent | present | P2 | S | 3-D2.7 |
| 4.5 | "Suggest prompt" button | absent | present | P2 | S | 3-D2.7 |
| 4.6 | "Clear chat" button | absent | present | P3 | S | 3-D2.9 |
| 4.7 | "Messaging an agent consumes credits" notice | absent | present | P3 | S | 3-D2.9 |
| — | Version + source ref + maturity badge on card | ✅ iCoDer differentiator | — | ✅ | — | — |
| — | Preset prompt paragraph | ✅ iCoDer differentiator | — | ✅ | — | — |

## D5 — Real-time orchestrator progress (1 gap)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 5.1 | Live "Calling expert: ..." messages in chat | absent (only "运行中…" button) | present | P2 | L | 3-D2.7 |
| — | SSE/Streams infrastructure (built in Phase 1.2) | ✅ present (just not wired to chat UI) | — | ✅ | — | — |

## D6 — Output rendering (2 gaps)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 6.1 | "Copy" button on rendered output | absent | present | P2 | S | 3-D2.7 |
| 6.2 | Emoji markers (⚠ ❌) in rendered output | absent (tabular only) | present | P3 | S | 3-D2.9 |
| — | "Rendered" + "JSON" tabs | ✅ iCoDer differentiator (Corti has 1 view) | — | ✅ | — | — |
| — | "View RunTrace" link | ✅ iCoDer differentiator | — | ✅ | — | — |

## D7 — RunTrace viewer (0 gaps, iCoDer beats Corti)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| — | 9-step Corti-parity timeline | ✅ present | absent (no Console viewer) | ✅ iCoDer-only | — | — |
| — | Step expandable detail panel | ✅ present | — | ✅ | — | — |
| — | "raw safe_metadata" JSON view (redacted) | ✅ present | — | ✅ | — | — |
| — | Blue border for dispatcher's 4 steps | ✅ present | — | ✅ | — | — |

## D8 — Tool Dispatch Detail (0 gaps, iCoDer beats Corti)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| — | 15-field dispatch_detail dict | ✅ present (Phase 3-D2.5 Part A) | absent | ✅ iCoDer-only | — | — |
| — | Auto-expand on handler_status=failed | ✅ present | — | ✅ | — | — |
| — | Display-safe invariant (no token/secret/PHI) | ✅ verified by 9/9 tests | — | ✅ | — | — |
| — | 3-layer redaction (input → trace → DB → API → render) | ✅ verified | — | ✅ | — | — |

## D9 — Safety / PHI / Auth (0 gaps, iCoDer verifiably safe)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| — | 4 API responses clean (trace / tools/list / message:send / tools/call) | ✅ verified | — | ✅ | — | — |
| — | PHI redaction (input "呼吸困难" not in trace) | ✅ verified | — | ✅ | — | — |
| — | 4 MCP auth types (in-process / oauth / static_token / heroku) | ✅ present | — | ✅ | — | — |
| — | 7 MCP error codes (-32006..-32012) | ✅ present | — | ✅ | — | — |
| — | `_redact_safe_metadata` + `_KNOWN_SECRET_KEYS` + `_is_token_blob` | ✅ present | — | ✅ | — | — |
| — | Frontend `SECRET_KEY_RE` defense-in-depth regex | ✅ present | — | ✅ | — | — |

## D10 — Output quality (1 P0 critical bug)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 10.1 | medical-coding-agent wrong primary dx (J44.900 COPD vs I20.0 unstable angina) | ❌ wrong | ✅ correct | **P0** | L | 3-D2.6 |
| 10.2 | medical-coding-agent 8 hallucinated procedures (腹腔穿刺 / 胸膜外引流 / 中心静脉置管 / 气管插管 / 呼吸机 / 血液透析 / 子宫内输血 / 静脉输液港) | ❌ hallucinated | ✅ correct | **P0** | L | 3-D2.6 |
| 10.3 | medical-coding-agent missed 3 documentation gaps (diabetes type / PCI detail / encounter type) | ❌ missed | ✅ caught | P1 | M | 3-D2.6 |
| 10.4 | medical-coding-agent missed 2 uncodable items (vessel location / complications) | ❌ missed | ✅ caught | P1 | M | 3-D2.6 |
| 10.5 | medical-coding-agent 9 secondary diagnoses (over-coding tendency) | ⚠ over-coded | ✅ 3 appropriate | P1 | M | 3-D2.6 |
| 10.6 | medical-coding-agent over-confident validation ("passed: true, manual_review_required: false") | ⚠ over-confident | ✅ "Medium" calibrated | P1 | M | 3-D2.6 |
| — | compliance-guardrail-agent output | ✅ correct | — | ✅ | — | — |
| — | code-validation-agent output | ✅ correct | — | ✅ | — | — |
| — | note-completeness-agent output (100% completeness score) | ✅ correct | — | ✅ | — | — |

## D11 — Performance (1 P1 blocker)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| 11.1 | Frontend axios 60s timeout vs 115s backend orchestrator | ❌ broken (every medical-coding chat fails) | ✅ ~60s complete | **P1** | S (raise timeout) or L (wire SSE) | 3-D2.6 |
| — | compliance-guardrail-agent (77ms) | ✅ excellent | — | ✅ | — | — |
| — | code-validation-agent (<100ms) | ✅ excellent | — | ✅ | — | — |
| — | note-completeness-agent (<100ms) | ✅ excellent | — | ✅ | — | — |

## D12 — i18n / Localization (0 gaps, iCoDer beats Corti)

| # | Gap | iCoDer | Corti | Severity | Effort | Phase |
|---|-----|--------|-------|----------|--------|-------|
| — | Bilingual (zh + en) language toggle | ✅ present | English-only | ✅ iCoDer-only | — | — |
| — | All sidebar items translated | ✅ present | — | ✅ | — | — |
| — | All agent names + descriptions translated | ✅ present | — | ✅ | — | — |
| — | All chat prompts + run trace labels translated | ✅ present | — | ✅ | — | — |
| — | All 9 Tool Dispatch Detail i18n keys (zh + en) | ✅ present (new in Phase 3-D2.5) | — | ✅ | — | — |

## Summary

| Dimension | Total gaps | P0 | P1 | P2 | P3 | ✅ match / differentiator |
|-----------|------------|----|----|----|----|---------------------------|
| D1 Sidebar IA | 4 | 0 | 0 | 0 | 4 | 14/17 match |
| D2 Agent Hub | 4 | 0 | 0 | 1 | 3 | 7/10 match + maturity badge differentiator |
| D3 Pre-built roster | 16 | 0 | 0 | 16 | 0 | 4/20 runnable + 4/20 metadata-only + 3 iCoDer-only extras |
| D4 Agent card | 7 | 0 | 0 | 5 | 2 | version/source/maturity/preset prompt differentiator |
| D5 Real-time progress | 1 | 0 | 0 | 1 | 0 | SSE infrastructure built but not wired to chat |
| D6 Output rendering | 2 | 0 | 0 | 1 | 1 | Rendered+JSON tabs + RunTrace link differentiator |
| D7 RunTrace viewer | 0 | 0 | 0 | 0 | 0 | iCoDer beats Corti |
| D8 Tool Dispatch Detail | 0 | 0 | 0 | 0 | 0 | iCoDer beats Corti (new in Phase 3-D2.5) |
| D9 Safety / PHI / Auth | 0 | 0 | 0 | 0 | 0 | iCoDer verifiably safe |
| D10 Output quality | 6 | 2 | 4 | 0 | 0 | 3/4 deterministic agents correct; medical-coding broken |
| D11 Performance | 1 | 0 | 1 | 0 | 0 | 3/4 agents excellent; medical-coding timeout |
| D12 i18n | 0 | 0 | 0 | 0 | 0 | iCoDer beats Corti |
| **Total** | **41** | **2** | **6** | **24** | **10** | **+11 differentiators** |

## Priority queue (sorted by severity → effort)

### P0 — Blockers (must fix before Phase 4 GA)

1. **#10.1** — medical-coding wrong primary dx (J44.900 COPD vs I20.0 unstable angina) — L effort, 3-D2.6
2. **#10.2** — medical-coding 8 hallucinated procedures — L effort, 3-D2.6

### P1 — High (must fix before Phase 4 GA)

3. **#11.1** — frontend axios 60s timeout vs 115s backend — S (raise timeout) or L (wire SSE), 3-D2.6
4. **#10.3** — medical-coding missed 3 documentation gaps — M effort, 3-D2.6
5. **#10.4** — medical-coding missed 2 uncodable items — M effort, 3-D2.6
6. **#10.5** — medical-coding 9 secondary diagnoses (over-coding) — M effort, 3-D2.6
7. **#10.6** — medical-coding over-confident validation — M effort, 3-D2.6

### P2 — Medium (close for full Corti parity)

8. **#3.1-3.11** — 9 missing Corti pre-built agents — L-XL each, 3-D2.8 / Phase 4.1+
9. **#3.12-3.16** — 5 metadata-only agents to promote to runnable — L each, 3-D2.8
10. **#4.1-4.5** — 5 chat UX features (Add context / Reply / Copy / Suggest prompt / What can you do) — S-L each, 3-D2.7
11. **#5.1** — live "Calling expert: ..." messages — L effort, 3-D2.7
12. **#6.1** — Copy button on rendered output — S effort, 3-D2.7
13. **#2.3** — API Client combobox — M effort, 3-D2.7

### P3 — Low (polish for parity)

14. **#1.1, 1.2, 1.4** — sidebar Text Generation / Embedded Assistant / 3 STT sub-modes — S-M each, 3-D2.9
15. **#2.1, 2.2, 2.4** — live cost UI / balance / announcement banner — S-M each, 3-D2.9
16. **#4.6, 4.7** — Clear chat button / credits notice — S each, 3-D2.9
17. **#6.2** — emoji markers (⚠ ❌) in rendered output — S effort, 3-D2.9
18. **#1.3** — Corti Models sub-item (frontier model marketplace) — L effort, Phase 4.1+
19. **#3.2-3.4** — Surgical Registry / ICU / Triage agents — XL each, Phase 4.1+

## Differentiators (iCoDer beats Corti)

1. **RunTrace viewer** — 9-step timeline + 15-field Tool Dispatch Detail (Corti has no Console viewer)
2. **Tool Dispatch Detail** — 15-field concentrated view with auto-expand on failure (Corti has no equivalent)
3. **Bilingual i18n** — full zh + en support (Corti is English-only)
4. **Agent card maturity badge + tags** — better for compliance-conscious buyers (Corti cards are sparser)
5. **Rendered + JSON tabs** — developer-friendly output view (Corti has 1 view only)
6. **Version + source ref on card** — explicit provenance (Corti hides these)
7. **Preset prompt paragraph** — explicit task framing (Corti uses conversational "Ask the agent...")
8. **3 China-specific extras** — DRG / Evidence Ranker / Documentation Gap (Corti doesn't serve China DRG/DIP)
9. **Per-agent "View RunTrace" link** — direct drill-down from output to dispatch lifecycle
10. **Blue border for dispatcher's 4 steps** — visual distinction in RunTrace timeline
11. **3-layer redaction defense-in-depth** — input → trace emit → DB persist → API → render (verifiable in 9 tests)

## Conclusion

iCoDer has **41 gaps** against Corti (2 P0 / 6 P1 / 24 P2 / 10 P3) but also **11 differentiators** where it beats Corti. The 2 P0 blockers (medical-coding output quality) and 1 P1 blocker (frontend timeout) are the only Phase 4 GA gates. The remaining 38 gaps are parity polish items that can be closed in 8-16 weeks of focused work (Phase 3-D2.7 / D2.8 / D2.9 / Phase 4.1+).
