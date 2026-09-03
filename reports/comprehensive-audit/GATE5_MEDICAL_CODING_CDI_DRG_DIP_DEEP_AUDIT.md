# Audit Gate 5 — Medical Coding / CDI / DRG-DIP Deep Audit (Tracks E + F + G)

> Per PDF §三 Track E (Medical Coding), Track F (CDI), Track G (DRG/DIP). Investigates real execution path, model connection, hospital-loop maturity, and whether the grouping engine is real vs mock.

## E. Track E — Medical Coding

### E1. Product capability — LIVE (single-runtime)

| Surface | Endpoint | Real call? | Verified by |
|---------|----------|------------|-------------|
| MedicalCodingPage Fast mode | `POST /api/v1/agents/medical-coding-agent/run` (corti_like_fast) | ✅ DeepSeek V4 chat, 5.6s avg over 35 runs | run_history cost_usd=0 but latency_ms=5646 |
| MedicalCodingPage Deep mode | same endpoint, `runtime_mode=medcoder_deep` | ✅ code path exists (MedCoderRuntime → HybridCodingAdapter 5-stage) | **0 production invocations** (G4-006 P1) |
| A2A mainline | `POST /api/icoder/agents/medical-coding-agent/v1/message:send` | ✅ Shared `dispatch_medical_coding_fast` facade | a2a_facade.py:141 |
| Coding Compliance 7-stage | `POST /api/v1/coding-compliance/run` | ✅ 7-stage orchestrator wired (Phase 5 Track C) | coding_compliance.py:42 |

**3 of 4 medical coding entry paths are LIVE.** Deep Evidence mode has zero production usage.

### E2. CN standards (ICD-10-CN + ICD-9-CM-3) — REAL

Loaded code catalogs (from `/api/health` + boot logs):

| Code system | Count | Source |
|-------------|-------|--------|
| ICD-10-CN | 33,304 codes | `data/medcoder/metadata.pkl` |
| ICD-9-CM-3 | 23,165 codes | `data/medcoder/metadata.pkl` |
| Synonyms (zh + en) | 35,468 + 5,560 | iCoDerA `icd10cn_synonym_map.json` |
| Evidence patterns | 972 codes × 6,490 patterns | iCoDerA `evidence_anchoring_kb.json` |

`backend/compliance_services/medical_coding_rules.py:21-39` enforces 6 code-system patterns:

```
ICD10_WHO_PATTERN             ^[A-Z]\d{2}(\.\d{1,2})?$           # A00, I21.9
ICD10_CN_6DIGIT_PATTERN       ^[A-Z]\d{2}\.\d{3}$                # J15.900, I21.100
ICD10_X_PLACEHOLDER_PATTERN   ^[A-Z]\d{2}\.x\d{0,3}$             # I21.x00
ICD10_CN_CLINICAL_EXT_PATTERN ^[A-Z]\d{2}\.\d{4,}[A-Za-z0-9]{0,2}$
ICD9_CM3_PATTERN              ^\d{2}\.\d{4}$                     # 81.0100, 84.5100
```

`classify_code_system()` correctly distinguishes all 5 + `unknown`. This is a **real CN-standard code validator**, not a stub.

### E3. Model connection — SINGLE PROVIDER (DeepSeek V4)

`backend/data/versions.json` (the canonical asset version manifest):

```json
{
  "model_version": "deepseek-v4-flash (M3-0 interim, B0 prediction pending)",
  "code_dict_version": "icd10cn_code_catalog 37,897 codes (M3-0 baseline)",
  "rule_version": "medical_coding R001-R010 + MC-R-M80-001 (M3-0 baseline)",
  "agent_version": "icoder/medcoder-coding-review-agent@1.0.0",
  "data_asset_version": "iCoDerA v1.0.0"
}
```

`backend/app/config.py:64-81`:
```python
LLM_PROVIDER: str = "deepseek"
LLM_BASE_URL: str = "https://api.deepseek.com/v1"
LLM_MODEL: str = "deepseek-chat"
LLM_PRICE_INPUT_PER_1M: float = 0.14   # CNY
LLM_PRICE_OUTPUT_PER_1M: float = 0.28  # CNY
```

**Verdict**: Production model = **DeepSeek V4 only** (via `deepseek-chat` model id). No B0/V18/V24-v2 baseline is wired into production. The version manifest itself admits "M3-0 interim, B0 prediction pending".

### E4. Quality maturity + research assets — INTERIM (no B0 trained)

PDF Track E asks: "B0/V18/V24-v2 区别是否清晰?"

- **B0** = baseline model — **NEVER TRAINED** (versions.json: "B0 prediction pending")
- **V18 / V24-v2** — no references found in production code; only as historical experiment names in archived docs

| Asset | Status | Location |
|-------|--------|----------|
| `cot_generation_progress_v2.json` (175/500 rerank CoT few-shot) | ✅ Present | iCoDerA/DataAsset/ |
| `icd10cn_code_catalog.json` (37,897 codes) | ✅ Present | iCoDerA/DataAsset/ |
| B0 trained baseline model | ❌ NEVER TRAINED | "M3-0 interim" per versions.json |
| V18 / V24-v2 model artifacts | ❌ Not in repo | only archived mentions |

**Evaluation fixtures** (`tests/fixtures/`):

| Fixture | Size | Purpose |
|---------|------|---------|
| `ccl2026_train_gold.json` | 11.4 MB | 1800 cases from CCL 2026 public train set |
| `ccl2026_val_100.json` | 645 KB | 100-case random sample (seed=42), CI smoke |
| `icoder_201.json` | 1.3 MB | 201-case iCoDer subset, regression baseline |

Evaluation scripts (`scripts/`):
- `e2e_runtime_validation.py` — 201-case golden benchmark
- `e2e_medcoder_validation.py` — 4 ablation variants (prompt / retrieve / prompt+retrieve / full)
- `build_medcoder_index.py` — builds FAISS index from iCoDerA catalog

**Maturity verdict**: `INTERIM_BASELINE_NOT_TRAINED`. The team has the eval harness + datasets but no B0 model — production runs DeepSeek V4 zero-shot with a CN-specific system prompt + dictionary RAG.

### E5. New Medical Coding findings

| ID | Severity | Title |
|----|----------|-------|
| **G5-001** | P0 | `FastCodingRuntime.predict` hard-codes `cost={"amount": 0.0, "currency": "internal_credit"}` (fast_runtime.py:307) — root cause of medical-coding-agent cost=0 across 35 production runs. Confirmed via DB introspection: 35 corti_like_fast rows have `cost_usd=0.0` despite `latency_ms=5646` (real LLM call). |
| **G5-002** | P0 | `MedCoderRuntime.predict` has the SAME hard-coded `cost={"amount": 0.0, ...}` (medcoder_runtime.py:255). Even if medcoder_deep is exercised, costs will be silently zero. |
| **G5-003** | P1 | `coding_review_runs` table: 16 of 16 rows are `prediction_mode='link_validation'` for `homepage-coding-review-agent`; **14 of 16 are `status='unavailable'`** (only 2 OK). The Phase 5 Track C 7-stage orchestrator has never written to its own dedicated run table. |
| G5-004 | P2 | Version manifest explicitly admits "B0 prediction pending" but README + product page describe the system as a coding agent — hospital buyers cannot tell from product surfaces that the underlying model is untrained interim DeepSeek V4 zero-shot. |
| G5-005 | P2 | `coding_reviews` table (separate from `coding_review_runs`) has **0 rows** — completely unused. Dead schema. |

## F. Track F — Clinical Documentation Improvement (CDI)

### F1. Workflow state — LIVE for generation, OPEN-LOOP for hospital

| Lifecycle state | Count |
|-----------------|-------|
| Total cdi_cases | 718 |
| Total cdi_documentation_gaps | 1,310 |
| Total cdi_provider_queries | 443 |
| Total cdi_clinician_responses | **0** ← hospital loop never closed |
| Total cdi_document_versions | **0** ← no document revisions recorded |

cdi_cases `completion_state` distribution:

```
AUTO_PASS           254
BLOCKED              97
REVIEW_RECOMMENDED   13
REVIEW_REQUIRED     354
```

cdi_provider_queries `lifecycle_state` distribution:

```
DRAFT              442  ← never sent to a clinician
CLOSED               1  ← single test closure
PENDING_REVIEW       0
RESPONDED            0
```

**Verdict**: `OPEN_LOOP_HOSPITAL_NEVER_EXERCISED`. The CDI orchestrator successfully generates clarification queries (443 of them) but **NO CLINICIAN HAS EVER RESPONDED** via the system — the cdi_clinician_responses table is empty, only 1 query ever transitioned out of DRAFT (and that single closure is `CASE-G7-ADMIN-001/Q-001`, the admin test case).

### F2. Real runner — DeepSeek V4 (verified)

`backend/app/icoder/agent_runtime/cdi/real_runner.py:65-66`:
```python
_PROVIDER_NAME = "deepseek"
_PROVIDER_MODEL_ENV_DEFAULT = "deepseek-v4-flash"
```

6 stages (per docstring):
1. `encounter_synthesis` → PureLLMProvider (DeepSeek chat, JSON output)
2. `gap_identification` → PureLLMProvider
3. `expert_consultation` → ExpertRunner × 4 (coding / pubmed / web-search / medical-calculator)
4. `query_generation` → PureLLMProvider
5. `query_compliance_gate` → pure-logic NLQ-001..009 (no LLM)
6. `specialist_trace_emit` → pure-logic

CDI API surface (`backend/app/api/cdi.py`):

| Method | Path | Real? |
|--------|------|-------|
| POST | `/api/v1/cdi/runs` | ✅ Wires RealCDIRunner + persists atomically |
| GET | `/api/v1/cdi/runs/{case_id}` | ✅ Reads back persisted state |
| POST | `/api/v1/cdi/queries/{query_id}/transition` | ✅ Lifecycle transition w/ RBAC + optimistic locking |
| GET | `/api/v1/cdi/audit/dashboard` | ✅ Audit snapshot |
| POST | `/api/v1/cdi/subscriptions` | ✅ Notification subscription |

CDI cost across 718 cases = **¥0** (bypass run_history, G4-007 P1). CDI LLM calls happen via `app.services.llm_service.llm_service.chat()` directly, NOT through `agent_run.py` facade.

### F3. Hospital integration — NOT VERIFIED

PDF §4.3 boundary (enforced in code at cdi.py:247):
> "Boundary: this endpoint does NOT call medical-coding tools. CDI ≠ coding."

CDI 9 red-lines checked in `cdi_query_compliance_gate` (NLQ-001..NLQ-009):
- ✅ No auto-modifying chart
- ✅ No auto-generating diagnosis
- ✅ No CMI/payment optimization framing
- ✅ Provider Query is non-leading (response_options_4plus padding per H3.18)
- ✅ Sentence-bounded negation look-back per H3.19

**Maturity**: `OPEN_LOOP_DESIGN_COMPLETE_HOSPITAL_LOOP_UNVERIFIED`. The provider query → clinician response → document revision → CDI review → medical coding loop is **designed + coded + tested but never used in a real hospital**.

### F4. New CDI findings

| ID | Severity | Title |
|----|----------|-------|
| **G5-006** | P0 | CDI hospital loop never exercised — 442 of 443 queries stuck in DRAFT, cdi_clinician_responses EMPTY, cdi_document_versions EMPTY. The closed-loop product story (Provider Query → Clinician Response → Document Revision → Coding) is unverified in production. |
| **G5-007** | P1 | CDI orchestrator runs 6 stages × 718 cases (~4,300 DeepSeek calls) with **zero cost recorded** in run_history — the orchestrator bypasses agent_run.py facade. |
| G5-008 | P2 | 647 of 718 cdi_cases (90%) are from a single user `u-g7-g7admin` (Track H calibration test user) — only 71 cases from other users. Production usage is thin. |
| G5-009 | P2 | CDI 9 red-lines enforced in code; no real-world audit possible since loop was never used by a real clinician. |

## G. Track G — DRG / DIP

### G1. Real grouper vs mock — REAL (CHS-DRG 1.1)

`backend/app/services/drg_grouper.py` is a **real rule-based implementation**, not a mock:

- **Bundled KB** (`backend/app/services/drg_kb.py`):
  - `SURGERY_TO_DRG` — high-frequency ICD-9-CM-3 procedure → ADRG/DRG mapping
  - `DRG_NAMES` — DRG code → Chinese name dictionary
  - `ADRG_LIST` — full ADRG catalog
  - `check_gender_consistency` — YA1 error group check

- **MDC mapping** (`_MDC_MAP` + `_MDC_OVERRIDES`): ICD-10 chapter letter → MDC (MDCF 循环, MDCE 呼吸, MDCG 消化, MDCL 泌尿, MDCA 神经, MDCI 骨骼, MDCB 眼, MDCZ 感染, MDCP 新生儿, MDCO 妊娠/分娩, MDCY 其他)

- **Medical ADRG assignment** (`_MEDICAL_ADRG`): 9 MDCs × ~5 ADRGs each, prefix-matched against primary diagnosis code (e.g. MDCF → FV3 高血压 [I10-I15] / FU1 心力衰竭 [I50] / FQ3 冠心病 [I20,I24,I25] / FR3 急性心肌梗死 [I21,I22] / FW1 心律失常 [I44-I49] / BV3 脑卒中 [I60-I66])

- **CC/MCC level** (`_CC_PREFIXES`): 15 high-impact codes (I50 心衰 MCC, J96 呼衰 MCC, N17/N18 肾衰, E11 糖尿病, I21/I22 心梗 MCC, A41 败血症 MCC, etc.)

- **DRG composition** (`_build_medical_drg`): ADRG + suffix (1=MCC, 3=CC, 5=without)

`drg-analyzer` agent in run_history: 37 runs (24 a2a_pure_llm + 13 corti_like_fast), total cost ¥0.018, all completed successfully.

### G2. DIP coverage — DESIGN ONLY, NO SCORER

`backend/compliance_services/drg_dip_rules.py` declares 7 rules:

```
DRG001 主诊断编码缺失              critical
DRG002 主手术/操作编码缺失          high
DRG003 CC/MCC 诊断编码完整性        medium
DRG004 性别与诊断编码一致性         critical (YA1 error group)
DIP001 诊断编码完整性               low
DIP002 手术操作编码缺失             medium
DIP003 主诊断与主手术一致性         high
```

DIP scoring (`DIPImpact` dataclass in `drg_analyzer_service.py:51-64`):

```python
@dataclass
class DIPImpact:
    dip_score: float = 0.0
    dip_score_ceiling: float = 0.0
    payment_estimate_yuan: float = 0.0
    note: str = ""
```

`_estimate_dip_impact()` in `drg_analyzer_service.py:412+` returns heuristic estimates — **NO REAL DIP SCORING TABLE**. The real China DIP system uses region-specific scoring tables published by NHSA; iCoDer does not embed those tables.

**Verdict**: DIP is **explanatory demo only**, not a real scorer. DRG is real grouping for high-frequency cases.

### G3. QY / CC / MCC handling

| Concept | Handling | Coverage |
|---------|----------|----------|
| **QY (青医/疑诊)** | Not implemented | 0% — QY error group not handled |
| **CC (合并症)** | Real — `_CC_PREFIXES` lookup | ~15 high-impact codes only |
| **MCC (重要合并症)** | Real — `_CC_PREFIXES` lookup | ~10 high-impact codes only |
| **Gender YA1** | Real — `check_gender_consistency` | Limited to known gender-specific diagnoses |

Real production coverage: grouper returns `coverage=true` for the 2 OK homepage-coding-review-agent runs (`I21.401 → EC13` 经皮冠状动脉支架植入伴 MCC). The 14 `status='unavailable'` runs returned `coverage=false` because their pipeline didn't produce codes.

### G4. New DRG/DIP findings

| ID | Severity | Title |
|----|----------|-------|
| G5-010 | P1 | DRG grouper has real CHS-DRG 1.1 implementation but only covers **high-frequency surgeries + ~50 medical ADRGs**; the China national DRG catalog has 376 ADRGs / 628 DRGs — long-tail coverage unknown. Production feedback (especially tail cases) is missing because 14/16 homepage-coding-review-agent runs returned `status='unavailable'`. |
| G5-011 | P1 | **DIP is explanatory only** — `DIPImpact` fields are placeholder (0.0 / 0.0 / 0.0 / "") with no real China DIP scoring tables embedded. The product claims "分组合规 (DRG/DIP)" but DIP is design-only. |
| G5-012 | P2 | QY (疑诊/error) DRG group is not handled — grouper silently produces empty result for QY-eligible cases. |
| G5-013 | P2 | `drg_grouper.py` carries legacy back-compat code path (`_surgery_drg_map`, `_adrg_map`, `_loaded` no-op shims) for a pre-Phase-4 data structure — confusing for new engineers. |

## H. Aggregate findings + verdicts

### H1. New findings registered in this gate

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G5-001** | P0 | cost-attribution | `FastCodingRuntime` hard-codes `cost=0` at fast_runtime.py:307 — root cause of medical-coding-agent 35 runs all cost=0 |
| **G5-002** | P0 | cost-attribution | `MedCoderRuntime` has identical hard-coded `cost=0` at medcoder_runtime.py:255 |
| **G5-003** | P1 | dead-surface | `coding_review_runs` table has 16 rows from Phase 5 Track C pilot; 14 of 16 are `status='unavailable'`. The 7-stage Coding Compliance pipeline never wrote a single OK row outside this one pilot run. |
| **G5-004** | P2 | disclosure | Production model is "M3-0 interim, B0 prediction pending" per versions.json — hospital buyers cannot tell from product surfaces that the underlying coding model is untrained interim DeepSeek V4 zero-shot |
| G5-005 | P2 | dead-schema | `coding_reviews` table completely empty (0 rows) — dead schema |
| **G5-006** | P0 | hospital-loop | CDI hospital loop never exercised — 442/443 queries stuck in DRAFT, cdi_clinician_responses EMPTY, cdi_document_versions EMPTY |
| **G5-007** | P1 | cost-attribution | CDI orchestrator runs ~4,300 DeepSeek calls across 718 cases with zero cost recorded (bypass agent_run facade) |
| G5-008 | P2 | usage-mix | 90% of cdi_cases (647/718) from a single Track H calibration test user `u-g7-g7admin` — production usage is thin |
| G5-009 | P2 | compliance | CDI 9 red-lines enforced in code; real-world audit impossible since loop never used |
| G5-010 | P1 | drg-coverage | DRG grouper covers high-frequency cases only; long-tail coverage unknown |
| G5-011 | P1 | drg-dip | DIP is explanatory only — no real China DIP scoring tables embedded |
| G5-012 | P2 | drg-coverage | QY (疑诊/error) DRG group not handled |
| G5-013 | P2 | orphan | drg_grouper.py carries legacy back-compat shims |

### H2. Track-level verdicts (interim, will be finalized in Gate 14)

| Track | Verdict |
|-------|---------|
| **Track E Medical Coding** | `LIVE_WITH_INTERIM_MODEL_AND_COST_ATTRIBUTION_BROKEN` — Real DeepSeek V4 path works, real CN code system, real eval harness; **B0 model never trained**, **cost attribution broken on 35 medical-coding runs**, **DIP explanatory-only** |
| **Track F CDI** | `OPEN_LOOP_DESIGN_COMPLETE_HOSPITAL_LOOP_NEVER_EXERCISED` — 718 cases generated, 1310 gaps identified, 443 queries drafted; **0 clinician responses, 0 document revisions, 442/443 queries stuck in DRAFT** |
| **Track G DRG/DIP** | `REAL_DRG_GROUPER_FOR_HIGH_FREQ_CASES__DIP_DEMO_ONLY` — Real CHS-DRG 1.1 rules + bundled KB; DIP has no real scoring tables; long-tail coverage unknown |

### H3. Gate 5 verdict

`MEDICAL_CODING_LIVE_WITH_P0_COST_BUG__CDI_OPEN_LOOP__DRG_PARTIAL_DIP_DEMO_ONLY`

Specifically:

- ✅ Medical Coding is a real, working product surface with real DeepSeek V4 calls and real CN standard enforcement
- ❌ **2 P0 cost attribution bugs** silently zero out medical coding costs in run_history (G5-001, G5-002)
- ❌ **B0 baseline model never trained** — production runs interim DeepSeek V4 zero-shot (G5-004)
- ❌ **CDI hospital loop is design-only** — 0 clinician responses in 718 cases (G5-006)
- ⚠️ DRG grouper is real but covers high-frequency cases only (G5-010); DIP is explanatory demo only (G5-011)
- ✅ Compliance rule engine is real (12 production rules across 2 rule sets)
- ✅ CDI 9 red-lines enforced in code

Gate 5 closes. Proceed to **Gate 6 — A2A, Runtime, Expert and Tool Architecture**.
