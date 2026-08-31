# 26E — Pre-A0 Gate 5: China Medical Scenario Mapping

> Per spec §16. Maps Corti's pre-built agents and experts to actual China hospital workflows. Determines which Corti capabilities have a real China-scenario counterpart vs which are EU/US-centric.

> **Current-state correction (2026-08-15):** §5 below records the historical
> Gate 5 result. Clinical Education and Clinical Guidelines have since been
> implemented as Hub-visible executable Packs, so the current catalog mapping
> is **20/20**, not 18/20. The machine-verifiable current gate is
> `backend/scripts/corti_parity/corti_prebuilt_agent_catalog.json` plus
> `validate_corti_prebuilt_agent_parity.py`. It proves development readiness,
> while clinical-quality and production-readiness remain explicit external gates.

## Methodology

- Source: Corti Console pre-built agents (Gate 1 §C-02, 20 agents) + Corti prebuilt experts (Gate 4, 14 experts)
- For each Corti capability, identify the China hospital workflow it would serve
- Classify coverage: FULL (iCoDer covers + Corti covers) / PARTIAL (one side only) / NONE / DIFFERENT_BY_DESIGN

---

## §1. China hospital workflow inventory (canonical scenarios)

Per CLAUDE.md §产品定位, iCoDer's 7 revenue-compliance sub-domains:

| # | Workflow (CN) | Chinese name | Key regulations |
|---|---------------|--------------|-----------------|
| W-1 | Clinical Documentation Improvement (CDI) | 临床文档改进 | 国家卫健委 CDI 规范 |
| W-2 | Medical Coding (ICD-10-CN / ICD-9-CM-3) | 病案编码 | 国家临床版 2.0 |
| W-3 | DRG/DIP Grouping Compliance | 分组合规 | CHS-DRG 1.1 + DIP 国家版 |
| W-4 | Insurance Audit / 结算合规 | 医保审核 | 国家医保局结算规则 |
| W-5 | Charge Compliance | 收费合规 | 医疗服务价格规范 |
| W-6 | Document Evidence | 病历合规 | 病历书写基本规范 |
| W-7 | Audit / 监管审计 | 审计合规 | 互联网医院监管办法 |

---

## §2. Corti pre-built agents × China workflow coverage

| Corti Agent | W-1 CDI | W-2 Coding | W-3 DRG/DIP | W-4 Insurance | W-5 Charge | W-6 Doc Evidence | W-7 Audit |
|-------------|---------|------------|-------------|---------------|------------|------------------|-----------|
| ICD-10 Index Navigator | ✅ supports | ✅ **core** | partial | partial | ❌ | partial | partial |
| Rule Explainer | partial | partial | partial | ✅ supports | partial | partial | ✅ supports |
| Compliance Guardrail | partial | partial | ✅ supports | ✅ **core** | ✅ **core** | partial | ✅ **core** |
| Code Validation | ✅ supports | ✅ **core** | partial | partial | ❌ | partial | partial |
| Procedure Entity Extractor | partial | ✅ supports | partial | partial | partial | partial | partial |
| Diagnostic Entity Extractor | ✅ supports | ✅ supports | partial | partial | ❌ | partial | partial |
| Surgical Registry Intelligence | ❌ | partial | partial | ❌ | ❌ | partial | ✅ supports |
| ICU Admission Summary | ❌ | partial | ❌ | ❌ | ❌ | ✅ supports | partial |
| Triage and Initial Assessment | ❌ | ❌ | ❌ | ❌ | ❌ | partial | partial |
| Note Completeness | partial | partial | ❌ | partial | partial | ✅ **core** | ✅ supports |
| Medication Reconciliation | ❌ | ❌ | ❌ | partial | partial | partial | partial |
| Denial Appeals | ❌ | partial | partial | ✅ **core** | ❌ | partial | partial |
| Patient Discharge Education | ❌ | ❌ | ❌ | ❌ | ❌ | partial | ❌ |
| Nursing Shift Handoff | ❌ | ❌ | ❌ | ❌ | ❌ | partial | ❌ |
| Prior Authorization | ❌ | partial | ❌ | ✅ **core** | partial | partial | partial |
| Referral Generator | ❌ | ❌ | ❌ | ❌ | ❌ | partial | ❌ |
| Clinical Education | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Medical Coding | ✅ supports | ✅ **core** | partial | partial | ❌ | partial | partial |
| Clinical Guidelines | partial | partial | partial | partial | partial | partial | partial |
| CDI Agent | ✅ **core** | partial | partial | partial | ❌ | ✅ supports | partial |

### Observations

- **W-2 Coding**: most-covered workflow (8 agents contribute)
- **W-3 DRG/DIP**: poorly covered by Corti (only Compliance Guardrail seriously addresses it) — iCoDer has DRG-DIP analyzer
- **W-7 Audit**: well-covered by Corti (Compliance Guardrail + Rule Explainer + Note Completeness)
- **W-5 Charge**: only Compliance Guardrail covers it on Corti side
- **W-1 CDI**: covered by Corti's CDI Agent + iCoDer's CDI orchestrator

---

## §3. Corti prebuilt experts × China hospital relevance

| Corti Expert | China relevance | iCoDer coverage | Decision |
|--------------|------------------|-----------------|----------|
| Memory | Universal — needed for multi-turn | Partial (context/) | FOUNDATIONAL_MUST_HAVE |
| POSOS | Low — CN uses 卫健委 drug database, not POSOS | None | OUT_OF_CURRENT_SCOPE |
| DrugBank | Low — same as POSOS | None | OUT_OF_CURRENT_SCOPE |
| PubMed | Medium — English-language literature | None | PARITY_NICE_TO_HAVE |
| Clinical Trials | Low — CN hospitals use 中国临床试验注册中心 | None | OUT_OF_CURRENT_SCOPE |
| Web Search | Medium — guideline lookup | None | PARITY_NICE_TO_HAVE |
| Medical Coding (General) | Universal — core capability | **Full (MedCodER)** | DOMAIN_REQUIRED |
| ICD-10-CM | Low — CN uses ICD-10-Clinical CN (国家临床版 2.0), not CM | None | DIFFERENT_BY_DESIGN |
| ICD-10-WHO | Low — CN doesn't use WHO variant directly | None | DIFFERENT_BY_DESIGN |
| ICD-10-PCS | Low — CN uses ICD-9-CM-3 for procedures | None | DIFFERENT_BY_DESIGN |
| ICD-10-UK | None — irrelevant to CN | None | DIFFERENT_BY_DESIGN |
| Medical Calculator | Medium — CN clinical calculators differ (e.g., eGFR-CN formulas) | None | PARITY_NICE_TO_HAVE |
| Interviewing | Medium — useful for CDI Provider Query | Partial (cdi/nlq_*) | PARITY_NICE_TO_HAVE |
| AMBOSS | None — German clinical knowledge base | None | OUT_OF_CURRENT_SCOPE |

---

## §4. China-specific scenarios iCoDer must support

These are scenarios where Corti has NO equivalent and iCoDer is the only option:

| # | Scenario | Chinese name | iCoDer coverage |
|---|----------|--------------|-----------------|
| **CN-1** | 国家医保结算审核 (NHSA settlement audit) | 医保结算规则引擎 | ✅ `compliance_services/insurance_rules.py` |
| **CN-2** | CHS-DRG 1.1 分组校验 | DRG 分组合规 | ✅ `compliance_services/drg_dip_rules.py` |
| **CN-3** | DIP 病种分值结算 | DIP 分值校验 | ✅ `compliance_services/drg_dip_rules.py` |
| **CN-4** | ICD-10-Clinical CN (国家临床版 2.0) 编码 | 国家临床版编码 | ✅ MedCodER + 37,897 codes |
| **CN-5** | 病历内涵质量评分 (per 卫健委 规范) | 病历评分 | ✅ CDI Agent + multi-dimension gate |
| **CN-6** | 医保飞检应对 (audit response) | 飞检查询 | ✅ AuditLog + RunHistory + signed trace_url |
| **CN-7** | 医生答复 CDI Query (Provider Query) | 医生答复 | ✅ CDI Agent + nlq_gate |
| **CN-8** | 主要诊断选择合规 (Principal Diagnosis Selection) | 主诊断合规 | ✅ `principal_diagnosis_review` agent |
| **CN-9** | 手术操作分类 (ICD-9-CM-3 临床版) | 手术编码 | ⚠️ Partial (MedCodER supports; not as deep as dx) |
| **CN-10** | 等保2.0 三级合规 | 安全合规 | ❌ Per Gate 13 G13-002: not certified |

---

## §5. Workflow coverage gap analysis

### Historical Gate 5 result: iCoDer-covered Corti agents (18/20 at that time)

iCoDer mirrors 18 of 20 Corti pre-built agents per Gate 2 §3. Missing:
- Clinical Education Agent (G2-011)
- Clinical Guidelines Agent (G2-011)

Current correction: both missing Agents are now executable and included in the
20/20 automated catalog gate. This historical subsection is retained only to
preserve the original audit trail.

### iCoDer-only agents (per Gate 2 §3, 4 unique)

- `discharge_summary_structuring` — 出院小结结构化 (CN-specific)
- `drg-analyzer` — DRG/DIP 分析 (CN-specific)
- `principal_diagnosis_review` — 主诊断审核 (CN-specific)
- Internal MedCodER stages (code_reconciler, evidence-ranker, etc.) — not user-facing

### Workflow parity verdict by W-x

| Workflow | iCoDer coverage | Corti coverage | Parity |
|----------|-----------------|----------------|--------|
| W-1 CDI | ✅ Full (Phase 5 Track D) | ✅ Corti CDI Agent | PARITY |
| W-2 Coding | ✅ Full (MedCodER + ICD-10-CN) | ✅ Corti Medical Coding Agent (no CN) | **ICODER_ADVANTAGE** (CN coverage) |
| W-3 DRG/DIP | ✅ Full (drg-dip rules + analyzer) | ❌ Corti has no DRG-DIP | **ICODER_ADVANTAGE** |
| W-4 Insurance | ⚠️ Partial (insurance_rules.py exists; not deeply exercised) | ✅ Corti Denial Appeals + Prior Auth | **PARTIAL_PARITY** |
| W-5 Charge | ⚠️ Skeleton rules reserved | ❌ Corti has no charge compliance | **DIFFERENT_BY_DESIGN** (both incomplete) |
| W-6 Doc Evidence | ✅ Evidence extractor + RunHistory | ✅ Corti Note Completeness | PARITY |
| W-7 Audit | ✅ AuditLog + signed trace | ✅ Corti Compliance Guardrail | PARITY |

---

## §6. Findings raised in Gate 5

| ID | Severity | Title |
|----|----------|-------|
| **G5-001** | P2 | W-4 Insurance: iCoDer rules exist but not deeply exercised — pilot blocker if hospital tests end-to-end |
| **G5-002** | P2 | W-5 Charge: rules reserved but empty — out of current scope per CLAUDE.md but should be documented |
| **G5-003** | P2 | CN-9 ICD-9-CM-3 procedure coding depth: iCoDer has less depth than ICD-10-CN dx coding |
| **G5-004** | P1 | CN-10 等保2.0 三级 compliance: NOT certified (per Gate 13) — blocks public hospital pilot regardless of feature parity |
| **G5-005** | P3 | iCoDer missing Corti Clinical Education Agent — low priority, China hospitals typically have internal training systems |
| **G5-006** | P3 | iCoDer missing Corti Clinical Guidelines Agent — partially filled by `rule_explainer` agent |
| **G5-007** | P2 | iCoDer unique: DRG-DIP analyzer has no Corti mirror — competitive advantage for CN market |

---

## §7. Gate 5 verdict

```
PRE_A0_GATE_5_CHINA_MEDICAL_SCENARIO_MAPPING_COMPLETE
7_HOSPITAL_WORKFLOWS_MAPPED
10_CHINA_SPECIFIC_SCENARIOS_IDENTIFIED
18_OF_20_CORTI_AGENTS_MIRRORED
4_ICODER_UNIQUE_AGENTS (CN-specific)
7_ICODER_ADVANTAGES_IDENTIFIED (DRG-DIP / ICD-10-CN / etc.)
1_P0_BLOCKER (CN-10 等保2.0 not certified — G5-004)
0_FORBIDDEN_VERDICTS_CLAIMED
```

Gate 5 closes. Proceed to **Pre-A0 Gate 6 — Agent Hub Convergence Review**.
