# Phase 5 Track B — Agent Product Redesign Recommendation

**Date:** 2026-07-11
**Source:** B-1.1 ~ B-1.5 audit findings
**Purpose:** Recommend first hospital pilot agent + first multi-agent chain + product roadmap to track B-2

## 1. Recommended first hospital pilot agent

### **`icoder/medical-coding-agent@2.0.0`** (医学编码智能体)

**Why this agent:**

| Criterion | Score | Rationale |
|---|---|---|
| Corti parity | 1:1 EXACT_MATCH | Both are flagship Coding and Revenue Cycle agents |
| China localization | Done | ICD-10-CN + ICD-9-CM-3 + Chinese clinical terms |
| Maturity | MVP → ready to promote | 200+ smoke runs since Phase 4-F1 |
| Workflow depth | 7-step + dual mode | Corti 7-step + MedCodER 5-stage (dual mode is iCoDer-only advantage) |
| Compliance gate | Hard gate | `human_review=required` + 4 red_lines |
| Audit trail | Full | RunHistory + RunTrace + 7 inline trace events + persisted trace_events |
| Cost transparency | Live | Topbar ¥X.XXXXXX per run |
| Hospital buyer value | Critical | Addresses #1 hospital financial workflow (编码合规) |
| Engineering ownership | iCoDer | 100% self-built, no vendor lock-in |

**Pilot scenario:** 50 inpatient cases at a Tier 2 hospital → 编码员 reviews AI suggestions → measure productivity gain (target: 30% reduction in coding time) + accuracy (target: F1 ≥ 0.92 vs 编码员 final codes).

**Prerequisites:**
- Promote maturity from `mvp` to `runnable` once 50-case smoke complete
- Promote `production_ready` to true once 200-case production validation complete
- Run GAP-14-02 fix (wire 3 Corti-equivalent experts: pubmed/web-search/medical-calculator) — optional for pilot

## 2. Recommended first multi-agent chain

### **编码合规五步链 (Coding Compliance 5-Step Chain)**

```
Step 1: evidence-extractor
  Input: 病历文本
  Output: per-finding evidence spans + strength scores

Step 2: medical-coding-agent (corti_like_fast mode)
  Input: 病历文本 + evidence from step 1
  Output: primary/secondary dx codes + procedure codes

Step 3: code-validation-agent
  Input: codes from step 2
  Output: PASS/WARNING/FAIL per code + cross-code issues

Step 4: drg-analyzer
  Input: codes from step 2 + 病历文本
  Output: risk_points + upcoding/downcoding flags

Step 5: note-completeness-agent
  Input: 病历文本
  Output: missing sections + completeness_score
```

**Why this chain:**

| Property | Value |
|---|---|
| Agent count | 5 (all iCoDer, 2 are ICODER_ONLY) |
| Total latency (estimated) | 5s + 7s + 4s + 4s + 3s = ~23s (sequential) |
| Compliance coverage | 编码 + 校验 + DRG + 文书 (full 编码合规 stack) |
| Corti equivalent | NONE — Corti has no DRG + no standalone evidence + no chain orchestration |
| Hospital value | Replaces 4-6 manual steps in current 编码员 workflow |

**Orchestration:** Use A2A v0.3 task protocol (Phase 6). For Phase 5 Track C, sequential HTTP calls via iCoDer unified endpoint suffice.

**Output:** Single audit-ready packet containing:
- Evidence spans (step 1)
- Code assignment (step 2)
- Validation report (step 3)
- DRG risk review (step 4)
- Documentation gaps (step 5)
- Combined trace_refs across all 5 runs

## 3. Product roadmap for Phase 5 Track B-2

### P1 (must close before pilot, ~4-6 days)

| Gap | Effort | Owner |
|---|---|---|
| GAP-13-01: Add 4 runnable agents to `.well-known/agent.json` | 1h | backend |
| GAP-13-03: Promote 3 PARTIAL_MATCH agents (diagnosis-extractor / denial-appeals / cdi-review) | 3-5d | backend + agents |
| GAP-14-03: Recategorize note-completeness-agent to Point of Care Tools | 30min | backend |

### P2 (post-pilot, ~3-5 weeks)

| Gap | Effort | Owner |
|---|---|---|
| GAP-14-02: Wire 3 Corti-equivalent experts (pubmed/web-search/medical-calculator) | 2-3d | backend |
| GAP-14-04: Expand drg-analyzer rule coverage | 2-3d | domain + backend |
| GAP-14-05: CN-DRG groupor integration | 1w | domain + backend |
| GAP-14-06: DIP scoring engine | 3-5d | domain + backend |
| GAP-14-07: Expand evidence_anchoring_kb 972 → 5,000 codes | 1w | data + backend |
| GAP-13-04: Build 4 Corti-equivalent category agents (Point of Care / Clinical Evidence / Care Coordination / CDI) | 1-2w | backend + domain |
| GAP-13-05: Backfill category_display for 5 prior metadata agents | 1h | backend |

### P3 (post-China-launch)

| Gap | Effort |
|---|---|
| streaming_sse (integration gap) | 2-3d |
| webhook_callbacks + webhooks_outbound (integration gap) | 1-2d |
| multi_language (i18n for JP/KR/SG markets) | 2-3w |
| expert_routing (LLM-driven conditional routing) | 1w |

## 4. Strategic positioning

**iCoDer vs Corti positioning for hospital buyers:**

| Dimension | iCoDer | Corti |
|---|---|---|
| Geographic focus | China (CN-DRG/DIP, ICD-10-CN, 中国医保) | US (ICD-10-CM, CPT/HCPCS, CMS) |
| Compliance philosophy | Evidence-first + manual review hard gate | Productivity-first + LLM-driven flexibility |
| Audit trail depth | Per-run trace_events + RunHistory + RunTrace UI | Aggregate dashboard only |
| Cost transparency | Live per-run cost in Topbar | Daily aggregate only |
| Agent count | 24 (9 runnable, 15 metadata-only) | 20 (all production) |
| Pilot agent | medical-coding-agent (dual mode) | medical-coding-icd-10-cpt-agent |

**iCoDer's pitch to a Chinese hospital:** "Corti-quality agent architecture, China-localized for ICD-10-CN + DRG/DIP, with full audit trail for医保 compliance. 5-agent chain covers your entire编码合规 workflow."

## 5. Decision needed

User to confirm:
1. **Pilot agent**: medical-coding-agent (recommended) OR another agent?
2. **Pilot hospital profile**: Tier 2 (recommended for first pilot) or Tier 3?
3. **Track B-2 sequencing**: Close all 3 P1 gaps first (4-6d) then start pilot, OR start pilot now and fix P1 in parallel?
4. **Multi-agent chain**: Build the 5-step chain in Phase 5 Track C (recommended) or defer to Phase 6?

Per "已锁定决策" pattern, recommend defaults:
1. medical-coding-agent
2. Tier 2 hospital (large enough volume, small enough risk)
3. Start pilot in parallel with P1 fix (parallel tracks de-risk timeline)
4. Build 5-step chain in Phase 5 Track C (sequential HTTP, no orchestrator needed for v1)
