# Phase 5 Track D — P0.5 Gate 6 — Workbench Product Language + Corti UI Comparison

**Date**: 2026-07-12
**PDF**: `iCoDer CDI Phase 5 Track D P0.5 Prompt.md` §3.4 R10/R11/R12 + Master Task §七
**Prior state**: Gate 5 PASS — Expert routing 4.0→1.0/case, C09 experts=0, -37% tokens, 298/298 tests PASS.
**Gate 6 scope**: workbench-facing product-language polish + Corti side-by-side walkthrough. No backend changes; pure frontend i18n / status-layering / role-gated disclosure refactor.
**Verdict**: **PARTIAL_IMPROVEMENT** — empirical before/after only, no verdict flag flips (per PDF §18).

---

## 1. Scope and risk mapping (Master Task §7.1-§7.4)

| Risk | Symptom pre-Gate-6 | Gate 6 close |
|---|---|---|
| **R10 internal-terminology leakage** | frontend showed `diagnostic_specificity` / `LLM_KNOWLEDGE_ONLY` / `coding-expert` raw enum / `RealCDIRunner` / `Phase 5 Track D` literals | cdiLabels.ts maps every backend enum to Chinese business label; raw enum only resurfaces inside admin/auditor-only "技术与审计详情" collapse |
| **R11 raw state-machine enum exposed** | `DRAFT / PENDING_CDI_REVIEW / SENT_TO_CLINICIAN` raw strings shown on chips and action buttons | LIFECYCLE_LABELS (12 states) → 草稿 / 待 CDI 审核 / 已发送医生 etc.; chips and action buttons read Chinese throughout |
| **R12 inconsistent labels across screens** | some pages used `cdi_specialist` (role enum), others used "CDI Specialist:" prefix, others "QC" | ROLE_LABELS unifies to 管理员/CDI 专员/临床医生/审计员/只读; single mapCDIRole() resolves app role to CDI role |

---

## 2. Design — three structural changes to CDIWorkbenchPage.tsx

### 2.1 Status layering (Master Task §7.3)

Clinical/CDI/auditor users think in six parallel status dimensions, not one. Pre-Gate-6 showed only "病例状态" inline; the other five were scattered or absent. Post-Gate-6 a `StatusRow` component renders a vertical stack:

```
状态分层
  病例状态        需要人工审核       ← labelCompletion(completion_state)
  缺口状态        发现 3 项          ← derived from documentation_gaps.length
  澄清任务状态    1 个任务           ← derived from proposed_provider_queries.length
  非诱导检查      通过               ← derived: PASS unless any query BLOCK
  必要性检查      已通过结构检查     ← confirms necessity gate ran
  证据支持状态    已校验 (每个关键声明均有病历证据)  ← confirms CEA gate ran
```

Each row derives its value from `caseData`; no extra backend call. Empty state (`idle`) hides the entire section because no case is loaded yet.

### 2.2 技术与审计详情 collapse (Master Task §7.4)

Stage traces / Token counts / run_id / trace_id / raw expert_id / raw execution_mode are operationally important for admin and auditor roles, but they are **NOT** business information. Clinicians seeing them confuses the mental model (Master Task §7.1: "普通业务界面不得显示 Token / run_id / trace_id / 原始 enum").

Post-Gate-6 layout:
- New `canSeeTechDetails(role)` predicate returns `true` only for `admin` and `auditor`.
- If predicate is `false`, the entire section does not render — no collapsed stub, no chevron, nothing.
- If predicate is `true`, a `<button>` toggles `techDetailsOpen` (default `false`). Section header reads `技术与审计详情 (N)` with a Lock icon.
- Inside the expanded panel: each stage trace row shows `{expert_label or stage_key} · {latency_ms}ms · {total_tokens}tok · {run_id}`. These remain technical (snake_case stage names, raw run_id) because the user self-selected into the technical view.

### 2.3 Role-aware action matrix cleanup

Pre-Gate-6 buttons leaked role/state into the button text:
- `CDI Specialist: 审核通过 (APPROVED)`
- `(CLOSED)`
- `Cancel (read_only)`

Post-Gate-6 `ActionButtons` component:
- Each state branch returns either a single Chinese action verb (`提交 CDI 审核` / `审核通过` / `发送给医生` / `标记为已查看` / `提交答复` / `CDI 复核`) or a status-only panel (`审计员只读` / `只读权限` / `已关闭` / `已升级 — 医生无法确定, 需人工跟进`).
- Role gating moves to `if (canReviewCDI)` / `if (canRespondClinician)` flags; the verb text itself is clean.

---

## 3. cdiLabels.ts — full enum→Chinese map catalog

| Map | Size | Source |
|---|---|---|
| `LIFECYCLE_LABELS` | 12 states | PDF §4.4 lifecycle |
| `COMPLETION_LABELS` | 4 states | AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED |
| `GAP_TYPE_LABELS` | 9 types | PDF §6.2 gap taxonomy |
| `NLQ_VERDICT_LABELS` | 3 | PASS / BLOCK / PENDING |
| `EXPERT_LABELS` | 4 | coding / pubmed / web-search / medical-calculator |
| `EXECUTION_MODE_LABELS` | 6 | Gate 5 ExpertExecutionMode enum |
| `RISK_FLAG_LABELS` | 4 | contradiction / unsupported_dx / ambiguous_term / copied_forward |
| `ROLE_LABELS` | 5 | admin / cdi_specialist / clinician / auditor / read_only |
| `RULE_ID_LABELS` | 29 | NLQ-001..011 + NQ-001..006 + SD-001..003 + CEA-001..009 |
| `SEMANTIC_VERDICT_LABELS` | 4 | PASS / REVIEW_REQUIRED / BLOCK / DEGRADED |
| `SEMANTIC_REASON_LABELS` | 5 | Gate 4 semantic codes |

11 lookup helpers (`labelXxx(value)`) with forward-compatible fallback (returns the raw value if unknown, so future backend enum additions don't crash the UI).

---

## 4. Corti UI walkthrough — observed comparison

Corti does **not** ship a CDI agent (only Medical Coding, Fact Extraction, Speech-to-Text, etc.). For the closest analog we walked through `AI Studio > Medical Coding` (input text → AI analysis → structured output) and `AI Studio > Agents` (catalog) — both observed via authorized account `songluhua@gmail.com` on console.corti.app.

### 4.1 Corti AI Studio > Agents (catalog page)

| Element | Corti | iCoDer CDI Workbench |
|---|---|---|
| Page header | "AI Studio / Agents" + `$0.000000 / API Client / $44.36` badge | "CDI 工作台 / 临床文档改进 · 临床事实被写清楚" + `¥50.00` |
| Currency | USD `$` | CNY `¥` (per CLAUDE.md §货币约定) |
| Hero CTA | "Create an agent / Build healthcare agents to take action across your systems / [New Agent]" | None — CDI workbench is single-purpose, not agent-authoring |
| Catalog tabs | "My agents" / "Pre-built agents" | None — only one CDI workbench exists |
| Card metadata | name + creation date + author | (N/A — no catalog) |

### 4.2 Corti AI Studio > Medical Coding (input→output page)

| Element | Corti | iCoDer CDI Workbench |
|---|---|---|
| Layout | 2-pane (Input flex-1 / Output w-480) + Event Inspector bottom | 3-pane (病例摘要 320px / 缺口+任务 flex-1 / 任务详情 420px) |
| Toolbar | Coding systems combobox + Predict codes + Config | (None — CDI has no coding-system selector; per PDF §16 no ICD visible to clinician) |
| Sample loader | 4 chips: Hospital medical record / GP transcript / Orthopedic referral letter / Guided demo | Single textarea + "加载已有病例" by case_id |
| Primary action | "Predict codes" | "运行 CDI 分析" |
| Empty state | "Predicted codes will show here" | "输入病历文本, 运行 CDI 分析 / 工作台将识别文档缺口并生成临床澄清任务" |
| Output cards | Per-code: code + description + Evidence (quoted strings) + Alternatives + Candidates | Per-gap: gap_type label + description + why_it_matters + Evidence quote; Per-query: topic + reason + lifecycle chip + option count |
| Right panel | (none) | 任务状态 + 澄清问句 + 可选答复 (radio) + 非诱导检查 + role-aware ActionButtons |
| Live cost | `$0.043360` per call shown in topbar (after run) | `¥50.00` credits in topbar (Phase 4-G wiring; per-call cost on RunTrace page) |

### 4.3 Corti AI Studio > Fact Extraction (second analog)

| Element | Corti | iCoDer CDI Workbench |
|---|---|---|
| Layout | 2-pane (Input/Samples + Output) + Settings/Code right tabs | 3-pane (no Settings/Code tab — CDI workbench is consumer-only) |
| Output language | Settings tab → "Output language: English (US) / en-US" | Hard-coded Chinese (product is China-focused per CLAUDE.md) |
| Generated content | Free-form facts | Structured gaps + queries with lifecycle state machine |

### 4.4 Key product-language differences (the actual Gate 6 lesson)

| Dimension | Corti choice | iCoDer CDI choice | Why |
|---|---|---|---|
| Currency | USD `$` | CNY `¥` | iCoDer is China-hospital-focused; DeepSeek priced in RMB |
| Output language | User-configurable (Settings tab) | Hard-coded zh-CN | Product target is Chinese hospitals; CLAUDE.md §产品定位 |
| Code visibility | ICD-10-CM codes prominent (J18.1 etc.) | ICD codes NEVER shown to clinician | PDF §16 forbids; CDI ≠ coding; NLQ-010 rule |
| Status vocabulary | None (stateless API call) | 12-state lifecycle (DRAFT → … → CLOSED) | CDI is a workflow, not a one-shot |
| Role awareness | None in console (it's a developer tool) | 5 roles (admin/cdi_specialist/clinician/auditor/read_only) with different action matrix | CDI is multi-role hospital workflow |
| Sample data | 4 pre-built samples | None (per Phase 5 P0 Gate 6 commit e18efcc: no SAMPLE_CASE) | PDF A8 fix — sample case was misleading |
| Empty state | "Predicted codes will show here" | "输入病历文本, 运行 CDI 分析" | iCoDer guides the user toward input; Corti just waits |

---

## 5. Forbidden-items audit (PDF §16 + Master Task §7.1)

Walkthrough grep on `CDIWorkbenchPage.tsx` after Gate 6:

```
Forbidden literal                  | Count in file
-----------------------------------+--------------
"Phase 5" / "P0" / "P0.5"          | 0 in user-facing text (1 in file header comment only)
"Core Entry Agent"                 | 0
"RealCDIRunner"                    | 0
"PDF" / "§"                        | 0
"NLQ-001" / "NQ-001" (raw code)    | 0 — only via labelRuleIds() lookup
"DRAFT" / "PENDING_CDI_REVIEW"     | 2 occurrences, both as object-key lookups in LIFECYCLE_LABELS map / LIFECYCLE_COLOR map (not rendered)
"coding-expert" / "pubmed-expert"  | 0 rendered — lookup keys only
"LLM_KNOWLEDGE_ONLY"               | 0 rendered — lookup key only
"token" / "run_id" / "trace_id"    | only inside 技术与审计详情 collapse (admin/auditor only)
```

The pre-Gate-6 file had ~17 user-facing occurrences of these literals. Gate 6 closes all 17.

---

## 6. Empirical verification

### 6.1 Browser walkthrough (real DeepSeek run)

Backend: uvicorn on :8000 with Gate 4+5 code. Frontend: Vite on :3000. User: `p05g6_1783814493` (role=ADMIN). Input chart:

> 患者男性,58岁,因咳嗽咳痰伴发热3天入院。查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。需要明确是社区获得性肺炎还是院内获得性肺炎,以及具体病原体。

Backend returned (CASE-64cf793d91ca, ~28s real DeepSeek, 7 stage traces):
- 3 documentation_gaps (all 诊断特异性)
- 1 proposed_provider_query (DRAFT, 4 response_options, NLQ verdict PENDING because never transitioned)
- 4 specialist_trace entries: coding + pubmed invoked (LLM_KNOWLEDGE_ONLY); web + calculator SKIPPED_NOT_NEEDED

### 6.2 What the user sees (admin role)

Screenshots in `docs/corti_parity/phase5_d_p05_gate6/`:
- `icoder_cdi_idle_gate6.png` — empty state with hint
- `icoder_cdi_populated_gate6.png` — full 3-pane populated
- `icoder_cdi_tech_expanded_gate6.png` — admin sees the 技术与审计详情 expanded

Key UI assertions (visible in screenshots):
- ✅ Topbar shows `¥50.00` (CNY, not USD)
- ✅ Header reads `CDI 工作台 / 临床文档改进 · 临床事实被写清楚` — no PDF / Phase / Track / P0.5
- ✅ Right corner shows `当前角色: 管理员` — not `admin` or `ADMIN`
- ✅ 状态分层 section shows all 6 rows with Chinese values
- ✅ 专家协作 shows `编码专家 / 模型知识 (未接真实工具)` etc. — no raw expert_id or execution_mode
- ✅ Gap card shows `诊断特异性` — not `diagnostic_specificity`
- ✅ Query chip shows `草稿` — not `DRAFT`
- ✅ Action button reads `提交 CDI 审核` — not `CDI Specialist: approve (PENDING_CDI_REVIEW)`
- ✅ Tech details section is collapsed by default (admin sees Lock icon + chevron + count)
- ✅ Expanding tech details shows stage names + latency + tokens + run_id (admin opted in)

### 6.3 Type check + test sweep

```
$ npx tsc --noEmit
(no output = 0 errors)

$ npx vitest run
Test Files  8 passed (8)
     Tests  77 passed (77)
```

No regressions in frontend tests. Backend untouched (Gate 6 is frontend-only).

---

## 7. Corti comparison — verdict per dimension

| Dimension | iCoDer CDI vs Corti Medical Coding | Tier |
|---|---|---|
| Layout clean-ness | Match (iCoDer 3-pane > Corti 2-pane for workflow, but Corti is one-shot so 2-pane fits) | PARITY |
| Currency correctness | iCoDer ¥ (correct for China) > Corti $ (correct for EU/US) | BOTH_CORRECT |
| Sample set | Corti ships 4 samples; iCoDer ships none (deliberate per PDF A8) | ICODER_CHOICE |
| Code visibility | iCoDer hides ICD (correct per PDF §16); Corti shows ICD (correct for coding product) | BOTH_CORRECT |
| Status vocabulary | iCoDer 12-state lifecycle; Corti stateless | ICODER_ADVANTAGE |
| Role awareness | iCoDer 5 roles with action matrix; Corti none | ICODER_ADVANTAGE |
| Live cost display | Both show in topbar | PARITY |
| Output language config | Corti configurable; iCoDer hard-coded zh-CN | ICODER_CHOICE |

**Verdict**: no dimension where iCoDer regresses below Corti. iCoDer extends Corti's one-shot pattern into a multi-role hospital workflow — which is the product's actual job-to-be-done.

---

## 8. What Gate 6 IS closing

- **R10 internal-terminology leakage**: CLOSED on workbench — every backend enum replaced with Chinese business label.
- **R11 raw state-machine enum**: CLOSED on workbench — 12 lifecycle states + 6 execution modes + 9 gap types all labeled.
- **R12 inconsistent labels**: CLOSED — single `cdiLabels.ts` module is the source of truth; lookup helpers used everywhere.
- **Technical-detail disclosure**: CLOSED — `canSeeTechDetails` predicate + collapsed section hides tokens/run_id/trace_id from clinicians.
- **Status layering**: CLOSED — 6-row stack surfaces the parallel status dimensions that clinicians actually need.

## 9. What Gate 6 is NOT catching (honest accounting)

- **Settings / Code right-panel pattern**: Corti exposes `Settings` (output language, model params) and `Code` (SDK tabs) on every AI Studio page. iCoDer CDI workbench has neither — the workbench is a consumer-only view, not a developer tool. If a future phase adds a developer-facing CDI Playground, it should adopt Corti's Settings/Code pattern.
- **Output language configurability**: hard-coded to zh-CN. If international deployments materialize (EU/US environments per CLAUDE.md), the labels need to be promoted into i18n message bundles. Current i18n keys exist in `frontend/src/i18n/` but `cdiLabels.ts` is not yet wired through it.
- **Sample chart library**: Corti ships 4 pre-built samples per AI Studio page. iCoDer CDI ships none — this was a Phase 5 P0 deliberate choice (PDF A8: SAMPLE_CASE removed because it was misleading). A future phase could add a curated sample library of 5-10 representative charts (社区获得性肺炎 / 心衰急性加重 / 糖尿病酮症 etc.) for training demos, clearly labeled as "示例 (非真实病例)".
- **Stage name i18n inside tech panel**: stage traces inside 技术与审计详情 still show snake_case keys (`encounter_synthesis`, `gap_identification`). Acceptable because the panel is admin/auditor-only and those users want raw keys for debugging. If we ever surface stage names to non-technical users, a STAGE_LABELS map would be needed.

---

## 10. PDF §16 forbidden-items checklist

- ✓ No `production_ready` / `validated` flag flipped — Gate 6 verdict is PARTIAL_IMPROVEMENT
- ✓ No ICD codes exposed to clinicians — workbench never renders codes
- ✓ No diagnosis invention — Gate 6 is UI-only, no backend change
- ✓ No leading query language — gate compliance unchanged
- ✓ No CMI / payment optimization language — labels stay clinical
- ✓ No Stub disguised as real — walkthrough used real DeepSeek (28s, ~2K tokens)
- ✓ No PubMed/web-search impersonation — `模型知识 (未接真实工具)` label discloses LLM_KNOWLEDGE_ONLY execution mode in Chinese
- ✓ No LLM-score-fabrication — `未调用: 当前病例不需要` discloses SKIPPED_NOT_NEEDED

---

## 11. PDF §18 verdict-ladder compliance

**PARTIAL_IMPROVEMENT** (Gate 6 tier, per Master Task §七):

- Forbidden-items audit clean (17 leaks → 0)
- Status layering + 技术与审计详情 collapse live
- 11 cdiLabels maps + 11 helpers wired
- Browser walkthrough verified on real DeepSeek (admin role sees full picture)
- tsc 0 errors + vitest 77/77 pass
- No verdict flag flipped; CDI agent label (`preview` per §B6) unchanged

This verdict is deliberately below `CHECKPOINT_*_PASS` — Gate 6 has no Checkpoint C/D criteria to meet because the change is product-language polish, not behavioral. Checkpoint C belongs to Gate 7 (4-role E2E).

---

## 12. Evidence files

| File | Purpose |
|---|---|
| `frontend/src/services/cdiLabels.ts` | NEW — 11 label maps + 11 helpers (~246 LOC) |
| `frontend/src/services/cdiApi.ts` | MODIFIED — SpecialistTraceEntry interface (Gate 5 fields) |
| `frontend/src/pages/CDIWorkbenchPage.tsx` | MODIFIED — status layering + 技术与审计详情 collapse + Chinese labels throughout (~918 LOC) |
| `docs/corti_parity/phase5_d_p05_gate6/corti_home_gate6.png` | Corti Console home walkthrough |
| `docs/corti_parity/phase5_d_p05_gate6/corti_medical_coding_gate6.png` | Corti Medical Coding empty state |
| `docs/corti_parity/phase5_d_p05_gate6/corti_medical_coding_output_gate6.png` | Corti Medical Coding populated (5 codes + evidence + alternatives) |
| `docs/corti_parity/phase5_d_p05_gate6/icoder_cdi_idle_gate6.png` | iCoDer CDI Workbench empty state |
| `docs/corti_parity/phase5_d_p05_gate6/icoder_cdi_populated_gate6.png` | iCoDer CDI Workbench 3-pane populated (admin view) |
| `docs/corti_parity/phase5_d_p05_gate6/icoder_cdi_tech_expanded_gate6.png` | iCoDer CDI Workbench 技术与审计详情 expanded |

---

## 13. What Gate 6 does NOT close

| Risk | Gate | Status after Gate 6 |
|---|---|---|
| R10/R11/R12 frontend language | 6 | ✓ CLOSED on workbench — labels, status layering, role-gated disclosure live |
| R13 4-role E2E | 7 | ⬜ NOT STARTED |
| R14 40-case Corti calibration | 8 | ⬜ NOT STARTED |

---

## 14. Known carry-forward

1. **cdiLabels.ts not yet wired through i18n bundles** — `frontend/src/i18n/locales/` has zh-CN/en-US structures, but `cdiLabels.ts` is a parallel module. If we ever need EN versions of CDI labels (EU/US deployment), the maps need to move into the i18n message catalog.
2. **No sample chart library** — Corti ships 4 samples per AI Studio page; iCoDer CDI ships zero (Phase 5 P0 Gate 6 PDF A8 decision). Future training/demo needs may want a curated library clearly labeled "示例 (非真实病例)".
3. **Stage names inside 技术与审计详情 remain snake_case** — `encounter_synthesis` / `gap_identification` / `query_generation` / `claim_evidence_alignment_gate` etc. Acceptable because the panel is admin/auditor-only; technical users want raw keys for log correlation.
4. **`mapCDIRole` is a stub** — maps `admin`/`qc`/`clinician`/`insurance` → CDI roles. The actual app role enum is `ADMIN/CODER/DEPT_HEAD/...` so the mapping currently falls through to `read_only` for most users. Gate 7 will need to fix this for the 4-role E2E.
5. **Tech-details panel layout is dense** — once 10+ stage traces exist, the panel becomes a long list. Future polish could group by stage category (orchestration / gates / experts) and add latency sparklines.

---

## 15. Resume point for next session

After Gate 6 commit (pending), next session opens **Gate 7 — 4-Role Browser E2E** (Master Task §八):

- Walk through workbench as ADMIN / CDI_SPECIALIST / CLINICIAN / AUDITOR
- Verify role-gated action matrix and 技术与审计详情 visibility for each role
- Verify lifecycle transitions work for at least one query through the full DRAFT → PENDING_CDI_REVIEW → APPROVED → SENT_TO_CLINICIAN → VIEWED → RESPONDED → DOCUMENTATION_UPDATED → REVALIDATED → CLOSED chain
- Checkpoint C: each role can complete its assigned action without seeing forbidden items

Estimated work: ~6 hours / ~30K tokens (mostly browser walkthrough + screenshot evidence).
