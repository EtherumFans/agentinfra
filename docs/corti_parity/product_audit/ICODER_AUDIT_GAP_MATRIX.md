# Phase 3-D2.5 — iCoDer × Corti Parity Audit Gap Matrix

> **历史基线，非当前 Agent roster。** 下表冻结于 2026-07-07，`absent`、`metadata-only` 和早期 P0/P1 判断不得直接用于当前上线结论。2026-08-27 最新增量见文末；机器权威状态以相应阶段 evidence 为准。

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
| 1.3 | Corti Models sub-item (frontier model marketplace) | partial: authenticated catalog、四眼 package governance、签名合成包、shadow-only binding/observation，以及开发环境幂等异步作业、fenced lease、崩溃接管和单次自动回滚；仍无真实模型托管、患者 shadow traffic、个人模型密钥生命周期、生产 worker/queue、autoscaling 或 SLA | present | P2 | L | Phase 4.1+ |
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

## 2026-08-24 当前 Agent Hub 增量

历史 D3 行中的 ICU Admission Summary `absent` 已不再成立。当前 `icu-summary` 是本地可运行、可审计、可测试的开发候选切片：只整理明确标签 ICU 事实，输出精确脱敏 span，且对临床评分、异常阈值、药物筛查、治疗建议和生产写回失败关闭。

| 当前项 | 证据状态 | 仍开放的 Corti 差距 |
|---|---|---|
| ICU Summary 本地运行 | `icoder.governed-icu-summary.v1`，合同 `icoder/IcuSummaryOutput/v3` | 自由文本/多源 EHR 综合、机构模板与阈值 |
| 证据与安全 | 6 条字段关系、1 条证据绑定；关系 112/112、绑定 36/36 对抗检测 | 独立 ICU 临床金标准、严重错误和遗漏率验证 |
| Agent Hub HTTP | 13/13 happy、13/13 adversarial、13/13 reference、78/78 stability | 其余 13 个外部模型 Agent 的严格 live-provider 证据 |
| Corti ICU experts | 本地固定不计算、不筛查 | PubMed、DrugBank、APACHE II/SOFA/GCS/死亡风险计算器 |
| 中国医院 | 中文明确标签和 CN 失败关闭 | HIS/EMR、ADT、MAR、LIS、监护/呼吸机接口及医院批准模板 |
| 上线状态 | 开发环境候选；production-ready 0/26 | 医院、法务、认证、云基础设施和独立 reviewer 门禁 |

### Referral Generator 后续增量

历史 D3 行中 Referral Generator `absent` 已不再成立。`referral-gen` 当前只从明确标题字段装配逐字、可追溯的转诊信；核心字段缺失时不生成草案，支持材料缺失时明确写“未记录”，并固定禁止临床推断、新诊断、新治疗、自动发送和写回。

| 当前项 | 证据状态 | 仍开放的 Corti 差距 |
|---|---|---|
| Referral 本地运行 | `icoder.governed-referral.v1`，合同 `icoder/ReferralOutput/v3` | 自由叙事理解、多文档综合和专业生成质量 |
| 证据与安全 | 7 条字段关系、1 条证据绑定；全 Hub 关系 184/184、绑定 42/42 对抗检测 | 独立临床金标准、遗漏/新增/严重错误率和医生盲评 |
| Agent Hub HTTP | 16/16 happy、16/16 adversarial、16/16 reference、96/96 stability | 其余 10 个外部模型 Agent 的严格 live-provider 证据 |
| 中国医院 | 双向转诊、转出/接收机构与科室、精确 span 和 CN 失败关闭 | HIS/EMR、区域转诊平台、接诊目录、回执/拒收/改派及医院模板 |
| 上线状态 | 开发环境候选；production-ready 0/26 | 医院、法务、认证、云基础设施和独立 reviewer 门禁 |

完整阶段证据与逐项差距见 `docs/corti_parity/ICODER_GOVERNED_REFERRAL_GENERATOR_PHASE_SUMMARY_2026-08-24.md`。历史汇总数字未重算，不得把本增量解释为完整 Corti 复刻、临床质量证明或生产批准。

完整阶段证据与逐项差距见 `docs/corti_parity/ICODER_GOVERNED_ICU_SUMMARY_PHASE_SUMMARY_2026-08-24.md`。历史汇总数字未重算，不得把本增量解释为完整 Corti 复刻或生产批准。

### Patient Discharge Education 后续增量

历史 D3 行中的 Patient Discharge Education `absent` 也已不再成立。当前 `discharge-edu` 是本地可运行、可审计、可测试的开发候选切片：只逐字整理明确标签的出院事实，输出精确脱敏 span，并对医学释义、结果解释、药物重整、外部知识、新增医疗建议和生产写回失败关闭。

| 当前项 | 证据状态 | 仍开放的 Corti 差距 |
|---|---|---|
| Discharge Education 本地运行 | `icoder.governed-discharge-education.v1`，合同 `icoder/DischargeEducationOutput/v3` | AVS/EHR 多源综合、患者友好医学释义、阅读等级与语言适配 |
| 证据与安全 | 6 条字段关系、1 条证据绑定；全 Hub 关系 138/138、绑定 38/38 对抗检测 | 独立临床/患者金标准、严重错误、遗漏、理解和误解风险验证 |
| Agent Hub HTTP | 14/14 happy、14/14 adversarial、14/14 reference、84/84 stability | 其余 12 个外部模型 Agent 的严格 live-provider 证据 |
| Corti experts | 本地固定不调用外部知识、不解释结果 | PubMed、Web Search、Medical Calculator 和受治理引用 |
| 中国医院 | 中文明确标签、teach-back/澄清问题和 CN 失败关闭 | HIS/EMR、医嘱、药房/MAR、LIS/PACS、转诊、随访、互联网医院/患者门户及医院批准模板 |
| 上线状态 | 开发环境候选；production-ready 0/26 | 医院、患者/照护者、法务、认证、云基础设施和独立 reviewer 门禁 |

完整阶段证据与逐项差距见 `docs/corti_parity/ICODER_GOVERNED_DISCHARGE_EDUCATION_PHASE_SUMMARY_2026-08-24.md`。历史汇总数字未重算，不得把本增量解释为完整 Corti 复刻、患者教育质量证明或生产批准。

### Discharge Summary Structuring 后续增量

`discharge-summary-structuring` 是 iCoDer 面向中国医院的额外 Agent，不在 Corti 当前公开的独立预置 Agent 清单中。当前本地切片只逐字重组明确章节标题并绑定脱敏 span，对自由叙事总结、推断、编码、药物重整、新增医嘱/随访和生产写回失败关闭。最近邻 Corti 对照是 Textgen `corti-discharge-summary` section 和 Patient Discharge Education，而不是一对一同名 Agent。

| 当前项 | 证据状态 | 仍开放的 Corti 差距 |
|---|---|---|
| Discharge Summary 本地运行 | `icoder.governed-discharge-summary.v1`，合同 `icoder/DischargeSummaryStructured/v5` | 全材料生成式出院记录、facts/transcript/多文档综合和文档时间线 |
| 证据与安全 | 6 条字段关系、1 条证据绑定；全 Hub 关系 161/161、绑定 40/40 对抗检测 | 独立临床金标准、事实遗漏/新增、严重错误和医院模板验证 |
| Agent Hub HTTP | 15/15 happy、15/15 adversarial、15/15 reference、90/90 stability | 其余 11 个外部模型 Agent 的严格 live-provider 证据 |
| Corti 邻近能力 | 本地固定只重组章节，不生成摘要或患者教育 | Textgen discharge-summary、文档 guardrails、多源 Patient Discharge Education |
| 中国医院 | 常见中文出院章节、精确 span 和 CN 失败关闭 | HIS/EMR、医嘱、MAR/药房、LIS/PACS、病案首页、签名/归档/更正及医院批准模板 |
| 上线状态 | 开发环境候选；production-ready 0/26 | 医院、法务、认证、云基础设施和独立 reviewer 门禁 |

完整阶段证据与逐项差距见 `docs/corti_parity/ICODER_GOVERNED_DISCHARGE_SUMMARY_STRUCTURING_PHASE_SUMMARY_2026-08-24.md`。历史汇总数字未重算，不得把本增量解释为 Corti Textgen 等价、完整复刻或生产批准。

### DRG/DIP Risk Review 后续增量

历史 D3 中的 `DRG 分析智能体` 已从依赖外部 LLM 的泛化实现收敛为受治理本地开发切片。它只复核编码员明确提供的 ICD-10-CN / ICD-9-CM-3 编码及逐字证据，运行 hash-pinned 开发期启发式规则，并固定把候选标记为非官方、未验证结果。

| 当前项 | 证据状态 | 仍开放的 Corti / 上线差距 |
|---|---|---|
| DRG/DIP 本地运行 | `icoder.governed-drg-dip-risk-review.v1`，合同 `icoder/DRGDIPRiskReview/v8` | 无官方/授权 DRG grouper、DIP 计分、地区版本、权重、CMI 和支付结算 |
| 证据与安全 | 全 Hub 字段关系 323/323、证据绑定 58/58、跨 Agent 关系 20/20 对抗检测 | 独立编码员金标准、分组准确率、严重错误率和真实病例验证 |
| Agent Hub HTTP | 23/23 happy、23/23 adversarial、23/23 reference、138/138 stability | CDI、Medical Coding、Triage 的真实外部 Provider 语义证据 |
| Corti 邻近能力 | 精确 span、签名上游一致性、RunTrace | Corti Medical Coding 的全病历提取、编码分配/验证、排序替代项和规则理由 |
| 中国医院 | ICD-10-CN / ICD-9-CM-3 明确版本、中文来源标签和失败关闭 | HIS/EMR/病案首页、官方/医院 grouper、医保/payer、地区 profile 与工作流验收 |
| 上线状态 | 开发环境候选；本地语义 23/26 | production-ready 仍为 0/26；医院、法务、认证、云和独立 reviewer 门禁 |

完整阶段证据与逐项差距见 `docs/corti_parity/ICODER_GOVERNED_DRG_DIP_RISK_REVIEW_PHASE_SUMMARY_2026-08-24.md`。Corti 当前公开 Agent Library 未见独立同名 DRG/DIP Agent，故本阶段只与邻近 Medical Coding 能力比较；不得解释为 Corti 同名复刻、官方分组或支付能力。

### Clinical Models 分布式 shadow 作业增量（2026-08-27）

Models 开发控制面已从同步合成 observation 扩展为持久化异步作业：创建接口强制幂等键，同一 binding 只保留一个活动槽位；worker 通过随机 fencing token 租约领取和续期，崩溃后允许其他 worker 在租约过期后接管，旧 token 不能写入终态；耗尽尝试会失败关闭并释放槽位。正常仓库 fixture 可通过，三类受控故障停止并只执行一次受审计回滚。

| 当前项 | 开发证据 | 仍开放的 Corti / 上线差距 |
|---|---|---|
| 作业与恢复 | Alembic `061`；queued/running/passed/stopped/failed/cancelled；幂等 replay、冲突拒绝、续租、过期接管、旧 worker 拒绝、尝试耗尽均通过 | 生产消息队列、跨主机/跨区域一致性、容量/长稳/chaos、死信与值班响应 |
| 数据与安全 | 只解析仓库签名合成 fixture；审计不含幂等键、lease token、bundle、患者文本或预测 | 合法去标识患者 shadow 流、consent、DLP、对象存储、生产 KMS/HSM 和安全审查 |
| API / SDK / Console | OpenAPI 289 paths / 317 schemas；JS、Python、.NET 和 Console 明示异步、租约和失败关闭边界 | Corti 托管 Models 的模型选择、真实推理、配额/成本、部署健康、autoscaling 和 SLA |
| 回滚 | 绑定版本变化失败关闭；受控故障原子恢复 previous binding，迟到 worker 无法重复结算 | 真实模型容器、流量路由、编排平台和医院私有化环境的回滚演练 |
| 上线状态 | 开发环境控制面候选；`real_shadow_traffic_used=false`、`corti_capability_parity_proven=false` | 独立临床 gold/reviewer、同病例 Corti 盲测、医院/法务/伦理/认证/云批准 |

完整阶段证据与边界见 `docs/corti_parity/ICODER_CLINICAL_MODEL_SHADOW_DISTRIBUTED_JOB_PHASE_SUMMARY_2026-08-27.md`。历史总 gap 数字未重算，本增量不得解释为真实临床模型质量、Corti Models 完整复刻或生产批准。
